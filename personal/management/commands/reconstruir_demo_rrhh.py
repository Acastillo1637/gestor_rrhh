"""Reconstrucción explícita; la planificación nunca ejecuta escrituras."""
import csv
import json
import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, User
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q
from django.db.models.deletion import Collector
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from personal import usernames
from personal.demo_plan import ESTRUCTURA, SALARIOS_PUESTO, claves_puestos, construir_plan
from personal.models import (Asistencia, Departamento, Empleado, EmpleadoPuesto, Evaluacion,
                             Feriado, HistorialSalario, Notificacion, Permiso, Puesto, Salario)


NEGOCIO = [Asistencia, Permiso, Evaluacion, Salario, HistorialSalario, EmpleadoPuesto, Empleado, Puesto, Departamento]


def instantanea_protegida():
    cuenta = User.objects.filter(pk=1).first()
    if (cuenta is None or cuenta.username != 'rrhh' or
            User.objects.filter(username__iexact='rrhh').exclude(pk=1).exists() or
            not cuenta.is_active or not cuenta.is_staff or not cuenta.is_superuser or
            not cuenta.has_usable_password() or Empleado.objects.filter(usuario_id=1).exists()):
        raise CommandError('Cuenta protegida inconsistente: se exige ID 1, username rrhh, activa, staff, superusuario, contraseña utilizable y sin ficha Empleado.')
    # Se compara en memoria; nunca se imprime ni exporta el hash de contraseña.
    return dict(campos=User.objects.filter(pk=1).values().get(),
                grupos=list(cuenta.groups.order_by('pk').values_list('pk', flat=True)),
                permisos=list(cuenta.user_permissions.order_by('pk').values_list('pk', flat=True)),
                permisos_grupos=list(Group.permissions.through.objects.filter(group__user=cuenta).order_by('pk').values()))


