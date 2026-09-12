# -----------------------------------------------------------------------------
# Configuración del panel de administración del sistema de RRHH.
# -----------------------------------------------------------------------------

from django.contrib import admin
from django import forms

from .models import (
    Empleado,
    HistorialSalario,
    Departamento,
    Puesto,
    EmpleadoPuesto,
    Salario,
    Asistencia,
    Permiso,
    Evaluacion,
)


# -----------------------------------------------------------------------------
# Personalización general del panel admin
# -----------------------------------------------------------------------------

admin.site.site_header = "Gestor de Personal - Recursos Humanos"
admin.site.site_title = "RRHH"
admin.site.index_title = "Administración de Personal"
admin.site.site_url = "/empleados/"


# =============================================================================
# EMPLEADO
# =============================================================================

class EmpleadoAdminForm(forms.ModelForm):

    departamento_selector = forms.ModelChoiceField(
        queryset=Departamento.objects.all().order_by('nombre'),
        label='Departamento',
        required=True,
        empty_label='Seleccione un departamento'
    )

    cargo_selector = forms.ChoiceField(
        label='Cargo',
        required=True,
        choices=[
            ('', 'Seleccione primero un departamento')
        ]
    )
    
    class Meta:
        model = Empleado
        exclude = (
            'cargo',
            'departamento',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Si estamos editando un empleado existente
        if self.instance and self.instance.pk:

            try:
                departamento = Departamento.objects.get(
                    nombre=self.instance.departamento
                )

                self.fields[
                    'departamento_selector'
                ].initial = departamento

                puestos = Puesto.objects.filter(
                    departamento=departamento
                ).order_by('nombre')

                self.fields['cargo_selector'].choices = [
                    ('', 'Seleccione un cargo')
                ] + [
                    (puesto.nombre, puesto.nombre)
                    for puesto in puestos
                ]

                self.fields[
                    'cargo_selector'
                ].initial = self.instance.cargo

            except Departamento.DoesNotExist:
                pass

        # Si el formulario viene enviado y hubo algún error,
        # mantenemos los cargos del departamento seleccionado.
        if self.is_bound:

            departamento_id = self.data.get(
                'departamento_selector'
            )

            if departamento_id:

                try:
                    departamento = Departamento.objects.get(
                        pk=departamento_id
                    )

                    puestos = Puesto.objects.filter(
                        departamento=departamento
                    ).order_by('nombre')

                    self.fields['cargo_selector'].choices = [
                        ('', 'Seleccione un cargo')
                    ] + [
                        (puesto.nombre, puesto.nombre)
                        for puesto in puestos
                    ]

                except Departamento.DoesNotExist:
                    pass

    def save(self, commit=True):

        empleado = super().save(commit=False)

        departamento = self.cleaned_data[
            'departamento_selector'
        ]

        empleado.departamento = departamento.nombre

        empleado.cargo = self.cleaned_data[
            'cargo_selector'
        ]

        if commit:
            empleado.save()

        return empleado


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):

    form = EmpleadoAdminForm
    
    fields = (
        'usuario',
        'nombre_completo',
        'email',
        'dni',
        'fecha_nacimiento',
        'genero',
        'telefono',
        'direccion',
        'fecha_contratacion',
        'estado_laboral',
        'departamento_selector',
        'cargo_selector',
        'salario_mensual',
    )
    
    class Media:
        js = (
        'personal/js/empleado_admin.js',
    )

    list_display = (
        'nombre_completo',
        'dni',
        'cargo',
        'departamento',
        'salario_mensual',
        'estado_laboral',
        'fecha_contratacion',
        'ultimo_salario',
    )

    list_filter = (
        'estado_laboral',
        'departamento',
        'cargo',
        'genero',
        'fecha_contratacion',
    )

    search_fields = (
        'nombre_completo',
        'email',
        'dni',
        'cargo',
        'departamento',
        'telefono',
    )

    ordering = (
        'nombre_completo',
    )

    # -------------------------------------------------------------------------
    # Muestra el último salario registrado.
    # Si todavía no existe una nómina, utiliza el salario mensual del empleado.
    # -------------------------------------------------------------------------

    def ultimo_salario(self, obj):

        salario = obj.salarios.order_by(
            '-mes_ano'
        ).first()

        if salario:
            return salario.neto

        return obj.salario_mensual

    ultimo_salario.short_description = 'Último salario'

    # -------------------------------------------------------------------------
    # Permisos del administrador
    # -------------------------------------------------------------------------

    def has_view_permission(self, request, obj=None):

        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
            or request.user.groups.filter(
                name='GERENTES'
            ).exists()
        )

    def has_add_permission(self, request):

        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
        )

    def has_change_permission(self, request, obj=None):

        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
        )

    def has_delete_permission(self, request, obj=None):

        return (
            request.user.is_superuser
            or request.user.groups.filter(
                name='RRHH'
            ).exists()
        )

    # -------------------------------------------------------------------------
    # Auditoría automática de cambios de salario
    # -------------------------------------------------------------------------

    def save_model(self, request, obj, form, change):

        salario_anterior = None

        if change:

            empleado_anterior = Empleado.objects.get(
                pk=obj.pk
            )

            salario_anterior = (
                empleado_anterior.salario_mensual
            )

        super().save_model(
            request,
            obj,
            form,
            change
        )

        if (
            change
            and salario_anterior != obj.salario_mensual
        ):

            HistorialSalario.objects.create(
                empleado=obj,
                salario_anterior=salario_anterior,
                salario_nuevo=obj.salario_mensual,
                modificado_por=request.user.username
            )


