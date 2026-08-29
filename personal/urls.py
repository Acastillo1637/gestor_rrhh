from django.shortcuts import render
from .models import Empleado


def listar_empleados(request):
    empleados = Empleado.objects.all()

    contexto = {
        'lista_empleados': empleados
    }

    return render(request, 'listar.html', contexto)