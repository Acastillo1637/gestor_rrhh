# -----------------------------------------------------------------------------
# Formularios del sistema de Recursos Humanos.
# -----------------------------------------------------------------------------

from django import forms
from django.core.exceptions import NON_FIELD_ERRORS
from django.utils import timezone

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
            'fecha_contratacion',
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
                    'min': '0',
                }
            ),

            # HTML date requiere ISO; el formato local deja el campo vacío al editar.
            'fecha_contratacion': forms.DateInput(
                format='%Y-%m-%d',
                attrs={
                    'class': 'form-control',
                    'type': 'date',
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


    def clean(self):
        datos = super().clean()
        importe = datos.get('salario_mensual')
        if importe is not None and importe < 0:
            self.add_error('salario_mensual', 'El importe debe ser superior o igual a 0.')
        return datos


class NombreEmpleadoForm(forms.ModelForm):
    """Campos y validación de nombre compartidos por el portal y el admin."""

    # required=True y strip=True rechazan vacíos y valores formados solo por espacios.
    # pattern hace una comprobación equivalente en el navegador; Django valida igualmente el POST.
    nombres = forms.CharField(
        label='Nombres', required=True, strip=True, max_length=150,
        error_messages={'required': 'Ingresa los nombres del empleado.'},
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'autocomplete': 'given-name',
            'pattern': r'.*\S.*', 'data-name-part': 'nombres',
            'aria-describedby': 'nombres-errors',
        }),
    )
    apellidos = forms.CharField(
        label='Apellidos', required=True, strip=True, max_length=150,
        error_messages={'required': 'Ingresa los apellidos del empleado.'},
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'autocomplete': 'family-name',
            'pattern': r'.*\S.*', 'data-name-part': 'apellidos',
            'aria-describedby': 'apellidos-errors',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Portal y admin exigen la fecha, conservando sus widgets y las fechas antiguas.
        # El modelo permite nulos para no modificar registros existentes ni requerir migraciones.
        fecha = self.fields['fecha_contratacion']
        fecha.required = True
        fecha.error_messages['required'] = 'Ingresa la fecha de contratación.'

    def clean(self):
        datos = super().clean()
        nombres = datos.get('nombres')
        apellidos = datos.get('apellidos')
        if nombres and apellidos:

            completo = ' '.join((nombres + ' ' + apellidos).split())
            campo = Empleado._meta.get_field('nombre_completo')
            try:
                completo = campo.clean(completo, self.instance)
            except forms.ValidationError:
                self.add_error('apellidos',
                    f'Los nombres y apellidos juntos no pueden superar {campo.max_length} caracteres.')
            else:
                self.instance.nombre_completo = completo
        return datos


    def precargar_nombre(self):
        """Propuesta editable: el modelo no conserva dónde se separó el nombre."""
        if not self.is_bound and self.instance.pk:
            partes = self.instance.nombre_completo.strip().split(maxsplit=1)
            self.initial.setdefault('nombres', partes[0] if partes else '')
            self.initial.setdefault('apellidos', partes[1] if len(partes) > 1 else '')


class CrearEmpleadoForm(NombreEmpleadoForm, EmpleadoForm):
    """Conserva los campos laborales del portal y la validación común del nombre."""

    class Meta(EmpleadoForm.Meta):
        fields = ['nombres', 'apellidos', 'cargo', 'departamento',
                  'salario_mensual', 'fecha_contratacion', 'estado_laboral']

class EditarEmpleadoForm(CrearEmpleadoForm):
    """Reutiliza la validación y el guardado del alta, sin duplicar campos del modelo."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.precargar_nombre()
        # En un POST inválido se conservan exactamente los datos enviados por el usuario.
        self.revisar_separacion_nombre = True


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

        if fecha_inicio and fecha_inicio <= timezone.localdate():
            raise forms.ValidationError(
                'La fecha de inicio debe ser desde mañana.'
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

        error_messages = {
            NON_FIELD_ERRORS: {
                'unique_together': 'Ya existe una liquidación para este empleado en el período seleccionado.',
            },
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

    def clean(self):
        datos = super().clean()
        for campo in ('salario_base', 'bonificacion', 'descuentos'):
            importe = datos.get(campo)
            if importe is not None and importe < 0:
                self.add_error(campo, 'El importe debe ser superior o igual a 0.')
        return datos

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


class GenerarNominaMensualForm(forms.Form):
    """Solicita un mes concreto; los importes provienen del salario del empleado."""
    periodo = forms.DateField(label='Mes de la nómina', input_formats=['%Y-%m'],
        widget=forms.DateInput(format='%Y-%m', attrs={'type': 'month', 'class': 'form-control'}),
        error_messages={'required': 'Selecciona el mes de la nómina.',
                        'invalid': 'Selecciona un mes válido (AAAA-MM).'})
