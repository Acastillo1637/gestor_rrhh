from datetime import timedelta
from urllib.parse import parse_qs

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import Empleado, HistorialSalario


class HistorialPaginacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_user('rrhh_historial')
        cls.usuario.groups.add(Group.objects.create(name='RRHH'))
        cls.empleado = Empleado.objects.create(nombre_completo='Empleado Principal', dni='PRINCIPAL')
        cls.otro = Empleado.objects.create(nombre_completo='Empleado Secundario', dni='SECUNDARIO')
        HistorialSalario.objects.bulk_create([
            HistorialSalario(empleado=cls.empleado if i < 105 else cls.otro,
                            salario_anterior=1000000, salario_nuevo=1100000,
                            modificado_por='Operador Prueba') for i in range(120)
        ])
        # Empates deliberados para verificar el desempate estable por PK.
        cls.fecha = timezone.now()
        HistorialSalario.objects.update(fecha_modificacion=cls.fecha)

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse('historial_salarial')

    def test_tamanos_validos_invalidos_y_total_global(self):
        for valor, esperado in [(None, 10), ('10', 10), ('25', 25), ('50', 50), ('100', 100),
                                ('0', 10), ('-1', 10), ('abc', 10), ('999999', 10)]:
            with self.subTest(valor=valor):
                response = self.client.get(self.url, {'por_pagina': valor} if valor else {})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context['registros']), esperado)
                self.assertEqual(response.context['total_registros'], 120)
                self.assertContains(response, f'value="{esperado}" selected')
                self.assertTemplateUsed(response, 'includes/listado_paginacion.html')
                self.assertTemplateUsed(response, 'includes/listado_selector.html')

    def test_navegacion_orden_estable_y_paginas_invalidas(self):
        # La fecha sigue siendo el criterio principal, incluso frente al ID.
        antiguo = HistorialSalario.objects.order_by('pk').first()
        HistorialSalario.objects.filter(pk=antiguo.pk).update(fecha_modificacion=self.fecha + timedelta(days=1))
        esperados = list(HistorialSalario.objects.order_by('-fecha_modificacion', '-pk').values_list('pk', flat=True))
        ids = []
        for numero in [1, 2]:
            response = self.client.get(self.url, {'page': numero})
            ids.extend(r.pk for r in response.context['registros'])
        self.assertEqual(ids, esperados[:20])
        self.assertEqual(len(set(ids)), 20)
        self.assertEqual(self.client.get(self.url, {'page': 'abc'}).context['pagina'].number, 1)
        self.assertEqual(self.client.get(self.url, {'page': '99999'}).context['pagina'].number, 12)

    def test_filtros_en_enlaces_y_cambio_de_cantidad(self):
        params = {'busqueda': 'Operador Prueba', 'empleado': self.empleado.pk, 'por_pagina': 25, 'page': 2}
        response = self.client.get(self.url, params)
        self.assertEqual(response.context['total_registros'], 105)
        self.assertTrue(all(r.empleado_id == self.empleado.pk for r in response.context['registros']))
        filtros = parse_qs(response.context['filtros_pagina'])
        self.assertEqual(filtros, {'busqueda': ['Operador Prueba'], 'empleado': [str(self.empleado.pk)], 'por_pagina': ['25']})
        # El formulario del selector no envia page: el cambio vuelve a la primera.
        campos = dict(response.context['filtros_selector'])
        self.assertNotIn('page', campos)
        campos['por_pagina'] = '50'
        cambiado = self.client.get(self.url, campos)
        self.assertEqual(cambiado.context['pagina'].number, 1)
        self.assertEqual(len(cambiado.context['registros']), 50)
        self.assertEqual(cambiado.context['total_registros'], 105)
        self.assertContains(response, 'this.form.requestSubmit()')

    def test_busqueda_y_ruta_por_empleado(self):
        for busqueda in ['Empleado Secundario', 'SECUNDARIO']:
            response = self.client.get(self.url, {'busqueda': busqueda})
            self.assertEqual(response.context['total_registros'], 15)
        url = reverse('historial_salarial_empleado', args=[self.empleado.pk])
        response = self.client.get(url, {'empleado': self.otro.pk, 'por_pagina': 25, 'page': 2})
        self.assertEqual(response.context['total_registros'], 105)
        self.assertTrue(all(r.empleado_id == self.empleado.pk for r in response.context['registros']))
        self.assertEqual(self.client.get(self.url, {'busqueda': 'Inexistente'}).context['total_registros'], 0)

    def test_sql_paginado_sin_n_mas_uno(self):
        cantidades = []
        for size in [10, 25, 50, 100]:
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(self.url, {'por_pagina': size})
            cantidades.append(len(queries))
            selects = [q['sql'] for q in queries if 'FROM "personal_historialsalario"' in q['sql'] and 'COUNT(' not in q['sql']]
            self.assertEqual(len(selects), 1)
            self.assertIn(f'LIMIT {size}', selects[0])
            self.assertIn('JOIN "personal_empleado"', selects[0])
            self.assertEqual(len(response.context['registros']), size)
        self.assertEqual(len(set(cantidades)), 1)
