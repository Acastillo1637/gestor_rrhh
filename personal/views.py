# -----------------------------------------------------------------------------
# Lógica de las páginas del sistema de Recursos Humanos.
# -----------------------------------------------------------------------------

from django.contrib.auth.models import User, Group
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.utils import timezone
from django.db import transaction
from django.urls import reverse, reverse_lazy
from datetime import datetime, time, timedelta

from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)

from django.contrib.auth.decorators import (
    login_required,
    user_passes_test,
)

from django.contrib.auth import (
    login,
    logout,
)

from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages

from django.db.models import (
    Sum,
    Q,
    Count,
)

from django.http import JsonResponse, HttpResponse
# Generación del libro Excel y estilos de sus encabezados.
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from django.template.loader import render_to_string
from django.middleware.csrf import get_token
from .context_processors import contexto_rol
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from .forms import (
    EmpleadoForm,
    CrearEmpleadoForm,
    PermisoForm,
    NominaForm,
)

from .models import (
    Empleado,
    HistorialSalario,
    Puesto,
    Permiso,
    Salario,
    Asistencia,
    Feriado,
    Notificacion,
)


# =============================================================================
# ROLES Y PERMISOS
# =============================================================================

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


def crear_notificacion(
    mensaje,
    tipo='sistema',
    usuario=None,
    url=''
):
    """
    Crea una notificación.

    usuario=None  -> visible para RRHH / Gerencia.
    usuario=User  -> visible solamente para ese trabajador.
    """

    return Notificacion.objects.create(
        usuario=usuario,
        mensaje=mensaje,
        tipo=tipo,
        url=url,
    )


def crear_usuario_para_empleado(empleado):
    """
    Crea automáticamente una cuenta de acceso para un empleado.

    Retorna:
        usuario creado
        contraseña temporal
    """

    # ---------------------------------------------------------
    # CREAR NOMBRE DE USUARIO
    # ---------------------------------------------------------

    # Ejemplo:
    # Juan Pérez González -> juan.perez.gonzalez
    username_base = slugify(
        empleado.nombre_completo
    ).replace("-", ".")

    if not username_base:
        username_base = "empleado"

    username = username_base
    contador = 1

    # Evita usuarios repetidos
    while User.objects.filter(username=username).exists():
        username = f"{username_base}{contador}"
        contador += 1

    # ---------------------------------------------------------
    # GENERAR CONTRASEÑA TEMPORAL
    # ---------------------------------------------------------

    caracteres = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ"
        "abcdefghijkmnopqrstuvwxyz"
        "23456789"
        "@#$"
    )

    password_temporal = get_random_string(
        12,
        allowed_chars=caracteres
    )

    # ---------------------------------------------------------
    # CREAR USUARIO DJANGO
    # ---------------------------------------------------------

    usuario = User.objects.create_user(
        username=username,
        email=empleado.email or "",
        password=password_temporal,
        is_active=True,
    )

    # Es trabajador normal, NO administrador
    usuario.is_staff = False
    usuario.is_superuser = False
    usuario.save()

    # ---------------------------------------------------------
    # GRUPO EMPLEADO
    # ---------------------------------------------------------

    grupo_empleado, _ = Group.objects.get_or_create(
        name="EMPLEADO"
    )

    usuario.groups.add(grupo_empleado)

    # ---------------------------------------------------------
    # VINCULAR CUENTA CON EMPLEADO
    # ---------------------------------------------------------

    empleado.usuario = usuario
    empleado.save(update_fields=["usuario"])

    return usuario, password_temporal


# =============================================================================
# INICIO SEGÚN ROL
# =============================================================================

@login_required(login_url='login')
def inicio(request):

    if usuario_autorizado(request.user):
        return redirect('dashboard_gestion')

    if hasattr(request.user, 'empleado'):
        return redirect('dashboard_empleado')

    messages.error(
        request,
        'Tu cuenta no tiene un perfil asociado dentro del sistema.'
    )

    logout(request)

    return redirect('login')


# =============================================================================
# CAMBIAR CONTRASEÑA
# =============================================================================

# Permite cambiar la contraseña de la cuenta autenticada.
class CambiarContrasenaView(PasswordChangeView):
    login_url = 'login'
    success_url = reverse_lazy('inicio')
    template_name = 'cambiar_contrasena.html'

# =============================================================================
# LOGIN
# =============================================================================

@never_cache
@ensure_csrf_cookie
def iniciar_sesion(request):

    if request.user.is_authenticated:
        return redirect('inicio')

    if request.method == 'POST':

        formulario = AuthenticationForm(
            request=request,
            data=request.POST
        )

        if formulario.is_valid():

            usuario = formulario.get_user()

            login(
                request,
                usuario
            )

            return redirect('inicio')

    else:

        formulario = AuthenticationForm()

    contexto = {
        'formulario': formulario,
        'titulo': 'Iniciar sesión',
    }

    return render(
        request,
        'login.html',
        contexto
    )


# =============================================================================
# LOGOUT
# =============================================================================

@login_required(login_url='login')
def cerrar_sesion(request):

    logout(request)

    messages.success(
        request,
        'Sesión cerrada correctamente.'
    )

    return redirect('login')


# =============================================================================
# DASHBOARD RRHH / GERENCIA
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def dashboard_gestion(request):

    empleados = Empleado.objects.all()

    total_empleados = empleados.count()

    total_activos = empleados.filter(
        estado_laboral__iexact='activo'
    ).count()

    total_inactivos = empleados.exclude(
        estado_laboral__iexact='activo'
    ).count()

    total_nomina = (
        empleados
        .filter(
            estado_laboral__iexact='activo'
        )
        .aggregate(
            total=Sum('salario_mensual')
        )['total']
        or 0
    )

    permisos_pendientes = (
        Permiso.objects
        .filter(
            estado='pendiente'
        )
        .count()
    )

    ultimos_permisos = (
        Permiso.objects
        .select_related('empleado')
        .order_by('-fecha_inicio')[:5]
    )

    departamentos = (
        Empleado.objects
        .exclude(departamento='')
        .values('departamento')
        .annotate(
            total=Count('id')
        )
        .order_by('-total')
    )

    contexto = {
        'total_empleados': total_empleados,
        'total_activos': total_activos,
        'total_inactivos': total_inactivos,
        'total_nomina': total_nomina,
        'permisos_pendientes': permisos_pendientes,
        'ultimos_permisos': ultimos_permisos,
        'departamentos': departamentos,

    }

    return render(
        request,
        'dashboard_gestion.html',
        contexto
    )