# =============================================================================
# HISTORIAL SALARIAL
# =============================================================================

@admin.register(HistorialSalario)
class HistorialSalarioAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'salario_anterior',
        'salario_nuevo',
        'modificado_por',
        'fecha_modificacion',
    )

    search_fields = (
        'empleado__nombre_completo',
        'modificado_por',
    )

    list_filter = (
        'fecha_modificacion',
    )

    readonly_fields = (
        'empleado',
        'salario_anterior',
        'salario_nuevo',
        'modificado_por',
        'fecha_modificacion',
    )

    ordering = (
        '-fecha_modificacion',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(
        self,
        request,
        obj=None
    ):
        return False

    def has_delete_permission(
        self,
        request,
        obj=None
    ):
        return False


# =============================================================================
# DEPARTAMENTO
# =============================================================================

@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):

    list_display = (
        'nombre',
        'jefe',
        'presupuesto',
    )

    search_fields = (
        'nombre',
        'descripcion',
        'jefe__nombre_completo',
    )

    list_filter = (
        'nombre',
    )


# =============================================================================
# PUESTO
# =============================================================================

@admin.register(Puesto)
class PuestoAdmin(admin.ModelAdmin):

    list_display = (
        'nombre',
        'departamento',
        'nivel',
        'salario_base',
    )

    search_fields = (
        'nombre',
        'departamento__nombre',
    )

    list_filter = (
        'departamento',
        'nivel',
    )


# =============================================================================
# HISTORIAL DE PUESTOS
# =============================================================================

@admin.register(EmpleadoPuesto)
class EmpleadoPuestoAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'puesto',
        'fecha_inicio',
        'fecha_fin',
        'es_actual',
    )

    search_fields = (
        'empleado__nombre_completo',
        'puesto__nombre',
    )

    list_filter = (
        'es_actual',
        'puesto__departamento',
        'fecha_inicio',
    )


# =============================================================================
# SALARIO / NÓMINA
# =============================================================================

@admin.register(Salario)
class SalarioAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'mes_ano',
        'salario_base',
        'bonificacion',
        'descuentos',
        'neto',
        'pagado',
    )

    search_fields = (
        'empleado__nombre_completo',
        'empleado__dni',
    )

    list_filter = (
        'pagado',
        'mes_ano',
    )

    ordering = (
        '-mes_ano',
    )


# =============================================================================
# ASISTENCIA
# =============================================================================

@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'fecha',
        'hora_entrada',
        'hora_salida',
        'minutos_trabajados',
        'estado',
    )

    search_fields = (
        'empleado__nombre_completo',
        'empleado__dni',
    )

    list_filter = (
        'estado',
        'fecha',
    )


# =============================================================================
# PERMISOS
# =============================================================================

@admin.register(Permiso)
class PermisoAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'tipo',
        'fecha_inicio',
        'fecha_fin',
        'dias',
        'estado',
        'aprobado',
    )

    search_fields = (
        'empleado__nombre_completo',
        'empleado__dni',
    )

    list_filter = (
        'tipo',
        'estado',
        'aprobado',
        'fecha_inicio',
    )


# =============================================================================
# EVALUACIONES
# =============================================================================

@admin.register(Evaluacion)
class EvaluacionAdmin(admin.ModelAdmin):

    list_display = (
        'empleado',
        'periodo',
        'puntuacion',
    )

    search_fields = (
        'empleado__nombre_completo',
        'periodo',
    )

    list_filter = (
        'puntuacion',
        'periodo',
    )