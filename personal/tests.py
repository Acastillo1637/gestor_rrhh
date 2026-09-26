from decimal import Decimal
from html.parser import HTMLParser

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


class CamposFormularioParser(HTMLParser):
    """Obtiene los valores que Django entrega al navegador para reenviarlos."""

    def __init__(self, contenido):
        super().__init__()
        self.campos = {}
        self.feed(contenido.decode())

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == 'input' and atributos.get('name'):
            self.campos[atributos['name']] = atributos


class ConservacionImportesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .models import Departamento, Puesto
        departamento = Departamento.objects.create(nombre='Pruebas de importes')
        Puesto.objects.create(
            nombre='Analista', departamento=departamento,
            nivel='junior', salario_base=Decimal('850000.00'),
        )
        cls.empleado = Empleado.objects.create(
            nombre_completo='Ana Prueba', departamento=departamento.nombre,
            cargo='Analista', salario_mensual=Decimal('850000.00'), fecha_contratacion='2026-09-10',
        )
        cls.usuario = User.objects.create_user(username='rrhh_importes')
        cls.usuario.groups.add(Group.objects.get_or_create(name='RRHH')[0])

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_formulario_empleado_rechaza_salario_negativo(self):
        from .forms import EmpleadoForm

        formulario = EmpleadoForm(instance=self.empleado, data={
            'nombre_completo': 'Ana Prueba',
            'cargo': 'Analista',
            'departamento': 'Pruebas de importes',
            'salario_mensual': '-1',
            'fecha_contratacion': '2026-09-10',
            'estado_laboral': 'activo',
        })

        self.assertFalse(formulario.is_valid())
        self.assertIn('El importe debe ser superior o igual a 0.', formulario.errors['salario_mensual'])

    def test_editar_nombre_conserva_salario_sin_crear_historial(self):
        from .models import HistorialSalario
        url = reverse('editar_empleado', args=[self.empleado.pk])
        for importe in ('850000.00', '1000.50', '0.00'):
            with self.subTest(importe=importe):
                self.empleado.salario_mensual = Decimal(importe)
                self.empleado.save(update_fields=['salario_mensual'])
                respuesta = self.client.get(url)
                campo = CamposFormularioParser(respuesta.content).campos['salario_mensual']
                self.assertEqual(campo['type'], 'number')
                self.assertEqual(campo['step'], '0.01')
                self.assertEqual(Decimal(campo['value']), Decimal(importe))
                respuesta = self.client.post(url, {
                    'nombres': 'Ana Maria', 'apellidos': 'Prueba',
                    'departamento': self.empleado.departamento,
                    'cargo': self.empleado.cargo, 'estado_laboral': 'activo',
                    'salario_mensual': campo['value'], 'fecha_contratacion': '2026-09-10',
                })
                self.assertRedirects(respuesta, reverse('listar_empleados'))
                self.empleado.refresh_from_db()
                self.assertEqual(self.empleado.nombre_completo, 'Ana Maria Prueba')
                self.assertEqual(self.empleado.salario_mensual, Decimal(importe))
                self.assertFalse(HistorialSalario.objects.filter(empleado=self.empleado).exists())

    def test_edicion_invalida_conserva_importe_para_corregir_nombre(self):
        url = reverse('editar_empleado', args=[self.empleado.pk])
        datos = {
            'nombres': 'Ana', 'apellidos': '',
            'departamento': self.empleado.departamento,
            'cargo': self.empleado.cargo, 'estado_laboral': 'activo',
            'salario_mensual': '1000.50', 'fecha_contratacion': '2026-09-10',
        }
        respuesta = self.client.post(url, datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('apellidos', respuesta.context['formulario'].errors)
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.salario_mensual, Decimal('850000.00'))
        campo = CamposFormularioParser(respuesta.content).campos['salario_mensual']
        self.assertEqual(Decimal(campo['value']), Decimal('1000.50'))
        datos.update(apellidos='Prueba', salario_mensual=campo['value'])
        respuesta = self.client.post(url, datos)
        self.assertRedirects(respuesta, reverse('listar_empleados'))
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.salario_mensual, Decimal('1000.50'))

    def test_nomina_rechaza_importes_negativos(self):
        from .forms import NominaForm

        formulario = NominaForm(data={
            'empleado': self.empleado.pk,
            'mes_ano': '2026-10-01',
            'salario_base': '-1',
            'bonificacion': '0',
            'descuentos': '0',
        })

        self.assertFalse(formulario.is_valid())
        self.assertIn('El importe debe ser superior o igual a 0.', formulario.errors['salario_base'])

    def test_nomina_invalida_conserva_importes_y_calcula_neto_al_corregir(self):
        from .models import Salario
        url = reverse('crear_liquidacion')
        datos = {
            'mes_ano': '2026-09-01', 'salario_base': '850000.00',
            'bonificacion': '1000.50', 'descuentos': '0.00',
        }
        respuesta = self.client.post(url, datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('empleado', respuesta.context['formulario'].errors)
        self.assertFalse(Salario.objects.filter(empleado=self.empleado).exists())
        campos = CamposFormularioParser(respuesta.content).campos
        for nombre in ('salario_base', 'bonificacion', 'descuentos'):
            self.assertEqual(campos[nombre]['type'], 'number')
            self.assertEqual(Decimal(campos[nombre]['value']), Decimal(datos[nombre]))
            datos[nombre] = campos[nombre]['value']
        datos['empleado'] = self.empleado.pk
        respuesta = self.client.post(url, datos)
        self.assertRedirects(respuesta, reverse('gestion_nomina'))
        liquidacion = Salario.objects.get(empleado=self.empleado)
        self.assertEqual(liquidacion.salario_base, Decimal('850000.00'))
        self.assertEqual(liquidacion.bonificacion, Decimal('1000.50'))
        self.assertEqual(liquidacion.descuentos, Decimal('0.00'))
        self.assertEqual(liquidacion.neto, Decimal('851000.50'))


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
                 'salario_mensual': '1000.00', 'estado_laboral': 'activo', 'fecha_contratacion': '2026-09-10'}
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
            'departamento': depto.nombre, 'cargo': 'Cargo edición', 'salario_mensual': '1000', 'estado_laboral': 'activo', 'fecha_contratacion': '2026-09-10'}

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