# =============================================================================
# DASHBOARD EMPLEADO
# =============================================================================

@login_required(login_url='login')
def dashboard_empleado(request):

    try:
        empleado = request.user.empleado

    except Empleado.DoesNotExist:

        messages.error(
            request,
            'Tu usuario no está asociado a un empleado.'
        )

        logout(request)

        return redirect('login')

    permisos = Permiso.objects.filter(
        empleado=empleado
    )

    permisos_pendientes = permisos.filter(
        estado='pendiente'
    ).count()

    permisos_aprobados = permisos.filter(
        estado='aprobado'
    ).count()

    permisos_rechazados = permisos.filter(
        estado='rechazado'
    ).count()

    ultima_liquidacion = (
        Salario.objects
        .filter(
            empleado=empleado
        )
        .order_by('-mes_ano')
        .first()
    )

    ultimos_permisos = permisos.order_by(
        '-fecha_inicio'
    )[:5]

    contexto = {
        'empleado': empleado,
        'permisos_pendientes': permisos_pendientes,
        'permisos_aprobados': permisos_aprobados,
        'permisos_rechazados': permisos_rechazados,
        'ultima_liquidacion': ultima_liquidacion,
        'ultimos_permisos': ultimos_permisos,

    }

    return render(
        request,
        'dashboard_empleado.html',
        contexto
    )


# =============================================================================
# LISTADO DE EMPLEADOS
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def listar_empleados(request):

    empleados = Empleado.objects.all()

    busqueda = request.GET.get(
        'busqueda',
        ''
    )

    departamento = request.GET.get(
        'departamento',
        ''
    )

    cargo = request.GET.get(
        'cargo',
        ''
    )

    estado = request.GET.get(
        'estado',
        ''
    )

    if busqueda:

        empleados = empleados.filter(
            Q(
                nombre_completo__icontains=busqueda
            )
            |
            Q(
                cargo__icontains=busqueda
            )
        )

    if departamento:

        empleados = empleados.filter(
            departamento=departamento
        )

    if cargo:

        empleados = empleados.filter(
            cargo=cargo
        )

    if estado == 'activo':

        empleados = empleados.filter(
            estado_laboral__iexact='activo'
        )

    elif estado == 'inactivo':

        empleados = empleados.exclude(
            estado_laboral__iexact='activo'
        )

    total_empleados = empleados.count()

    total_activos = empleados.filter(
        estado_laboral__iexact='activo'
    ).count()

    total_inactivos = empleados.exclude(
        estado_laboral__iexact='activo'
    ).count()

    total_nomina = (
        empleados
        .filter(
            estado_laboral__iexact='activo'
        )
        .aggregate(
            total=Sum('salario_mensual')
        )['total']
        or 0
    )

    departamentos = (
        Empleado.objects
        .exclude(departamento='')
        .values_list(
            'departamento',
            flat=True
        )
        .distinct()
        .order_by('departamento')
    )

    cargos = (
        Empleado.objects
        .exclude(cargo='')
        .values_list(
            'cargo',
            flat=True
        )
        .distinct()
        .order_by('cargo')
    )

    puede_editar = (
        request.user.is_superuser
        or request.user.groups.filter(
            name='RRHH'
        ).exists()
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

    return render(
        request,
        'listar.html',
        contexto
    )


# =============================================================================
# CREAR EMPLEADO
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_rrhh,
    login_url='login'
)
def crear_empleado(request):
    # Solo el alta usa la captura separada. La edición mantiene EmpleadoForm porque
    # no podemos deducir con certeza los nombres y apellidos de los registros antiguos.

    if request.method == 'POST':

        formulario = CrearEmpleadoForm(
            request.POST
        )

        if formulario.is_valid():

            try:
                # Si falla la creación del usuario, también se revierte
                # la creación del empleado para no dejar datos incompletos.
                with transaction.atomic():

                    empleado = formulario.save()

                    usuario = None
                    password_temporal = None

                    if not empleado.usuario:
                        usuario, password_temporal = crear_usuario_para_empleado(
                            empleado
                        )

                crear_notificacion(
                    mensaje=(
                        f'{request.user.username} creó al empleado '
                        f'{empleado.nombre_completo}.'
                    ),
                    tipo='empleado',
                    url=reverse(
                        'editar_empleado',
                        args=[empleado.id]
                    )
                )

                if usuario and password_temporal:
                    messages.success(
                        request,
                        (
                            f'Empleado creado correctamente. '
                            f'Usuario: {usuario.username} | '
                            f'Contraseña temporal: {password_temporal}'
                        )
                    )
                else:
                    messages.success(
                        request,
                        'Empleado creado correctamente.'
                    )

                return redirect('listar_empleados')

            except Exception as error:
                messages.error(
                    request,
                    (
                        'No fue posible crear el empleado y su cuenta de acceso. '
                        f'Detalle: {error}'
                    )
                )

    else:

        formulario = CrearEmpleadoForm()

    contexto = {
        'formulario': formulario,
        'titulo': 'Nuevo empleado',

    }

    return render(
        request,
        'formulario_empleado.html',
        contexto
    )


# =============================================================================
# EDITAR EMPLEADO
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_rrhh,
    login_url='login'
)
def editar_empleado(
    request,
    empleado_id
):

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

            empleado_editado = formulario.save(
                commit=False
            )

            salario_nuevo = (
                empleado_editado
                .salario_mensual
            )

            empleado_editado.save()

            if (
                salario_anterior
                != salario_nuevo
            ):

                HistorialSalario.objects.create(
                    empleado=empleado_editado,
                    salario_anterior=salario_anterior,
                    salario_nuevo=salario_nuevo,
                    modificado_por=request.user.username
                )

            crear_notificacion(
                mensaje=(
                    f'{request.user.username} editó al empleado '
                    f'{empleado_editado.nombre_completo}.'
                ),
                tipo='empleado',
                url=reverse(
                    'editar_empleado',
                    args=[empleado_editado.id]
                )
            )

            messages.success(
                request,
                'Empleado actualizado correctamente.'
            )

            return redirect('listar_empleados')

    else:

        formulario = EmpleadoForm(
            instance=empleado
        )

    contexto = {
        'formulario': formulario,
        'titulo': 'Editar empleado',

    }

    return render(
        request,
        'formulario_empleado.html',
        contexto
    )


