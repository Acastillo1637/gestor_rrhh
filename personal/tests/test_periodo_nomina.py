from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..forms import NominaForm
from ..models import Empleado, Salario


class PeriodoNominaTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_superuser('admin_periodo', password='prueba')
        self.client.force_login(self.usuario)
        self.empleado = Empleado.objects.create(nombre_completo='Empleado de prueba')

    def test_get_mes_local_y_cambio_de_anio(self):
        for hoy in [date(2026,9,27), date(2026,10,1), date(2026,12,31), date(2027,1,1)]:
            with self.subTest(hoy=hoy), patch('personal.forms.timezone.localdate', return_value=hoy):
                response = self.client.get(reverse('crear_liquidacion'))
                self.assertEqual(response.context['formulario'].initial['mes_ano'], hoy.replace(day=1))
                self.assertContains(response, f'value="{hoy.replace(day=1).isoformat()}"')
                self.assertFalse(response.context['formulario'].fields['mes_ano'].disabled)

    def test_post_invalido_conserva_periodo_manual(self):
        response = self.client.post(reverse('crear_liquidacion'), {
            'empleado': self.empleado.pk, 'mes_ano': '2026-07-15',
            'salario_base': 'invalido', 'bonificacion': 0, 'descuentos': 0,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['formulario']['mes_ano'].value(), '2026-07-15')
        self.assertFalse(Salario.objects.exists())

    def test_periodo_manual_se_guarda(self):
        response = self.client.post(reverse('crear_liquidacion'), {
            'empleado': self.empleado.pk, 'mes_ano': '2026-07-15',
            'salario_base': 1000000, 'bonificacion': 0, 'descuentos': 0,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Salario.objects.get().mes_ano, date(2026,7,15))

    def test_no_sobrescribe_instancia_ni_initial_explicito(self):
        fecha = date(2025,5,1)
        registro = Salario.objects.create(empleado=self.empleado, mes_ano=fecha, salario_base=1000000)
        self.assertEqual(NominaForm(instance=registro).initial['mes_ano'], fecha)
        self.assertEqual(NominaForm(initial={'mes_ano': fecha}).initial['mes_ano'], fecha)
