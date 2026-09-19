from .models import Notificacion


def contexto_rol(request):
    """Roles y campana disponibles en todas las plantillas con request.

    Conserva el buzón general de gestión y el buzón privado del empleado.
    El contador incluye todos los avisos sin leer, no solo los ocho recientes.
    """

    es_gestion = (
        request.user.is_authenticated
        and (
            request.user.is_superuser
            or request.user.groups.filter(name__in=['RRHH', 'GERENTES']).exists()
        )
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
