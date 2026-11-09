from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.auditoria.models import Accion
from apps.auditoria.servicios import registrar
from apps.catalogo import servicios as catalogo
from apps.monitoreo.en_vivo import desconectar

from . import restablecimiento
from .limite import LimitePorAlcance
from .models import Rol
from .permisos import EsAdministrador
from .serializers import (
    CierreSesionSerializer,
    ConfirmacionRestablecimientoSerializer,
    InicioSesionSerializer,
    PerfilSerializer,
    SolicitudRestablecimientoSerializer,
    UsuarioAdministradorSerializer,
    UsuarioListaSerializer,
)
from .tokens import revocar_refresh

Usuario = get_user_model()


class InicioSesionView(TokenObtainPairView):
    """RF-01: inicia sesión y devuelve el par de tokens JWT (access y refresh)."""

    serializer_class = InicioSesionSerializer
    throttle_classes = [LimitePorAlcance]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        respuesta = super().post(request, *args, **kwargs)
        if respuesta.status_code == status.HTTP_200_OK:
            usuario = Usuario.objects.get(pk=respuesta.data["usuario"]["id"])
            registrar(usuario, Accion.INICIO_SESION, "Inicio de sesión (API)", request=request)
        return respuesta


class RenovarTokenView(TokenRefreshView):
    """RF-02: renueva el access token con el refresh (que rota)."""

    throttle_classes = [LimitePorAlcance]
    throttle_scope = "renovar"


class CierreSesionView(APIView):
    """RF-02: revoca el refresh token."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=CierreSesionSerializer, responses={204: None})
    def post(self, request):
        serializer = CierreSesionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        revocar_refresh(serializer.validated_data["refresh"])
        desconectar(request.user)
        registrar(request.user, Accion.CIERRE_SESION, "Cierre de sesión (API)", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PerfilView(APIView):
    @extend_schema(responses=PerfilSerializer)
    def get(self, request):
        return Response(PerfilSerializer(request.user).data)


class AceptarTratamientoDatosView(APIView):
    """RNF-11: constancia de aceptación del tratamiento de datos (Ley 1581)."""

    @extend_schema(request=None, responses=PerfilSerializer)
    def post(self, request):
        if request.user.acepto_tratamiento_datos_en is None:
            request.user.acepto_tratamiento_datos_en = timezone.now()
            request.user.save(update_fields=["acepto_tratamiento_datos_en"])
            registrar(
                request.user,
                Accion.ACEPTA_TRATAMIENTO_DATOS,
                "Aceptó la política de tratamiento de datos",
                request=request,
            )
        return Response(PerfilSerializer(request.user).data)


class SolicitarRestablecimientoView(APIView):
    """RF-03: envía al correo el enlace para restablecer la contraseña."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LimitePorAlcance]
    throttle_scope = "restablecer"

    @extend_schema(request=SolicitudRestablecimientoSerializer, responses={202: None})
    def post(self, request):
        serializer = SolicitudRestablecimientoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        restablecimiento.solicitar(serializer.validated_data["email"])
        return Response(
            {"detalle": "Si el correo está registrado, recibirá un enlace para restablecer."},
            status=status.HTTP_202_ACCEPTED,
        )


class ConfirmarRestablecimientoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LimitePorAlcance]
    throttle_scope = "restablecer"

    @extend_schema(request=ConfirmacionRestablecimientoSerializer, responses={204: None})
    def post(self, request):
        serializer = ConfirmacionRestablecimientoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        try:
            restablecimiento.confirmar(
                datos["uid"], datos["token"], datos["nueva_password"], request=request
            )
        except DjangoValidationError as exc:
            return Response({"nueva_password": exc.messages}, status=400)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsuarioViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """RF-04 / RF-05: el administrador consulta todos los usuarios, crea y edita
    administradores y desactiva cualquier usuario."""

    permission_classes = [EsAdministrador]
    queryset = Usuario.objects.all().order_by("first_name", "last_name")
    filterset_fields = ["rol", "is_active"]
    search_fields = ["email", "first_name", "last_name"]

    def get_serializer_class(self):
        if self.action in ("list", "retrieve") or self.action in ("activar", "desactivar"):
            return UsuarioListaSerializer
        return UsuarioAdministradorSerializer

    def perform_create(self, serializer):
        usuario = serializer.save()
        registrar(
            self.request.user,
            Accion.CREAR,
            f"Usuario: {usuario}",
            objeto=usuario,
            request=self.request,
        )

    def perform_update(self, serializer):
        if serializer.instance.rol != Rol.ADMINISTRADOR:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "Los conductores y responsables se editan desde su propio módulo."
            )
        usuario = serializer.save()
        registrar(
            self.request.user,
            Accion.EDITAR,
            f"Usuario: {usuario}",
            objeto=usuario,
            request=self.request,
        )

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        usuario = catalogo.cambiar_activo(request.user, self.get_object(), True, request=request)
        return Response(UsuarioListaSerializer(usuario).data)

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None):
        usuario = catalogo.cambiar_activo(request.user, self.get_object(), False, request=request)
        return Response(UsuarioListaSerializer(usuario).data)
