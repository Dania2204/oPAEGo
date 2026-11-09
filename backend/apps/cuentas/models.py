from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Rol(models.TextChoices):
    """Roles del control de acceso basado en roles (numeral 2.2.9, RF-05)."""

    ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
    CONDUCTOR = "CONDUCTOR", "Conductor"
    INSTITUCION = "INSTITUCION", "Institución educativa"


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **campos):
        if not email:
            raise ValueError("El correo es obligatorio.")
        usuario = self.model(email=self.normalize_email(email).lower(), **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **campos):
        campos.setdefault("is_staff", False)
        campos.setdefault("is_superuser", False)
        return self._crear(email, password, **campos)

    def create_superuser(self, email, password=None, **campos):
        campos.setdefault("rol", Rol.ADMINISTRADOR)
        campos["is_staff"] = True
        campos["is_superuser"] = True
        return self._crear(email, password, **campos)


class Usuario(AbstractUser):
    """Usuario del sistema; inicia sesión con su correo (RF-01)."""

    username = None
    email = models.EmailField("correo", unique=True)
    rol = models.CharField(max_length=20, choices=Rol.choices)
    telefono = models.CharField(max_length=30, blank=True)
    # RNF-11 (Ley 1581 de 2012): constancia de aceptación del tratamiento de datos.
    acepto_tratamiento_datos_en = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuario"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def es_administrador(self):
        return self.rol == Rol.ADMINISTRADOR

    @property
    def es_conductor(self):
        return self.rol == Rol.CONDUCTOR

    @property
    def es_institucion(self):
        return self.rol == Rol.INSTITUCION
