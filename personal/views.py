from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Q

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

    # Consulta base
    empleados = Empleado.objects.all()

    # Valores recibidos desde los filtros
    busqueda = request.GET.get('busqueda', '')
    departamento = request.GET.get('departamento', '')
    cargo = request.GET.get('cargo', '')
    estado = request.GET.get('estado', '')

    # Buscar por nombre o cargo
    if busqueda:
        empleados = empleados.filter(
            Q(nombre_completo__icontains=busqueda) |
            Q(cargo__icontains=busqueda)
        )

    # Filtrar por departamento
    if departamento:
        empleados = empleados.filter(
            departamento=departamento
        )

    # Filtrar por cargo
    if cargo:
        empleados = empleados.filter(
            cargo=cargo
        )

    # Filtrar por estado
    if estado == 'activo':
        empleados = empleados.filter(
            esta_activo=True
        )

    elif estado == 'inactivo':
        empleados = empleados.filter(
            esta_activo=False
        )

    # -----------------------------------
    # INDICADORES DEL RESULTADO FILTRADO
    # -----------------------------------

    total_empleados = empleados.count()

    total_activos = empleados.filter(
        esta_activo=True
    ).count()

    total_inactivos = empleados.filter(
        esta_activo=False
    ).count()

    total_nomina = (
        empleados
        .filter(esta_activo=True)
        .aggregate(total=Sum('salario_mensual'))
        ['total']
        or 0
    )

    # -----------------------------------
    # OPCIONES PARA LOS SELECT
    # -----------------------------------

    departamentos = (
        Empleado.objects
        .values_list('departamento', flat=True)
        .distinct()
        .order_by('departamento')
    )

    cargos = (
        Empleado.objects
        .values_list('cargo', flat=True)
        .distinct()
        .order_by('cargo')
    )

    # RRHH puede crear/editar
    puede_editar = (
        request.user.is_superuser
        or request.user.groups.filter(name='RRHH').exists()
    )

    contexto = {
        'lista_empleados': empleados,

        'total_empleados': total_empleados,
        'total_activos': total_activos,
        'total_inactivos': total_inactivos,
        'total_nomina': total_nomina,

        'departamentos': departamentos,
        'cargos': cargos,

        'busqueda': busqueda,
        'departamento_seleccionado': departamento,
        'cargo_seleccionado': cargo,
        'estado_seleccionado': estado,

        'puede_editar': puede_editar,
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