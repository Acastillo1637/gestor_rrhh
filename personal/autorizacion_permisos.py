from django.utils import timezone

from .models import Empleado


def departamento_actual(empleado):
    """Resuelve relaciones reales y deniega historiales ambiguos."""
    puestos = list(empleado.historial_puestos.filter(es_actual=True)
                   .select_related('puesto__departamento')[:2])
    if len(puestos) != 1:
        return None
    actual = puestos[0]
    if actual.fecha_fin is not None or actual.fecha_inicio > timezone.localdate():
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