# =============================================================================
# HISTORIAL SALARIAL - RRHH / GERENCIA
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def historial_salarial(request, empleado_id=None):
    """Consulta de cambios del salario mensual registrados al editar empleados."""

    registros = (
        HistorialSalario.objects
        .select_related('empleado')
        .all()
        .order_by('-fecha_modificacion')
    )

    empleado_seleccionado = None

    if empleado_id is not None:
        empleado_seleccionado = get_object_or_404(Empleado, id=empleado_id)
        registros = registros.filter(empleado=empleado_seleccionado)

    busqueda = request.GET.get('busqueda', '').strip()
    empleado_filtro = request.GET.get('empleado', '').strip()

    if busqueda:
        registros = registros.filter(
            Q(empleado__nombre_completo__icontains=busqueda)
            | Q(empleado__dni__icontains=busqueda)
            | Q(modificado_por__icontains=busqueda)
        )

    if empleado_filtro.isdigit() and empleado_id is None:
        registros = registros.filter(empleado_id=int(empleado_filtro))

    empleados = Empleado.objects.all().order_by('nombre_completo')

    contexto = {
        'registros': registros,
        'empleados': empleados,
        'empleado_seleccionado': empleado_seleccionado,
        'busqueda': busqueda,
        'empleado_filtro': empleado_filtro,
        'total_registros': registros.count(),
    }

    return render(request, 'historial_salarial.html', contexto)


# =============================================================================
# GESTIÓN DE PERMISOS - RRHH / GERENCIA
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def gestion_permisos(request):

    permisos = (
        Permiso.objects
        .select_related('empleado')
        .all()
    )

    busqueda = request.GET.get(
        'busqueda',
        ''
    )

    tipo = request.GET.get(
        'tipo',
        ''
    )

    estado = request.GET.get(
        'estado',
        ''
    )

    if busqueda:

        permisos = permisos.filter(
            Q(
                empleado__nombre_completo__icontains=busqueda
            )
        )

    if tipo:

        permisos = permisos.filter(
            tipo=tipo
        )

    if estado:

        permisos = permisos.filter(
            estado=estado
        )

    permisos = permisos.order_by(
        '-fecha_inicio'
    )

    total_permisos = permisos.count()

    total_pendientes = permisos.filter(
        estado='pendiente'
    ).count()

    total_aprobados = permisos.filter(
        estado='aprobado'
    ).count()

    total_rechazados = permisos.filter(
        estado='rechazado'
    ).count()

    contexto = {
        'permisos': permisos,

        'total_permisos':
            total_permisos,

        'total_pendientes':
            total_pendientes,

        'total_aprobados':
            total_aprobados,

        'total_rechazados':
            total_rechazados,

        'busqueda':
            busqueda,

        'tipo_seleccionado':
            tipo,

        'estado_seleccionado':
            estado,

        'tipos_permiso':
            Permiso.TIPOS,

    }

    return render(
        request,
        'gestion_permisos.html',
        contexto
    )


# =============================================================================
# APROBAR PERMISO
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def aprobar_permiso(
    request,
    permiso_id
):

    if request.method != 'POST':
        return redirect('gestion_permisos')

    permiso = get_object_or_404(
        Permiso,
        id=permiso_id
    )

    if permiso.estado != 'pendiente':

        messages.warning(
            request,
            'Esta solicitud ya fue procesada.'
        )

        return redirect('gestion_permisos')

    permiso.estado = 'aprobado'
    permiso.aprobado = True

    permiso.save()

    crear_notificacion(
        mensaje=(
            f'{request.user.username} aprobó el permiso de '
            f'{permiso.empleado.nombre_completo}.'
        ),
        tipo='permiso',
        url=reverse('gestion_permisos')
    )

    if permiso.empleado.usuario:
        crear_notificacion(
            mensaje='Tu solicitud de permiso fue aprobada.',
            tipo='permiso',
            usuario=permiso.empleado.usuario,
            url=reverse('mis_permisos')
        )

    messages.success(
        request,
        (
            f'El permiso de '
            f'{permiso.empleado.nombre_completo} '
            f'fue aprobado correctamente.'
        )
    )

    return redirect('gestion_permisos')


# =============================================================================
# RECHAZAR PERMISO
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def rechazar_permiso(
    request,
    permiso_id
):

    if request.method != 'POST':
        return redirect('gestion_permisos')

    permiso = get_object_or_404(
        Permiso,
        id=permiso_id
    )

    if permiso.estado != 'pendiente':

        messages.warning(
            request,
            'Esta solicitud ya fue procesada.'
        )

        return redirect('gestion_permisos')

    permiso.estado = 'rechazado'
    permiso.aprobado = False

    permiso.save()

    crear_notificacion(
        mensaje=(
            f'{request.user.username} rechazó el permiso de '
            f'{permiso.empleado.nombre_completo}.'
        ),
        tipo='permiso',
        url=reverse('gestion_permisos')
    )

    if permiso.empleado.usuario:
        crear_notificacion(
            mensaje='Tu solicitud de permiso fue rechazada.',
            tipo='permiso',
            usuario=permiso.empleado.usuario,
            url=reverse('mis_permisos')
        )

    messages.success(
        request,
        (
            f'El permiso de '
            f'{permiso.empleado.nombre_completo} '
            f'fue rechazado.'
        )
    )

    return redirect('gestion_permisos')


# =============================================================================
# SOLICITAR PERMISO
# =============================================================================

