# -----------------------------------------------------------------------------
# Lógica de las páginas: listado, filtros, creación y edición de empleados.
# -----------------------------------------------------------------------------
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Q
from django.http import JsonResponse

from .forms import EmpleadoForm
from .models import Empleado, HistorialSalario, Puesto


# Comprueba si el usuario puede consultar el listado de empleados.
def usuario_autorizado(user):
    return (
        user.is_superuser
        or user.groups.filter(name='RRHH').exists()
        or user.groups.filter(name='GERENTES').exists()
    )


# Comprueba si el usuario tiene permisos para crear o editar empleados.
def usuario_rrhh(user):
    return (
        user.is_superuser
        or user.groups.filter(name='RRHH').exists()
    )


@login_required(login_url='/admin/login/')
@user_passes_test(usuario_autorizado, login_url='/admin/login/')
# Vista principal: lista empleados y aplica los filtros enviados por GET.
def listar_empleados(request):

    # Consulta base
    # Consulta inicial a todos los empleados. (El ordenamiento ya viene del modelo: -salario_mensual)
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

    # Filtrar por estado laboral (se usa iexact para evitar discrepancias por mayúsculas o minúsculas)
    if estado == 'activo':
        empleados = empleados.filter(
            estado_laboral__iexact='activo'
        )

    elif estado == 'inactivo':
        # Excluimos a los activos para incluir otros estados como 'despedido' y 'renuncio'
        empleados = empleados.exclude(
            estado_laboral__iexact='activo'
        )

    # -----------------------------------
    # INDICADORES DEL RESULTADO FILTRADO
    # -----------------------------------

    # Total general de empleados que coinciden con los filtros aplicados.
    total_empleados = empleados.count()

    # Total de empleados con estado activo (insensible a mayúsculas/minúsculas).
    total_activos = empleados.filter(
        estado_laboral__iexact='activo'
    ).count()

    # Total de empleados inactivos (todos aquellos cuyo estado no sea activo).
    total_inactivos = empleados.exclude(
        estado_laboral__iexact='activo'
    ).count()

    # Cálculo del gasto mensual total en nómina: suma de los salarios de todos los empleados activos.
    total_nomina = (
        empleados
        .filter(estado_laboral__iexact='activo')
        .aggregate(total=Sum('salario_mensual'))
        ['total']
        or 0
    )

    # -----------------------------------
    # OPCIONES PARA LOS SELECT
    # -----------------------------------

    # Obtiene departamentos únicos para construir el filtro desplegable.
    departamentos = (
        Empleado.objects
        .values_list('departamento', flat=True)
        .distinct()
        .order_by('departamento')
    )

    # Obtiene cargos únicos para construir el filtro desplegable.
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
# Vista protegida para registrar un nuevo empleado.
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
# Vista protegida para modificar un empleado existente y registrar cambios de salario.
def editar_empleado(request, empleado_id):

    empleado = get_object_or_404(
        Empleado,
        id=empleado_id
    )

    # Se conserva el salario previo para detectar si hubo modificación.
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
    
def obtener_puestos_por_departamento(request):
    departamento_id = request.GET.get('departamento_id')

    puestos = Puesto.objects.filter(
        departamento_id=departamento_id
    ).order_by('nombre')

    data = [
        {
            'nombre': puesto.nombre,
            'salario_base': float(puesto.salario_base),
        }
        for puesto in puestos
    ]

    return JsonResponse(data, safe=False)