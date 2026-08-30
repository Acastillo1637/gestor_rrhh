# -----------------------------------------------------------------------------
# Comando personalizado que crea grupos, usuarios de demostración y datos iniciales de empleados.
# -----------------------------------------------------------------------------
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from personal.models import Empleado


class Command(BaseCommand):
    help = 'Carga datos iniciales de empleados y usuarios'

    def handle(self, *args, **kwargs):

        # -------------------------------------------------
        # CREAR GRUPOS
        # -------------------------------------------------

        grupo_rrhh, creado = Group.objects.get_or_create(name='RRHH')
        grupo_gerente, creado = Group.objects.get_or_create(name='GERENTES')

        # RRHH puede agregar y modificar empleados
        permisos_rrhh = Permission.objects.filter(
            codename__in=[
                'view_empleado',
                'add_empleado',
                'change_empleado',
                'view_historialsalario',
            ]
        )

        grupo_rrhh.permissions.set(permisos_rrhh)

        # Gerente solamente puede visualizar
        permisos_gerente = Permission.objects.filter(
            codename__in=[
                'view_empleado',
                'view_historialsalario',
            ]
        )

        grupo_gerente.permissions.set(permisos_gerente)

        # -------------------------------------------------
        # CREAR USUARIO RRHH
        # -------------------------------------------------

        usuario_rrhh, creado = User.objects.get_or_create(
            username='rrhh'
        )

        usuario_rrhh.set_password('Rrhh2026!')
        usuario_rrhh.is_staff = True
        usuario_rrhh.is_active = True
        usuario_rrhh.save()

        usuario_rrhh.groups.clear()
        usuario_rrhh.groups.add(grupo_rrhh)

        # -------------------------------------------------
        # CREAR USUARIO GERENTE
        # -------------------------------------------------

        usuario_gerente, creado = User.objects.get_or_create(
            username='gerente'
        )

        usuario_gerente.set_password('Clave#2026Demo')
        usuario_gerente.is_staff = True
        usuario_gerente.is_active = True
        usuario_gerente.save()

        usuario_gerente.groups.clear()
        usuario_gerente.groups.add(grupo_gerente)

        # -------------------------------------------------
        # EMPLEADOS
        # -------------------------------------------------

        empleados = [
            {
                'nombre_completo': 'Empleado 5',
                'cargo': 'Supervisor',
                'departamento': 'Operaciones',
                'salario_mensual': 9000000,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Empleado 1',
                'cargo': 'Operador',
                'departamento': 'Operaciones',
                'salario_mensual': 600000,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Empleado 2',
                'cargo': 'Operador',
                'departamento': 'Operaciones',
                'salario_mensual': 600000,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Empleado 3',
                'cargo': 'Operador',
                'departamento': 'Operaciones',
                'salario_mensual': 600000,
                'esta_activo': False,
            },
            {
                'nombre_completo': 'Empleado 4',
                'cargo': 'Ayudante Supervisor',
                'departamento': 'Operaciones',
                'salario_mensual': 100000,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Jesus Sarmiento',
                'cargo': 'Analista',
                'departamento': 'Administración',
                'salario_mensual': 20000,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Ana Torres',
                'cargo': 'Gerente Técnico',
                'departamento': 'Tecnología',
                'salario_mensual': 4500,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Juan Pérez',
                'cargo': 'Desarrollador Python',
                'departamento': 'Tecnología',
                'salario_mensual': 3200,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Carlos Díaz',
                'cargo': 'Desarrollador Python',
                'departamento': 'Tecnología',
                'salario_mensual': 3000,
                'esta_activo': False,
            },
            {
                'nombre_completo': 'María Soto',
                'cargo': 'Contador',
                'departamento': 'Finanzas',
                'salario_mensual': 2800,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Pedro González',
                'cargo': 'Asistente Admin',
                'departamento': 'Administración',
                'salario_mensual': 2200,
                'esta_activo': True,
            },
        ]

        # -------------------------------------------------
        # CREAR O ACTUALIZAR EMPLEADOS
        # -------------------------------------------------

        for datos in empleados:

            empleado, creado = Empleado.objects.get_or_create(
                nombre_completo=datos['nombre_completo']
            )

            empleado.cargo = datos['cargo']
            empleado.departamento = datos['departamento']
            empleado.salario_mensual = datos['salario_mensual']
            empleado.estado_laboral = 'activo' if datos['esta_activo'] else 'despedido'

            empleado.save()

        # -------------------------------------------------
        # MENSAJE FINAL
        # -------------------------------------------------

        self.stdout.write(
            self.style.SUCCESS(
                'Datos cargados correctamente.'
            )
        )

        self.stdout.write(
            'Usuario RRHH: rrhh / Rrhh2026!'
        )

        self.stdout.write(
            'Usuario GERENTE: gerente / Clave#2026Demo'
        )