@login_required(login_url='login')
def solicitar_permiso(request):

    try:

        empleado = request.user.empleado

    except Empleado.DoesNotExist:

        messages.error(
            request,
            'Tu usuario no está asociado a un empleado.'
        )

        return redirect('inicio')

    if request.method == 'POST':

        formulario = PermisoForm(
            request.POST
        )

        if formulario.is_valid():

            fecha_inicio = formulario.cleaned_data['fecha_inicio']
            fecha_fin = formulario.cleaned_data['fecha_fin']

            permiso_duplicado = Permiso.objects.filter(
            empleado=empleado,
            fecha_inicio__lte=fecha_fin,
            fecha_fin__gte=fecha_inicio
            ).exists()

            if permiso_duplicado:
                messages.warning(
                    request,
                    'Ya existe una solicitud de permiso que coincide con esas fechas.'
                )
                return redirect('mis_permisos')

            permiso = formulario.save(
                commit=False
            )

            permiso.empleado = empleado
            permiso.estado = 'pendiente'
            permiso.aprobado = False

            permiso.save()

            crear_notificacion(
                mensaje=(
                    f'{empleado.nombre_completo} solicitó un permiso '
                    f'de tipo {permiso.get_tipo_display()}.'
                ),
                tipo='permiso',
                url=reverse('gestion_permisos')
            )

            crear_notificacion(
                mensaje='Tu solicitud de permiso fue registrada.',
                tipo='permiso',
                usuario=request.user,
                url=reverse('mis_permisos')
            )

            messages.success(
                request,
                'Tu solicitud fue enviada correctamente.'
            )

            return redirect('mis_permisos')

        else:
            for errores in formulario.errors.values():
                for error in errores:
                    messages.error(
                        request,
                        str(error)
                    )

    else:

        formulario = PermisoForm()

    contexto = {
        'formulario': formulario,
        'empleado': empleado,
        'titulo': 'Solicitar permiso',

    }

    return render(
        request,
        'solicitar_permiso.html',
        contexto
    )


# =============================================================================
# MIS PERMISOS
# =============================================================================

@login_required(login_url='login')
def mis_permisos(request):

    try:

        empleado = request.user.empleado

    except Empleado.DoesNotExist:

        messages.error(
            request,
            'Tu usuario no está asociado a un empleado.'
        )

        return redirect('inicio')

    permisos = (
        Permiso.objects
        .filter(
            empleado=empleado
        )
        .order_by('-fecha_inicio')
    )

    contexto = {
        'empleado': empleado,
        'permisos': permisos,
        'titulo': 'Mis permisos',

    }

    return render(
        request,
        'mis_permisos.html',
        contexto
    )

# =============================================================================
# GESTIÓN DE NÓMINA - RRHH / GERENCIA
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def gestion_nomina(request):

    liquidaciones = (
        Salario.objects
        .select_related('empleado')
        .all()
    )

    busqueda = request.GET.get(
        'busqueda',
        ''
    )

    estado_pago = request.GET.get(
        'estado_pago',
        ''
    )

    if busqueda:

        liquidaciones = (
            liquidaciones.filter(
                empleado__nombre_completo__icontains=busqueda
            )
        )

    if estado_pago == 'pagado':

        liquidaciones = (
            liquidaciones.filter(
                pagado=True
            )
        )

    elif estado_pago == 'pendiente':

        liquidaciones = (
            liquidaciones.filter(
                pagado=False
            )
        )

    liquidaciones = liquidaciones.order_by(
        '-mes_ano',
        'empleado__nombre_completo'
    )

    total_liquidaciones = (
        liquidaciones.count()
    )

    total_pagadas = (
        liquidaciones.filter(
            pagado=True
        ).count()
    )

    total_pendientes = (
        liquidaciones.filter(
            pagado=False
        ).count()
    )

    total_neto = (
        liquidaciones.aggregate(
            total=Sum('neto')
        )['total']
        or 0
    )

    puede_gestionar = (
        request.user.is_superuser
        or request.user.groups.filter(
            name='RRHH'
        ).exists()
    )

    contexto = {
        'liquidaciones':
            liquidaciones,

        'total_liquidaciones':
            total_liquidaciones,

        'total_pagadas':
            total_pagadas,

        'total_pendientes':
            total_pendientes,

        'total_neto':
            total_neto,

        'busqueda':
            busqueda,

        'estado_pago_seleccionado':
            estado_pago,

        'puede_gestionar':
            puede_gestionar,

    }

    return render(
        request,
        'gestion_nomina.html',
        contexto
    )


