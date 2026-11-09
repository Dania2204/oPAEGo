"""API de envíos. La consumen el panel web (administrador) y la app móvil
Flutter (conductor e institución). Cada rol solo ve sus propios envíos."""

from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.auditoria.serializers import RegistroAuditoriaSerializer
from apps.cuentas.models import Rol
from apps.cuentas.permisos import (
    EsAdministrador,
    EsConductor,
    EsConductorOInstitucion,
    EsInstitucion,
)
from apps.sincronizacion.operaciones import ejecutar

from .filtros import EnvioFilter
from .models import Envio, ItemEnvio, Novedad
from .serializers import (
    ConfirmacionRecepcionSerializer,
    EnvioCrearSerializer,
    EnvioEditarSerializer,
    EnvioSerializer,
    MotivoSerializer,
    NovedadEntradaSerializer,
    NovedadSerializer,
    PosicionSerializer,
    ReasignarSerializer,
    UbicacionEntradaSerializer,
    UbicacionSerializer,
)

ENCABEZADO_OPERACION = OpenApiParameter(
    name="X-Operacion-Id",
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "UUID generado por el cliente. Hace la operación idempotente: si se "
        "reintenta con el mismo valor no se duplica (RF-38)."
    ),
)


def datos_planos(request):
    """Convierte un QueryDict (multipart) en dict simple; JSON queda igual."""
    datos = request.data
    if hasattr(datos, "lists"):
        return {k: v[0] if len(v) == 1 else v for k, v in datos.lists()}
    return dict(datos)


def queryset_por_rol(usuario):
    envios = Envio.objects.select_related(
        "institucion", "conductor__usuario", "vehiculo", "evidencia"
    ).prefetch_related(Prefetch("items", queryset=ItemEnvio.objects.order_by("id")))
    rol = getattr(usuario, "rol", None)  # el generador del esquema usa AnonymousUser
    if rol == Rol.ADMINISTRADOR:
        return envios
    if rol == Rol.CONDUCTOR:
        return envios.filter(conductor__usuario=usuario)
    if rol == Rol.INSTITUCION:
        return envios.filter(institucion__responsables__usuario=usuario)
    return envios.none()


class EnvioViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """RF-17 (administrador), RF-19 (conductor: sus envíos asignados) y
    RF-24 (institución: envíos programados y en camino hacia ella)."""

    serializer_class = EnvioSerializer
    filterset_class = EnvioFilter
    search_fields = ["codigo", "institucion__nombre"]
    ordering_fields = ["programado_para", "estado"]

    def get_queryset(self):
        return queryset_por_rol(self.request.user)

    def get_permissions(self):
        permisos = {
            "create": [EsAdministrador],
            "update": [EsAdministrador],
            "reasignar": [EsAdministrador],
            "cancelar": [EsAdministrador],
            "cerrar_con_novedad": [EsAdministrador],
            "historial": [EsAdministrador],
            "salida": [EsConductor],
            "ubicaciones": [EsConductor],
            "llegada": [EsConductor],
            "confirmar": [EsInstitucion],
            "novedades": [EsConductorOInstitucion],
        }
        if self.action == "novedades" and self.request.method == "GET":
            return [p() for p in self.permission_classes]
        if self.action == "ubicaciones" and self.request.method == "GET":
            return [p() for p in self.permission_classes]
        return [p() for p in permisos.get(self.action, self.permission_classes)]

    def _operar(self, tipo, datos, envio_id=None, codigo=status.HTTP_200_OK):
        datos = dict(datos)
        if envio_id is not None:
            datos["envio"] = envio_id
        resultado, respuesta = ejecutar(
            self.request.user,
            tipo,
            datos,
            uuid_cliente=self.request.headers.get("X-Operacion-Id") or None,
            request=self.request,
            propagar=True,
        )
        return respuesta

    def _envio_respuesta(self, envio_id, codigo=status.HTTP_200_OK):
        envio = queryset_por_rol(self.request.user).get(pk=envio_id)
        return Response(self.get_serializer(envio).data, status=codigo)

    def _exigir_visible(self, pk):
        # 404 si el envío no pertenece al usuario (no revela su existencia).
        return self.get_object().pk

    # ---------------------------------------------------------- administrador
    @extend_schema(
        request=EnvioCrearSerializer,
        responses={201: EnvioSerializer},
        parameters=[ENCABEZADO_OPERACION],
    )
    def create(self, request):
        """RF-13 a RF-15: crea el envío con sus alimentos y lo asigna."""
        respuesta = self._operar("envio.crear", datos_planos(request))
        return self._envio_respuesta(respuesta["id"], status.HTTP_201_CREATED)

    @extend_schema(
        request=EnvioEditarSerializer, responses=EnvioSerializer, parameters=[ENCABEZADO_OPERACION]
    )
    def update(self, request, pk=None):
        """RF-16: modifica el envío antes de su salida (motivo obligatorio)."""
        self._operar("envio.editar", datos_planos(request), self._exigir_visible(pk))
        return self._envio_respuesta(pk)

    @extend_schema(
        request=ReasignarSerializer, responses=EnvioSerializer, parameters=[ENCABEZADO_OPERACION]
    )
    @action(detail=True, methods=["post"])
    def reasignar(self, request, pk=None):
        """RF-16: reasigna conductor y vehículo antes de la salida."""
        self._operar("envio.reasignar", datos_planos(request), self._exigir_visible(pk))
        return self._envio_respuesta(pk)

    @extend_schema(
        request=MotivoSerializer, responses=EnvioSerializer, parameters=[ENCABEZADO_OPERACION]
    )
    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """RF-16: cancela el envío antes de la salida."""
        self._operar("envio.cancelar", datos_planos(request), self._exigir_visible(pk))
        return self._envio_respuesta(pk)

    @extend_schema(
        request=MotivoSerializer, responses=EnvioSerializer, parameters=[ENCABEZADO_OPERACION]
    )
    @action(detail=True, methods=["post"], url_path="cerrar-con-novedad")
    def cerrar_con_novedad(self, request, pk=None):
        """Cierra con novedad un envío en tránsito que no pudo entregarse."""
        self._operar("envio.cerrar_con_novedad", datos_planos(request), self._exigir_visible(pk))
        return self._envio_respuesta(pk)

    @extend_schema(responses=RegistroAuditoriaSerializer(many=True))
    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        """RF-34: historial completo del envío en forma de línea de tiempo."""
        envio = self.get_object()
        registros = envio.registros_auditoria.select_related("usuario").order_by(
            "ocurrido_en", "id"
        )
        return Response(RegistroAuditoriaSerializer(registros, many=True).data)

    # ---------------------------------------------------------------- conductor
    @extend_schema(
        request=PosicionSerializer, responses=EnvioSerializer, parameters=[ENCABEZADO_OPERACION]
    )
    @action(detail=True, methods=["post"])
    def salida(self, request, pk=None):
        """RF-20: registra la salida con fecha, hora y ubicación."""
        self._operar("envio.salida", datos_planos(request), self._exigir_visible(pk))
        return self._envio_respuesta(pk)

    @extend_schema(
        methods=["POST"],
        request=UbicacionEntradaSerializer,
        responses={201: None},
        parameters=[ENCABEZADO_OPERACION],
    )
    @extend_schema(methods=["GET"], responses=UbicacionSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def ubicaciones(self, request, pk=None):
        """POST RF-21: transmite la ubicación. GET RF-35: ruta recorrida."""
        envio_id = self._exigir_visible(pk)
        if request.method == "GET":
            if request.user.rol == Rol.CONDUCTOR:
                raise PermissionDenied()
            puntos = self.get_object().ubicaciones.order_by("ocurrido_en")
            return Response(UbicacionSerializer(puntos, many=True).data)
        respuesta = self._operar("envio.ubicacion", datos_planos(request), envio_id)
        return Response(respuesta, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=PosicionSerializer, responses=EnvioSerializer, parameters=[ENCABEZADO_OPERACION]
    )
    @action(detail=True, methods=["post"])
    def llegada(self, request, pk=None):
        """RF-22: registra la llegada a la institución."""
        self._operar("envio.llegada", datos_planos(request), self._exigir_visible(pk))
        return self._envio_respuesta(pk)

    @extend_schema(
        methods=["POST"],
        request=NovedadEntradaSerializer,
        responses={201: NovedadSerializer},
        parameters=[ENCABEZADO_OPERACION],
    )
    @extend_schema(methods=["GET"], responses=NovedadSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def novedades(self, request, pk=None):
        """POST RF-23 / RF-28: reporta una novedad (foto opcional, multipart o base64)."""
        envio_id = self._exigir_visible(pk)
        if request.method == "GET":
            novedades = Novedad.objects.filter(envio_id=envio_id).select_related(
                "reportado_por", "envio"
            )
            return Response(NovedadSerializer(novedades, many=True).data)
        respuesta = self._operar("envio.novedad", datos_planos(request), envio_id)
        novedad = Novedad.objects.get(pk=respuesta["id"])
        return Response(NovedadSerializer(novedad).data, status=status.HTTP_201_CREATED)

    # -------------------------------------------------------------- institución
    @extend_schema(
        request=ConfirmacionRecepcionSerializer,
        responses=EnvioSerializer,
        parameters=[ENCABEZADO_OPERACION],
    )
    @action(detail=True, methods=["post"])
    def confirmar(self, request, pk=None):
        """RF-25 a RF-28: verifica cantidades, confirma la recepción y registra
        la evidencia (código de verificación, foto opcional y huella SHA-256)."""
        self._operar("envio.confirmar", datos_planos(request), self._exigir_visible(pk))
        return self._envio_respuesta(pk)
