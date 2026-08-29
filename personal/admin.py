from django.contrib import admin
from .models import Empleado, HistorialSalario


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = (
        'nombre_completo',
        'cargo',
        'salario_mensual',
        'esta_activo'
    )

    list_filter = ('esta_activo', 'cargo')
    search_fields = ('nombre_completo', 'cargo')
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


@admin.register(HistorialSalario)
class HistorialSalarioAdmin(admin.ModelAdmin):
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