# =============================================================================
# CREAR LIQUIDACIÓN
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def exportar_nomina_excel(request):
    """Descarga las liquidaciones filtradas sin modificar empleados ni pagos.

    Los decoradores exigen sesión y el rol autorizado: superusuario, RRHH
    o GERENTES. Sin filtros incluye todos los registros de Salario;
    los empleados sin liquidaciones no generan filas en este reporte.
    """

    # Obtiene también el empleado en la misma consulta para evitar consultas por fila.
    liquidaciones = (
        Salario.objects
        .select_related('empleado')
        .all()
    )

    # Lee los mismos filtros GET que utiliza la pantalla de nómina.
    busqueda = request.GET.get(
        'busqueda',
        ''
    )

    estado_pago = request.GET.get(
        'estado_pago',
        ''
    )

    # Filtra por nombre y estado; un estado desconocido no restringe los resultados.
    if busqueda:

        liquidaciones = (
            liquidaciones.filter(
                empleado__nombre_completo__icontains=busqueda
            )
        )

    if estado_pago == 'pagado':

        liquidaciones = (
            liquidaciones.filter(
                pagado=True
            )
        )

    elif estado_pago == 'pendiente':

        liquidaciones = (
            liquidaciones.filter(
                pagado=False
            )
        )

    # Mantiene el orden de la pantalla: periodo reciente primero y luego nombre.
    liquidaciones = liquidaciones.order_by(
        '-mes_ano',
        'empleado__nombre_completo'
    )

    # Crea el archivo en memoria y define las diez columnas del reporte.
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Nómina'

    hoja.append([
        'Empleado',
        'DNI',
        'Departamento',
        'Cargo',
        'Periodo',
        'Salario base',
        'Bonificación',
        'Descuentos',
        'Neto',
        'Estado de pago',
    ])

    # Destaca y centra los encabezados, incluso cuando no hay resultados.
    for celda in hoja[1]:

        celda.font = Font(bold=True)
        celda.alignment = Alignment(
            horizontal='center'
        )

    # Escribe una fila por liquidación; conserva fechas e importes como valores nativos.
    for liquidacion in liquidaciones:

        hoja.append([
            liquidacion.empleado.nombre_completo,
            liquidacion.empleado.dni or '',
            liquidacion.empleado.departamento,
            liquidacion.empleado.cargo,
            liquidacion.mes_ano,
            liquidacion.salario_base,
            liquidacion.bonificacion,
            liquidacion.descuentos,
            liquidacion.neto,
            'Pagado' if liquidacion.pagado else 'Pendiente',
        ])

        fila = hoja.max_row

        # Conserva ceros iniciales del DNI y evita interpretar nombres como fórmulas.
        for columna in range(1, 5):

            hoja.cell(
                row=fila,
                column=columna
            ).data_type = 's'

        # Muestra mes/año sin convertir la fecha en texto.
        hoja.cell(
            row=fila,
            column=5
        ).number_format = 'mm/yyyy'

        # F-I: formato monetario visual; no redondea el valor almacenado.
        for columna in range(6, 10):

            hoja.cell(
                row=fila,
                column=columna
            ).number_format = '$#,##0'

    # Anchos fijos legibles para nombres, identificadores e importes.
    anchos = {
        'A': 35,
        'B': 20,
        'C': 25,
        'D': 30,
        'E': 15,
        'F': 20,
        'G': 20,
        'H': 20,
        'I': 20,
        'J': 20,
    }

    for columna, ancho in anchos.items():

        hoja.column_dimensions[columna].width = ancho

    # El tipo MIME identifica un Excel; Content-Disposition fuerza su descarga.
    respuesta = HttpResponse(
        content_type=(
            'application/vnd.openxmlformats-officedocument.'
            'spreadsheetml.sheet'
        )
    )

    respuesta['Content-Disposition'] = (
        'attachment; filename="reporte_nomina.xlsx"'
    )

    # Serializa el libro directamente en la respuesta, sin guardar archivos en disco.
    libro.save(respuesta)

    return respuesta


