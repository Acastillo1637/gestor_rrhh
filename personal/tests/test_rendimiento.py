from datetime import date, timedelta
from urllib.parse import parse_qs

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..autorizacion_permisos import preparar_acciones_permisos, puede_resolver_permiso
from ..models import Departamento, Empleado, EmpleadoPuesto, Puesto, Permiso, Asistencia, Salario
from ..rendimiento import roles_en_request, roles_usuario


class ListadosRendimientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('rrhh_demo')
        cls.user.groups.add(Group.objects.create(name='RRHH'))
        cls.empleado = Empleado.objects.create(nombre_completo='Persona Prueba', departamento='Tecnologia')
        cls.otro = Empleado.objects.create(nombre_completo='Otra Persona', departamento='Operaciones')
        cls.inicio = date(2020, 1, 1)
        Permiso.objects.bulk_create([
            Permiso(empleado=cls.empleado, tipo='medico', fecha_inicio=cls.inicio+timedelta(days=i),
                    fecha_fin=cls.inicio+timedelta(days=i), estado='pendiente') for i in range(110)])
        Asistencia.objects.bulk_create([
            Asistencia(empleado=cls.empleado, fecha=cls.inicio+timedelta(days=i), estado='permiso')
            for i in range(110)])
        Salario.objects.bulk_create([
            Salario(empleado=cls.empleado, mes_ano=date(2010+i//12, i%12+1, 1),
                    salario_base=1000000, neto=1000000, pagado=i%2 == 0) for i in range(110)])

    def setUp(self):
        self.client.force_login(self.user)

    def get(self, vista, **params):
        if vista == 'gestion_asistencia':
            params = dict(fecha_desde='2020-01-01', fecha_hasta='2021-01-01', **params)
        return self.client.get(reverse(vista), params)

    def test_limites_lista_cerrada_y_metricas_globales(self):
        for vista in ['gestion_permisos', 'gestion_asistencia', 'gestion_nomina']:
            for valor, limite in [(None,10),('10',10),('25',25),('50',50),('100',100),
                                  ('0',10),('-1',10),('999999',10),('abc',10)]:
                with self.subTest(vista=vista,valor=valor):
                    response = self.get(vista, **({'por_pagina':valor} if valor else {}))
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(len(response.context['pagina']),limite)
                    self.assertEqual(response.context['pagina'].paginator.count,110)
                    self.assertContains(response,f'value="{limite}" selected')
                    if vista == 'gestion_nomina':
                        self.assertEqual(response.context['total_liquidaciones'],110)
                        self.assertEqual(response.context['total_pagadas'],55)
                        self.assertEqual(response.context['total_neto'],110000000)
                        self.assertContains(response,'1.000.000')
                    if vista == 'gestion_permisos':
                        self.assertEqual(response.context['total_permisos'],110)
                        self.assertEqual(response.context['total_pendientes'],110)

    def test_paginas_disjuntas_y_fuera_de_rango(self):
        for vista in ['gestion_permisos','gestion_asistencia','gestion_nomina']:
            primero=self.get(vista).context['pagina']
            segundo=self.get(vista,page=2).context['pagina']
            self.assertFalse({r.pk for r in primero}&{r.pk for r in segundo})
            self.assertEqual(self.get(vista,page='invalido').context['pagina'].number,1)
            self.assertEqual(self.get(vista,page='999999').context['pagina'].number,11)

    def test_filtros_y_selector_conservan_parametros_sin_page(self):
        for vista in ['gestion_permisos','gestion_asistencia','gestion_nomina']:
            response=self.get(vista,page=2,por_pagina=25,busqueda='Persona',orden='existente')
            filtros=parse_qs(response.context['filtros_pagina'])
            self.assertEqual(filtros['por_pagina'],['25'])
            self.assertEqual(filtros['busqueda'],['Persona'])
            self.assertEqual(filtros['orden'],['existente'])
            self.assertNotIn('page',filtros)
            selector=dict(response.context['filtros_selector'])
            self.assertNotIn('page',selector)
            self.assertNotIn('por_pagina',selector)
            self.assertContains(response,'this.form.requestSubmit()')
            selector['por_pagina']='50'
            # Submit the selector's actual fields: page is deliberately absent.
            reset=self.client.get(reverse(vista),selector)
            self.assertEqual(reset.context['pagina'].number,1)

    def test_asistencia_filtra_antes_de_limitar_y_consulta_permisos_en_lote(self):
        primero=Permiso.objects.create(empleado=self.empleado,tipo='vacaciones',estado='aprobado',
            fecha_inicio=self.inicio,fecha_fin=date(2021,1,1))
        Permiso.objects.create(empleado=self.empleado,tipo='medico',estado='aprobado',
            fecha_inicio=self.inicio,fecha_fin=date(2021,1,1))
        Asistencia.objects.create(empleado=self.otro,fecha=self.inicio)
        for size in [10,100]:
            with CaptureQueriesContext(connection) as queries:
                response=self.get('gestion_asistencia',por_pagina=size,empleado=self.empleado.pk,
                                  departamento='Tecnologia')
            select_asistencia=[q['sql'] for q in queries if 'FROM "personal_asistencia"' in q['sql'] and 'COUNT(' not in q['sql']]
            self.assertEqual(len(select_asistencia),1)
            self.assertIn(f'LIMIT {size}',select_asistencia[0])
            permisos=[q for q in queries if 'FROM "personal_permiso"' in q['sql']]
            self.assertEqual(len(permisos),1)
            self.assertTrue(all(a.motivo_permiso==primero.get_tipo_display() for a in response.context['pagina']))
            self.assertTrue(all(a.empleado_id==self.empleado.pk for a in response.context['pagina']))
        response=self.client.get(reverse('gestion_asistencia'),{'fecha_desde':'2020-01-01','fecha_hasta':'2020-01-02','empleado':self.empleado.pk})
        self.assertEqual(len(response.context['pagina']),2)

    def test_nomina_filtros_orden_y_acciones(self):
        response=self.get('gestion_nomina',busqueda='Persona Prueba',estado_pago='pendiente',por_pagina=25)
        pagina=response.context['pagina']
        self.assertEqual(pagina.paginator.count,55)
        self.assertEqual(response.context['total_neto'],55000000)
        self.assertTrue(all(not r.pagado for r in pagina))
        self.assertEqual([r.mes_ano for r in pagina],sorted([r.mes_ano for r in pagina],reverse=True))
        self.assertContains(response,reverse('marcar_liquidacion_pagada',args=[pagina[0].pk]))
        self.assertEqual(self.get('gestion_nomina',busqueda='NoExiste').context['pagina'].paginator.count,0)

    def test_permisos_filtrados_y_consultas_acotadas(self):
        for size in [10,100]:
            with CaptureQueriesContext(connection) as queries:
                response=self.get('gestion_permisos',por_pagina=size,tipo='medico',estado='pendiente',busqueda='Persona')
            self.assertLessEqual(len(queries),12)
            self.assertTrue(all(p.puede_resolver for p in response.context['pagina']))
        self.assertEqual(self.get('gestion_permisos',estado='rechazado').context['pagina'].paginator.count,0)


class AutorizacionLoteTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('gerente')
        self.user.groups.add(Group.objects.create(name='GERENTES'))
        self.depto=Departamento.objects.create(nombre='Tecnologia')
        self.puesto=Puesto.objects.create(nombre='Cargo',departamento=self.depto,nivel='senior',salario_base=1000)
        self.jefe=Empleado.objects.create(nombre_completo='Jefe',usuario=self.user)
        self.local=Empleado.objects.create(nombre_completo='Local')
        self.depto.jefe=self.jefe; self.depto.save()
        for e in [self.jefe,self.local]:
            EmpleadoPuesto.objects.create(empleado=e,puesto=self.puesto,fecha_inicio=date(2020,1,1))
        self.permiso=Permiso.objects.create(empleado=self.local,tipo='medico',fecha_inicio=date(2026,1,1),fecha_fin=date(2026,1,1))

    def decision(self,esperado):
        user=User.objects.get(pk=self.user.pk)
        permiso=Permiso.objects.select_related('empleado').get(pk=self.permiso.pk)
        preparar_acciones_permisos(user,[permiso])
        self.assertEqual(permiso.puede_resolver,esperado)
        self.assertEqual(puede_resolver_permiso(user,permiso),esperado)

    def test_lote_conserva_decisiones_seguras(self):
        self.decision(True)
        self.permiso.empleado=self.jefe; self.permiso.save(); self.decision(False)
        self.permiso.empleado=self.local; self.permiso.save()
        self.depto.jefe=None; self.depto.save(); self.decision(False)
        self.depto.jefe=self.jefe; self.depto.save()
        self.jefe.estado_laboral='renuncio'; self.jefe.save(); self.decision(False)
        self.jefe.estado_laboral='activo'; self.jefe.save()
        self.jefe.usuario=None; self.jefe.save(); self.decision(False)

    def test_puesto_ambiguo_ausente_futuro_o_cerrado(self):
        for empleado in [self.jefe,self.local]:
            actual=empleado.historial_puestos.get()
            extra=EmpleadoPuesto.objects.create(empleado=empleado,puesto=self.puesto,fecha_inicio=date(2020,1,1))
            self.decision(False); extra.delete()
            actual.fecha_fin=date(2025,1,1); actual.save(); self.decision(False)
            actual.fecha_fin=None; actual.fecha_inicio=date(2099,1,1); actual.save(); self.decision(False)
            actual.fecha_inicio=date(2020,1,1); actual.es_actual=False; actual.save(); self.decision(False)
            actual.es_actual=True; actual.save(); self.decision(True)

    def test_otro_departamento_rrhh_superusuario_y_procesados(self):
        otro=Departamento.objects.create(nombre='Otro')
        puesto=Puesto.objects.create(nombre='Otro',departamento=otro,nivel='senior',salario_base=1000)
        self.local.historial_puestos.update(puesto=puesto)
        self.decision(False)
        self.user.groups.add(Group.objects.create(name='RRHH')); self.decision(True)
        self.user.groups.clear(); self.user.is_superuser=True; self.user.save(); self.decision(True)
        for estado in ['aprobado','rechazado']:
            self.permiso.estado=estado
            preparar_acciones_permisos(self.user,[self.permiso])
            self.assertFalse(self.permiso.puede_resolver)

    def test_consultas_lote_constantes_y_cache_solo_request(self):
        permisos=[self.permiso]*100
        with CaptureQueriesContext(connection) as queries:
            preparar_acciones_permisos(User.objects.get(pk=self.user.pk),permisos)
        self.assertLessEqual(len(queries),4)
        request=RequestFactory().get('/'); request.user=self.user
        @roles_en_request
        def view(request):
            return roles_usuario(request.user)
        self.assertIn('GERENTES',view(request))
        self.assertFalse(hasattr(self.user,'_roles_del_request'))
        self.user.groups.clear()
        self.assertNotIn('GERENTES',view(request))
