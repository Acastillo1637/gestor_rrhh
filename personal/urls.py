from django.urls import path
from . import views

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
]