@login_required(login_url='login')
@user_passes_test(
    usuario_autorizado,
    login_url='login'
)
def exportar_nomina_pdf(request):
    """Descarga la nómina filtrada en PDF sin modificar empleados ni pagos."""

    # Importaciones locales: la dependencia PDF se usa solo en esta descarga.
    from pathlib import Path
    from xml.sax.saxutils import escape
    from django.utils import timezone
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, LongTable, Table, TableStyle,
    )

    # Conserva los filtros y el orden utilizados por la pantalla y el Excel.
    liquidaciones = Salario.objects.select_related('empleado').all()
    busqueda = request.GET.get('busqueda', '')
    estado_pago = request.GET.get('estado_pago', '')

    if busqueda:
        liquidaciones = liquidaciones.filter(
            empleado__nombre_completo__icontains=busqueda
        )

    if estado_pago == 'pagado':
        liquidaciones = liquidaciones.filter(pagado=True)
    elif estado_pago == 'pendiente':
        liquidaciones = liquidaciones.filter(pagado=False)

    liquidaciones = liquidaciones.order_by(
        '-mes_ano', 'empleado__nombre_completo'
    )

    respuesta = HttpResponse(content_type='application/pdf')
    respuesta['Content-Disposition'] = (
        'attachment; filename="reporte_nomina.pdf"'
    )

    # A4 horizontal deja espacio para las diez columnas y los saltos de página.
    documento = SimpleDocTemplate(
        respuesta, pagesize=landscape(A4),
        leftMargin=24, rightMargin=24, topMargin=42, bottomMargin=38,
        title='Reporte de nómina',
    )
    # Paleta y jerarquía visual comunes para encabezados, cifras y estados.
    azul = colors.HexColor('#19364B')
    verde = colors.HexColor('#087F8C')
    texto = ParagraphStyle(
        'TextoNomina', fontName='Helvetica', fontSize=8, leading=11,
        textColor=azul,
    )
    importe = ParagraphStyle('ImporteNomina', parent=texto, alignment=2)
    neto = ParagraphStyle('NetoNomina', parent=importe, fontName='Helvetica-Bold')
    pagado = ParagraphStyle('PagadoNomina', parent=texto, textColor=colors.HexColor('#16704A'), fontName='Helvetica-Bold')
    pendiente = ParagraphStyle('PendienteNomina', parent=texto, textColor=colors.HexColor('#975B11'), fontName='Helvetica-Bold')
    resumen_estilo = ParagraphStyle('ResumenNomina', parent=texto, fontSize=11, leading=16)
    etiqueta = ParagraphStyle('EtiquetaNomina', parent=texto, fontSize=8, textColor=verde, spaceAfter=6)
    titulo = ParagraphStyle('TituloNomina', parent=texto, fontName='Helvetica-Bold', fontSize=26, leading=30)
    encabezado = ParagraphStyle(
        'EncabezadoNomina', parent=texto,
        fontName='Helvetica-Bold', textColor=colors.white,
    )

    # Paragraph ajusta textos largos; escape impide interpretarlos como etiquetas.
    elementos = [
        Paragraph('GESTIÓN DE RECURSOS HUMANOS', etiqueta),
        Paragraph('Reporte de nómina', titulo),
        Spacer(1, 8),
        Paragraph(
            'Generado: ' + timezone.localtime().strftime('%d/%m/%Y %H:%M'),
            texto,
        ),
        Paragraph(
            'Búsqueda: ' + escape(busqueda or 'Todas')
            + ' | Estado: ' + {
                'pagado': 'Pagado', 'pendiente': 'Pendiente',
            }.get(estado_pago, 'Todos'),
            texto,
        ),
        Spacer(1, 12),
    ]
    columnas = [
        'Empleado', 'DNI', 'Departamento', 'Cargo', 'Periodo',
        'Salario base', 'Bonificación', 'Descuentos', 'Neto', 'Estado de pago',
    ]
    # Los títulos monetarios se alinean con sus importes.
    encabezado_importe = ParagraphStyle('EncabezadoImporte', parent=encabezado, alignment=2)
    filas = [[
        Paragraph(nombre, encabezado_importe if 5 <= i <= 8 else encabezado)
        for i, nombre in enumerate(columnas)
    ]]
    total_neto = 0

    for liquidacion in liquidaciones:
        empleado = liquidacion.empleado
        datos = [
            empleado.nombre_completo, empleado.dni or '',
            empleado.departamento, empleado.cargo,
            liquidacion.mes_ano.strftime('%m/%Y'),
            f'${liquidacion.salario_base:,.0f}',
            f'${liquidacion.bonificacion:,.0f}',
            f'${liquidacion.descuentos:,.0f}',
            f'${liquidacion.neto:,.0f}',
            'Pagado' if liquidacion.pagado else 'Pendiente',
        ]
        # Alinea cifras a la derecha y distingue estados con texto y color.
        estilos = [texto] * 5 + [importe] * 3 + [neto, pagado if liquidacion.pagado else pendiente]
        filas.append([
            Paragraph(escape(str(valor)), estilo)
            for valor, estilo in zip(datos, estilos)
        ])
        total_neto += liquidacion.neto

    # Repite la cabecera al cambiar de página; los anchos suman el espacio útil.
    tabla = LongTable(
        filas, colWidths=[125, 65, 95, 95, 48, 75, 75, 70, 75, 70],
        repeatRows=1, hAlign='LEFT',
    )
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), azul),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F5F8')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 1), (-1, -1), 0.25, colors.HexColor('#DCE5EC')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.HexColor('#24364B')),
    ]))
    elementos.append(tabla)
    if len(filas) == 1:
        elementos.append(Paragraph('No hay liquidaciones para estos filtros.', texto))
    # Resumen destacado al inicio, calculado sobre las mismas filas exportadas.
    resumen = Table([[
        Paragraph(f'Liquidaciones: {len(filas) - 1}', resumen_estilo),
        Paragraph(f'Total neto: ${total_neto:,.0f}', resumen_estilo),
    ]], colWidths=[260, 533], hAlign='LEFT')
    resumen.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EAF4F5')),
        ('LINEBEFORE', (0, 0), (0, -1), 3, verde),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elementos[6:6] = [resumen, Spacer(1, 16)]

    # Recurso local incluido en el proyecto; no requiere red ni nuevas dependencias.
    logo = Path(__file__).resolve().parent / 'static' / 'personal' / 'logo_rrhh.png'

    def numerar_pagina(canvas, doc):
        """Añade el número de página fuera de la tabla, en el margen inferior."""
        canvas.saveState()
        ancho, alto = doc.pagesize
        # Logo en la primera página, a la derecha del título, sin deformarlo.
        # Si falta el recurso, el reporte sigue disponible sin la imagen.
        if doc.page == 1 and logo.is_file():
            canvas.drawImage(
                str(logo), ancho - 78, alto - 90,
                width=48, height=48, preserveAspectRatio=True, mask='auto',
            )
        canvas.setFillColor(verde)
        canvas.rect(24, alto - 25, ancho - 48, 3, fill=1, stroke=0)
        if doc.page > 1:
            canvas.setFont('Helvetica-Bold', 8)
            canvas.setFillColor(azul)
            canvas.drawString(24, alto - 37, 'REPORTE DE NÓMINA | Continuación')
        canvas.setStrokeColor(colors.HexColor('#DCE5EC'))
        canvas.line(24, 29, ancho - 24, 29)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(azul)
        canvas.drawString(24, 16, 'Gestión RRHH | Reporte de remuneraciones')
        canvas.drawRightString(ancho - 24, 16, f'Página {doc.page}')
        canvas.restoreState()

    # Genera el documento directamente en la respuesta de descarga.
    documento.build(
        elementos, onFirstPage=numerar_pagina, onLaterPages=numerar_pagina
    )
    return respuesta



@login_required(login_url='login')
@user_passes_test(
    usuario_rrhh,
    login_url='login'
)
def crear_liquidacion(request):

    if request.method == 'POST':

        formulario = NominaForm(
            request.POST
        )

        if formulario.is_valid():

            liquidacion = formulario.save()

            crear_notificacion(
                mensaje=(
                    f'{request.user.username} creó la liquidación de '
                    f'{liquidacion.empleado.nombre_completo}.'
                ),
                tipo='nomina',
                url=reverse('gestion_nomina')
            )

            if liquidacion.empleado.usuario:
                crear_notificacion(
                    mensaje=(
                        f'Ya está disponible tu liquidación de '
                        f'{liquidacion.mes_ano:%m/%Y}.'
                    ),
                    tipo='nomina',
                    usuario=liquidacion.empleado.usuario,
                    url=reverse('mis_liquidaciones')
                )

            messages.success(
                request,
                (
                    f'Liquidación de '
                    f'{liquidacion.empleado.nombre_completo} '
                    f'creada correctamente.'
                )
            )

            return redirect(
                'gestion_nomina'
            )

    else:

        formulario = NominaForm()

    contexto = {
        'formulario':
            formulario,

        'titulo':
            'Nueva liquidación',

    }

    return render(
        request,
        'formulario_nomina.html',
        contexto
    )


# =============================================================================
# MARCAR LIQUIDACIÓN COMO PAGADA
# =============================================================================

