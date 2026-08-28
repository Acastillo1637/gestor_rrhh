from django.contrib import admin
from .models import Empleado


# Registramos el modelo Empleado en el panel de administración.
@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):

    # Columnas que se mostrarán en la lista de empleados.
    list_display = (
        'nombre_completo',
        'cargo',
        'salario_mensual',
        'esta_activo'
    )

    # Permite filtrar empleados por estado y cargo.
    list_filter = (
        'esta_activo',
        'cargo'
    )

    # Permite buscar empleados por nombre o cargo.
    search_fields = (
        'nombre_completo',
        'cargo'
    )