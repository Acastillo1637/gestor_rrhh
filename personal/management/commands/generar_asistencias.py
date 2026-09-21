from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from personal.models import (
    Empleado,
    Asistencia,
    Feriado,
    Permiso,
)


class Command(BaseCommand):
    help = "Genera los registros de asistencia faltantes"

    def handle(self, *args, **options):

        hoy = timezone.localdate()

        fecha_limite = hoy - timedelta(days=1)

        empleados_activos = list(
            Empleado.objects.filter(estado_laboral__iexact="activo")
        )

        for empleado in empleados_activos:

            if not empleado.fecha_contratacion:
                continue

            fecha_inicio = empleado.fecha_contratacion

            if fecha_inicio > fecha_limite:
                continue

            fechas_con_asistencia = set(
                Asistencia.objects.filter(
                    empleado=empleado, fecha__range=(fecha_inicio, fecha_limite)
                ).values_list("fecha", flat=True)
            )

            permisos_aprobados = list(
                Permiso.objects.filter(
                    empleado=empleado,
                    estado="aprobado",
                    fecha_inicio__lte=fecha_limite,
                    fecha_fin__gte=fecha_inicio,
                )
            )

            feriados_irrenunciables = set(
                Feriado.objects.filter(
                    fecha__range=(fecha_inicio, fecha_limite), irrenunciable=True
                ).values_list("fecha", flat=True)
            )

            self.stdout.write(
                f"{empleado.nombre_completo}: "
                f'{fecha_inicio.strftime("%d/%m/%Y")} → '
                f'{fecha_limite.strftime("%d/%m/%Y")}'
            )

            fecha_actual = fecha_inicio

            registros_nuevos = []

            while fecha_actual <= fecha_limite:

                # No se tocan, registros existentes
                if fecha_actual in fechas_con_asistencia:
                    fecha_actual += timedelta(days=1)
                    continue

                # Feriados irrenunciables
                if fecha_actual in feriados_irrenunciables:
                    registros_nuevos.append(
                        Asistencia(
                            empleado=empleado,
                            fecha=fecha_actual,
                            estado="feriado",
                            minutos_trabajados=0,
                        )
                    )

                    fecha_actual += timedelta(days=1)
                    continue

                # fin de semana
                if fecha_actual.weekday() >= 5:
                    registros_nuevos.append(
                        Asistencia(
                            empleado=empleado,
                            fecha=fecha_actual,
                            estado="descanso",
                            minutos_trabajados=0,
                        )
                    )

                    fecha_actual += timedelta(days=1)
                    continue

                # Permisos aprobados
                permiso = next(
                    (
                        permiso
                        for permiso in permisos_aprobados
                        if permiso.fecha_inicio <= fecha_actual <= permiso.fecha_fin
                    ),
                    None,
                )

                if permiso:
                    registros_nuevos.append(
                        Asistencia(
                            empleado=empleado,
                            fecha=fecha_actual,
                            estado="permiso",
                            minutos_trabajados=0,
                        )
                    )

                    fecha_actual += timedelta(days=1)
                    continue

                # Día laboral sin registro
                registros_nuevos.append(
                    Asistencia(
                        empleado=empleado,
                        fecha=fecha_actual,
                        estado="ausente",
                        minutos_trabajados=0,
                    )
                )

                fecha_actual += timedelta(days=1)

            if registros_nuevos:
                creados = Asistencia.objects.bulk_create(
                    registros_nuevos, ignore_conflicts=True
                )

                self.stdout.write(
                    f"  -> Registros preparados: {len(registros_nuevos)} | "
                    f"Procesados: {len(creados)}"
                )

        self.stdout.write(
            f'Generando asistencias hasta {fecha_limite.strftime("%d/%m/%Y")}...'
        )
