from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum

from .models import Empleado


def usuario_autorizado(user):
    return (
        user.is_superuser
        or user.groups.filter(name='RRHH').exists()
        or user.groups.filter(name='GERENTES').exists()
    )


@login_required(login_url='/admin/login/')
@user_passes_test(usuario_autorizado, login_url='/admin/login/')
def listar_empleados(request):

    empleados = Empleado.objects.all()

    total_nomina = (
        Empleado.objects
        .filter(esta_activo=True)
        .aggregate(total=Sum('salario_mensual'))
        ['total']
        or 0
    )

    contexto = {
        'lista_empleados': empleados,
        'total_nomina': total_nomina
    }

    return render(request, 'listar.html', contexto)