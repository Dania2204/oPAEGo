from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Rol

Usuario = get_user_model()


class PerfilSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="get_full_name", read_only=True)
    conductor_id = serializers.SerializerMethodField()
    institucion_id = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "nombre",
            "rol",
            "telefono",
            "acepto_tratamiento_datos_en",
            "conductor_id",
            "institucion_id",
        ]
        read_only_fields = fields

    def get_conductor_id(self, obj) -> int | None:
        conductor = getattr(obj, "conductor", None)
        return conductor.pk if conductor else None

    def get_institucion_id(self, obj) -> int | None:
        responsable = getattr(obj, "responsable_recepcion", None)
        return responsable.institucion_id if responsable else None


class InicioSesionSerializer(TokenObtainPairSerializer):
    """RF-01: credenciales -> par de tokens JWT + perfil y rol."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["rol"] = user.rol
        token["nombre"] = user.get_full_name()
        return token

    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].strip().lower()
        datos = super().validate(attrs)
        datos["usuario"] = PerfilSerializer(self.user).data
        return datos


class CierreSesionSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class SolicitudRestablecimientoSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ConfirmacionRestablecimientoSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    nueva_password = serializers.CharField(write_only=True)


class UsuarioAdministradorSerializer(serializers.ModelSerializer):
    """RF-04 / RF-05: usuarios con rol administrador.

    Los conductores y los responsables de recepción se crean desde sus propios
    módulos (RF-09, RF-12), que les asignan el rol correspondiente.
    """

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "telefono",
            "rol",
            "is_active",
            "last_login",
            "date_joined",
            "password",
        ]
        read_only_fields = ["rol", "is_active", "last_login", "date_joined"]
        extra_kwargs = {"first_name": {"required": True}, "last_name": {"required": True}}

    def validate_email(self, valor):
        return valor.strip().lower()

    def validate(self, attrs):
        password = attrs.get("password")
        if self.instance is None and not password:
            raise serializers.ValidationError({"password": "La contraseña es obligatoria."})
        if password:
            validate_password(password)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return Usuario.objects.create_user(
            password=password, rol=Rol.ADMINISTRADOR, **validated_data
        )

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class UsuarioListaSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="get_full_name", read_only=True)
    rol_nombre = serializers.CharField(source="get_rol_display", read_only=True)

    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "nombre",
            "rol",
            "rol_nombre",
            "telefono",
            "is_active",
            "last_login",
        ]
        read_only_fields = fields