@login_required(login_url='login')
@user_passes_test(
    usuario_rrhh,
    login_url='login'
)
def marcar_liquidacion_pagada(
    request,
    liquidacion_id
):

    if request.method != 'POST':

        return redirect(
            'gestion_nomina'
        )

    liquidacion = get_object_or_404(
        Salario,
        id=liquidacion_id
    )

    if liquidacion.pagado:

        messages.warning(
            request,
            'Esta liquidación ya figura como pagada.'
        )

        return redirect(
            'gestion_nomina'
        )

    liquidacion.pagado = True

    liquidacion.save()

    crear_notificacion(
        mensaje=(
            f'{request.user.username} marcó como pagada la liquidación de '
            f'{liquidacion.empleado.nombre_completo}.'
        ),
        tipo='nomina',
        url=reverse('gestion_nomina')
    )

    if liquidacion.empleado.usuario:
        crear_notificacion(
            mensaje=(
                f'Tu liquidación de {liquidacion.mes_ano:%m/%Y} '
                f'fue marcada como pagada.'
            ),
            tipo='nomina',
            usuario=liquidacion.empleado.usuario,
            url=reverse('mis_liquidaciones')
        )

    messages.success(
        request,
        (
            f'La liquidación de '
            f'{liquidacion.empleado.nombre_completo} '
            f'fue marcada como pagada.'
        )
    )

    return redirect(
        'gestion_nomina'
    )

# =============================================================================
# MIS LIQUIDACIONES
# =============================================================================

@login_required(login_url='login')
def mis_liquidaciones(request):

    try:

        empleado = request.user.empleado

    except Empleado.DoesNotExist:

        messages.error(
            request,
            'Tu usuario no está asociado a un empleado.'
        )

        return redirect('inicio')

    liquidaciones = (
        Salario.objects
        .filter(
            empleado=empleado
        )
        .order_by('-mes_ano')
    )

    contexto = {
        'empleado': empleado,
        'liquidaciones': liquidaciones,
        'titulo': 'Mis liquidaciones',

    }

    return render(
        request,
        'mis_liquidaciones.html',
        contexto
    )


# =============================================================================
# NOTIFICACIONES
# =============================================================================

@login_required(login_url='login')
def ver_notificacion(request, notificacion_id):
    """Abre el destino sin cambiar el estado: la lectura se guarda mediante POST."""

    if usuario_autorizado(request.user):
        notificacion = get_object_or_404(
            Notificacion,
            id=notificacion_id,
            usuario__isnull=True
        )
    else:
        notificacion = get_object_or_404(
            Notificacion,
            id=notificacion_id,
            usuario=request.user
        )

    if notificacion.url:
        return redirect(notificacion.url)

    return redirect('inicio')


def volver_a_notificaciones(request):
    """Vuelve a una página local y permite reabrir la campana actualizada."""
    # El retorno debe permanecer en este sitio, aunque se manipule el formulario.
    destino = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        destino = reverse('inicio')
    return redirect(destino.split('#', 1)[0] + '#notificaciones')


@login_required(login_url='login')
@require_POST
def marcar_notificaciones_leidas(request):
    """Marca el buzón actual sin borrar filas; gestión conserva su buzón compartido."""

    if usuario_autorizado(request.user):
        notificaciones = Notificacion.objects.filter(
            usuario__isnull=True,
            leida=False
        )
    else:
        notificaciones = Notificacion.objects.filter(
            usuario=request.user,
            leida=False
        )

    notificaciones.update(leida=True)

    return respuesta_notificaciones(request)


def respuesta_notificaciones(request):
    """Reutiliza el contexto global y el HTML del panel tras cada operación."""
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return volver_a_notificaciones(request)
    # Misma consulta que al navegar: cuenta todos los pendientes y lista los ocho
    # más recientes, reponiendo una fila cuando se elimina una de las visibles.
    contexto = contexto_rol(request)
    # El fragmento se renderiza sin RequestContext: añadimos el token para que
    # sus nuevos formularios sigan protegidos en las siguientes acciones.
    contexto['csrf_token'] = get_token(request)
    return JsonResponse({
        'unread': contexto['notificaciones_no_leidas'],
        'html': render_to_string('includes/notification_panel.html', contexto),
    })


def notificacion_editable(request, notificacion_id):
    """Dueño del aviso personal, o gestión para un aviso general compartido."""
    alcance = Q(usuario=request.user)
    if usuario_autorizado(request.user):
        alcance |= Q(usuario__isnull=True)
    # Ser staff no basta; nunca se incluyen avisos personales de otros usuarios.
    return get_object_or_404(Notificacion.objects.filter(alcance), pk=notificacion_id)


@login_required(login_url='login')
@require_POST
def marcar_notificacion_leida(request, notificacion_id):
    """Marca un aviso autorizado; repetir el POST no altera otros registros."""
    # El alcance se comprueba antes de modificar el aviso, también para gestión.
    aviso = notificacion_editable(request, notificacion_id)
    Notificacion.objects.filter(pk=aviso.pk).update(leida=True)
    return respuesta_notificaciones(request)


@login_required(login_url='login')
@require_POST
def eliminar_notificacion(request, notificacion_id):
    """El usuario viene de la sesión, nunca de datos enviados por el navegador."""
    aviso = notificacion_editable(request, notificacion_id)
    # La búsqueda anterior limita el borrado a una sola fila del buzón autorizado.
    aviso.delete()
    return respuesta_notificaciones(request)


# =============================================================================
# AJAX - PUESTOS POR DEPARTAMENTO
# =============================================================================

@login_required(login_url='login')
def obtener_puestos_por_departamento(request):

    departamento_id = request.GET.get(
        'departamento_id'
    )

    if not departamento_id:

        return JsonResponse(
            [],
            safe=False
        )

    puestos = (
        Puesto.objects
        .filter(
            departamento_id=departamento_id
        )
        .order_by('nombre')
    )

    data = [
        {
            'nombre': puesto.nombre,
            'salario_base': float(
                puesto.salario_base
            ),
        }

        for puesto in puestos
    ]

    return JsonResponse(
        data,
        safe=False
    )


# =============================================================================
# GESTIÓN DE ASISTENCIA - RRHH / GERENCIA
# =============================================================================
@login_required(login_url='login')
@user_passes_test(
    usuario_rrhh,
    login_url='login'
)

