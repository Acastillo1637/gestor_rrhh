from django.shortcuts import render
from .models import Empleado
from django.contrib.auth.decorators import login_required

# Protegemos la vista para que solo usuarios con sesión iniciada puedan entrar
@login_required 
def listar_empleados(request):
    empleados = Empleado.objects.all() # Consulta SQL encubierta: trae todos los registros de la tabla
    contexto = {'lista_empleados': empleados} # Empaquetamos los datos en un diccionario
    return render(request, 'listar.html', contexto) # Enviamos el paquete de datos al archivo HTML