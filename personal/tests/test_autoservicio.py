from datetime import date, timedelta
from urllib.parse import parse_qs

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..models import Asistencia, Empleado, Evaluacion, Permiso, Salario


class AutoservicioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {}
        for rol in ['RRHH', 'GERENTES', 'EMPLEADO']:
            user = User.objects.create_user(rol.lower())
            user.groups.add(Group.objects.create(name=rol))
            empleado = Empleado.objects.create(usuario=user, nombre_completo=rol, estado_laboral='activo')
            cls.usuarios[rol] = user
            Asistencia.objects.bulk_create([Asistencia(empleado=empleado, fecha=date(2020,1,1)+timedelta(days=i)) for i in range(110)])
            Permiso.objects.bulk_create([Permiso(empleado=empleado, tipo='vacaciones',
                fecha_inicio=date(2020,1,1), fecha_fin=date(2020,1,2)) for _ in range(110)])
            Salario.objects.bulk_create([Salario(empleado=empleado, mes_ano=date(2010+i//12,i%12+1,1), salario_base=1000) for i in range(110)])
            Evaluacion.objects.create(empleado=empleado, periodo='2026 - Primer semestre', puntuacion=5)
        cls.tecnico = User.objects.create_user('tecnico_sin_ficha')
        cls.tecnico.groups.add(Group.objects.get(name='RRHH'))

    listados = [('mi_asistencia', Asistencia, '-fecha'),
                ('mis_permisos', Permiso, '-fecha_inicio'),
                ('mis_liquidaciones', Salario, '-mes_ano')]

    def test_rrhh_navegacion_y_gestion(self):
        self.client.force_login(self.usuarios['RRHH'])
        response = self.client.get(reverse('dashboard_gestion'))
        self.assertEqual(response.status_code, 200)
        for vista in ['mi_asistencia','mis_permisos','solicitar_permiso','mis_liquidaciones','mis_evaluaciones','crear_empleado','gestion_permisos']:
            self.assertContains(response, reverse(vista))
        self.assertContains(response, 'Autoservicio personal')

    def test_sin_ficha_y_ficha_inactiva(self):
        self.client.force_login(self.tecnico)
        response = self.client.get(reverse('dashboard_gestion'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Autoservicio personal')
        for vista in ['mi_asistencia','mis_permisos','solicitar_permiso','mis_liquidaciones','mis_evaluaciones']:
            self.assertNotContains(response, reverse(vista))
            self.assertEqual(self.client.get(reverse(vista)).status_code, 403)
        empleado = self.usuarios['RRHH'].empleado
        empleado.estado_laboral = 'renuncio'
        empleado.save()
        self.client.force_login(self.usuarios['RRHH'])
        self.assertNotContains(self.client.get(reverse('dashboard_gestion')), 'Autoservicio personal')
        self.assertEqual(self.client.post(reverse('mi_asistencia'), {'accion':'entrada'}).status_code,403)

    def test_paginacion_tamanos_invalidos_y_aislamiento_por_rol(self):
        for rol, user in self.usuarios.items():
            self.client.force_login(user)
            for vista, modelo, orden in self.listados:
                for valor, tamano in [(None,10),('25',25),('50',50),('100',100),('0',10),('-1',10),('abc',10),('999999',10)]:
                    with self.subTest(rol=rol,vista=vista,valor=valor):
                        params = {'empleado':self.tecnico.pk, 'usuario':self.tecnico.pk}
                        if valor is not None: params['por_pagina'] = valor
                        response = self.client.get(reverse(vista), params)
                        pagina = response.context['pagina']
                        self.assertEqual(pagina.paginator.count,110)
                        self.assertEqual(len(pagina),tamano)
                        self.assertTrue(all(r.empleado_id == user.empleado.pk for r in pagina))
                        self.assertTemplateUsed(response,'includes/listado_paginacion.html')

    def test_orden_navegacion_y_selector(self):
        user = self.usuarios['RRHH']
        self.client.force_login(user)
        for vista, modelo, orden in self.listados:
            esperado = list(modelo.objects.filter(empleado=user.empleado).order_by(orden,'-pk').values_list('pk',flat=True))
            primero = self.client.get(reverse(vista)).context['pagina']
            response = self.client.get(reverse(vista), {'page':2,'por_pagina':10,'orden':'reciente'})
            self.assertEqual([r.pk for r in primero]+[r.pk for r in response.context['pagina']],esperado[:20])
            self.assertEqual(parse_qs(response.context['filtros_pagina'])['por_pagina'],['10'])
            campos = dict(response.context['filtros_selector'])
            self.assertNotIn('page',campos)
            self.assertEqual(campos['orden'],'reciente')
            campos['por_pagina'] = '25'
            self.assertEqual(self.client.get(reverse(vista),campos).context['pagina'].number,1)

    def test_limit_sql_y_consultas_constantes(self):
        self.client.force_login(self.usuarios['RRHH'])
        for vista, modelo, orden in self.listados:
            cantidades = []
            for size in [10,25,50,100]:
                with CaptureQueriesContext(connection) as consultas:
                    response = self.client.get(reverse(vista), {'por_pagina':size})
                cantidades.append(len(consultas))
                selects = [q['sql'] for q in consultas if f'FROM "{modelo._meta.db_table}"' in q['sql'] and 'COUNT(' not in q['sql']]
                self.assertTrue(any(f'LIMIT {size}' in sql for sql in selects))
                self.assertTrue(all('LIMIT ' in sql for sql in selects))
                self.assertEqual(len(response.context['pagina']),size)
            self.assertEqual(len(set(cantidades)),1)

    def test_post_rrhh_no_puede_suplantar_empleado(self):
        user = self.usuarios['RRHH']
        otro = self.usuarios['EMPLEADO'].empleado
        self.client.force_login(user)
        for accion in ['entrada','salida']:
            self.assertEqual(self.client.post(reverse('mi_asistencia'), {'accion':accion,'empleado':otro.pk}).status_code,302)
        self.assertEqual(Asistencia.objects.filter(empleado=user.empleado).count(),111)
        self.assertEqual(Asistencia.objects.filter(empleado=otro).count(),110)
        response = self.client.post(reverse('solicitar_permiso'), {'empleado':otro.pk,
            'tipo':'vacaciones','fecha_inicio':'2030-01-01','fecha_fin':'2030-01-02'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Permiso.objects.latest('pk').empleado_id,user.empleado.pk)

    def test_evaluaciones_personales_y_detalle_aislados(self):
        for user in self.usuarios.values():
            self.client.force_login(user)
            response = self.client.get(reverse('mis_evaluaciones'), {'empleado':self.tecnico.pk})
            self.assertTrue(all(e.empleado_id==user.empleado.pk for e in response.context['pagina']))
            for evaluacion in Evaluacion.objects.all():
                code = 200 if evaluacion.empleado_id == user.empleado.pk else 404
                self.assertEqual(self.client.get(reverse('mi_evaluacion',args=[evaluacion.pk])).status_code,code)
