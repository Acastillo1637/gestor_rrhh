# -----------------------------------------------------------------------------
# Configuración del panel de administración de Django, permisos y registro del historial salarial.
# -----------------------------------------------------------------------------
from django.contrib import admin
from .models import Empleado, HistorialSalario

# Personaliza el encabezado, título y nombre de la página principal del administrador.
admin.site.site_header = "Gestor de Personal - Recursos Humanos"
admin.site.site_title = "RRHH"
admin.site.index_title = "Administración de Personal"
admin.site.site_url = "/empleados/"


# Configuración de Empleado dentro del panel de administración.
@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    # Columnas que se muestran en el listado de empleados.
    list_display = (
        'nombre_completo',
        'cargo',
        'departamento',
        'salario_mensual',
        'estado_laboral'  # <-- Corregido
    )

    # Filtros laterales disponibles en el administrador.
    list_filter = (
        'departamento',
        'cargo',
        'estado_laboral'  # <-- Corregido
    )

    # Campos que se pueden buscar mediante el buscador del administrador.
    search_fields = (
        'nombre_completo',
        'cargo',
        'departamento'
    )

    ordering = ('-salario_mensual',)

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.groups.filter(name='RRHH').exists()
            or request.user.groups.filter(name='GERENTES').exists()
        )

    def has_add_permission(self, request):
        return (
            request.user.is_superuser
            or request.user.groups.filter(name='RRHH').exists()
        )

    def has_change_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.groups.filter(name='RRHH').exists()
        )

    def has_delete_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.groups.filter(name='RRHH').exists()
        )

    # Sobrescribe el guardado para registrar automáticamente cambios de salario.
    def save_model(self, request, obj, form, change):
        salario_anterior = None

        if change:
            empleado_anterior = Empleado.objects.get(pk=obj.pk)
            salario_anterior = empleado_anterior.salario_mensual

        super().save_model(request, obj, form, change)

        if change and salario_anterior != obj.salario_mensual:
            HistorialSalario.objects.create(
                empleado=obj,
                salario_anterior=salario_anterior,
                salario_nuevo=obj.salario_mensual,
                modificado_por=request.user.username
            )


# El historial se muestra como solo lectura para evitar alterar la trazabilidad.
@admin.register(HistorialSalario)
class HistorialSalarioAdmin(admin.ModelAdmin):
    # Columnas que se muestran en el listado del historial.
    list_display = (
        'empleado',
        'salario_anterior',
        'salario_nuevo',
        'modificado_por',
        'fecha_modificacion'
    )

    readonly_fields = (
        'empleado',
        'salario_anterior',
        'salario_nuevo',
        'modificado_por',
        'fecha_modificacion'
    )

    ordering = ('-fecha_modificacion',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False