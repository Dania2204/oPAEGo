from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

LATITUD = [MinValueValidator(-90), MaxValueValidator(90)]
LONGITUD = [MinValueValidator(-180), MaxValueValidator(180)]


class Institucion(models.Model):
    """RF-07 / RF-08: institución educativa receptora."""

    nombre = models.CharField(max_length=200)
    sede = models.CharField(max_length=120, default="Principal")
    direccion = models.CharField(max_length=255)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, validators=LATITUD)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, validators=LONGITUD)
    contacto_nombre = models.CharField("nombre de contacto", max_length=150, blank=True)
    contacto_telefono = models.CharField("teléfono de contacto", max_length=30, blank=True)
    contacto_email = models.EmailField("correo de contacto", blank=True)
    # Claves oficiales del Ministerio (SIMAT/DUE). Permiten enlazar la matrícula
    # importada con la sede de forma idempotente. En blanco si la sede se creó a mano.
    codigo_dane = models.CharField("código DANE", max_length=12, blank=True)
    consecutivo_sede = models.CharField(
        "consecutivo de sede (SIMAT)", max_length=14, null=True, blank=True, unique=True
    )
    # Caché del total de matrícula (RF-14): se recalcula al importar SIMAT y se usa
    # para sugerir la cantidad de raciones de un envío. 0 si no se ha importado.
    beneficiarios_total = models.PositiveIntegerField("beneficiarios (matrícula)", default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "institución educativa"
        verbose_name_plural = "instituciones educativas"
        ordering = ["nombre", "sede"]
        constraints = [
            models.UniqueConstraint(fields=["nombre", "sede"], name="institucion_nombre_sede_unica")
        ]

    def __str__(self):
        return f"{self.nombre} — {self.sede}"


class MatriculaSede(models.Model):
    """Conteo agregado de matrícula por sede, grado y jornada (Anexo 6A de SIMAT).

    Solo almacena totales: ningún dato personal de estudiantes se guarda
    (minimización de datos, Ley 1581). Alimenta la sugerencia de raciones
    (RF-14) y el reporte de cobertura (RF-32)."""

    institucion = models.ForeignKey(
        Institucion, on_delete=models.CASCADE, related_name="matriculas"
    )
    anio = models.PositiveSmallIntegerField("año")
    grado = models.CharField(max_length=4)  # código SIMAT; etiqueta en apps.catalogo.simat
    jornada = models.CharField(max_length=2)  # código SIMAT TIPO_JORNADA
    zona = models.CharField(max_length=10, blank=True)
    total = models.PositiveIntegerField()

    class Meta:
        verbose_name = "matrícula por sede"
        verbose_name_plural = "matrículas por sede"
        ordering = ["institucion", "grado", "jornada"]
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "anio", "grado", "jornada", "zona"],
                name="matricula_sede_unica",
            )
        ]

    def __str__(self):
        return f"{self.institucion} — grado {self.grado} ({self.total})"


class Conductor(models.Model):
    """RF-09 / RF-10: datos de identificación y contacto del conductor."""

    class TipoDocumento(models.TextChoices):
        CC = "CC", "Cédula de ciudadanía"
        CE = "CE", "Cédula de extranjería"
        PPT = "PPT", "Permiso por protección temporal"

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="conductor"
    )
    tipo_documento = models.CharField(max_length=5, choices=TipoDocumento.choices, default="CC")
    numero_documento = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=30)
    numero_licencia = models.CharField("número de licencia", max_length=30, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "conductores"
        ordering = ["usuario__first_name", "usuario__last_name"]

    def __str__(self):
        return f"{self.usuario.get_full_name()} ({self.numero_documento})"


class Vehiculo(models.Model):
    """RF-11: vehículo asociado a un conductor."""

    placa = models.CharField(max_length=10, unique=True)
    tipo = models.CharField(max_length=50, help_text="Ej.: camión, furgón, camioneta, moto")
    capacidad_kg = models.DecimalField("capacidad (kg)", max_digits=8, decimal_places=2)
    conductor = models.ForeignKey(
        Conductor, null=True, blank=True, on_delete=models.SET_NULL, related_name="vehiculos"
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "vehículo"
        ordering = ["placa"]

    def __str__(self):
        return f"{self.placa} ({self.tipo})"

    def save(self, *args, **kwargs):
        self.placa = self.placa.upper().replace(" ", "")
        super().save(*args, **kwargs)


class ResponsableRecepcion(models.Model):
    """RF-12: personal de la institución designado para recibir los alimentos."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="responsable_recepcion"
    )
    institucion = models.ForeignKey(
        Institucion, on_delete=models.PROTECT, related_name="responsables"
    )
    cargo = models.CharField(max_length=100, help_text="Ej.: rector, coordinador, almacenista")
    telefono = models.CharField(max_length=30, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "responsable de recepción"
        verbose_name_plural = "responsables de recepción"
        ordering = ["institucion__nombre", "usuario__first_name"]

    def __str__(self):
        return f"{self.usuario.get_full_name()} — {self.institucion}"
