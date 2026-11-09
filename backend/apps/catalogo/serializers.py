from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.cuentas.models import Rol

from .models import Conductor, Institucion, ResponsableRecepcion, Vehiculo

Usuario = get_user_model()


class InstitucionSerializer(serializers.ModelSerializer):
    """RF-07 / RF-08."""

    class Meta:
        model = Institucion
        fields = [
            "id",
            "nombre",
            "sede",
            "direccion",
            "latitud",
            "longitud",
            "contacto_nombre",
            "contacto_telefono",
            "contacto_email",
            "activo",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["activo", "creado_en", "actualizado_en"]


class _ConUsuarioSerializer(serializers.ModelSerializer):
    """Crea o actualiza el usuario asociado al perfil y le asigna el rol."""

    rol_usuario: str = ""
    email = serializers.EmailField(source="usuario.email")
    first_name = serializers.CharField(source="usuario.first_name", label="Nombres")
    last_name = serializers.CharField(source="usuario.last_name", label="Apellidos")
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, label="Contraseña"
    )
    nombre = serializers.CharField(source="usuario.get_full_name", read_only=True)

    def validate(self, attrs):
        datos_usuario = attrs.get("usuario", {})
        email = datos_usuario.get("email")
        if email:
            email = email.strip().lower()
            datos_usuario["email"] = email
            existentes = Usuario.objects.filter(email=email)
            if self.instance is not None:
                existentes = existentes.exclude(pk=self.instance.usuario_id)
            if existentes.exists():
                raise serializers.ValidationError(
                    {"email": "Ya existe un usuario con este correo."}
                )
        password = attrs.get("password")
        if self.instance is None and not password:
            raise serializers.ValidationError({"password": "La contraseña es obligatoria."})
        if password:
            validate_password(password)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        datos_usuario = validated_data.pop("usuario")
        password = validated_data.pop("password")
        usuario = Usuario.objects.create_user(
            password=password, rol=self.rol_usuario, **datos_usuario
        )
        return self.Meta.model.objects.create(usuario=usuario, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        datos_usuario = validated_data.pop("usuario", {})
        password = validated_data.pop("password", "")
        usuario = instance.usuario
        for campo, valor in datos_usuario.items():
            setattr(usuario, campo, valor)
        if password:
            usuario.set_password(password)
        usuario.save()
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        return instance


class ConductorSerializer(_ConUsuarioSerializer):
    """RF-09 / RF-10."""

    rol_usuario = Rol.CONDUCTOR
    vehiculos = serializers.SerializerMethodField()

    class Meta:
        model = Conductor
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "password",
            "nombre",
            "tipo_documento",
            "numero_documento",
            "telefono",
            "numero_licencia",
            "activo",
            "vehiculos",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["activo", "creado_en", "actualizado_en"]

    def get_vehiculos(self, obj) -> list[str]:
        return [v.placa for v in obj.vehiculos.all() if v.activo]


class ResponsableRecepcionSerializer(_ConUsuarioSerializer):
    """RF-12."""

    rol_usuario = Rol.INSTITUCION
    institucion = serializers.PrimaryKeyRelatedField(
        queryset=Institucion.objects.filter(activo=True)
    )
    institucion_nombre = serializers.CharField(source="institucion.__str__", read_only=True)

    class Meta:
        model = ResponsableRecepcion
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "password",
            "nombre",
            "institucion",
            "institucion_nombre",
            "cargo",
            "telefono",
            "activo",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["activo", "creado_en", "actualizado_en"]


class VehiculoSerializer(serializers.ModelSerializer):
    """RF-11."""

    conductor = serializers.PrimaryKeyRelatedField(
        queryset=Conductor.objects.filter(activo=True), required=False, allow_null=True
    )
    conductor_nombre = serializers.CharField(
        source="conductor.usuario.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = Vehiculo
        fields = [
            "id",
            "placa",
            "tipo",
            "capacidad_kg",
            "conductor",
            "conductor_nombre",
            "activo",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["activo", "creado_en", "actualizado_en"]

    def validate_placa(self, valor):
        placa = valor.upper().replace(" ", "")
        existentes = Vehiculo.objects.filter(placa=placa)
        if self.instance is not None:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise serializers.ValidationError("Ya existe un vehículo con esta placa.")
        return placa

    def validate_capacidad_kg(self, valor):
        if valor <= 0:
            raise serializers.ValidationError("La capacidad debe ser mayor que cero.")
        return valor
