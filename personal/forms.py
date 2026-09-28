# -----------------------------------------------------------------------------
# Formularios del sistema de Recursos Humanos.
# -----------------------------------------------------------------------------

from django import forms
from django.core.exceptions import NON_FIELD_ERRORS
from django.utils import timezone
from .salario_liquidacion import modo_salario

from .models import (
    Empleado,
    Departamento,
    Puesto,
    Permiso,
    Salario,
    Asistencia,
    Evaluacion,
)


# =============================================================================
# EMPLEADO
# =============================================================================

class EvaluacionForm(forms.ModelForm):
    periodo = forms.ChoiceField(
        label='Período', widget=forms.Select(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        semestre = 'Primer' if hoy.month <= 6 else 'Segundo'
        periodo_actual = f'{hoy.year} - {semestre} semestre'
        periodos = [periodo_actual]
        # Permite conservar el valor histórico de esta evaluación, sin ofrecerlo
        # al crear otras evaluaciones ni aceptar texto arbitrario por POST.
        if self.instance.pk and self.instance.periodo not in periodos:
            periodos.append(self.instance.periodo)
        self.fields['periodo'].choices = [
            (periodo, periodo) for periodo in periodos
        ]
        if not self.instance.pk:
            self.initial['periodo'] = periodo_actual

    puntuacion = forms.TypedChoiceField(
        choices=[(n, f'{n},0') for n in range(1, 6)], coerce=int,
        label='Puntuación', widget=forms.Select(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = Evaluacion
        fields = ['empleado', 'periodo', 'puntuacion', 'feedback']
        labels = {'periodo': 'Período', 'feedback': 'Comentarios'}
        widgets = {
            'empleado': forms.Select(attrs={'class': 'form-control'}),
            'feedback': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
        }


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
                    puesto.nombre
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
    nombre = forms.CharField(
        label='Nombre',
        required=True,
        strip=True,
        max_length=150,
        error_messages={'required': 'Ingresa el nombre del empleado.'},
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'given-name',
        }),
    )

    apellido_paterno = forms.CharField(
        label='Apellido paterno',
        required=True,
        strip=True,
        max_length=150,
        error_messages={'required': 'Ingresa el apellido paterno.'},
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'family-name',
        }),
    )

    apellido_materno = forms.CharField(
        label='Apellido materno',
        required=True,
        strip=True,
        max_length=150,
        error_messages={'required': 'Ingresa el apellido materno.'},
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'family-name',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fecha = self.fields['fecha_contratacion']
        fecha.required = True
        fecha.error_messages['required'] = 'Ingresa la fecha de contratación.'
        for campo in ('nombre', 'apellido_paterno', 'apellido_materno'):
            self.fields[campo].widget.attrs.update({
                'data-name-part': campo,
                'data-name-label': self.fields[campo].label.lower(),
                'pattern': r'.*\S.*',
                'aria-describedby': f'{campo}-errors',
            })

    def clean(self):
        datos = super().clean()

        nombre = datos.get('nombre')
        apellido_paterno = datos.get('apellido_paterno')
        apellido_materno = datos.get('apellido_materno')

        if nombre and apellido_paterno and apellido_materno:
            completo = ' '.join(
                f'{nombre} {apellido_paterno} {apellido_materno}'.split()
            )

            campo = Empleado._meta.get_field('nombre_completo')

            try:
                completo = campo.clean(completo, self.instance)
            except forms.ValidationError:
                self.add_error(
                    'apellido_materno',
                    f'El nombre completo no puede superar {campo.max_length} caracteres.'
                )
            else:
                self.instance.nombre_completo = completo

        return datos

    def precargar_nombre(self):
        if not self.is_bound and self.instance.pk:
            partes = self.instance.nombre_completo.strip().split()

            self.initial.setdefault(
                'nombre',
                ' '.join(partes[:-2]) if len(partes) >= 3 else (partes[0] if partes else '')
            )
            self.initial.setdefault(
                'apellido_paterno',
                partes[-2] if len(partes) >= 3 else (partes[1] if len(partes) == 2 else '')
            )
            self.initial.setdefault(
                'apellido_materno',
                partes[-1] if len(partes) >= 3 else ''
            )


class CrearEmpleadoForm(NombreEmpleadoForm, EmpleadoForm):
    """Conserva los campos laborales del portal y la validación común del nombre."""

    es_alta = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.es_alta:
            return
        self.fields['estado_laboral'].disabled = True
        self.fields['estado_laboral'].widget = forms.HiddenInput()
        self.initial['estado_laboral'] = 'activo'
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault('fecha_contratacion', timezone.localdate())
        self.departamentos_cargos = dict(Departamento.objects.values_list('nombre', 'pk'))
        departamento = self.data.get('departamento') if self.is_bound else self.initial.get('departamento')
        puestos = Puesto.objects.filter(departamento__nombre=departamento).order_by('nombre') if departamento else Puesto.objects.none()
        opciones = [(p.nombre, p.nombre) for p in puestos]
        mensaje = 'Seleccione un cargo' if opciones else (
            'Este departamento no tiene cargos disponibles' if departamento else 'Seleccione primero un departamento')
        self.fields['cargo'].choices = [('', mensaje)] + opciones
        if not opciones:
            self.fields['cargo'].widget.attrs['disabled'] = True

    def clean_estado_laboral(self):
        return 'activo' if self.es_alta else self.cleaned_data['estado_laboral']

    class Meta(EmpleadoForm.Meta):
        fields = [
            'nombre',
            'apellido_paterno',
            'apellido_materno',
            'cargo',
            'departamento',
            'salario_mensual',
            'fecha_contratacion',
            'estado_laboral']

class EditarEmpleadoForm(CrearEmpleadoForm):
    """Reutiliza la validación y el guardado del alta, sin duplicar campos del modelo."""

    es_alta = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.precargar_nombre()
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

        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault('mes_ano', timezone.localdate().replace(day=1))
        self.fields['mes_ano'].widget.format = '%Y-%m-%d'
        self.mes_actual = timezone.localdate().strftime('%Y-%m')
        try:
            fecha = self.fields['mes_ano'].clean(
                self.data.get(self.add_prefix('mes_ano')) if self.is_bound else self.initial.get('mes_ano'))
        except forms.ValidationError:
            fecha = None
        self.modo_salario = modo_salario(fecha)
        self.salario_automatico = self.modo_salario == 'actual' and not self.instance.pk
        self.salario_actual = None
        if self.salario_automatico:
            campo = self.fields['salario_base']
            campo.disabled = True
            campo.required = False
            identificador = self.data.get(self.add_prefix('empleado')) if self.is_bound else self.initial.get('empleado')
            if isinstance(identificador, Empleado):
                identificador = identificador.pk
            if str(identificador).isdigit():
                self.salario_actual = self.fields['empleado'].queryset.filter(pk=identificador).values_list('salario_mensual', flat=True).first()
            self.initial['salario_base'] = self.salario_actual

    def clean(self):
        datos = super().clean()
        # ModelChoiceField obtiene el empleado del servidor durante la validación.
        # Nunca se toma el importe del POST para una nueva liquidación actual.
        empleado = datos.get('empleado')
        if self.salario_automatico and empleado:
            datos['salario_base'] = empleado.salario_mensual
        for campo in ('salario_base', 'bonificacion', 'descuentos'):
            importe = datos.get(campo)
            if importe is not None and importe < 0:
                self.add_error(campo, 'El importe debe ser superior o igual a 0.')
        empleado, fecha = datos.get('empleado'), datos.get('mes_ano')
        if empleado and fecha:
            existentes = Salario.objects.filter(
                empleado=empleado, mes_ano__year=fecha.year, mes_ano__month=fecha.month,
            ).exclude(pk=self.instance.pk)
            if existentes.exists():
                self.add_error('mes_ano', 'Ya existe una liquidación para este empleado en el período seleccionado.')
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
