from datetime import date

from django.apps import apps
from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Departamento, Empleado, EmpleadoPuesto, Notificacion, Permiso, Puesto


class PermisosDepartamentoTests(TestCase):
    def setUp(self):
        self.gerente = User.objects.create_user('gerente')
        self.gerente.groups.add(Group.objects.get_or_create(name='GERENTES')[0])
        self.tecnologia = Departamento.objects.create(nombre='Tecnologia')
        self.operaciones = Departamento.objects.create(nombre='Operaciones')
        self.jefe = self.empleado('Jefe', self.tecnologia, self.gerente)
        self.tecnologia.jefe = self.jefe
        self.tecnologia.save()
        self.local = self.empleado('Local', self.tecnologia)
        self.ajeno = self.empleado('Ajeno', self.operaciones)
        self.client.force_login(self.gerente)

    def empleado(self, nombre, departamento, usuario=None):
        empleado = Empleado.objects.create(nombre_completo=nombre, usuario=usuario,
                                          departamento='Texto legado no fiable')
        puesto = Puesto.objects.create(nombre=nombre, departamento=departamento,
                                       nivel='senior', salario_base=1000000)
        EmpleadoPuesto.objects.create(empleado=empleado, puesto=puesto,
                                     fecha_inicio=date(2020, 1, 1))
        return empleado

    def permiso(self, empleado):
        return Permiso.objects.create(empleado=empleado, tipo='vacaciones',
                                      fecha_inicio=date(2026, 10, 1),
                                      fecha_fin=date(2026, 10, 3), dias=3)

    def denegado(self, empleado):
        for accion in ['aprobar_permiso', 'rechazar_permiso']:
            permiso = self.permiso(empleado)
            antes = list(Permiso.objects.filter(pk=permiso.pk).values())
            conteos = {m: m.objects.count() for m in apps.get_app_config('personal').get_models()}
            for metodo in ['get', 'post']:
                with CaptureQueriesContext(connection) as consultas:
                    respuesta = getattr(self.client, metodo)(reverse(accion, args=[permiso.pk]))
                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(list(Permiso.objects.filter(pk=permiso.pk).values()), antes)
                self.assertEqual({m: m.objects.count() for m in conteos}, conteos)
                escrituras = [q['sql'] for q in consultas if q['sql'].lstrip().upper().startswith(
                    ('INSERT ', 'UPDATE ', 'DELETE '))]
                self.assertEqual(escrituras, [])

    def test_gerente_aprueba_y_rechaza_departamento_propio(self):
        for accion, estado in [('aprobar_permiso', 'aprobado'), ('rechazar_permiso', 'rechazado')]:
            permiso = self.permiso(self.local)
            respuesta = self.client.post(reverse(accion, args=[permiso.pk]))
            self.assertEqual(respuesta.status_code, 302)
            permiso.refresh_from_db()
            self.assertEqual(permiso.estado, estado)
            self.assertEqual(permiso.aprobado, estado == 'aprobado')

    def test_otro_departamento(self):
        self.denegado(self.ajeno)

    def test_autosolicitud(self):
        self.denegado(self.jefe)

    def test_sin_ficha(self):
        self.jefe.usuario = None
        self.jefe.save()
        self.denegado(self.local)

    def test_sin_departamento_relacional(self):
        self.jefe.historial_puestos.all().delete()
        self.denegado(self.local)

    def test_inactivo(self):
        self.jefe.estado_laboral = 'renuncio'
        self.jefe.save()
        self.denegado(self.local)

    def test_no_es_jefatura(self):
        self.tecnologia.jefe = self.local
        self.tecnologia.save()
        self.denegado(self.local)

    def test_puestos_ambiguos(self):
        actual = self.jefe.historial_puestos.get()
        actual.pk = None
        actual.save()
        self.denegado(self.local)

    def test_solicitante_sin_departamento(self):
        self.local.historial_puestos.all().delete()
        self.denegado(self.local)

    def test_empleado_normal(self):
        self.gerente.groups.clear()
        self.gerente.groups.add(Group.objects.get_or_create(name='EMPLEADO')[0])
        self.denegado(self.local)

    def test_rrhh_y_superusuario_cualquier_departamento(self):
        for rol in ['RRHH', 'superusuario']:
            usuario = User.objects.create_user(rol, is_superuser=rol == 'superusuario')
            if rol == 'RRHH':
                usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
            self.client.force_login(usuario)
            for empleado in [self.local, self.ajeno, self.jefe]:
                for accion in ['aprobar_permiso', 'rechazar_permiso']:
                    permiso = self.permiso(empleado)
                    self.assertEqual(self.client.post(reverse(accion, args=[permiso.pk])).status_code, 302)
                    permiso.refresh_from_db()
                    self.assertEqual(permiso.estado, 'aprobado' if accion == 'aprobar_permiso' else 'rechazado')

    def test_botones_solo_para_solicitudes_autorizadas(self):
        propio = self.permiso(self.local)
        ajeno = self.permiso(self.ajeno)
        personal = self.permiso(self.jefe)
        respuesta = self.client.get(reverse('gestion_permisos'))
        self.assertEqual(respuesta.status_code, 200)
        for accion in ['aprobar_permiso', 'rechazar_permiso']:
            self.assertContains(respuesta, reverse(accion, args=[propio.pk]))
            for permiso in [ajeno, personal]:
                self.assertNotContains(respuesta, reverse(accion, args=[permiso.pk]))
        self.assertContains(respuesta, 'Ajeno')

    def test_gerente_sin_admin(self):
        self.assertFalse(self.gerente.is_staff)
        self.assertFalse(self.gerente.is_superuser)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
