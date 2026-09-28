from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from ..forms import NominaForm
from ..models import Empleado, Salario


class SalarioActualTests(TestCase):
    def setUp(self):
        self.fecha = patch('django.utils.timezone.localdate', return_value=date(2026, 9, 27))
        self.fecha.start()
        self.addCleanup(self.fecha.stop)
        self.empleado = Empleado.objects.create(nombre_completo='Ana Prueba', salario_mensual=1400000)
        self.otro = Empleado.objects.create(nombre_completo='Otro Prueba', salario_mensual=1700000)
        self.client.force_login(User.objects.create_superuser('admin_salario', password='test'))

    def datos(self, **extra):
        datos = dict(empleado=self.empleado.pk, mes_ano='2026-09-01', salario_base='1', bonificacion='0', descuentos='0')
        datos.update(extra)
        return datos

    def estado(self, **extra):
        return self.client.get(reverse('estado_liquidacion'), self.datos(**extra))

    def test_endpoint_importe_formato_y_cambio_empleado(self):
        for empleado, valor, formato in [(self.empleado,'1400000.00','$1.400.000'), (self.otro,'1700000.00','$1.700.000')]:
            data = self.estado(empleado=empleado.pk).json()
            self.assertEqual(data['modo_salario'], 'actual')
            self.assertEqual(data['salario_base'], valor)
            self.assertEqual(data['salario_formateado'], formato)

    def test_transicion_periodos_no_expone_salario_fuera_mes_actual(self):
        for fecha, modo in [('2026-08-01','historico'), ('2026-09-30','actual'), ('2026-10-01','futuro'), ('2025-09-01','historico')]:
            data = self.estado(mes_ano=fecha).json()
            self.assertEqual(data['modo_salario'], modo)
            if modo != 'actual':
                self.assertIsNone(data['salario_base'])

    def test_post_manipulado_ignorado_incluso_ausente_o_invalido(self):
        for valor in ['1', '-100', 'texto', '', '$1.400.000']:
            form = NominaForm(self.datos(salario_base=valor))
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.save(commit=False).salario_base, 1400000)
        datos = self.datos()
        del datos['salario_base']
        self.assertTrue(NominaForm(datos).is_valid())

    def test_guardado_real_backend(self):
        response = self.client.post(reverse('crear_liquidacion'), self.datos())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Salario.objects.get().salario_base, 1400000)

    def test_lectura_actualizada_al_validar(self):
        form = NominaForm(self.datos())
        Empleado.objects.filter(pk=self.empleado.pk).update(salario_mensual=1500000)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['salario_base'], 1500000)

    def test_historico_y_futuro_manuales(self):
        for fecha in ['2026-08-01','2026-10-01']:
            response = self.client.post(reverse('crear_liquidacion'), self.datos(mes_ano=fecha,salario_base='1234567'))
            self.assertEqual(response.status_code, 302)
            self.assertEqual(Salario.objects.get(mes_ano=fecha).salario_base, 1234567)

    def test_post_invalido_actual_muestra_importe_correcto(self):
        response = self.client.post(reverse('crear_liquidacion'), self.datos(bonificacion='-1'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '$1.400.000')
        self.assertContains(response, 'value="$1.400.000"')
        self.assertContains(response, 'class="form-control" readonly min="0" step="0.01"')
        self.assertTrue(response.context['formulario'].fields['salario_base'].disabled)
        self.assertFalse(Salario.objects.exists())

    def test_post_invalido_historico_conserva_importe(self):
        response = self.client.post(reverse('crear_liquidacion'), self.datos(mes_ano='2026-08-01',salario_base='1234567',bonificacion='-1'))
        form = response.context['formulario']
        self.assertFalse(form.fields['salario_base'].disabled)
        self.assertEqual(form['salario_base'].value(), '1234567')
        self.assertContains(response, 'Período histórico')

    def test_duplicados_pagados_y_pendientes(self):
        registro = Salario.objects.create(empleado=self.empleado,mes_ano=date(2026,9,1),salario_base=1400000)
        for pagado in [False, True]:
            registro.pagado = pagado
            registro.save()
            self.assertTrue(self.estado().json()['existe'])
            self.assertFalse(NominaForm(self.datos()).is_valid())

    def test_endpoint_consultas_constantes(self):
        with CaptureQueriesContext(connection) as antes:
            self.estado()
        Empleado.objects.bulk_create([Empleado(nombre_completo=f'Extra {i}') for i in range(30)])
        with CaptureQueriesContext(connection) as despues:
            self.estado()
        self.assertEqual(len(antes),len(despues))
        tablas = [q['sql'] for q in despues if 'FROM "personal_' in q['sql']]
        self.assertEqual(len(tablas), 2)

    def test_amaro_actual_pagado_respuesta_completa(self):
        self.empleado.nombre_completo = 'Amaro Castillo Ahumada'
        self.empleado.salario_mensual = 3825000
        self.empleado.save()
        Salario.objects.create(empleado=self.empleado, mes_ano=date(2026,9,1),
            salario_base=3825000, pagado=True)
        respuesta = self.estado()
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos['modo_salario'], 'actual')
        self.assertEqual(datos['salario_base'], '3825000.00')
        self.assertEqual(datos['salario_formateado'], '$3.825.000')
        self.assertTrue(datos['existe'])
        self.assertEqual(datos['estado'], 'Pagada')

    def test_pagina_entrega_script_actual_y_bloqueo_inicial(self):
        from html.parser import HTMLParser
        class BotonParser(HTMLParser):
            boton = None
            def handle_starttag(self, tag, attrs):
                atributos = dict(attrs)
                if tag == 'button' and atributos.get('id') == 'guardar-liquidacion':
                    self.boton = atributos
        response = self.client.get(reverse('crear_liquidacion'))
        parser = BotonParser()
        parser.feed(response.content.decode())
        self.assertIn('disabled', parser.boton)
        self.assertContains(response, '?v=salario-input-3')
        self.assertContains(response, 'name="salario_base" id="id_salario_base" class="form-control" readonly')
        self.assertNotContains(response, '<output id="salario-automatico"')
