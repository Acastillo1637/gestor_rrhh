from django.utils import timezone

from .models import Empleado, EmpleadoPuesto
from .rendimiento import roles_usuario


def departamento_actual(empleado):
    """Resuelve relaciones reales y deniega historiales ambiguos."""
    puestos = list(empleado.historial_puestos.filter(es_actual=True)
                   .select_related('puesto__departamento')[:2])
    return _departamento_valido(puestos, timezone.localdate())


def _departamento_valido(puestos, hoy):
    if len(puestos) != 1:
        return None
    actual = puestos[0]
    if actual.fecha_fin is not None or actual.fecha_inicio > hoy:
        return None
    return actual.puesto.departamento


def puede_resolver_permiso(user, permiso):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser or user.groups.filter(name='RRHH').exists():
        return True
    if not user.groups.filter(name='GERENTES').exists():
        return False
    gerente = Empleado.objects.filter(usuario=user, estado_laboral='activo').first()
    if gerente is None or gerente.pk == permiso.empleado_id:
        return False
    departamento = departamento_actual(gerente)
    if departamento is None or departamento.jefe_id != gerente.pk:
        return False
    solicitante = departamento_actual(permiso.empleado)
    return solicitante is not None and solicitante.pk == departamento.pk


def preparar_acciones_permisos(user, permisos):
    """Resuelve solo la página visible, sin cachear decisiones entre requests.

    La comprobación individual de los endpoints sigue consultando el estado actual.
    """
    for permiso in permisos:
        permiso.puede_resolver = False
    pendientes = [p for p in permisos if p.estado == 'pendiente']
    if not pendientes or not user.is_authenticated or not user.is_active:
        return
    roles = roles_usuario(user) if not user.is_superuser else frozenset()
    if user.is_superuser or 'RRHH' in roles:
        for permiso in pendientes:
            permiso.puede_resolver = True
        return
    if 'GERENTES' not in roles:
        return
    try:
        gerente = user.empleado
    except Empleado.DoesNotExist:
        return
    if gerente.estado_laboral != 'activo':
        return
    ids = {p.empleado_id for p in pendientes} | {gerente.pk}
    puestos = {}
    for puesto in EmpleadoPuesto.objects.filter(
        empleado_id__in=ids, es_actual=True,
    ).select_related('puesto__departamento').order_by():
        puestos.setdefault(puesto.empleado_id, []).append(puesto)
    hoy = timezone.localdate()

    def departamento(empleado_id):
        return _departamento_valido(puestos.get(empleado_id, []), hoy)

    propio = departamento(gerente.pk)
    if propio is None or propio.jefe_id != gerente.pk:
        return
    for permiso in pendientes:
        destino = departamento(permiso.empleado_id)
        permiso.puede_resolver = (
            permiso.empleado_id != gerente.pk
            and destino is not None and destino.pk == propio.pk
        )
