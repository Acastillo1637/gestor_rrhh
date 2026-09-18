# -----------------------------------------------------------------------------
# Lógica de las páginas del sistema de Recursos Humanos.
# -----------------------------------------------------------------------------

from django.contrib.auth.models import User, Group
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.utils import timezone
from django.db import transaction
from django.urls import reverse
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

from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages

from django.db.models import (
    Sum,
    Q,
    Count,
)

from django.http import JsonResponse

from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from .forms import (
    EmpleadoForm,
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


def contexto_rol(request):

    es_gestion = (
        request.user.is_authenticated
        and usuario_autorizado(request.user)
    )

    es_empleado = (
        request.user.is_authenticated
        and hasattr(request.user, 'empleado')
    )

    if not request.user.is_authenticated:
        notificaciones = Notificacion.objects.none()
    elif es_gestion:
        # RRHH y Gerencia ven la actividad general del sistema.
        notificaciones = Notificacion.objects.filter(
            usuario__isnull=True
        )
    else:
        # Los trabajadores solamente ven sus propias notificaciones.
        notificaciones = Notificacion.objects.filter(
            usuario=request.user
        )

    notificaciones_no_leidas = notificaciones.filter(
        leida=False
    ).count()

    ultimas_notificaciones = notificaciones[:8]

    return {
        'es_gestion': es_gestion,
        'es_empleado': es_empleado,
        'notificaciones_no_leidas': notificaciones_no_leidas,
        'ultimas_notificaciones': ultimas_notificaciones,
    }


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

        **contexto_rol(request),
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

        **contexto_rol(request),
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

        **contexto_rol(request),
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

    if request.method == 'POST':

        formulario = EmpleadoForm(
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

        formulario = EmpleadoForm()

    contexto = {
        'formulario': formulario,
        'titulo': 'Nuevo empleado',

        **contexto_rol(request),
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

        **contexto_rol(request),
    }

    return render(
        request,
        'formulario_empleado.html',
        contexto
    )


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

        **contexto_rol(request),
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

            tipo = formulario.cleaned_data['tipo']
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

        formulario = PermisoForm()

    contexto = {
        'formulario': formulario,
        'empleado': empleado,
        'titulo': 'Solicitar permiso',

        **contexto_rol(request),
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

        **contexto_rol(request),
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

        **contexto_rol(request),
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

        **contexto_rol(request),
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

        **contexto_rol(request),
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

    if not notificacion.leida:
        notificacion.leida = True
        notificacion.save(update_fields=['leida'])

    if notificacion.url:
        return redirect(notificacion.url)

    return redirect('inicio')


@login_required(login_url='login')
def marcar_notificaciones_leidas(request):

    if request.method != 'POST':
        return redirect('inicio')

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

    return redirect(
        request.POST.get('next') or 'inicio'
    )


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

        **contexto_rol(request),
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
        **contexto_rol(request),
    }

    return render(
        request,
        'mi_asistencia.html',
        contexto
    )