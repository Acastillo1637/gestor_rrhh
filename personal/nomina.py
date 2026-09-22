"""Preparación y generación mensual sin reemplazar liquidaciones existentes."""
from calendar import monthrange
from django.db import transaction, IntegrityError
from django.urls import reverse
from .models import Empleado, Salario, Notificacion


def preparar_nomina(periodo):
    fin = periodo.replace(day=monthrange(periodo.year, periodo.month)[1])
    existentes = set(Salario.objects.filter(mes_ano__year=periodo.year,
        mes_ano__month=periodo.month).values_list('empleado_id', flat=True))
    pendientes, omitidos = [], []
    for empleado in Empleado.objects.filter(estado_laboral__iexact='activo').order_by('pk'):
        motivo = None
        if empleado.pk in existentes:
            motivo = 'Ya tiene liquidación en este mes.'
        elif not empleado.fecha_contratacion:
            motivo = 'Falta la fecha de contratación.'
        elif empleado.fecha_contratacion > fin:
            motivo = 'Fue contratado después del mes seleccionado.'
        elif empleado.salario_mensual < 0:
            motivo = 'El salario mensual es negativo.'
        if motivo:
            omitidos.append({'empleado': empleado, 'motivo': motivo})
        else:
            pendientes.append(empleado)
    return pendientes, omitidos


@transaction.atomic
def generar_nomina_mensual(periodo, usuario):
    # Las solicitudes de generación se serializan por empleado en PostgreSQL.
    # Se vuelve a calcular al confirmar: la vista previa no reserva ni guarda datos.
    list(Empleado.objects.select_for_update().filter(
        estado_laboral__iexact='activo').order_by('pk').values_list('pk', flat=True))
    pendientes, omitidos = preparar_nomina(periodo)
    creadas = 0
    for empleado in pendientes:
        try:
            # El savepoint permite comprobar un duplicado concurrente sin invalidar el lote.
            with transaction.atomic():
                Salario.objects.create(empleado=empleado, mes_ano=periodo.replace(day=1),
                    salario_base=empleado.salario_mensual, bonificacion=0,
                    descuentos=0, pagado=False)
        except IntegrityError:
            if not Salario.objects.filter(empleado=empleado, mes_ano__year=periodo.year,
                    mes_ano__month=periodo.month).exists():
                raise
            omitidos.append({'empleado': empleado, 'motivo': 'Ya tiene liquidación en este mes.'})
            continue
        creadas += 1
        if empleado.usuario_id:
            Notificacion.objects.create(usuario_id=empleado.usuario_id, tipo='nomina',
                mensaje=f'Ya está disponible tu liquidación de {periodo:%m/%Y}.',
                url=reverse('mis_liquidaciones'))
    if creadas:
        Notificacion.objects.create(tipo='nomina',
            mensaje=f'{usuario.username} generó {creadas} liquidaciones de {periodo:%m/%Y}.',
            url=reverse('gestion_nomina'))
    return creadas, len(omitidos)
