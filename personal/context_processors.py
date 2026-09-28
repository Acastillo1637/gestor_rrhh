from .models import Notificacion
from .rendimiento import roles_usuario


def contexto_rol(request):
    """Roles y campana disponibles en todas las plantillas con request.

    Conserva el buzón general de gestión y el buzón privado del empleado.
    El contador incluye todos los avisos sin leer, no solo los ocho recientes.
    """

    roles = roles_usuario(request.user)
    es_gestion = (
        request.user.is_authenticated
        and (
            request.user.is_superuser
            or bool(roles & {'RRHH', 'GERENTES'})
        )
    )

    es_gerente = (
    request.user.is_authenticated
    and not request.user.is_superuser
    and 'GERENTES' in roles
    )

    es_empleado = (
        request.user.is_authenticated
        and hasattr(request.user, 'empleado')
    )

    puede_modificar_buzon = not es_gestion or (
        request.user.is_superuser
        or 'RRHH' in roles
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
        'tiene_grupos': bool(roles),
        'es_gestion': es_gestion,
        'es_gerente': es_gerente,
        'es_empleado': es_empleado,
        'puede_modificar_buzon': puede_modificar_buzon,
        'notificaciones_no_leidas': notificaciones_no_leidas,
        'ultimas_notificaciones': ultimas_notificaciones,
    }
