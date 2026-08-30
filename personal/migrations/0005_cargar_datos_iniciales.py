from django.db import migrations

def crear_datos_iniciales(apps, schema_editor):
    Empleado = apps.get_model('personal', 'Empleado')

    empleados_data = [
        {
            "nombre_completo": "Carlos Silva",
            "cargo": "Desarrollador Backend",
            "departamento": "Tecnología",
            "salario_mensual": 1300000,
            "estado_laboral": "activo"
        },
        {
            "nombre_completo": "María Torres",
            "cargo": "Analista de Ciberseguridad",
            "departamento": "Tecnología",
            "salario_mensual": 1450000,
            "estado_laboral": "activo"
        },
        {
            "nombre_completo": "Esteban Rojas",
            "cargo": "Soporte TI",
            "departamento": "Tecnología",
            "salario_mensual": 950000,
            "estado_laboral": "activo"
        },
        {
            "nombre_completo": "Valentina Morales",
            "cargo": "Coordinadora de RRHH",
            "departamento": "Recursos Humanos",
            "salario_mensual": 1200000,
            "estado_laboral": "activo"
        },
        {
            "nombre_completo": "Ignacio Valenzuela",
            "cargo": "Administrador de BD",
            "departamento": "Tecnología",
            "salario_mensual": 1600000,
            "estado_laboral": "renuncio"
        }
    ]

    for data in empleados_data:
        Empleado.objects.update_or_create(
            nombre_completo=data["nombre_completo"],
            defaults=data
        )

class Migration(migrations.Migration):

    dependencies = [
        ('personal', '0004_remove_empleado_esta_activo_empleado_estado_laboral'),
    ]

    operations = [
        migrations.RunPython(crear_datos_iniciales),
    ]