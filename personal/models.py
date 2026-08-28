from django.db import models


# Definimos la tabla de empleados en la base de datos.
class Empleado(models.Model):

    # Campo de texto para almacenar el nombre completo.
    nombre_completo = models.CharField(max_length=150)

    # Campo de texto para almacenar el cargo o puesto.
    cargo = models.CharField(max_length=100)

    # Campo decimal para almacenar el salario con precisión.
    salario_mensual = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # Indica si el empleado se encuentra activo o inactivo.
    esta_activo = models.BooleanField(default=True)

    class Meta:
        # Ordena automáticamente los empleados
        # desde el salario más alto al más bajo.
        ordering = ['-salario_mensual']

    def __str__(self):
        return self.nombre_completo