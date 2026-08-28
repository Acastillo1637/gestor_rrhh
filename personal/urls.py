from django.urls import path
from .views import listar_empleados

# Conectamos la dirección URL '/empleados/' con la función de la vista
urlpatterns = [
    path('empleados/', listar_empleados, name='listar_empleados'),
]