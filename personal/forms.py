# -----------------------------------------------------------------------------
# Formulario ModelForm usado para crear y editar empleados.
# -----------------------------------------------------------------------------

from django import forms
from .models import Empleado, Departamento, Puesto


class EmpleadoForm(forms.ModelForm):

    class Meta:
        model = Empleado

        fields = [
            'nombre_completo',
            'cargo',
            'departamento',
            'salario_mensual',
            'estado_laboral',
        ]

        widgets = {
            'nombre_completo': forms.TextInput(attrs={
                'class': 'form-control',
            }),

            'salario_mensual': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
            }),

            'estado_laboral': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Lista de departamentos registrados en la base de datos.
        departamentos = Departamento.objects.order_by('nombre')

        self.fields['departamento'] = forms.ChoiceField(
            choices=[
                ('', 'Seleccione un departamento')
            ] + [
                (departamento.nombre, departamento.nombre)
                for departamento in departamentos
            ],
            widget=forms.Select(attrs={
                'class': 'form-control'
            })
        )

        # Lista de puestos registrados en la base de datos.
        puestos = Puesto.objects.select_related(
            'departamento'
        ).order_by(
            'departamento__nombre',
            'nombre'
        )

        self.fields['cargo'] = forms.ChoiceField(
            choices=[
                ('', 'Seleccione un cargo')
            ] + [
                (
                    puesto.nombre,
                    f'{puesto.nombre} - {puesto.departamento.nombre}'
                )
                for puesto in puestos
            ],
            widget=forms.Select(attrs={
                'class': 'form-control'
            })
        )