# -----------------------------------------------------------------------------
# Rutas de la aplicación personal y relación de cada URL con su vista.
# -----------------------------------------------------------------------------
from django.urls import path
from . import views

# Rutas disponibles para la gestión de empleados.
urlpatterns = [
    path(
        'empleados/',
        views.listar_empleados,
        name='listar_empleados'
    ),

    path(
        'empleados/nuevo/',
        views.crear_empleado,
        name='crear_empleado'
    ),

    path(
        'empleados/<int:empleado_id>/editar/',
        views.editar_empleado,
        name='editar_empleado'
    ),
    path(
    'ajax/puestos/',
    views.obtener_puestos_por_departamento,
    name='obtener_puestos_por_departamento'
    ),
]