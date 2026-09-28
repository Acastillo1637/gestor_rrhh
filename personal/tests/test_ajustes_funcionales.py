from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs

from django.contrib.auth.models import User, Group
from django.db import connection, IntegrityError, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..forms import NominaForm
from ..models import Empleado, Asistencia, Salario, Notificacion


class AjustesFuncionalesTests(TestCase):
    def setUp(self):
        self.rrhh = User.objects.create_user('rrhh_prueba')
        self.rrhh.groups.add(Group.objects.create(name='RRHH'))
        self.gerente = User.objects.create_user('gerente_prueba')
        self.gerente.groups.add(Group.objects.create(name='GERENTES'))
        self.jefe = Empleado.objects.create(nombre_completo='Gerente', usuario=self.gerente)
        self.empleado = Empleado.objects.create(nombre_completo='Empleado')
        self.client.force_login(self.rrhh)

    def datos(self, **extra):
        return dict(empleado=self.empleado.pk, mes_ano='2026-09-27', salario_base='1000000',
                    bonificacion='0', descuentos='0', **extra)

    def salario(self, **extra):
        valores = dict(empleado=self.empleado, mes_ano=date(2026,9,1), salario_base=1000000)
        valores.update(extra)
        return Salario.objects.create(**valores)

    def estado(self, empleado=None, fecha='2026-09-27'):
        return self.client.get(reverse('estado_liquidacion'),
                               {'empleado': (empleado or self.empleado).pk, 'mes_ano': fecha})

    def test_gerente_navegacion_y_marcacion_propia(self):
        self.client.force_login(self.gerente)
        response=self.client.get(reverse('dashboard_gerente'))
        for view in ['mi_asistencia','mis_permisos','solicitar_permiso','mis_liquidaciones','mis_evaluaciones']:
            self.assertContains(response, reverse(view))
        self.assertEqual(self.client.get(reverse('mi_asistencia')).status_code,200)
        for accion in ['entrada','salida']:
            self.assertEqual(self.client.post(reverse('mi_asistencia'), {'accion':accion,'empleado':self.empleado.pk}).status_code,302)
        registro=Asistencia.objects.get()
        self.assertEqual(registro.empleado,self.jefe)
        self.assertIsNotNone(registro.hora_entrada)
        self.assertIsNotNone(registro.hora_salida)
        self.assertFalse(self.gerente.is_staff)
        self.assertEqual(self.client.get(reverse('estado_liquidacion')).status_code,403)
        self.assertNotEqual(self.client.post(reverse('crear_liquidacion'),self.datos()).status_code,200)
        self.assertFalse(Salario.objects.exists())

    def test_empleado_marca_igual_y_admin_no_crea_ficha(self):
        self.gerente.groups.clear()
        self.gerente.groups.add(Group.objects.create(name='EMPLEADO'))
        self.client.force_login(self.gerente)
        self.client.post(reverse('mi_asistencia'), {'accion':'entrada','empleado':self.empleado.pk})
        self.assertEqual(Asistencia.objects.get().empleado,self.jefe)
        self.assertEqual(self.estado().status_code,403)
        self.client.force_login(self.rrhh)
        self.assertEqual(self.client.get(reverse('gestion_asistencia')).status_code,200)
        self.assertFalse(Empleado.objects.filter(usuario=self.rrhh).exists())

    def test_mes_completo_incluye_febrero_y_cambio_anio(self):
        for hoy,desde,hasta in [(date(2026,9,27),'2026-09-01','2026-09-30'),
                                (date(2026,2,10),'2026-02-01','2026-02-28'),
                                (date(2024,2,10),'2024-02-01','2024-02-29'),
                                (date(2026,12,31),'2026-12-01','2026-12-31'),
                                (date(2027,1,1),'2027-01-01','2027-01-31')]:
            with self.subTest(hoy=hoy),patch('personal.views.timezone.localdate',return_value=hoy):
                response=self.client.get(reverse('gestion_asistencia'))
                self.assertEqual(response.context['fecha_desde'],desde)
                self.assertEqual(response.context['fecha_hasta'],hasta)
                filtros=parse_qs(response.context['filtros_pagina'])
                self.assertEqual(filtros['fecha_desde'],[desde])
                self.assertEqual(filtros['fecha_hasta'],[hasta])

    def test_rango_manual_y_mes_implicito_persisten(self):
        url=reverse('gestion_asistencia')
        with patch('personal.views.timezone.localdate',return_value=date(2026,9,27)):
            response=self.client.get(url)
        selector=dict(response.context['filtros_selector'])
        with patch('personal.views.timezone.localdate',return_value=date(2026,10,1)):
            for size in [10,25,50,100]:
                selector['por_pagina']=size
                response=self.client.get(url,selector)
                self.assertEqual(response.context['fecha_hasta'],'2026-09-30')
                self.assertEqual(response.context['pagina'].number,1)
            response=self.client.get(url,{'fecha_desde':'2025-05-10','fecha_hasta':'2025-06-12','page':2,'por_pagina':25})
            self.assertEqual(response.context['fecha_desde'],'2025-05-10')
            self.assertEqual(response.context['fecha_hasta'],'2025-06-12')
            self.assertEqual(dict(response.context['filtros_selector'])['fecha_desde'],'2025-05-10')

    def test_estado_sin_liquidacion_y_creacion(self):
        self.assertFalse(self.estado().json()['existe'])
        response=self.client.post(reverse('crear_liquidacion'),self.datos())
        self.assertEqual(response.status_code,302)
        self.assertEqual(Salario.objects.count(),1)
        self.assertTrue(self.estado().json()['existe'])

    def test_estado_pendiente_pagada_cambio_empleado_y_periodo(self):
        registro=self.salario()
        for pagado,estado in [(False,'Pendiente de pago'),(True,'Pagada')]:
            registro.pagado=pagado;registro.save()
            datos=self.estado().json()
            self.assertTrue(datos['existe'])
            self.assertEqual(datos['estado'],estado)
            self.assertEqual(datos['periodo'],'septiembre de 2026')
            self.assertFalse(self.estado(self.jefe).json()['existe'])
            self.assertFalse(self.estado(fecha='2026-10-01').json()['existe'])

    def test_post_duplicado_dia_distinto_mismo_mes_sin_efectos(self):
        self.salario()
        response=self.client.post(reverse('crear_liquidacion'),self.datos())
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Ya existe una liquidación para este empleado en el período seleccionado.')
        self.assertNotContains(response,'IntegrityError')
        self.assertEqual(Salario.objects.count(),1)
        self.assertFalse(Notificacion.objects.exists())

    def test_restriccion_mensual_base_de_datos_permanece(self):
        self.salario()
        with self.assertRaises(IntegrityError),transaction.atomic():
            self.salario(mes_ano=date(2026,9,27))

    def test_colision_despues_de_validar_muestra_error_amigable(self):
        original=NominaForm.is_valid
        def validar_y_simular_otra_peticion(form):
            valido=original(form)
            if valido:self.salario()
            return valido
        with patch.object(NominaForm,'is_valid',validar_y_simular_otra_peticion):
            response=self.client.post(reverse('crear_liquidacion'),self.datos())
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Ya existe una liquidación para este empleado en el período seleccionado.')
        self.assertEqual(Salario.objects.count(),1)
        self.assertFalse(Notificacion.objects.exists())

    def test_endpoint_autorizacion_validacion_y_consultas_constantes(self):
        self.salario()
        cantidades=[]
        for empleado in [self.empleado,self.jefe]:
            with CaptureQueriesContext(connection) as consultas:
                response=self.estado(empleado)
            self.assertEqual(response.status_code,200)
            sql=[q['sql'] for q in consultas if 'FROM "personal_salario"' in q['sql']]
            self.assertEqual(len(sql),1)
            self.assertIn('LIMIT 1',sql[0])
            cantidades.append(len(consultas))
        self.assertEqual(cantidades[0],cantidades[1])
        self.assertEqual(self.estado(fecha='2026-02-30').status_code,400)
        self.assertEqual(self.client.post(reverse('estado_liquidacion')).status_code,405)
        admin=User.objects.create_superuser('admin',password='prueba')
        self.client.force_login(admin)
        self.assertEqual(self.estado().status_code,200)
        self.client.logout()
        self.assertEqual(self.estado().status_code,302)
