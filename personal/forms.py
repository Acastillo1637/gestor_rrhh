# -----------------------------------------------------------------------------
# Formularios del sistema de Recursos Humanos.
# -----------------------------------------------------------------------------

from django import forms

from .models import (
    Empleado,
    Departamento,
    Puesto,
    Permiso,
    Salario,
    Asistencia,
)


# =============================================================================
# EMPLEADO
# =============================================================================

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
            'nombre_completo': forms.TextInput(
                attrs={
                    'class': 'form-control',
                }
            ),

            'salario_mensual': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.01',
                }
            ),

            'estado_laboral': forms.Select(
                attrs={
                    'class': 'form-control'
                }
            ),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        departamentos = (
            Departamento.objects
            .order_by('nombre')
        )

        self.fields['departamento'] = forms.ChoiceField(
            choices=[
                (
                    '',
                    'Seleccione un departamento'
                )
            ] + [
                (
                    departamento.nombre,
                    departamento.nombre
                )
                for departamento in departamentos
            ],
            widget=forms.Select(
                attrs={
                    'class': 'form-control'
                }
            )
        )

        puestos = (
            Puesto.objects
            .select_related('departamento')
            .order_by(
                'departamento__nombre',
                'nombre'
            )
        )

        self.fields['cargo'] = forms.ChoiceField(
            choices=[
                (
                    '',
                    'Seleccione un cargo'
                )
            ] + [
                (
                    puesto.nombre,
                    (
                        f'{puesto.nombre} - '
                        f'{puesto.departamento.nombre}'
                    )
                )
                for puesto in puestos
            ],
            widget=forms.Select(
                attrs={
                    'class': 'form-control'
                }
            )
        )


# =============================================================================
# PERMISOS
# =============================================================================

class PermisoForm(forms.ModelForm):

    class Meta:
        model = Permiso

        fields = [
            'tipo',
            'fecha_inicio',
            'fecha_fin',
        ]

        widgets = {

            'tipo': forms.Select(
                attrs={
                    'class': 'form-control',
                }
            ),

            'fecha_inicio': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                }
            ),

            'fecha_fin': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                }
            ),
        }

        labels = {
            'tipo': 'Tipo de permiso',
            'fecha_inicio': 'Fecha de inicio',
            'fecha_fin': 'Fecha de término',
        }

    def clean(self):

        cleaned_data = super().clean()

        fecha_inicio = cleaned_data.get(
            'fecha_inicio'
        )

        fecha_fin = cleaned_data.get(
            'fecha_fin'
        )

        if (
            fecha_inicio
            and fecha_fin
            and fecha_fin < fecha_inicio
        ):

            raise forms.ValidationError(
                (
                    'La fecha de término no puede ser '
                    'anterior a la fecha de inicio.'
                )
            )

        return cleaned_data

    def save(self, commit=True):

        permiso = super().save(
            commit=False
        )

        if (
            permiso.fecha_inicio
            and permiso.fecha_fin
        ):

            diferencia = (
                permiso.fecha_fin
                - permiso.fecha_inicio
            )

            permiso.dias = (
                diferencia.days + 1
            )

        if not permiso.pk:

            permiso.estado = 'pendiente'
            permiso.aprobado = False

        if commit:

            permiso.save()

        return permiso


# =============================================================================
# NÓMINA / LIQUIDACIONES
# =============================================================================

class NominaForm(forms.ModelForm):

    class Meta:
        model = Salario

        fields = [
            'empleado',
            'mes_ano',
            'salario_base',
            'bonificacion',
            'descuentos',
            'pagado',
        ]

        widgets = {

            'empleado': forms.Select(
                attrs={
                    'class': 'form-control',
                }
            ),

            'mes_ano': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                }
            ),

            'salario_base': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.01',
                    'min': '0',
                }
            ),

            'bonificacion': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.01',
                    'min': '0',
                }
            ),

            'descuentos': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.01',
                    'min': '0',
                }
            ),

            'pagado': forms.CheckboxInput(
                attrs={
                    'class': 'form-check-input',
                }
            ),
        }

        labels = {
            'empleado': 'Empleado',
            'mes_ano': 'Periodo',
            'salario_base': 'Salario base',
            'bonificacion': 'Bonificación',
            'descuentos': 'Descuentos',
            'pagado': 'Marcar como pagado',
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields['empleado'].queryset = (
            Empleado.objects
            .filter(
                estado_laboral__iexact='activo'
            )
            .order_by(
                'nombre_completo'
            )
        )

# =============================================================================
# ASISTENCIA
# =============================================================================

class AsistenciaForm(forms.ModelForm):

    class Meta:
        model = Asistencia

        fields = [
            'empleado',
            'fecha',
            'hora_entrada',
            'hora_salida',
        ]

        widgets = {
            'empleado': forms.Select(
                attrs={
                    'class': 'form-control',
                }
            ),

            'fecha': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date',
                }
            ),

            'hora_entrada': forms.TimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'time',
                }
            ),

            'hora_salida': forms.TimeInput(
                attrs={
                    'class': 'form-control',
                    'type': 'time',
                }
            ),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields['empleado'].queryset = (
            Empleado.objects
            .filter(estado_laboral__iexact='activo')
            .order_by('nombre_completo')
        )

    def clean(self):

        cleaned_data = super().clean()

        hora_entrada = cleaned_data.get('hora_entrada')
        hora_salida = cleaned_data.get('hora_salida')

        if (
            hora_entrada
            and hora_salida
            and hora_salida <= hora_entrada
        ):
            raise forms.ValidationError(
                'La hora de salida debe ser posterior a la hora de entrada.'
            )

        return cleaned_data
