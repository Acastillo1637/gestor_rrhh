from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum

from .forms import EmpleadoForm
from .models import Empleado, HistorialSalario


def usuario_autorizado(user):
    return (
        user.is_superuser
        or user.groups.filter(name='RRHH').exists()
        or user.groups.filter(name='GERENTES').exists()
    )


def usuario_rrhh(user):
    return (
        user.is_superuser
        or user.groups.filter(name='RRHH').exists()
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
    'total_nomina': total_nomina,
    'puede_editar': (
        request.user.is_superuser
        or request.user.groups.filter(name='RRHH').exists()
    )
}

    return render(request, 'listar.html', contexto)


@login_required(login_url='/admin/login/')
@user_passes_test(usuario_rrhh, login_url='/admin/login/')
def crear_empleado(request):

    if request.method == 'POST':
        formulario = EmpleadoForm(request.POST)

        if formulario.is_valid():
            formulario.save()
            return redirect('listar_empleados')

    else:
        formulario = EmpleadoForm()

    contexto = {
        'formulario': formulario,
        'titulo': 'Nuevo empleado'
    }

    return render(
        request,
        'formulario_empleado.html',
        contexto
    )


@login_required(login_url='/admin/login/')
@user_passes_test(usuario_rrhh, login_url='/admin/login/')
def editar_empleado(request, empleado_id):

    empleado = get_object_or_404(
        Empleado,
        id=empleado_id
    )

    salario_anterior = empleado.salario_mensual

    if request.method == 'POST':
        formulario = EmpleadoForm(
            request.POST,
            instance=empleado
        )

        if formulario.is_valid():

            empleado_editado = formulario.save(commit=False)

            salario_nuevo = empleado_editado.salario_mensual

            empleado_editado.save()

            if salario_anterior != salario_nuevo:
                HistorialSalario.objects.create(
                    empleado=empleado_editado,
                    salario_anterior=salario_anterior,
                    salario_nuevo=salario_nuevo,
                    modificado_por=request.user.username
                )

            return redirect('listar_empleados')

    else:
        formulario = EmpleadoForm(
            instance=empleado
        )

    contexto = {
        'formulario': formulario,
        'titulo': 'Editar empleado'
    }

    return render(
        request,
        'formulario_empleado.html',
        contexto
    )