class Command(BaseCommand):
    help = 'Planifica o reconstruye selectivamente la empresa demo (80 empleados). Sin --ejecutar solo lee.'

    def add_arguments(self, parser):
        modo = parser.add_mutually_exclusive_group()
        modo.add_argument('--dry-run', action='store_true')
        modo.add_argument('--ejecutar', action='store_true')
        parser.add_argument('--seed', type=int, default=2026)
        parser.add_argument('--fecha-referencia', type=date.fromisoformat, default=None)
        parser.add_argument('--confirmar', default='')
        parser.add_argument('--eliminar-usuario', action='append', default=[],
                            help='Username adicional de prueba, no vinculado, cuya eliminación se autoriza explícitamente.')

    def inventario(self, extras):
        protegido = instantanea_protegida()
        yubel = User.objects.filter(Q(pk=10) | Q(username__iexact='yubel'))
        if yubel.exists() and (yubel.count() != 1 or not yubel.filter(pk=10, username='yubel').exists()):
            raise CommandError('Identidad de yubel inconsistente (se espera ID 10 + username yubel).')
        vinculados = set(Empleado.objects.exclude(usuario=None).values_list('usuario_id', flat=True))
        eliminar = vinculados | set(yubel.values_list('pk', flat=True))
        # Cuenta inspeccionada y autorizada como demo. Un nombre parecido no basta.
        prueba = User.objects.filter(username='gerente.prueba').first()
        if prueba is not None:
            perfil_demo = (
                prueba.pk == 20 and prueba.is_active and not prueba.is_staff and not prueba.is_superuser
                and not prueba.email and not prueba.first_name and not prueba.last_name
                and set(prueba.groups.values_list('name', flat=True)) == {'GERENTES'}
                and not prueba.user_permissions.exists()
                and not Empleado.objects.filter(usuario=prueba).exists()
                and not Notificacion.objects.filter(usuario=prueba).exists()
                and not LogEntry.objects.filter(user=prueba).exists()
                and not LogEntry.objects.filter(content_type__app_label='auth', content_type__model='user', object_id=str(prueba.pk)).exists()
            )
            if not perfil_demo:
                raise CommandError('gerente.prueba no coincide con el perfil demo inspeccionado; revisar antes de borrar.')
            eliminar.add(prueba.pk)
        for nombre in extras:
            usuario = User.objects.filter(username=nombre).first()
            if usuario is None:
                raise CommandError(f'Usuario adicional inexistente: {nombre}')
            eliminar.add(usuario.pk)
        if 1 in eliminar:
            raise CommandError('La cuenta rrhh no puede formar parte de la limpieza.')
        if User.objects.filter(pk__in=eliminar, is_superuser=True).exclude(pk=10).exists():
            raise CommandError('Hay otro superusuario entre las cuentas seleccionadas; requiere revisión previa.')
        for modelo in NEGOCIO:
            for relacion in modelo._meta.related_objects:
                if relacion.related_model not in NEGOCIO:
                    raise CommandError(f'Dependencia de negocio no prevista: {relacion.related_model._meta.label}')
        usuarios = list(User.objects.filter(pk__in=eliminar).order_by('pk').values('id', 'username'))
        # Inspección de cascadas: un modelo nuevo desconocido obliga a revisar el comando.
        collector = Collector(using='default')
        collector.collect(User.objects.filter(pk__in=eliminar))
        permitidos = {User, LogEntry, Notificacion, User.groups.through, User.user_permissions.through}
        encontrados = set(collector.data) | {qs.model for qs in collector.fast_deletes}
        if encontrados - permitidos:
            raise CommandError('Dependencias de User no previstas: ' + ', '.join(m._meta.label for m in encontrados - permitidos))
        notificaciones = Notificacion.objects.filter(Q(usuario__isnull=True) | Q(usuario_id__in=eliminar))
        # Invalidación global autorizada, sin decodificar ni cambiar ninguna cuenta.
        sesiones = list(Session.objects.order_by('pk').values_list('pk', flat=True))
        return protegido, eliminar, dict(
            eliminar={m._meta.label: m.objects.count() for m in NEGOCIO},
            usuarios_eliminar=usuarios,
            usuarios_conservar=list(User.objects.exclude(pk__in=eliminar).order_by('pk').values('id', 'username')),
            notificaciones_eliminar=notificaciones.count(),
            auditoria_archivar=LogEntry.objects.count(),
            auditoria_eliminar=LogEntry.objects.filter(user_id__in=eliminar).count(),
            dependencias_yubel=dict(auditoria=LogEntry.objects.filter(user_id=10).count(),
                                   notificaciones=Notificacion.objects.filter(usuario_id=10).count(),
                                   empleados=Empleado.objects.filter(usuario_id=10).count()),
            sesiones_eliminar=sesiones,
        )

    def handle(self, *args, **options):
        referencia = options['fecha_referencia'] or timezone.localdate()
        if referencia.year < 2000 or referencia > timezone.localdate():
            raise CommandError('Use una fecha de referencia entre 2000-01-01 y la fecha local actual.')
        protegido, eliminar, inventario = self.inventario(options['eliminar_usuario'])
        feriados = set(Feriado.objects.filter(irrenunciable=True).values_list('fecha', flat=True))
        plan = construir_plan(options['seed'], referencia, feriados)
        inventario_publico = dict(inventario, sesiones_eliminar=len(inventario['sesiones_eliminar']))
        cantidades_nomina = [len(p['nominas']) for p in plan]
        resumen = dict(seed=options['seed'], fecha_referencia=str(referencia), inventario=inventario_publico,
                       crear=dict(empleados=len(plan), usuarios=len(plan), departamentos=len(ESTRUCTURA),
                                  estados=dict(Counter(p['estado'] for p in plan)),
                                  roles=dict(Counter(p['rol'] for p in plan)),
                                  asignaciones=sum(2 if p['ascenso'] else 1 for p in plan),
                                  puestos=len(claves_puestos(plan)),
                                  historial_salarial=sum(bool(p['ascenso']) for p in plan),
                                  asistencias=sum(len(p['asistencias']) for p in plan),
                                  permisos=sum(len(p['permisos']) for p in plan),
                                  liquidaciones=sum(len(p['nominas']) for p in plan),
                                  evaluaciones=sum(len(p['evaluaciones']) for p in plan), notificaciones=81),
                       distribucion=[dict(departamento=n, activos=a, historicos=len(h)) for n, a, h, *_ in ESTRUCTURA],
                       detalle=dict(
                           sesiones='Se invalidarán TODAS las sesiones Django, incluida rrhh, sin cambiar atributos de User.',
                           usuarios_finales=len(inventario['usuarios_conservar']) + 80,
                           liquidaciones_por_empleado={f'{a}-{b}': sum(a <= n <= b for n in cantidades_nomina)
                                                       for a, b in [(1, 3), (4, 6), (7, 9), (10, 12)]},
                           maximo_liquidaciones=max(cantidades_nomina),
                           permisos_estados=dict(Counter(q['estado'] for p in plan for q in p['permisos'])),
                           permisos_tipos=dict(Counter(q['tipo'] for p in plan for q in p['permisos'])),
                           pendientes_departamento=dict(Counter(p['departamento'] for p in plan for q in p['permisos'] if q['estado'] == 'pendiente')),
                           evaluaciones_por_empleado=dict(Counter(len(p['evaluaciones']) for p in plan))),
                       conservar='rrhh íntegro, usuarios no seleccionados, grupos/permisos existentes, feriados, content types y migraciones')
        self.stdout.write(json.dumps(resumen, ensure_ascii=False, indent=2))
        if not options['ejecutar']:
            self.stdout.write('SIMULACIÓN: no se ha escrito en BD ni archivos. Los usernames se resolverán contra las cuentas supervivientes mediante personal.usernames.')
            return
        if options['confirmar'] != 'RECONSTRUIR_DEMO_RRHH':
            raise CommandError('La ejecución real exige --confirmar RECONSTRUIR_DEMO_RRHH. Revise primero el dry-run y respalde PostgreSQL.')
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError('Hay migraciones pendientes. No se ejecutará la reconstrucción.')
        carpeta = Path(settings.BASE_DIR) / '.demo_rrhh' / uuid.uuid4().hex
        credenciales = carpeta / 'credenciales_demo_rrhh.csv'
        try:
            with transaction.atomic():
                # Modo mantenimiento: evita cambios concurrentes en las tablas reconstruidas.
                if connection.vendor == 'postgresql':
                    tablas = [m._meta.db_table for m in NEGOCIO + [User, Group, LogEntry, Notificacion, Feriado, Session,
                              User.groups.through, User.user_permissions.through, Group.permissions.through]]
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '10s'")
                        cursor.execute('LOCK TABLE ' + ', '.join(connection.ops.quote_name(t) for t in sorted(set(tablas))) + ' IN ACCESS EXCLUSIVE MODE')
                protegido_actual, eliminar_actual, inventario_actual = self.inventario(options['eliminar_usuario'])
                if protegido_actual != protegido or eliminar_actual != eliminar or inventario_actual != inventario:
                    raise CommandError('El inventario cambió; repita la simulación.')
                if set(Feriado.objects.filter(irrenunciable=True).values_list('fecha', flat=True)) != feriados:
                    raise CommandError('El calendario cambió; repita la simulación.')
                carpeta.mkdir(parents=True, exist_ok=False)
                # Archivo previo al borrado; no contiene contraseñas ni hashes de User.
                auditoria = list(LogEntry.objects.order_by('pk').values())
                (carpeta / 'auditoria_anterior.json').write_text(json.dumps(auditoria, default=str, ensure_ascii=False, indent=2), encoding='utf-8')
                (carpeta / 'plan.json').write_text(json.dumps(resumen, default=str, ensure_ascii=False, indent=2), encoding='utf-8')
                self.limpiar(eliminar, inventario['sesiones_eliminar'])
                filas = self.poblar(plan, options['seed'], referencia)
                self.validar(plan, protegido)
                with credenciales.open('x', encoding='utf-8-sig', newline='') as salida:
                    writer = csv.DictWriter(salida, fieldnames=list(filas[0]))
                    writer.writeheader()
                    writer.writerows(filas)
        except Exception:
            # Un CSV no debe aparentar una carga exitosa cuando la transacción falló.
            if credenciales.exists():
                credenciales.unlink()
            if carpeta.exists():
                (carpeta / 'FALLO.txt').write_text('La reconstrucción no terminó correctamente. La auditoría es una copia previa; no usar como confirmación de carga.', encoding='utf-8')
            raise
        (carpeta / 'COMPLETADO.txt').write_text('Transacción confirmada.', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Reconstrucción confirmada. Credenciales DEMO: {credenciales}'))
        elegidos = [next(f for f in filas if f['nombre_completo'] == 'Amaro Castillo Ahumada')]
        for rol in ['RRHH', 'GERENTES', 'EMPLEADO']:
            elegidos.append(next(f for f in filas if f['rol'] == rol and f['activo'] and f not in elegidos))
        for fila in elegidos:
            self.stdout.write(f"{fila['nombre_completo']} | {fila['rol']} | {fila['username']} | {fila['password_demo']}")
        self.stdout.write('Contraseñas exclusivamente DEMO; no utilizar estas credenciales en producción.')

    def limpiar(self, eliminar, sesiones):
        LogEntry.objects.filter(user_id__in=eliminar).delete()
        Notificacion.objects.filter(Q(usuario__isnull=True) | Q(usuario_id__in=eliminar)).delete()
        Session.objects.filter(pk__in=sesiones).delete()
        Departamento.objects.update(jefe=None)
        for modelo in NEGOCIO:
            modelo.objects.all().delete()
        User.objects.filter(pk__in=eliminar).delete()

    def poblar(self, plan, seed, referencia):
        grupos = {rol: Group.objects.get_or_create(name=rol)[0] for rol in ['GERENTES', 'RRHH', 'EMPLEADO']}
        departamentos = {nombre: Departamento.objects.create(nombre=nombre, descripcion='Empresa ficticia de demostración', presupuesto=0)
                         for nombre, *_ in ESTRUCTURA}
        puestos = {}

        def obtener_puesto(departamento, nombre, nivel):
            clave = (departamento.pk, nombre, nivel)
            if clave not in puestos:
                puestos[clave] = Puesto.objects.create(departamento=departamento, nombre=nombre,
                                                       nivel=nivel, salario_base=SALARIOS_PUESTO[nivel])
            return puestos[clave]
        filas = []
        password = f'DemoRRHH!{seed}'
        for dato in plan:
            departamento = departamentos[dato['departamento']]
            puesto = obtener_puesto(departamento, dato['cargo'], dato['nivel'])
            username = usernames.generar_username_unico(dato['nombre'], dato['paterno'], dato['materno'])
            usuario = User.objects.create_user(username=username, password=password, email=f'{username}@empresa.example',
                                               is_staff=False, is_superuser=False, is_active=dato['estado'] == 'activo')
            usuario.groups.add(grupos[dato['rol']])
            empleado = Empleado.objects.create(usuario=usuario,
                nombre_completo=f"{dato['nombre']} {dato['paterno']} {dato['materno']}",
                email=usuario.email, dni=f"DEMO-{dato['indice']:04d}",
                fecha_nacimiento=dato['nacimiento'], fecha_contratacion=dato['ingreso'],
                genero='no_indica', telefono='', direccion=f"Dirección ficticia {dato['indice']}, Santiago",
                estado_laboral=dato['estado'], cargo=dato['cargo'], departamento=dato['departamento'], salario_mensual=dato['sueldo'])
            if dato['ascenso']:
                anterior = obtener_puesto(departamento, 'Asistente ' + dato['cargo'], 'junior')
                EmpleadoPuesto.objects.create(empleado=empleado, puesto=anterior, fecha_inicio=dato['ingreso'],
                                             fecha_fin=dato['ascenso']-timedelta(days=1), es_actual=False)
                historia = HistorialSalario.objects.create(empleado=empleado, salario_anterior=dato['previo'], salario_nuevo=dato['sueldo'], modificado_por='Reconstrucción DEMO')
                HistorialSalario.objects.filter(pk=historia.pk).update(fecha_modificacion=timezone.make_aware(datetime.combine(dato['ascenso'], time(12))))
            EmpleadoPuesto.objects.create(empleado=empleado, puesto=puesto, fecha_inicio=dato['ascenso'] or dato['ingreso'],
                                         fecha_fin=dato['salida'], es_actual=dato['estado'] == 'activo')
            if dato['jefe']:
                departamento.jefe = empleado
                departamento.save(update_fields=['jefe'])
            Permiso.objects.bulk_create([Permiso(empleado=empleado, **p) for p in dato['permisos']])
            Salario.objects.bulk_create([Salario(empleado=empleado, **p) for p in dato['nominas']])
            Evaluacion.objects.bulk_create([Evaluacion(empleado=empleado, **p) for p in dato['evaluaciones']])
            Asistencia.objects.bulk_create([Asistencia(empleado=empleado, fecha=dia, estado=estado,
                hora_entrada=time(9, 10) if estado == 'atraso' else (time(9) if estado == 'presente' else None),
                hora_salida=time(18) if estado in ['presente', 'atraso'] else None,
                minutos_trabajados=530 if estado == 'atraso' else (540 if estado == 'presente' else 0))
                for dia, estado in dato['asistencias']], batch_size=500)
            aviso = Notificacion.objects.create(usuario=usuario, mensaje='Tu información histórica de demostración está disponible.', tipo='sistema', url='/mi-cuenta/', leida=dato['estado'] != 'activo')
            Notificacion.objects.filter(pk=aviso.pk).update(fecha=timezone.make_aware(datetime.combine(dato['salida'] or referencia, time(12))))
            filas.append(dict(nombre_completo=empleado.nombre_completo, departamento=dato['departamento'], cargo=dato['cargo'],
                              rol=dato['rol'], username=username, password_demo=password, activo=usuario.is_active))
        Notificacion.objects.create(mensaje='Empresa DEMO reconstruida: 80 empleados, 73 activos.', tipo='sistema', url='/empleados/')
        return filas

    def validar(self, plan, protegido):
        if instantanea_protegida() != protegido:
            raise CommandError('La cuenta protegida cambió: rollback obligatorio.')
        if Counter(Empleado.objects.values_list('estado_laboral', flat=True)) != Counter(activo=73, renuncio=4, despedido=3):
            raise CommandError('Distribución de empleados incorrecta.')
        if Session.objects.exists():
            raise CommandError('Quedan sesiones antiguas: rollback obligatorio.')
        if Puesto.objects.count() != len(claves_puestos(plan)):
            raise CommandError('Catálogo de puestos inconsistente.')
        for dato in plan:
            empleado = Empleado.objects.select_related('usuario').get(dni=f"DEMO-{dato['indice']:04d}")
            actual = empleado.historial_puestos.filter(es_actual=True)
            if actual.count() != (1 if dato['estado'] == 'activo' else 0):
                raise CommandError('Asignaciones actuales inconsistentes.')
            if empleado.usuario.is_staff or empleado.usuario.is_superuser or empleado.usuario.is_active != (dato['estado'] == 'activo'):
                raise CommandError('Acceso de usuario demo inconsistente.')
            if set(empleado.usuario.groups.values_list('name', flat=True)) != {dato['rol']}:
                raise CommandError('Rol demo inconsistente.')
            if dato['jefe'] and not Departamento.objects.filter(nombre=dato['departamento'], jefe=empleado).exists():
                raise CommandError('Jefatura inconsistente.')
            if dato['salida'] and empleado.asistencias.filter(fecha__gt=dato['salida']).exists():
                raise CommandError('Asistencia posterior a la salida.')
            if empleado.asistencias.filter(fecha__lt=dato['ingreso']).exists() or empleado.salarios.filter(mes_ano__lt=dato['ingreso']).exists():
                raise CommandError('Historia anterior a contratación.')
            meses = [(s.mes_ano.year, s.mes_ano.month) for s in empleado.salarios.all()]
            if len(meses) > 12 or len(meses) != len(set(meses)):
                raise CommandError('Liquidaciones mensuales inconsistentes.')
            if dato['salida'] and empleado.salarios.filter(mes_ano__gt=dato['salida']).exists():
                raise CommandError('Liquidación posterior a la salida.')
            if (empleado.asistencias.count() != len(dato['asistencias']) or
                    empleado.salarios.count() != len(dato['nominas']) or
                    empleado.permisos.count() != len(dato['permisos']) or
                    empleado.evaluaciones.count() != len(dato['evaluaciones'])):
                raise CommandError('Faltan registros históricos planificados.')
