from datetime import date

from django.core.management.base import BaseCommand

from personal.models import Feriado, Asistencia, Empleado


class Command(BaseCommand):
    help = 'Carga los feriados nacionales de Chile para 2026'

    def handle(self, *args, **options):

        feriados = [
            (date(2026, 1, 1), 'Año Nuevo', True),
            (date(2026, 4, 3), 'Viernes Santo', False),
            (date(2026, 4, 4), 'Sábado Santo', False),
            (date(2026, 5, 1), 'Día del Trabajo', True),
            (date(2026, 5, 21), 'Día de las Glorias Navales', False),
            (date(2026, 6, 21), 'Día Nacional de los Pueblos Indígenas', False),
            (date(2026, 6, 29), 'San Pedro y San Pablo', False),
            (date(2026, 7, 16), 'Día de la Virgen del Carmen', False),
            (date(2026, 8, 15), 'Asunción de la Virgen', False),
            (date(2026, 9, 18), 'Independencia Nacional', True),
            (date(2026, 9, 19), 'Día de las Glorias del Ejército', True),
            (date(2026, 10, 12), 'Encuentro de Dos Mundos', False),
            (date(2026, 10, 31), 'Día Nacional de las Iglesias Evangélicas', False),
            (date(2026, 11, 1), 'Día de Todos los Santos', False),
            (date(2026, 12, 8), 'Inmaculada Concepción', False),
            (date(2026, 12, 25), 'Navidad', True),
        ]

        creados = 0
        actualizados = 0

        for fecha, nombre, irrenunciable in feriados:

            _, creado = Feriado.objects.update_or_create(
                fecha=fecha,
                defaults={
                    'nombre': nombre,
                    'irrenunciable': irrenunciable,
                }
            )

            if creado:
                creados += 1
            else:
                actualizados += 1

        # ---------------------------------------------------------
        # REGISTRAR FERIADOS IRRENUNCIABLES EN ASISTENCIA
        # ---------------------------------------------------------

        empleados_activos = list(
            Empleado.objects.filter(
                estado_laboral__iexact='activo'
            )
        )

        fechas_irrenunciables = [
            fecha
            for fecha, nombre, irrenunciable in feriados
            if irrenunciable
        ]

        registros_existentes = set(
            Asistencia.objects.filter(
                fecha__in=fechas_irrenunciables,
                empleado__in=empleados_activos
            ).values_list(
                'empleado_id',
                'fecha'
            )
        )

        nuevas_asistencias = []

        for empleado in empleados_activos:
            for fecha in fechas_irrenunciables:

                if (empleado.id, fecha) not in registros_existentes:
                    nuevas_asistencias.append(
                        Asistencia(
                            empleado=empleado,
                            fecha=fecha,
                            estado='feriado',
                            minutos_trabajados=0
                        )
                    )

        Asistencia.objects.bulk_create(
            nuevas_asistencias
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Feriados cargados correctamente. '
                f'Creados: {creados} | Actualizados: {actualizados}'
            )
        )