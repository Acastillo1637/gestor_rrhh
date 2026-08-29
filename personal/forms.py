from django import forms
from .models import Empleado


class EmpleadoForm(forms.ModelForm):
    class Meta:
        model = Empleado
        fields = [
            'nombre_completo',
            'cargo',
            'salario_mensual',
            'esta_activo',
        ]

        widgets = {
            'nombre_completo': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'cargo': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'salario_mensual': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'esta_activo': forms.CheckboxInput(),
        }