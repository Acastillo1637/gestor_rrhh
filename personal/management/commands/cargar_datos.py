from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission

from personal.models import Empleado


class Command(BaseCommand):
    help = 'Crea grupos, permisos, usuarios y datos de prueba'

    def handle(self, *args, **options):

        # ==========================
        # CREAR GRUPOS
        # ==========================

        grupo_rrhh, _ = Group.objects.get_or_create(name='RRHH')
        grupo_gerentes, _ = Group.objects.get_or_create(name='GERENTES')

        # ==========================
        # PERMISOS EMPLEADO
        # ==========================

        permisos_rrhh = Permission.objects.filter(
            content_type__app_label='personal',
            codename__in=[
                'view_empleado',
                'add_empleado',
                'change_empleado',
                'delete_empleado',
                'view_historialsalario',
            ]
        )

        grupo_rrhh.permissions.set(permisos_rrhh)

        permisos_gerentes = Permission.objects.filter(
            content_type__app_label='personal',
            codename__in=[
                'view_empleado',
                'view_historialsalario',
            ]
        )

        grupo_gerentes.permissions.set(permisos_gerentes)

        # ==========================
        # USUARIO RRHH
        # ==========================

        usuario_rrhh, creado = User.objects.get_or_create(
            username='rrhh'
        )

        usuario_rrhh.is_active = True
        usuario_rrhh.is_staff = True
        usuario_rrhh.is_superuser = False

        usuario_rrhh.set_password('Rrhh2026!')

        usuario_rrhh.save()

        usuario_rrhh.groups.clear()
        usuario_rrhh.groups.add(grupo_rrhh)

        # ==========================
        # USUARIO GERENTE
        # ==========================

        usuario_gerente, creado = User.objects.get_or_create(
            username='gerente'
        )

        usuario_gerente.is_active = True
        usuario_gerente.is_staff = True
        usuario_gerente.is_superuser = False

        usuario_gerente.set_password('Clave#2026Demo')

        usuario_gerente.save()

        usuario_gerente.groups.clear()
        usuario_gerente.groups.add(grupo_gerentes)

        # ==========================
        # EMPLEADOS DE PRUEBA
        # ==========================

        empleados = [
            {
                'nombre_completo': 'Ana Torres',
                'cargo': 'Gerente Técnico',
                'salario_mensual': 4500,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Juan Pérez',
                'cargo': 'Desarrollador Python',
                'salario_mensual': 3200,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'María Soto',
                'cargo': 'Contador',
                'salario_mensual': 2800,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Pedro González',
                'cargo': 'Asistente Admin',
                'salario_mensual': 2200,
                'esta_activo': True,
            },
            {
                'nombre_completo': 'Carlos Díaz',
                'cargo': 'Desarrollador Python',
                'salario_mensual': 3000,
                'esta_activo': False,
            },
        ]

        for datos in empleados:
            Empleado.objects.get_or_create(
                nombre_completo=datos['nombre_completo'],
                defaults={
                    'cargo': datos['cargo'],
                    'salario_mensual': datos['salario_mensual'],
                    'esta_activo': datos['esta_activo'],
                }
            )

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