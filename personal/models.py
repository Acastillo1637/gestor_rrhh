# -----------------------------------------------------------------------------
# Modelos de datos del sistema de Gestión de Personal (RRHH)
# -----------------------------------------------------------------------------

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator


# =============================================================================
# DEPARTAMENTO
# =============================================================================

class Departamento(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)

    jefe = models.ForeignKey(
        'Empleado',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departamentos_a_cargo'
    )

    presupuesto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    def __str__(self):
        return self.nombre


# =============================================================================
# EMPLEADO
# =============================================================================

class Empleado(models.Model):

    ESTADOS_LABORALES = [
        ('activo', 'Activo'),
        ('despedido', 'Despedido'),
        ('renuncio', 'Renunció'),
    ]

    GENEROS = [
        ('masculino', 'Masculino'),
        ('femenino', 'Femenino'),
        ('otro', 'Otro'),
        ('no_indica', 'Prefiere no indicar'),
    ]

    # Relación opcional con usuario de Django.
    usuario = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='empleado'
    )

    nombre_completo = models.CharField(
        max_length=150
    )

    email = models.EmailField(
        unique=True,
        null=True,
        blank=True
    )

    dni = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True
    )

    fecha_nacimiento = models.DateField(
        null=True,
        blank=True
    )

    genero = models.CharField(
        max_length=20,
        choices=GENEROS,
        default='no_indica'
    )

    telefono = models.CharField(
        max_length=20,
        blank=True
    )

    direccion = models.CharField(
        max_length=200,
        blank=True
    )

    fecha_contratacion = models.DateField(
        null=True,
        blank=True
    )

    estado_laboral = models.CharField(
        max_length=20,
        choices=ESTADOS_LABORALES,
        default='activo'
    )

    # -------------------------------------------------------------------------
    # CAMPOS DEL PROYECTO ANTERIOR
    # Los conservamos temporalmente para no romper las vistas actuales.
    # -------------------------------------------------------------------------

    cargo = models.CharField(
        max_length=100,
        blank=True
    )

    departamento = models.CharField(
        max_length=100,
        blank=True
    )

    salario_mensual = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    class Meta:
        ordering = ['nombre_completo']

    def __str__(self):
        return self.nombre_completo

    def save(self, *args, **kwargs):
        if self.estado_laboral:
            self.estado_laboral = self.estado_laboral.lower()

        super().save(*args, **kwargs)


# =============================================================================
# PUESTO
# =============================================================================

class Puesto(models.Model):

    NIVELES = [
        ('junior', 'Junior'),
        ('semi_senior', 'Semi Senior'),
        ('senior', 'Senior'),
        ('jefatura', 'Jefatura'),
        ('gerencia', 'Gerencia'),
    ]

    nombre = models.CharField(max_length=100)

    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.CASCADE,
        related_name='puestos'
    )

    nivel = models.CharField(
        max_length=20,
        choices=NIVELES
    )

    salario_base = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        return f"{self.nombre} - {self.departamento.nombre}"


# =============================================================================
# HISTORIAL DE PUESTOS
# =============================================================================

class EmpleadoPuesto(models.Model):

    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='historial_puestos'
    )

    puesto = models.ForeignKey(
        Puesto,
        on_delete=models.PROTECT,
        related_name='empleados'
    )

    fecha_inicio = models.DateField()

    fecha_fin = models.DateField(
        null=True,
        blank=True
    )

    es_actual = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f"{self.empleado} - {self.puesto}"


# =============================================================================
# SALARIO / NÓMINA
# =============================================================================

class Salario(models.Model):

    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='salarios'
    )

    mes_ano = models.DateField()

    salario_base = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    bonificacion = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    descuentos = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    neto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    pagado = models.BooleanField(
        default=False
    )

    class Meta:
        unique_together = ('empleado', 'mes_ano')
        ordering = ['-mes_ano']

    def save(self, *args, **kwargs):
        self.neto = (
            self.salario_base
            + self.bonificacion
            - self.descuentos
        )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.empleado} - {self.mes_ano:%m/%Y}"


# =============================================================================
# ASISTENCIA
# =============================================================================

class Asistencia(models.Model):

    ESTADOS = [
        ('presente', 'Presente'),
        ('ausente', 'Ausente'),
        ('atraso', 'Atraso'),
        ('permiso', 'Permiso'),
        ('descanso', 'Descanso'),
        ('feriado', 'Feriado'),
    ]

    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='asistencias'
    )

    fecha = models.DateField()

    hora_entrada = models.TimeField(
        null=True,
        blank=True
    )

    hora_salida = models.TimeField(
        null=True,
        blank=True
    )

    minutos_trabajados = models.PositiveIntegerField(
        default=0
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='presente'
    )

    class Meta:
        unique_together = ('empleado', 'fecha')
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.empleado} - {self.fecha}"


# =============================================================================
# PERMISOS
# =============================================================================

class Permiso(models.Model):

    TIPOS = [
        ('vacaciones', 'Vacaciones'),
        ('medico', 'Médico'),
        ('administrativo', 'Administrativo'),
        ('otro', 'Otro'),
    ]

    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
    ]

    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='permisos'
    )

    tipo = models.CharField(
        max_length=30,
        choices=TIPOS
    )

    fecha_inicio = models.DateField()

    fecha_fin = models.DateField()

    dias = models.PositiveIntegerField(
        default=1
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='pendiente'
    )

    aprobado = models.BooleanField(
        default=False
    )

    def __str__(self):
        return f"{self.empleado} - {self.tipo}"


# =============================================================================
# EVALUACIONES
# =============================================================================

class Evaluacion(models.Model):

    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='evaluaciones'
    )

    periodo = models.CharField(
        max_length=50
    )

    puntuacion = models.PositiveIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5)
        ]
    )

    feedback = models.TextField(
        blank=True
    )

    def __str__(self):
        return f"{self.empleado} - {self.periodo}"


# =============================================================================
# HISTORIAL SALARIAL DEL PROYECTO ANTERIOR
# =============================================================================

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
        return (
            f"Auditoría: {self.empleado.nombre_completo} - "
            f"{self.fecha_modificacion:%Y-%m-%d %H:%M}"
        )

# =============================================================================
# NOTIFICACIONES DEL SISTEMA
# =============================================================================

class Notificacion(models.Model):

    TIPOS = [
        ('empleado', 'Empleado'),
        ('permiso', 'Permiso'),
        ('nomina', 'Nómina'),
        ('asistencia', 'Asistencia'),
        ('evaluacion', 'Evaluación'),
        ('sistema', 'Sistema'),
    ]

    # Si usuario es NULL, la notificación es para RRHH / Gerencia.
    # Si tiene usuario, solamente la verá ese trabajador.
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notificaciones'
    )

    mensaje = models.CharField(
        max_length=255
    )

    tipo = models.CharField(
        max_length=20,
        choices=TIPOS,
        default='sistema'
    )

    url = models.CharField(
        max_length=255,
        blank=True
    )

    leida = models.BooleanField(
        default=False
    )

    fecha = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        destinatario = (
            self.usuario.username
            if self.usuario
            else 'RRHH / Gerencia'
        )

        return f"{destinatario}: {self.mensaje}"
