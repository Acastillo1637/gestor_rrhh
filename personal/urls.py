from django.urls import path
from . import views

urlpatterns = [
    path('empleados/', views.listar_empleados, name='listar_empleados'),
]