class EmpleadoAdminNombresTests(TestCase):
    def setUp(self):
        from .models import Departamento, Puesto
        self.depto = Departamento.objects.create(nombre='Depto admin prueba')
        self.puesto = Puesto.objects.create(nombre='Cargo admin prueba', departamento=self.depto, salario_base=1000)
        self.admin = User.objects.create_superuser(username='admin_empleado_prueba', password='prueba')
        self.client.force_login(self.admin)
        self.datos = {'nombres': 'María José', 'apellidos': 'De la Cruz Pérez',
            'departamento_selector': self.depto.pk, 'cargo_selector': self.puesto.nombre,
            'salario_mensual': '1000', 'estado_laboral': 'activo', 'genero': 'femenino', '_save': 'Guardar', 'fecha_contratacion': '2026-09-10'}

    def test_alta_edicion_e_historiales(self):
        from .models import EmpleadoPuesto, HistorialSalario, Puesto
        response = self.client.post(reverse('admin:personal_empleado_add'), self.datos)
        self.assertEqual(response.status_code, 302, response.context['adminform'].form.errors if response.status_code == 200 else '')
        empleado = Empleado.objects.get(nombre_completo='María José De la Cruz Pérez')
        self.assertEqual(empleado.departamento, self.depto.nombre)
        self.assertEqual(empleado.cargo, self.puesto.nombre)
        self.assertTrue(EmpleadoPuesto.objects.filter(empleado=empleado, puesto=self.puesto, es_actual=True).exists())
        url = reverse('admin:personal_empleado_change', args=[empleado.pk])
        response = self.client.post(url, dict(self.datos, nombres='Ana María'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(HistorialSalario.objects.filter(empleado=empleado).exists())
        nuevo = Puesto.objects.create(nombre='Segundo cargo', departamento=self.depto, salario_base=1200)
        response = self.client.post(url, dict(self.datos, cargo_selector=nuevo.nombre, salario_mensual='1200'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HistorialSalario.objects.get(empleado=empleado).salario_anterior, 1000)
        self.assertTrue(EmpleadoPuesto.objects.filter(empleado=empleado, puesto=self.puesto, es_actual=False).exists())
        self.assertTrue(EmpleadoPuesto.objects.filter(empleado=empleado, puesto=nuevo, es_actual=True).exists())

    def test_validacion_admin_y_limite(self):
        from .admin import EmpleadoAdminForm
        for campo in ['nombres', 'apellidos']:
            for valor in ['', '   ', '\u00a0']:
                f = EmpleadoAdminForm(dict(self.datos, **{campo: valor}))
                self.assertFalse(f.is_valid())
                self.assertIn(campo, f.errors)
        f = EmpleadoAdminForm(dict(self.datos, nombres='A'*75, apellidos='B'*75))
        self.assertFalse(f.is_valid())
        self.assertIn('apellidos', f.errors)
        f = EmpleadoAdminForm(self.datos)
        self.assertTrue(f.is_valid(), f.errors)
        obj = f.save(commit=False)
        self.assertIsNone(obj.pk)
        self.assertEqual(obj.nombre_completo, 'María José De la Cruz Pérez')
        self.assertEqual(obj.cargo, self.puesto.nombre)

    def test_precarga_y_post_invalido_no_modifica(self):
        e = Empleado.objects.create(nombre_completo='Almendra Valdés Antúnez', departamento=self.depto.nombre,
                                    cargo=self.puesto.nombre, salario_mensual=1000)
        url = reverse('admin:personal_empleado_change', args=[e.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Almendra"')
        self.assertContains(response, 'value="Valdés Antúnez"')
        self.assertNotContains(response, 'name="nombre_completo"')
        response = self.client.post(url, dict(self.datos, apellidos='  '))
        self.assertContains(response, 'Ingresa los apellidos del empleado.')
        e.refresh_from_db()
        self.assertEqual(e.nombre_completo, 'Almendra Valdés Antúnez')

    def test_permisos_se_conservan(self):
        staff = User.objects.create_user(username='staff_no_rrhh', is_staff=True)
        self.client.force_login(staff)
        response = self.client.post(reverse('admin:personal_empleado_add'), self.datos)
        self.assertEqual(response.status_code, 403)


class FechaContratacionObligatoriaTests(TestCase):
    """Comprueba las rutas reales sin escribir en la base de producción."""

    def test_fecha_obligatoria_en_portal_y_admin(self):
        from datetime import date
        from .models import Departamento, Puesto
        depto = Departamento.objects.create(nombre='Fecha prueba')
        puesto = Puesto.objects.create(nombre='Cargo fecha', departamento=depto, salario_base=1000)
        usuario = User.objects.create_superuser(username='admin_fecha', password='prueba')
        self.client.force_login(usuario)
        empleado = Empleado.objects.create(nombre_completo='Ana Pérez', departamento=depto.nombre,
            cargo=puesto.nombre, salario_mensual=1000, genero='femenino')
        datos = dict(nombres='Ana', apellidos='Pérez', departamento=depto.nombre,
            cargo=puesto.nombre, departamento_selector=depto.pk, cargo_selector=puesto.nombre,
            salario_mensual='1000', estado_laboral='activo', genero='femenino', _save='Guardar')
        rutas = [
            (reverse('crear_empleado'), False, False),
            (reverse('editar_empleado', args=[empleado.pk]), False, True),
            (reverse('admin:personal_empleado_add'), True, False),
            (reverse('admin:personal_empleado_change', args=[empleado.pk]), True, True),
        ]
        for url, admin, edicion in rutas:
            with self.subTest(url=url):
                response = self.client.get(url)
                form = response.context['adminform'].form if admin else response.context['formulario']
                self.assertTrue(form.fields['fecha_contratacion'].required)
                self.assertIn('required', str(form['fecha_contratacion']))
                cantidad = Empleado.objects.count()
                for valor in [None, '', '   ', '2026-02-30']:
                    payload = dict(datos)
                    if valor is not None:
                        payload['fecha_contratacion'] = valor
                    response = self.client.post(url, payload)
                    self.assertEqual(response.status_code, 200)
                    form = response.context['adminform'].form if admin else response.context['formulario']
                    self.assertIn('fecha_contratacion', form.errors)
                    if valor in [None, '']:
                        self.assertContains(response, 'Ingresa la fecha de contratación.')
                    self.assertEqual(Empleado.objects.count(), cantidad)
                if edicion:
                    empleado.refresh_from_db()
                    response = self.client.post(url, dict(datos, fecha_contratacion='2026-09-10'))
                    self.assertEqual(response.status_code, 302)
                    empleado.refresh_from_db()
                    self.assertEqual(empleado.fecha_contratacion, date(2026, 9, 10))
                    # Al intentar borrar la fecha ya guardada, se conserva en la base.
                    self.client.post(url, dict(datos, fecha_contratacion=''))
                    empleado.refresh_from_db()
                    self.assertEqual(empleado.fecha_contratacion, date(2026, 9, 10))


class FiltroFechasAsistenciaTests(TestCase):
    """Las fechas de la URL se validan antes de consultar la base de datos."""

    def setUp(self):
        self.usuario = User.objects.create_superuser(username='revision_fechas', password='prueba')
        self.client.force_login(self.usuario)
        self.url = reverse('gestion_asistencia')

    def test_fechas_invalidas_y_rango_invertido(self):
        from django.utils import timezone
        from .models import Asistencia
        empleado = Empleado.objects.create(nombre_completo='Empleado filtro', departamento='Prueba fechas')
        casos = [
            {'fecha_desde': 'no-es-fecha'},
            {'fecha_hasta': '2026-02-30'},
            {'fecha_desde': '2026-13-01'},
            {'fecha_hasta': '   '},
            {'fecha_desde': '2026-09-22', 'fecha_hasta': '2026-09-21'},
        ]
        for fechas in casos:
            with self.subTest(fechas=fechas):
                response = self.client.get(self.url, dict(fechas, empleado=empleado.pk,
                    departamento=empleado.departamento), follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.redirect_chain), 1)
                self.assertContains(response, 'Se restableció el rango de fechas a hoy.')
                self.assertEqual(response.context['fecha_desde'], timezone.localdate().isoformat())
                self.assertEqual(response.context['fecha_hasta'], timezone.localdate().isoformat())
                self.assertEqual(response.context['empleado_seleccionado'], str(empleado.pk))
                self.assertEqual(response.context['departamento_seleccionado'], empleado.departamento)
                self.assertFalse(Asistencia.objects.exists())

    def test_filtro_valido_y_fechas_vacias(self):
        from .models import Asistencia
        from django.utils import timezone
        empleado = Empleado.objects.create(nombre_completo='Empleado rango')
        dentro = Asistencia.objects.create(empleado=empleado, fecha='2026-09-10')
        Asistencia.objects.create(empleado=empleado, fecha='2026-09-11')
        response = self.client.get(self.url, {'fecha_desde': '2026-09-10', 'fecha_hasta': '2026-09-10'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([a.pk for a in response.context['asistencias']], [dentro.pk])
        for parametros in [{}, {'fecha_desde': '', 'fecha_hasta': ''}]:
            response = self.client.get(self.url, parametros)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['fecha_desde'], timezone.localdate().isoformat())
            self.assertEqual(response.context['fecha_hasta'], timezone.localdate().isoformat())
        self.assertEqual(Asistencia.objects.count(), 2)


class PaginacionEmpleadosTests(TestCase):
    """La navegación conserva los filtros y los totales del conjunto completo."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser(
            username='revision_paginacion', password='prueba'
        )
        empleados = [
            Empleado(
                nombre_completo=f'Ana Prueba {indice:02d}',
                departamento='Paginación & Datos',
                cargo='Analista',
                estado_laboral='activo',
                salario_mensual=Decimal('100000.00'),
            )
            for indice in range(1, 13)
        ]
        empleados.extend([
            Empleado(nombre_completo='Ana Ventas', departamento='Ventas',
                     cargo='Analista', estado_laboral='activo'),
            Empleado(nombre_completo='Ana Retirada', departamento='Paginación & Datos',
                     cargo='Analista', estado_laboral='renuncio'),
            Empleado(nombre_completo='Bruno Prueba', departamento='Paginación & Datos',
                     cargo='Analista', estado_laboral='activo'),
            Empleado(nombre_completo='Carla Prueba', departamento='Ventas',
                     cargo='Gerente', estado_laboral='activo'),
        ])
        Empleado.objects.bulk_create(empleados)

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse('listar_empleados')

    def test_segunda_pagina_no_repite_empleados_y_conserva_totales(self):
        primera = self.client.get(self.url, {'departamento': 'Paginación & Datos'})
        segunda = self.client.get(self.url, {
            'departamento': 'Paginación & Datos', 'page': '2'
        })
        ids_primera = {empleado.pk for empleado in primera.context['lista_empleados']}
        ids_segunda = {empleado.pk for empleado in segunda.context['lista_empleados']}

        self.assertEqual((len(ids_primera), len(ids_segunda)), (10, 4))
        self.assertFalse(ids_primera & ids_segunda)
        self.assertEqual(len(ids_primera | ids_segunda), 14)
        self.assertEqual(segunda.context['total_empleados'], 14)
        self.assertEqual(segunda.context['total_activos'], 13)
        self.assertEqual(segunda.context['total_inactivos'], 1)
        self.assertEqual(segunda.context['total_nomina'], Decimal('1200000.00'))
        self.assertEqual(
            (segunda.context['pagina_empleados'].start_index(),
             segunda.context['pagina_empleados'].end_index()),
            (11, 14),
        )

    def test_busqueda_y_filtros_combinados_llegan_a_segunda_pagina(self):
        filtros = {
            'busqueda': 'Ana Prueba',
            'departamento': 'Paginación & Datos',
            'cargo': 'Analista',
            'estado': 'activo',
        }
        primera = self.client.get(self.url, filtros)
        segunda = self.client.get(self.url, {**filtros, 'page': '2'})

        self.assertEqual(len(primera.context['lista_empleados']), 10)
        self.assertEqual(len(segunda.context['lista_empleados']), 2)
        self.assertEqual(segunda.context['total_empleados'], 12)
        self.assertEqual(segunda.context['total_activos'], 12)
        self.assertEqual(segunda.context['total_nomina'], Decimal('1200000.00'))
        self.assertContains(
            primera,
            'page=2&amp;busqueda=Ana+Prueba&amp;departamento=Paginaci%C3%B3n+%26+Datos'
            '&amp;cargo=Analista&amp;estado=activo',
        )
        self.assertEqual(
            [empleado.nombre_completo for empleado in segunda.context['lista_empleados']],
            ['Ana Prueba 11', 'Ana Prueba 12'],
        )

    def test_pagina_invalida_y_busqueda_sin_resultados(self):
        primera = self.client.get(self.url, {
            'departamento': 'Paginación & Datos', 'page': 'no-es-numero'
        })
        ultima = self.client.get(self.url, {
            'departamento': 'Paginación & Datos', 'page': '999'
        })
        vacia = self.client.get(self.url, {'busqueda': 'Nadie', 'page': '2'})

        self.assertEqual(primera.context['pagina_empleados'].number, 1)
        self.assertEqual(ultima.context['pagina_empleados'].number, 2)
        self.assertEqual(vacia.context['total_empleados'], 0)
        self.assertEqual(len(vacia.context['lista_empleados']), 0)
        self.assertNotContains(vacia, 'aria-label="Página siguiente"')
