from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..forms import CrearEmpleadoForm, EditarEmpleadoForm
from ..models import Departamento, Empleado, Puesto


class AltaEmpleadoTests(TestCase):
    def setUp(self):
        self.depto = Departamento.objects.create(nombre='Tecnologia')
        self.otro = Departamento.objects.create(nombre='Operaciones')
        self.vacio = Departamento.objects.create(nombre='Sin cargos')
        Puesto.objects.create(nombre='Desarrollo', departamento=self.depto, salario_base=1000)
        Puesto.objects.create(nombre='Operador', departamento=self.otro, salario_base=1000)
        self.client.force_login(User.objects.create_user('admin_alta', is_superuser=True))
        self.datos = dict(nombre='Ana', apellido_paterno='Perez', apellido_materno='Soto',
                          departamento=self.depto.nombre, cargo='Desarrollo', salario_mensual=1000,
                          fecha_contratacion='2020-03-04', estado_laboral='activo')

    def test_fecha_local_inicial(self):
        with patch('personal.forms.timezone.localdate', return_value=date(2026, 9, 27)):
            respuesta = self.client.get(reverse('crear_empleado'))
        self.assertEqual(respuesta.context['formulario'].initial['fecha_contratacion'], date(2026, 9, 27))

    def test_fecha_elegida_se_guarda(self):
        self.assertEqual(self.client.post(reverse('crear_empleado'), self.datos).status_code, 302)
        self.assertEqual(Empleado.objects.get(nombre_completo='Ana Perez Soto').fecha_contratacion, date(2020, 3, 4))

    def test_post_invalido_conserva_fecha(self):
        respuesta = self.client.post(reverse('crear_empleado'), dict(self.datos, nombre=''))
        self.assertEqual(respuesta.context['formulario']['fecha_contratacion'].value(), '2020-03-04')

    def test_edicion_conserva_fecha_estado_y_cargos(self):
        empleado = Empleado.objects.create(nombre_completo='Ana Perez Soto', fecha_contratacion=date(2020, 3, 4), estado_laboral='renuncio')
        form = EditarEmpleadoForm(instance=empleado)
        self.assertEqual(form.initial['fecha_contratacion'], date(2020, 3, 4))
        self.assertFalse(form.fields['estado_laboral'].disabled)
        self.assertNotIn('disabled', form.fields['cargo'].widget.attrs)
        self.assertIn(('Operador', 'Operador'), form.fields['cargo'].choices)

    def test_cargo_inicial_deshabilitado(self):
        form = CrearEmpleadoForm()
        self.assertTrue(form.fields['cargo'].widget.attrs['disabled'])
        self.assertEqual([valor for valor, _ in form.fields['cargo'].choices], [''])

    def test_endpoint_solo_cargos_del_departamento(self):
        respuesta = self.client.get(reverse('obtener_puestos_por_departamento'), {'departamento_id': self.depto.pk})
        self.assertEqual([p['nombre'] for p in respuesta.json()], ['Desarrollo'])

    def test_cargo_ajeno_y_cambio_departamento(self):
        for datos in [dict(self.datos, cargo='Operador'), dict(self.datos, departamento=self.otro.nombre)]:
            form = CrearEmpleadoForm(datos)
            self.assertFalse(form.is_valid())
            self.assertIn('cargo', form.errors)
            antes = Empleado.objects.count()
            self.assertEqual(self.client.post(reverse('crear_empleado'), datos).status_code, 200)
            self.assertEqual(Empleado.objects.count(), antes)

    def test_departamento_sin_cargos(self):
        form = CrearEmpleadoForm(dict(self.datos, departamento=self.vacio.nombre))
        self.assertFalse(form.is_valid())
        self.assertTrue(form.fields['cargo'].widget.attrs['disabled'])
        self.assertIn('no tiene cargos', str(form['cargo']))

    def test_estado_forzado_activo(self):
        for estado in ['activo', 'despedido', 'renuncio', 'renunciado', 'inventado']:
            self.assertEqual(self.client.post(reverse('crear_empleado'), dict(self.datos, estado_laboral=estado)).status_code, 302)
        creados = Empleado.objects.filter(nombre_completo='Ana Perez Soto')
        self.assertEqual(creados.count(), 5)
        self.assertFalse(creados.exclude(estado_laboral='activo').exists())
