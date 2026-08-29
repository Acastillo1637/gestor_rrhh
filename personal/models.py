from django.db import models

class Empleado(models.Model):

    nombre_completo = models.CharField(
        max_length=150
    )

    cargo = models.CharField(
        max_length=100
    )

    departamento = models.CharField(
        max_length=100,
        default='Sin departamento'
    )

    salario_mensual = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    esta_activo = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = ['-salario_mensual']

    def __str__(self):
        return self.nombre_completo

# Historial de cambios realizados en los salarios.
class HistorialSalario(models.Model):

    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE
    )

    salario_anterior = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    salario_nuevo = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    modificado_por = models.CharField(
        max_length=150
    )

    fecha_modificacion = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.empleado.nombre_completo} - {self.fecha_modificacion}"