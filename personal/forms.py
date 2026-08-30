# -----------------------------------------------------------------------------
# Formulario ModelForm usado para crear y editar empleados desde la interfaz web.
# -----------------------------------------------------------------------------
from django import forms
from .models import Empleado


# Formulario basado directamente en el modelo Empleado.
class EmpleadoForm(forms.ModelForm):
    # Meta indica qué modelo y campos utilizará el formulario.
    class Meta:
        model = Empleado

        # Se muestran los campos necesarios para gestionar empleados, incluyendo el estado detallado.
        fields = [
            'nombre_completo',
            'cargo',
            'departamento',
            'salario_mensual',
            'estado_laboral',
        ]

        # Personaliza los controles HTML que Django generará para cada campo (fusionado en un solo diccionario).
        widgets = {
            'nombre_completo': forms.TextInput(attrs={
                'class': 'form-control',
            }),

            'cargo': forms.TextInput(attrs={
                'class': 'form-control',
            }),

            'departamento': forms.TextInput(attrs={
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