def gestion_asistencia(request):

    asistencias = (
        Asistencia.objects
        .select_related('empleado')
        .order_by('-fecha', 'empleado__nombre_completo')
    )

    # ---------------------------------------------------------
    # FILTROS
    # ---------------------------------------------------------

    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    empleado_id = request.GET.get('empleado', '')
    departamento = request.GET.get('departamento', '')

    hoy = timezone.localdate()

    if not fecha_desde:
        fecha_desde = hoy.strftime('%Y-%m-%d')

    if not fecha_hasta:
        fecha_hasta = hoy.strftime('%Y-%m-%d')

    if fecha_desde:
        asistencias = asistencias.filter(
            fecha__gte=fecha_desde
        )

    if fecha_hasta:
        asistencias = asistencias.filter(
            fecha__lte=fecha_hasta
        )

    if empleado_id:
        asistencias = asistencias.filter(
            empleado_id=empleado_id
        )

    if departamento:
        asistencias = asistencias.filter(
            empleado__departamento=departamento
        )

    # ---------------------------------------------------------
    # OPCIONES PARA LOS FILTROS
    # ---------------------------------------------------------

    empleados = (
        Empleado.objects
        .filter(estado_laboral__iexact='activo')
        .order_by('nombre_completo')
    )

    empleados_calendario = empleados

    if empleado_id:
        empleados_calendario = empleados_calendario.filter(
            id=empleado_id
        )

    if departamento:
        empleados_calendario = empleados_calendario.filter(
            departamento=departamento
        )

    departamentos = (
        Empleado.objects
        .filter(estado_laboral__iexact='activo')
        .exclude(departamento__isnull=True)
        .exclude(departamento='')
        .values_list('departamento', flat=True)
        .distinct()
        .order_by('departamento')
    )

    # ---------------------------------------------------------
    # DATOS VISUALES DE ASISTENCIA
    # ---------------------------------------------------------
    asistencias = list(
        asistencias.order_by
        ('-fecha',
        'empleado__nombre_completo'
        )
    )

    # Feriados irrenunciables dentro del rango seleccionado
    feriados_irrenunciables = set(
        Feriado.objects.filter(
            fecha__gte=fecha_desde,
            fecha__lte=fecha_hasta,
            irrenunciable=True
        ).values_list('fecha', flat=True)
    )

    hora_salida_turno = time(17, 0)

    for asistencia in asistencias:

        asistencia.es_feriado = (
            asistencia.fecha in feriados_irrenunciables
        )

        asistencia.es_fin_semana = (
            asistencia.fecha.weekday() >= 5
            and not asistencia.es_feriado
        )

        asistencia.minutos_salida_anticipada = 0

        if (
            asistencia.hora_salida
            and asistencia.hora_salida < hora_salida_turno
        ):
            salida_programada = datetime.combine(
                asistencia.fecha,
                hora_salida_turno
            )

            salida_real = datetime.combine(
                asistencia.fecha,
                asistencia.hora_salida.replace(second=0, microsecond=0)
            )

            diferencia = salida_programada - salida_real

            asistencia.minutos_salida_anticipada = int(
                diferencia.total_seconds() / 60
            )

    # ---------------------------------------------------------
    # LÍMITE DE EDICIÓN RRHH
    # ---------------------------------------------------------

    fecha_limite_edicion = (
        timezone.localdate()
        - timedelta(days=14)
    )

    contexto = {
        'asistencias': asistencias,

        'empleados': empleados,
        'departamentos': departamentos,

        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'empleado_seleccionado': empleado_id,
        'departamento_seleccionado': departamento,

        'fecha_limite_edicion': fecha_limite_edicion,

    }

    return render(
        request,
        'gestion_asistencia.html',
        contexto
    )

# =============================================================================
# MI ASISTENCIA - EMPLEADO 
# =============================================================================

@login_required(login_url='login')
def mi_asistencia(request):

    try:
        empleado = request.user.empleado

    except Empleado.DoesNotExist:

        messages.error(
            request,
            'Tu usuario no está asociado a un empleado.'
        )

        return redirect('dashboard_empleado')

    hoy = timezone.localdate()

    asistencia_hoy = (
        Asistencia.objects
        .filter(
            empleado=empleado,
            fecha=hoy
        )
        .first()
    )

    if request.method == 'POST':

        accion = request.POST.get('accion')

        ahora = timezone.localtime()
        hora_actual = ahora.time().replace(
            microsecond=0
        )

        # ---------------------------------------------------------
        # MARCAR ENTRADA
        # ---------------------------------------------------------

        if accion == 'entrada':

            if asistencia_hoy and asistencia_hoy.hora_entrada:

                messages.warning(
                    request,
                    'Ya registraste tu entrada de hoy.'
                )

            else:

                if not asistencia_hoy:

                    asistencia_hoy = Asistencia.objects.create(
                        empleado=empleado,
                        fecha=hoy
                    )

                asistencia_hoy.hora_entrada = hora_actual

                hora_limite = time(9, 0)

                if hora_actual > hora_limite:
                    asistencia_hoy.estado = 'atraso'
                else:
                    asistencia_hoy.estado = 'presente'

                asistencia_hoy.save()

                messages.success(
                    request,
                    'Entrada registrada correctamente.'
                )

        # ---------------------------------------------------------
        # MARCAR SALIDA
        # ---------------------------------------------------------

        elif accion == 'salida':

            if not asistencia_hoy or not asistencia_hoy.hora_entrada:

                messages.error(
                    request,
                    'Debes registrar tu entrada antes de marcar la salida.'
                )

            elif asistencia_hoy.hora_salida:

                messages.warning(
                    request,
                    'Ya registraste tu salida de hoy.'
                )

            else:

                asistencia_hoy.hora_salida = hora_actual

                entrada = datetime.combine(
                    hoy,
                    asistencia_hoy.hora_entrada
                )

                salida = datetime.combine(
                    hoy,
                    asistencia_hoy.hora_salida
                )

                diferencia = salida - entrada

                asistencia_hoy.minutos_trabajados = int(
                    diferencia.total_seconds() / 60
                )

                asistencia_hoy.save()

                messages.success(
                    request,
                    'Salida registrada correctamente.'
                )

        return redirect('mi_asistencia')

    mis_asistencias = (
        Asistencia.objects
        .filter(
            empleado=empleado
        )
        .order_by('-fecha')[:30]
    )

    contexto = {
        'empleado': empleado,
        'asistencia_hoy': asistencia_hoy,
        'mis_asistencias': mis_asistencias,
    }

    return render(
        request,
        'mi_asistencia.html',
        contexto
    )