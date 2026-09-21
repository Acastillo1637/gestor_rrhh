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
                if superuser and aviso.usuario_id is None:
                    continue  # Gestión puede actuar sobre el buzón general.
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


class CrearEmpleadoNombresTests(TestCase):
    """El alta captura nombres separados sin cambiar el almacenamiento existente."""

    # Las pruebas cubren validación, guardado, creación de cuenta y edición anterior.
    # TestCase usa una base de pruebas; no modifica los empleados de la base real.

    @classmethod
    def setUpTestData(cls):
        from .models import Departamento, Puesto
        departamento, _ = Departamento.objects.get_or_create(nombre='Pruebas nombres')
        Puesto.objects.get_or_create(nombre='Cargo prueba', departamento=departamento, defaults={'salario_base': 1000})
        cls.admin = User.objects.create_user(username='rrhh_prueba', is_superuser=True)

    def datos(self, **cambios):
        datos = {'nombres': 'María José', 'apellidos': 'De la Cruz Pérez',
                 'departamento': 'Pruebas nombres', 'cargo': 'Cargo prueba',
                 'salario_mensual': '1000.00', 'estado_laboral': 'activo'}
        datos.update(cambios)
        return datos

    def test_obligatorios_y_espacios(self):
        from .forms import CrearEmpleadoForm
        for campo in ['nombres', 'apellidos']:
            for valor in ['', '   ', '\t\n', '\u00a0']:
                with self.subTest(campo=campo, valor=valor):
                    f = CrearEmpleadoForm(self.datos(**{campo: valor}))
                    self.assertFalse(f.is_valid())
                    self.assertIn(campo, f.errors)
                    with self.assertRaises(ValueError):
                        f.save()

    def test_union_y_commit_false(self):
        from .forms import CrearEmpleadoForm
        f = CrearEmpleadoForm(self.datos(nombres='  María   José ', apellidos=' De la Cruz-Pérez '))
        self.assertTrue(f.is_valid(), f.errors)
        empleado = f.save(commit=False)
        self.assertIsNone(empleado.pk)
        self.assertEqual(empleado.nombre_completo, 'María José De la Cruz-Pérez')
        empleado.save()
        empleado.refresh_from_db()
        self.assertEqual(empleado.nombre_completo, 'María José De la Cruz-Pérez')

    def test_limite_combinado(self):
        from .forms import CrearEmpleadoForm
        f = CrearEmpleadoForm(self.datos(nombres='A' * 75, apellidos='B' * 74))
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(len(f.save().nombre_completo), 150)
        f = CrearEmpleadoForm(self.datos(nombres='A' * 75, apellidos='B' * 75))
        self.assertFalse(f.is_valid())
        self.assertIn('apellidos', f.errors)

    def test_alta_completa_y_busqueda(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse('crear_empleado'), self.datos())
        self.assertEqual(respuesta.status_code, 302)
        empleado = Empleado.objects.get(nombre_completo='María José De la Cruz Pérez')
        self.assertIsNotNone(empleado.usuario)
        self.assertEqual(empleado.departamento, 'Pruebas nombres')
        self.assertEqual(empleado.cargo, 'Cargo prueba')
        self.assertEqual(empleado.salario_mensual, 1000)
        self.assertEqual(empleado.estado_laboral, 'activo')
        self.assertTrue(Empleado.objects.filter(nombre_completo__icontains='De la Cruz').exists())

    def test_post_invalido_no_crea_empleado_ni_cuenta(self):
        self.client.force_login(self.admin)
        cantidad = User.objects.count()
        empleados_antes = Empleado.objects.count()
        respuesta = self.client.post(reverse('crear_empleado'), self.datos(apellidos='  '))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Ingresa los apellidos del empleado.')
        self.assertEqual(Empleado.objects.count(), empleados_antes)
        self.assertEqual(User.objects.count(), cantidad)

    def test_edicion_preserva_nombre_existente(self):
        from .forms import EmpleadoForm
        empleado = Empleado.objects.create(nombre_completo='Ana María de los Ángeles Pérez')
        datos = self.datos(nombre_completo=empleado.nombre_completo)
        f = EmpleadoForm(datos, instance=empleado)
        self.assertTrue(f.is_valid(), f.errors)
        self.assertNotIn('nombres', f.fields)
        self.assertEqual(f.save().nombre_completo, 'Ana María de los Ángeles Pérez')

    def test_campos_y_atributos_html(self):
        from .forms import CrearEmpleadoForm
        f = CrearEmpleadoForm()
        self.assertEqual(set(f.fields), {'nombres', 'apellidos', 'cargo', 'departamento', 'salario_mensual', 'fecha_contratacion', 'estado_laboral'})
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse('crear_empleado'))
        self.assertNotContains(respuesta, 'name="nombre_completo"')
        for campo in ['nombres', 'apellidos']:
            self.assertIn('required', str(f[campo]))
            self.assertIn('pattern=', str(f[campo]))
            self.assertContains(respuesta, f'id="{campo}-errors"')


class AdminMensajesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='admin_avisos', password='solo-prueba')
        self.client.force_login(self.admin)

    def test_guardar_en_admin_muestra_aviso_una_vez(self):
        respuesta = self.client.post(reverse('admin:auth_group_add'),
                                     {'name': 'Grupo prueba avisos', '_save': 'Guardar'}, follow=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(Group.objects.filter(name='Grupo prueba avisos').exists())
        self.assertContains(respuesta, 'data-admin-messages')
        self.assertContains(respuesta, 'rrhh-message-success')
        self.assertContains(respuesta, 'Grupo prueba avisos')
        self.assertNotContains(respuesta, '<ul class="messagelist">')
        respuesta = self.client.get(reverse('admin:auth_group_changelist'))
        self.assertNotContains(respuesta, 'data-admin-messages')

    def test_todos_los_niveles_y_escape(self):
        from django.contrib.messages.storage.base import Message
        from django.contrib.messages.storage.session import SessionStorage
        request = RequestFactory().get('/admin/')
        request.session = self.client.session
        SessionStorage(request)._store([
            Message(25, 'Guardado'), Message(40, 'Error de prueba'),
            Message(30, 'Advertencia'), Message(20, '<script>prueba</script>'),
        ], response=None)
        request.session.save()
        with self.settings(MESSAGE_STORAGE='django.contrib.messages.storage.session.SessionStorage'):
            respuesta = self.client.get(reverse('admin:index'))
        for nivel in ['success', 'error', 'warning', 'info']:
            self.assertContains(respuesta, f'rrhh-message-{nivel}')
        self.assertContains(respuesta, '&lt;script&gt;prueba&lt;/script&gt;')
        self.assertNotContains(respuesta, '<script>prueba</script>')
        self.assertContains(respuesta, 'data-accept-admin-messages', count=1)

    def test_gestion_opera_compartidos_staff_no_autorizado_no(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        otro = User.objects.create_user(username='propietario_privado')
        privado = Notificacion.objects.create(usuario=otro, mensaje='Privado')
        staff = User.objects.create_user(username='staff_sin_rol', is_staff=True)
        for rol in ['staff', 'RRHH', 'GERENTES', 'superusuario']:
            usuario = self.admin if rol == 'superusuario' else staff
            staff.groups.clear()
            if rol in ['RRHH', 'GERENTES']:
                staff.groups.add(Group.objects.get_or_create(name=rol)[0])
            cliente.force_login(usuario)
            cliente.get(reverse('cambiar_contrasena'))
            token = cliente.cookies['csrftoken'].value
            aviso = Notificacion.objects.create(mensaje='Compartido ' + rol)
            for accion in ['marcar_notificacion_leida', 'eliminar_notificacion']:
                url = reverse(accion, args=[aviso.pk])
                self.assertEqual(cliente.get(url).status_code, 405)
                self.assertEqual(cliente.post(url).status_code, 403)
                response = cliente.post(url, {'csrfmiddlewaretoken': token}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
                self.assertEqual(response.status_code, 404 if rol == 'staff' else 200)
                self.assertEqual(cliente.post(reverse(accion, args=[privado.pk]), {'csrfmiddlewaretoken': token}).status_code, 404)
            self.assertEqual(Notificacion.objects.filter(pk=aviso.pk).exists(), rol == 'staff')
        privado.refresh_from_db()
        self.assertFalse(privado.leida)

    def test_admin_carga_botones_modal_y_script(self):
        Notificacion.objects.create(mensaje='Aviso compartido')
        response = self.client.get(reverse('admin:index'))
        for texto in ['Marcar como leída', 'Eliminar notificación', 'id="deleteNotificationDialog"', 'notification_actions.js', 'admin_notifications.css']:
            self.assertContains(response, texto)


class EditarEmpleadoNombresTests(TestCase):
    def setUp(self):
        from .models import Departamento, Puesto
        depto, _ = Departamento.objects.get_or_create(nombre='Edición prueba')
        Puesto.objects.get_or_create(nombre='Cargo edición', departamento=depto, defaults={'salario_base': 1000})
        self.empleado = Empleado.objects.create(nombre_completo='Almendra Valdés Antúnez',
            departamento=depto.nombre, cargo='Cargo edición', salario_mensual=1000, estado_laboral='activo')
        self.admin = User.objects.create_user(username='editor_prueba', is_superuser=True)
        self.client.force_login(self.admin)
        self.url = reverse('editar_empleado', args=[self.empleado.pk])
        self.datos = {'nombres': 'Almendra', 'apellidos': 'Valdés Antúnez',
            'departamento': depto.nombre, 'cargo': 'Cargo edición', 'salario_mensual': '1000', 'estado_laboral': 'activo'}

    def test_precarga_y_conservacion_de_palabras(self):
        from .forms import EditarEmpleadoForm
        for nombre in ['Almendra Valdés Antúnez', 'María José de la Cruz Pérez', 'Pedro González', 'Almendra']:
            self.empleado.nombre_completo = nombre
            f = EditarEmpleadoForm(instance=self.empleado)
            self.assertEqual((f.initial['nombres'] + ' ' + f.initial['apellidos']).strip(), nombre)
        response = self.client.get(self.url)
        self.assertContains(response, 'name="nombres"')
        self.assertContains(response, 'name="apellidos"')
        self.assertNotContains(response, 'name="nombre_completo"')

    def test_vacios_no_modifican_y_conservan_valores(self):
        from .models import HistorialSalario
        avisos = Notificacion.objects.count()
        for campo in ['nombres', 'apellidos']:
            for valor in ['', '   ', '\u00a0']:
                datos = dict(self.datos, **{campo: valor})
                response = self.client.post(self.url, datos)
                self.assertEqual(response.status_code, 200)
                self.assertIn(campo, response.context['formulario'].errors)
                self.assertEqual(response.context['formulario'][campo].value(), valor)
                self.empleado.refresh_from_db()
                self.assertEqual(self.empleado.nombre_completo, 'Almendra Valdés Antúnez')
        self.assertEqual(Notificacion.objects.count(), avisos)
        self.assertFalse(HistorialSalario.objects.filter(empleado=self.empleado).exists())

    def test_guardado_y_historial_salarial(self):
        from .models import HistorialSalario
        response = self.client.post(self.url, dict(self.datos, nombres='María José', apellidos='De la Cruz Pérez'))
        self.assertEqual(response.status_code, 302)
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.nombre_completo, 'María José De la Cruz Pérez')
        self.assertEqual(self.empleado.salario_mensual, 1000)
        self.assertEqual(self.empleado.cargo, 'Cargo edición')
        self.assertEqual(self.empleado.departamento, 'Edición prueba')
        self.assertFalse(HistorialSalario.objects.filter(empleado=self.empleado).exists())
        response = self.client.post(self.url, dict(self.datos, salario_mensual='1200'))
        self.assertEqual(response.status_code, 302)
        historial = HistorialSalario.objects.get(empleado=self.empleado)
        self.assertEqual(historial.salario_anterior, 1000)
        self.assertEqual(historial.salario_nuevo, 1200)

    def test_limite_unido_y_commit_false(self):
        from .forms import EditarEmpleadoForm
        f = EditarEmpleadoForm(dict(self.datos, nombres='A'*75, apellidos='B'*75), instance=self.empleado)
        self.assertFalse(f.is_valid())
        self.assertIn('apellidos', f.errors)
        f = EditarEmpleadoForm(dict(self.datos, nombres=' Ana María ', apellidos=' Pérez '), instance=self.empleado)
        self.assertTrue(f.is_valid(), f.errors)
        empleado = f.save(commit=False)
        self.assertEqual(empleado.nombre_completo, 'Ana María Pérez')
        self.assertEqual(Empleado.objects.get(pk=empleado.pk).nombre_completo, 'Almendra Valdés Antúnez')

    def test_fecha_contratacion_visible_y_conservada(self):
        from datetime import date
        self.empleado.fecha_contratacion = date(2026, 9, 10)
        self.empleado.save(update_fields=['fecha_contratacion'])
        response = self.client.get(self.url)
        self.assertContains(response, 'value="2026-09-10"')
        response = self.client.post(self.url, dict(self.datos, fecha_contratacion='2026-09-10'))
        self.assertEqual(response.status_code, 302)
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.fecha_contratacion, date(2026, 9, 10))