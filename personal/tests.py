from django.contrib.auth.models import AnonymousUser, Group, User
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Empleado, Notificacion


class NotificacionesGlobalesTests(TestCase):
    """Regresión de la campana entre vistas normales y PasswordChangeView."""

    paginas = (
        'dashboard_empleado', 'cambiar_contrasena', 'mis_permisos',
        'mi_asistencia', 'mis_liquidaciones',
    )

    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user(username='empleado_prueba')
        cls.otro = User.objects.create_user(username='otro_empleado')
        Empleado.objects.create(nombre_completo='Empleado de prueba', usuario=cls.usuario)
        for i in range(3):
            Notificacion.objects.create(usuario=cls.usuario, mensaje=f'Aviso propio {i}')
        Notificacion.objects.create(usuario=cls.usuario, mensaje='Aviso leído', leida=True)
        Notificacion.objects.create(usuario=cls.otro, mensaje='AVISO PRIVADO AJENO')
        Notificacion.objects.create(mensaje='AVISO GENERAL')

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_mismo_contador_y_privacidad_en_cinco_paginas(self):
        for nombre in self.paginas:
            with self.subTest(pagina=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.context['notificaciones_no_leidas'], 3)
                self.assertContains(respuesta, '<span class="notification-badge">\n                                3\n                            </span>', html=True)
                self.assertContains(respuesta, 'Aviso propio 0')
                self.assertNotContains(respuesta, 'AVISO PRIVADO AJENO')
                self.assertNotContains(respuesta, 'AVISO GENERAL')

    def test_sin_notificaciones(self):
        Notificacion.objects.filter(usuario=self.usuario).delete()
        for nombre in self.paginas:
            with self.subTest(pagina=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.context['notificaciones_no_leidas'], 0)
                self.assertNotContains(respuesta, '<span class="notification-badge">')
                self.assertContains(respuesta, 'No tienes notificaciones.')

    def test_contador_no_limitado_a_ocho(self):
        for i in range(7):
            Notificacion.objects.create(usuario=self.usuario, mensaje=f'Adicional {i}')
        respuesta = self.client.get(reverse('cambiar_contrasena'))
        self.assertEqual(respuesta.context['notificaciones_no_leidas'], 10)
        self.assertEqual(len(respuesta.context['ultimas_notificaciones']), 8)

    def test_anonimo_no_consulta_notificaciones(self):
        from .context_processors import contexto_rol
        request = RequestFactory().get('/login/')
        request.user = AnonymousUser()
        with self.assertNumQueries(0):
            contexto = contexto_rol(request)
            self.assertEqual(contexto['notificaciones_no_leidas'], 0)
            self.assertEqual(list(contexto['ultimas_notificaciones']), [])
        self.assertFalse(contexto['es_gestion'])
        self.assertFalse(contexto['es_empleado'])

    def test_gestion_conserva_su_buzon_general(self):
        for rol in ['RRHH', 'GERENTES', 'superusuario']:
            with self.subTest(rol=rol):
                usuario = User.objects.create_user(username=rol, is_superuser=(rol == 'superusuario'))
                if rol != 'superusuario':
                    usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
                self.client.force_login(usuario)
                for nombre in ['dashboard_gestion', 'cambiar_contrasena']:
                    respuesta = self.client.get(reverse(nombre))
                    self.assertEqual(respuesta.context['notificaciones_no_leidas'], 1)
                    self.assertContains(respuesta, 'AVISO GENERAL')
                    self.assertNotContains(respuesta, 'AVISO PRIVADO AJENO')
                    self.assertNotContains(respuesta, 'Aviso propio 0')

    def test_no_duplica_consultas_del_buzon(self):
        for nombre in self.paginas:
            with self.subTest(pagina=nombre):
                with CaptureQueriesContext(connection) as consultas:
                    self.client.get(reverse(nombre))
                consultas_buzon = [c['sql'] for c in consultas if 'personal_notificacion' in c['sql'].lower()]
                self.assertEqual(len(consultas_buzon), 2)  # Total sin leer y últimos ocho.

    def test_lectura_actualiza_todas_las_paginas_sin_tocar_otro_usuario(self):
        aviso = Notificacion.objects.filter(usuario=self.usuario, leida=False).first()
        self.client.post(reverse('marcar_notificacion_leida', args=[aviso.pk]))
        for nombre in self.paginas:
            respuesta = self.client.get(reverse(nombre))
            self.assertEqual(respuesta.context['notificaciones_no_leidas'], 2)
        self.client.post(reverse('marcar_notificaciones_leidas'))
        self.assertTrue(Notificacion.objects.filter(usuario=self.otro, leida=False).exists())
        for nombre in self.paginas:
            respuesta = self.client.get(reverse(nombre))
            self.assertEqual(respuesta.context['notificaciones_no_leidas'], 0)


    # Simula el mismo POST AJAX que envía el panel, sin tocar la base real.
    def accion(self, nombre, aviso, **data):
        return self.client.post(reverse(nombre, args=[aviso.pk]), data,
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_acciones_individuales_y_contador(self):
        aviso = Notificacion.objects.filter(usuario=self.usuario, leida=False).first()
        total = Notificacion.objects.count()
        for _ in range(2):
            respuesta = self.accion('marcar_notificacion_leida', aviso)
            self.assertEqual(respuesta.json()['unread'], 2)
        self.assertEqual(Notificacion.objects.count(), total)
        aviso.refresh_from_db()
        self.assertTrue(aviso.leida)
        respuesta = self.accion('eliminar_notificacion', aviso)
        self.assertEqual(respuesta.json()['unread'], 2)  # Borrar leído no resta otra vez.
        self.assertFalse(Notificacion.objects.filter(pk=aviso.pk).exists())
        for aviso in Notificacion.objects.filter(usuario=self.usuario):
            respuesta = self.accion('eliminar_notificacion', aviso)
        self.assertEqual(respuesta.json()['unread'], 0)
        self.assertIn('No tienes notificaciones.', respuesta.json()['html'])
        for pagina in self.paginas:
            pagina = self.client.get(reverse(pagina))
            self.assertEqual(pagina.context['notificaciones_no_leidas'], 0)

    def test_otro_usuario_y_buzon_compartido_protegidos(self):
        for superuser in [False, True]:
            self.usuario.is_superuser = superuser
            self.usuario.save(update_fields=['is_superuser'])
            for aviso in Notificacion.objects.exclude(usuario=self.usuario):
                for accion in ['marcar_notificacion_leida', 'eliminar_notificacion']:
                    self.assertEqual(self.accion(accion, aviso, usuario=self.usuario.pk).status_code, 404)
                aviso.refresh_from_db()
                self.assertFalse(aviso.leida)

    # El cliente normal de Django omite CSRF; aquí lo activamos para verificar el bloqueo real.
    def test_post_csrf_y_autenticacion(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        cliente.get(reverse('cambiar_contrasena'))
        token = cliente.cookies['csrftoken'].value
        aviso = Notificacion.objects.filter(usuario=self.usuario, leida=False).first()
        for accion in ['marcar_notificacion_leida', 'eliminar_notificacion']:
            url = reverse(accion, args=[aviso.pk])
            self.assertEqual(cliente.get(url).status_code, 405)
            self.assertEqual(cliente.post(url).status_code, 403)
            self.assertEqual(cliente.post(url, {'csrfmiddlewaretoken': 'incorrecto'}).status_code, 403)
            self.assertEqual(cliente.post(url, {'csrfmiddlewaretoken': token}).status_code, 302)
        self.client.logout()
        self.assertEqual(self.accion('eliminar_notificacion', aviso).status_code, 302)

    def test_marcar_todas_conserva_avisos_y_devuelve_panel(self):
        ids = set(Notificacion.objects.values_list('pk', flat=True))
        respuesta = self.client.post(reverse('marcar_notificaciones_leidas'),
                                    HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(respuesta.json()['unread'], 0)
        self.assertEqual(ids, set(Notificacion.objects.values_list('pk', flat=True)))
        self.assertNotIn('title="Marcar como leída"', respuesta.json()['html'])
        self.assertIn('Eliminar notificación', respuesta.json()['html'])

    def test_panel_repone_el_octavo_y_escapa_texto(self):
        for i in range(8):
            Notificacion.objects.create(usuario=self.usuario, mensaje=f'Extra {i}')
        aviso = Notificacion.objects.filter(usuario=self.usuario).first()
        respuesta = self.accion('eliminar_notificacion', aviso)
        self.assertEqual(respuesta.json()['html'].count('data-notification-id='), 8)
        Notificacion.objects.create(usuario=self.usuario, mensaje='<script>alert(1)</script>')
        respuesta = self.accion('marcar_notificacion_leida', Notificacion.objects.filter(usuario=self.usuario).first())
        self.assertIn('&lt;script&gt;', respuesta.json()['html'])
        self.assertNotIn('<script>', respuesta.json()['html'])

    def test_get_abrir_no_modifica_y_destino_externo_rechazado(self):
        aviso = Notificacion.objects.filter(usuario=self.usuario, leida=False).first()
        self.client.get(reverse('ver_notificacion', args=[aviso.pk]))
        aviso.refresh_from_db()
        self.assertFalse(aviso.leida)
        respuesta = self.client.post(reverse('marcar_notificacion_leida', args=[aviso.pk]),
                                    {'next': 'https://example.com/'})
        self.assertEqual(respuesta.url, reverse('inicio') + '#notificaciones')
