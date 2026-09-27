import csv
import io
import json
import tempfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission, User
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from personal import usernames
from personal.autorizacion_permisos import puede_resolver_permiso
from personal.demo_plan import ESTRUCTURA, claves_puestos, construir_plan
from personal.management.commands.reconstruir_demo_rrhh import Command, instantanea_protegida
from personal.models import Asistencia, Departamento, Empleado, Feriado, Notificacion, Permiso, Puesto


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReconstruccionDemoTests(TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.override = override_settings(BASE_DIR=Path(self.temporal.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.rrhh = User.objects.create_superuser(pk=1, username='rrhh', password='Original-segura', email='protegida@example.test')
        grupo = Group.objects.create(name='Protegido')
        grupo.permissions.add(Permission.objects.first())
        self.rrhh.groups.add(grupo)
        self.rrhh.user_permissions.add(Permission.objects.last())
        self.yubel = User.objects.create_superuser(pk=10, username='yubel', password='Prueba')
        self.viejo = Empleado.objects.create(nombre_completo='Prueba anterior', usuario=self.yubel)
        self.log = LogEntry.objects.create(user=self.yubel, object_id=str(self.viejo.pk), object_repr='Anterior', action_flag=1)
        self.log_rrhh = LogEntry.objects.create(user=self.rrhh, object_id=str(self.viejo.pk), object_repr='Anterior', action_flag=2)
        Notificacion.objects.create(usuario=self.yubel, mensaje='Antigua')
        Notificacion.objects.create(usuario=self.rrhh, mensaje='Protegida')
        self.feriado = Feriado.objects.create(fecha=date(2026, 9, 18), nombre='Calendario existente', irrenunciable=True)
        from django.contrib.sessions.backends.db import SessionStore
        Session.objects.create(session_key='sesion-rrhh', session_data=SessionStore().encode({'_auth_user_id': '1'}),
                               expire_date=timezone.now()+timedelta(days=1))
        Session.objects.create(session_key='sesion-indecodificable', session_data='contenido-no-valido',
                               expire_date=timezone.now()+timedelta(days=1))

    def ejecutar(self, real=False, **kwargs):
        return call_command('reconstruir_demo_rrhh', seed=2026, fecha_referencia=date(2026, 9, 27),
                            ejecutar=real, confirmar='RECONSTRUIR_DEMO_RRHH' if real else '',
                            stdout=io.StringIO(), **kwargs)

    def snapshot(self):
        return {m._meta.label: list(m.objects.order_by('pk').values()) for m in apps.get_models()}

    def test_dry_run_es_realmente_solo_lectura(self):
        antes = self.snapshot()
        with connection.cursor() as cur:
            cur.execute('SELECT * FROM sqlite_sequence ORDER BY name')
            secuencias = cur.fetchall()
        with CaptureQueriesContext(connection) as consultas:
            self.ejecutar(dry_run=True)
        self.assertEqual(self.snapshot(), antes)
        self.assertFalse(list(Path(self.temporal.name).iterdir()))
        self.assertFalse([q['sql'] for q in consultas if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER'))])
        with connection.cursor() as cur:
            cur.execute('SELECT * FROM sqlite_sequence ORDER BY name')
            self.assertEqual(cur.fetchall(), secuencias)

    def test_sin_bandera_solo_simula(self):
        antes = self.snapshot()
        self.ejecutar()
        self.assertEqual(self.snapshot(), antes)

    def test_plan_reproducible_y_estados(self):
        plan = construir_plan(2026, date(2026, 9, 27), {self.feriado.fecha})
        self.assertEqual(plan, construir_plan(2026, date(2026, 9, 27), {self.feriado.fecha}))
        self.assertNotEqual(plan, construir_plan(2027, date(2026, 9, 27), {self.feriado.fecha}))
        self.assertEqual(Counter(p['estado'] for p in plan), Counter(activo=73, renuncio=4, despedido=3))

    def test_reconstruccion_completa_aislada_y_credenciales(self):
        protegido = instantanea_protegida()
        superviviente = User.objects.create_user(username='amaro.castillo', password='Conservar')
        original = User.objects.filter(pk=superviviente.pk).values().get()
        with patch('personal.usernames.generar_username_unico', wraps=usernames.generar_username_unico) as helper:
            self.ejecutar(real=True)
        self.assertEqual(helper.call_count, 80)
        self.assertEqual(instantanea_protegida(), protegido)
        self.assertEqual(User.objects.filter(pk=superviviente.pk).values().get(), original)
        self.assertFalse(User.objects.filter(username='yubel').exists())
        self.assertEqual(Empleado.objects.count(), 80)
        self.assertEqual(User.objects.count(), 82)
        self.assertFalse(Session.objects.exists())
        self.assertEqual(Empleado.objects.filter(usuario__is_active=False).count(), 7)
        self.assertEqual(Empleado.objects.exclude(usuario=None).count(), 80)
        puestos = list(Puesto.objects.values_list('departamento_id', 'nombre', 'nivel'))
        self.assertEqual(len(puestos), len(set(puestos)))
        for nombre, activos, historicos, *_ in ESTRUCTURA:
            empleados = Empleado.objects.filter(departamento=nombre)
            self.assertEqual(empleados.count(), activos + len(historicos))
            self.assertEqual(empleados.filter(estado_laboral='activo').count(), activos)
        amaro = Empleado.objects.get(nombre_completo='Amaro Castillo Ahumada')
        self.assertEqual(amaro.usuario.username, 'amaro.castilloa')
        self.assertEqual(Departamento.objects.get(nombre='Tecnología').jefe, amaro)
        self.assertTrue(amaro.usuario.check_password('DemoRRHH!2026'))
        propio = Permiso.objects.filter(empleado__departamento='Tecnología').exclude(empleado=amaro).first()
        ajeno = Permiso.objects.filter(empleado__departamento='Operaciones').first()
        with patch('personal.autorizacion_permisos.timezone.localdate', return_value=date(2026, 9, 27)):
            self.assertTrue(puede_resolver_permiso(amaro.usuario, propio))
            self.assertFalse(puede_resolver_permiso(amaro.usuario, ajeno))
            self.assertFalse(puede_resolver_permiso(amaro.usuario, amaro.permisos.first()))
        for empleado in Empleado.objects.select_related('usuario'):
            self.assertFalse(empleado.usuario.is_staff)
            self.assertFalse(empleado.usuario.is_superuser)
            self.assertEqual(empleado.usuario.is_active, empleado.estado_laboral == 'activo')
            self.assertEqual(empleado.historial_puestos.filter(es_actual=True).count(), int(empleado.estado_laboral == 'activo'))
        carpeta = next((Path(self.temporal.name) / '.demo_rrhh').iterdir())
        with (carpeta / 'credenciales_demo_rrhh.csv').open(encoding='utf-8-sig') as archivo:
            filas = list(csv.DictReader(archivo))
        self.assertEqual(len(filas), 80)
        self.assertNotIn('rrhh', [f['username'] for f in filas])
        self.assertTrue(all(f['password_demo'] == 'DemoRRHH!2026' for f in filas))
        self.assertEqual(sum(f['activo'] == 'False' for f in filas), 7)
        auditoria = json.loads((carpeta / 'auditoria_anterior.json').read_text(encoding='utf-8'))
        self.assertIn(self.log.pk, [a['id'] for a in auditoria])
        self.assertTrue(LogEntry.objects.filter(pk=self.log_rrhh.pk).exists())
        self.assertTrue(Feriado.objects.filter(pk=self.feriado.pk).exists())
        self.assertTrue(Notificacion.objects.filter(usuario=self.rrhh, mensaje='Protegida').exists())

    def test_fallo_final_revierte_datos_y_no_publica_credenciales(self):
        antes = self.snapshot()
        with patch.object(Command, 'validar', side_effect=CommandError('Fallo simulado')):
            with self.assertRaises(CommandError):
                self.ejecutar(real=True)
        self.assertEqual(self.snapshot(), antes)
        self.assertFalse(list(Path(self.temporal.name).rglob('*.csv')))

    def test_proteccion_id_username_y_ficha(self):
        User.objects.filter(pk=1).update(username='otro')
        antes = self.snapshot()
        with self.assertRaises(CommandError):
            self.ejecutar(real=True)
        self.assertEqual(self.snapshot(), antes)
        User.objects.filter(pk=1).update(username='rrhh')
        Empleado.objects.create(nombre_completo='Prohibido', usuario_id=1)
        with self.assertRaises(CommandError):
            self.ejecutar(real=True)

    def test_no_elimina_rrhh_explicito(self):
        with self.assertRaises(CommandError):
            self.ejecutar(real=True, eliminar_usuario=['rrhh'])

    def test_superusuario_inesperado_aborta(self):
        usuario = User.objects.create_superuser(username='otro_admin', password='Original')
        Empleado.objects.create(nombre_completo='No borrar', usuario=usuario)
        with self.assertRaises(CommandError):
            self.ejecutar(real=True)

    def test_exige_confirmacion_real(self):
        antes = self.snapshot()
        with self.assertRaises(CommandError):
            call_command('reconstruir_demo_rrhh', ejecutar=True, stdout=io.StringIO())
        self.assertEqual(self.snapshot(), antes)

    def test_historia_coherente(self):
        plan = construir_plan(2026, date(2026, 9, 27), {self.feriado.fecha})
        estados = Counter()
        for persona in plan:
            fin = persona['salida'] or date(2026, 9, 27)
            self.assertLess(persona['nacimiento'], persona['ingreso'])
            meses = set()
            self.assertLessEqual(len(persona['nominas']), 12)
            for salario in persona['nominas']:
                fecha = salario['mes_ano']
                self.assertTrue(persona['ingreso'] <= fecha <= fin)
                self.assertNotIn((fecha.year, fecha.month), meses)
                meses.add((fecha.year, fecha.month))
                self.assertEqual(salario['neto'], salario['salario_base']+salario['bonificacion']-salario['descuentos'])
            for dia, estado in persona['asistencias']:
                self.assertTrue(persona['ingreso'] <= dia <= fin)
                if dia == self.feriado.fecha:
                    self.assertEqual(estado, 'feriado')
                elif dia.weekday() >= 5:
                    self.assertEqual(estado, 'descanso')
                elif any(p['aprobado'] and p['fecha_inicio'] <= dia <= p['fecha_fin'] for p in persona['permisos']):
                    self.assertEqual(estado, 'permiso')
                estados[estado] += 1
        self.assertGreater(estados['presente'], 10 * (estados['ausente'] + estados['atraso']))

    def test_sesiones_planificadas_sin_decodificar_y_sin_escrituras(self):
        antes = list(Session.objects.order_by('pk').values())
        salida = io.StringIO()
        with patch.object(Session, 'get_decoded', side_effect=AssertionError('No decodificar')):
            call_command('reconstruir_demo_rrhh', dry_run=True, seed=2026,
                         fecha_referencia=date(2026, 9, 27), stdout=salida)
        self.assertIn('"sesiones_eliminar": 2', salida.getvalue())
        self.assertEqual(list(Session.objects.order_by('pk').values()), antes)

    def test_gerente_prueba_confirmado_y_total_81(self):
        prueba = User.objects.create_user(pk=20, username='gerente.prueba', password='Prueba')
        prueba.groups.add(Group.objects.get_or_create(name='GERENTES')[0])
        protegido = instantanea_protegida()
        self.ejecutar(real=True)
        self.assertFalse(User.objects.filter(username='gerente.prueba').exists())
        self.assertEqual(User.objects.count(), 81)
        self.assertEqual(Empleado.objects.count(), 80)
        self.assertEqual(instantanea_protegida(), protegido)
        self.assertFalse(Session.objects.exists())
        amaro = Empleado.objects.get(nombre_completo='Amaro Castillo Ahumada')
        self.assertEqual(amaro.usuario.username, 'amaro.castillo')
        pendientes = Permiso.objects.filter(estado='pendiente', empleado__departamento='Tecnología').exclude(empleado=amaro)
        self.assertEqual(pendientes.count(), 3)
        with patch('personal.autorizacion_permisos.timezone.localdate', return_value=date(2026, 9, 27)):
            self.assertTrue(all(puede_resolver_permiso(amaro.usuario, p) for p in pendientes))

    def test_gerente_prueba_cambiado_aborta_sin_borrar(self):
        prueba = User.objects.create_user(pk=20, username='gerente.prueba', password='Prueba', email='nuevo@example.test')
        prueba.groups.add(Group.objects.get_or_create(name='GERENTES')[0])
        antes = self.snapshot()
        with self.assertRaises(CommandError):
            self.ejecutar(real=True)
        self.assertEqual(self.snapshot(), antes)

    def test_nombre_prueba_con_otro_id_no_se_elimina(self):
        prueba = User.objects.create_user(pk=21, username='gerente.prueba', password='Prueba')
        prueba.groups.add(Group.objects.get_or_create(name='GERENTES')[0])
        with self.assertRaises(CommandError):
            self.ejecutar(real=True)
        self.assertTrue(User.objects.filter(pk=21).exists())

    def test_volumen_solicitudes_evaluaciones_y_puestos(self):
        referencia = date(2026, 9, 27)
        plan = construir_plan(2026, referencia, {self.feriado.fecha})
        pendientes = Counter(p['departamento'] for p in plan for q in p['permisos'] if q['estado'] == 'pendiente')
        self.assertEqual(sum(pendientes.values()), 10)
        self.assertEqual(set(pendientes), {n for n, *_ in ESTRUCTURA})
        self.assertEqual(pendientes['Tecnología'], 4)
        self.assertLess(sum(len(p['permisos']) for p in plan), 200)
        self.assertLess(len(claves_puestos(plan)), 99)
        for p in plan:
            periodos = set()
            for e in p['evaluaciones']:
                anio = int(e['periodo'][:4])
                fin = date(anio, 6, 30) if 'Primer' in e['periodo'] else date(anio, 12, 31)
                self.assertTrue(p['ingreso'] <= fin <= (p['salida'] or referencia))
                self.assertNotIn(e['periodo'], periodos)
                periodos.add(e['periodo'])
            for q in p['permisos']:
                self.assertEqual(q['aprobado'], q['estado'] == 'aprobado')
                self.assertGreaterEqual(q['fecha_inicio'], p['ingreso'])
                if p['salida']:
                    self.assertLessEqual(q['fecha_fin'], p['salida'])
