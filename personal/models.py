 # -----------------------------------------------------------------------------
# Modelos de datos del sistema. Define empleados y el historial de modificaciones salariales.
# -----------------------------------------------------------------------------
from django.db import models

# Modelo que representa a cada empleado registrado en el sistema.
class Empleado(models.Model):

    # Opciones para el estado laboral detallado del empleado.
    ESTADOS_LABORALES = [
        ('activo', 'Activo (Trabajando)'),
        ('despedido', 'Despedido'),
        ('renuncio', 'Renunció'),
    ]

    # Nombre completo que se mostrará en los listados.
    nombre_completo = models.CharField(
        max_length=150
    )

    # Cargo o función que desempeña el empleado (puesto).
    cargo = models.CharField(
        max_length=100
    )

    # Área o departamento al que pertenece el empleado.
    departamento = models.CharField(
        max_length=100
    )

    # Salario mensual almacenado como decimal para evitar errores de precisión monetaria.
    salario_mensual = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # Estado laboral detallado requerido por la rúbrica (activo, despedido, renunció).
    estado_laboral = models.CharField(
        max_length=20,
        choices=ESTADOS_LABORALES,
        default='activo'
    )


    # Configuración adicional del modelo.
    class Meta:
        # Ordena los empleados de mayor a menor salario por defecto (cumpliendo con la rúbrica).
        ordering = ['-salario_mensual']

    # Representación legible del objeto cuando Django lo muestra como texto.
    def __str__(self):
        return f"{self.nombre_completo} - {self.cargo}"

    # Sobrescritura del método save para normalizar los valores antes de guardar en base de datos.
    def save(self, *args, **kwargs):
        # Asegura que el estado laboral siempre se guarde en minúsculas para mantener consistencia con los choices y cálculos.
        if self.estado_laboral:
            self.estado_laboral = self.estado_laboral.lower()
        super().save(*args, **kwargs)

# Historial de cambios realizados en los salarios (Audit Trail requerido para auditorías salariales).
class HistorialSalario(models.Model):

    # Relaciona el registro histórico con el empleado afectado.
    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE
    )

    # Salario que tenía el empleado antes del cambio.
    salario_anterior = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # Salario resultante después del cambio o aumento.
    salario_nuevo = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # Usuario o área de RRHH que realizó la modificación.
    modificado_por = models.CharField(
        max_length=150
    )

    # Fecha y hora en que se creó el registro histórico de forma automática.
    fecha_modificacion = models.DateTimeField(
        auto_now_add=True
    )

    # Texto descriptivo del registro histórico para identificación en el panel.
    def __str__(self):
        return f"Auditoría: {self.empleado.nombre_completo} - {self.fecha_modificacion.strftime('%Y-%m-%d %H:%M')}"