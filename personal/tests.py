from django.contrib.auth.models import AnonymousUser, Group, User
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import Empleado, Notificacion
from .models import Evaluacion


class EvaluacionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rrhh = User.objects.create_user('evaluador', is_staff=True)
        cls.gerente = User.objects.create_user('lector', is_staff=True)
        cls.trabajador = User.objects.create_user('trabajador')
        cls.superusuario = User.objects.create_user('supervisor', is_superuser=True, is_staff=True)
        cls.rrhh.groups.add(Group.objects.get_or_create(name='RRHH')[0])
        cls.gerente.groups.add(Group.objects.get_or_create(name='GERENTES')[0])
        cls.trabajador.groups.add(Group.objects.get_or_create(name='EMPLEADO')[0])
        cls.empleado = Empleado.objects.create(nombre_completo='Propio', usuario=cls.trabajador)
        cls.otro = Empleado.objects.create(nombre_completo='Ajeno')
        cls.propia = Evaluacion.objects.create(empleado=cls.empleado, periodo='Propio 2026', puntuacion=4, feedback='Comentario propio')
        cls.ajena = Evaluacion.objects.create(empleado=cls.otro, periodo='Privado 2026', puntuacion=2, feedback='Comentario privado')

    def datos(self, **cambios):
        hoy = timezone.localdate()
        semestre = 'Primer' if hoy.month <= 6 else 'Segundo'
        return dict({'empleado': self.empleado.pk, 'periodo': f'{hoy.year} - {semestre} semestre', 'puntuacion': 5, 'feedback': 'Buen desempeño'}, **cambios)

    def test_periodos_semestrales_preestablecidos(self):
        from datetime import date
        from unittest.mock import patch
        from .forms import EvaluacionForm
        self.client.force_login(self.rrhh)
        for fecha, periodo in [
            (date(2026, 6, 30), '2026 - Primer semestre'),
            (date(2026, 7, 1), '2026 - Segundo semestre'),
            (date(2026, 12, 31), '2026 - Segundo semestre'),
            (date(2027, 1, 1), '2027 - Primer semestre'),
        ]:
            with self.subTest(fecha=fecha), patch('personal.forms.timezone.localdate', return_value=fecha):
                formulario = EvaluacionForm()
                self.assertEqual(list(formulario.fields['periodo'].choices), [(periodo, periodo)])
                self.assertEqual(formulario['periodo'].value(), periodo)
                respuesta = self.client.post(reverse('crear_evaluacion'), self.datos(periodo=periodo))
                self.assertEqual(respuesta.status_code, 302)
                self.assertEqual(Evaluacion.objects.latest('pk').periodo, periodo)

    def test_creacion_rechaza_semestres_pasados_y_futuros(self):
        from datetime import date
        from unittest.mock import patch
        self.client.force_login(self.rrhh)
        with patch('personal.forms.timezone.localdate', return_value=date(2026, 9, 26)):
            for periodo in ['2026 - Primer semestre', '2027 - Primer semestre', '2025 - Segundo semestre']:
                respuesta = self.client.post(reverse('crear_evaluacion'), self.datos(periodo=periodo))
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn('periodo', respuesta.context['formulario'].errors)
        self.assertEqual(Evaluacion.objects.count(), 2)

    def test_periodo_arbitrario_rechazado_al_crear_y_editar(self):
        self.client.force_login(self.rrhh)
        for nombre, args in [('crear_evaluacion', []), ('editar_evaluacion', [self.propia.pk])]:
            respuesta = self.client.post(reverse(nombre, args=args), self.datos(periodo='Período inventado'))
            self.assertEqual(respuesta.status_code, 200)
            self.assertIn('periodo', respuesta.context['formulario'].errors)
        self.assertEqual(Evaluacion.objects.count(), 2)
        self.propia.refresh_from_db()
        self.assertEqual(self.propia.periodo, 'Propio 2026')

    def test_edicion_conserva_periodo_historico(self):
        self.client.force_login(self.rrhh)
        url = reverse('editar_evaluacion', args=[self.propia.pk])
        respuesta = self.client.get(url)
        self.assertContains(respuesta, '<option value="Propio 2026" selected>')
        self.assertEqual(self.client.post(url, self.datos(periodo='Propio 2026')).status_code, 302)
        self.propia.refresh_from_db()
        self.assertEqual(self.propia.periodo, 'Propio 2026')
        respuesta = self.client.post(reverse('crear_evaluacion'), self.datos(periodo='Propio 2026'))
        self.assertIn('periodo', respuesta.context['formulario'].errors)

    def test_empleado_consulta_solo_sus_evaluaciones(self):
        self.client.force_login(self.trabajador)
        respuesta = self.client.get(reverse('mis_evaluaciones'), {'empleado': self.otro.pk})
        self.assertContains(respuesta, 'Propio 2026')
        self.assertNotContains(respuesta, 'Privado 2026')
        self.assertContains(self.client.get(reverse('detalle_evaluacion', args=[self.propia.pk])), 'Comentario propio')
        self.assertEqual(self.client.get(reverse('detalle_evaluacion', args=[self.ajena.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('gestion_evaluaciones')).status_code, 403)

    def test_gerente_y_empleado_no_pueden_escribir(self):
        for usuario in [self.gerente, self.trabajador]:
            self.client.force_login(usuario)
            for nombre, args in [('crear_evaluacion', []), ('editar_evaluacion', [self.propia.pk])]:
                with self.subTest(usuario=usuario.username, ruta=nombre):
                    url = reverse(nombre, args=args)
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, self.datos()).status_code, 403)
        self.propia.refresh_from_db()
        self.assertEqual(self.propia.puntuacion, 4)
        self.assertEqual(Evaluacion.objects.count(), 2)

    def test_rrhh_y_superusuario_crean_y_editan(self):
        for usuario in [self.rrhh, self.superusuario]:
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('crear_evaluacion')).status_code, 200)
            respuesta = self.client.post(reverse('crear_evaluacion'), self.datos())
            creada = Evaluacion.objects.latest('pk')
            self.assertRedirects(respuesta, reverse('detalle_evaluacion', args=[creada.pk]))
            self.assertEqual(creada.empleado, self.empleado)
            self.assertEqual(creada.puntuacion, 5)
            self.assertTrue(Notificacion.objects.filter(usuario=self.trabajador, tipo='evaluacion', url=reverse('detalle_evaluacion', args=[creada.pk])).exists())
            url = reverse('editar_evaluacion', args=[creada.pk])
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertRedirects(self.client.post(url, self.datos(puntuacion=3, feedback='Actualizado')), reverse('detalle_evaluacion', args=[creada.pk]))
            creada.refresh_from_db()
            self.assertEqual(creada.puntuacion, 3)
            self.assertEqual(creada.feedback, 'Actualizado')

    def test_gerente_consulta_sin_acciones_de_edicion(self):
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse('gestion_evaluaciones'))
        self.assertContains(respuesta, 'Privado 2026')
        self.assertNotContains(respuesta, reverse('crear_evaluacion'))
        respuesta = self.client.get(reverse('detalle_evaluacion', args=[self.ajena.pk]))
        self.assertContains(respuesta, 'Comentario privado')
        self.assertNotContains(respuesta, reverse('editar_evaluacion', args=[self.ajena.pk]))

    def test_validacion_no_guarda_datos_invalidos(self):
        self.client.force_login(self.rrhh)
        for cambios in [{'puntuacion': 0}, {'puntuacion': 6}, {'periodo': '   '}, {'empleado': 999999}]:
            respuesta = self.client.post(reverse('crear_evaluacion'), self.datos(**cambios))
            self.assertEqual(respuesta.status_code, 200)
            self.assertTrue(respuesta.context['formulario'].errors)
        self.assertEqual(Evaluacion.objects.count(), 2)

    def test_filtros_y_paginacion(self):
        self.client.force_login(self.rrhh)
        respuesta = self.client.get(reverse('gestion_evaluaciones'), {'busqueda': 'Propio', 'periodo': '2026', 'puntuacion': '4'})
        self.assertEqual(respuesta.context['total'], 1)
        self.assertNotContains(respuesta, 'Privado 2026')
        self.assertEqual(self.client.get(reverse('gestion_evaluaciones'), {'puntuacion': 'invalida'}).context['total'], 0)
        Evaluacion.objects.bulk_create([Evaluacion(empleado=self.empleado, periodo=f'Extra {i}', puntuacion=3) for i in range(22)])
        respuesta = self.client.get(reverse('gestion_evaluaciones'), {'page': 2, 'busqueda': 'Propio'})
        self.assertEqual(len(respuesta.context['pagina']), 3)
        self.assertContains(respuesta, 'busqueda=Propio')

    def test_anonimo_requiere_login(self):
        for nombre, args in [('gestion_evaluaciones', []), ('mis_evaluaciones', []), ('crear_evaluacion', []), ('editar_evaluacion', [self.propia.pk]), ('detalle_evaluacion', [self.propia.pk])]:
            self.assertEqual(self.client.get(reverse(nombre, args=args)).status_code, 302)

    def test_admin_respeta_roles(self):
        from django.contrib import admin
        configuracion = admin.site._registry[Evaluacion]
        for usuario, edita in [(self.rrhh, True), (self.gerente, False), (self.trabajador, False), (self.superusuario, True)]:
            request = RequestFactory().get('/')
            request.user = usuario
            self.assertEqual(configuracion.has_add_permission(request), edita)
            self.assertEqual(configuracion.has_change_permission(request, self.propia), edita)
            self.assertEqual(configuracion.has_view_permission(request), usuario != self.trabajador)
            self.assertEqual(configuracion.has_delete_permission(request, self.propia), usuario.is_superuser)

    def test_csrf_y_comentarios_escapados(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.rrhh)
        self.assertEqual(cliente.post(reverse('crear_evaluacion'), self.datos()).status_code, 403)
        self.propia.feedback = '<script>alert(1)</script>'
        self.propia.save()
        self.client.force_login(self.trabajador)
        self.assertContains(self.client.get(reverse('detalle_evaluacion', args=[self.propia.pk])), '&lt;script&gt;')


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
