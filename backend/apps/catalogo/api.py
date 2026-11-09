from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.cuentas.permisos import EsAdministrador

from . import servicios
from .models import Conductor, Institucion, ResponsableRecepcion, Vehiculo
from .serializers import (
    ConductorSerializer,
    InstitucionSerializer,
    ResponsableRecepcionSerializer,
    VehiculoSerializer,
)


class _CatalogoViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Consultar, registrar, editar y desactivar (nunca borrar) con auditoría."""

    permission_classes = [EsAdministrador]
    filterset_fields = ["activo"]

    def create(self, request, *args, **kwargs):
        objeto = servicios.guardar(
            request.user, self.get_serializer_class(), request.data, request=request
        )
        return Response(self.get_serializer(objeto).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        objeto = servicios.guardar(
            request.user,
            self.get_serializer_class(),
            request.data,
            instancia=self.get_object(),
            request=request,
        )
        return Response(self.get_serializer(objeto).data)

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        objeto = servicios.cambiar_activo(request.user, self.get_object(), True, request=request)
        return Response(self.get_serializer(objeto).data)

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None):
        objeto = servicios.cambiar_activo(request.user, self.get_object(), False, request=request)
        return Response(self.get_serializer(objeto).data)


class InstitucionViewSet(_CatalogoViewSet):
    """RF-07 / RF-08: instituciones educativas."""

    queryset = Institucion.objects.all()
    serializer_class = InstitucionSerializer
    search_fields = ["nombre", "sede", "direccion"]


class ConductorViewSet(_CatalogoViewSet):
    """RF-09 / RF-10: conductores (crea su usuario con rol CONDUCTOR)."""

    queryset = Conductor.objects.select_related("usuario").prefetch_related("vehiculos")
    serializer_class = ConductorSerializer
    search_fields = ["usuario__first_name", "usuario__last_name", "numero_documento"]


class VehiculoViewSet(_CatalogoViewSet):
    """RF-11: vehículos asociados a conductores."""

    queryset = Vehiculo.objects.select_related("conductor__usuario")
    serializer_class = VehiculoSerializer
    filterset_fields = ["activo", "conductor"]
    search_fields = ["placa", "tipo"]


class ResponsableRecepcionViewSet(_CatalogoViewSet):
    """RF-12: responsables de recepción (crea su usuario con rol INSTITUCION)."""

    queryset = ResponsableRecepcion.objects.select_related("usuario", "institucion")
    serializer_class = ResponsableRecepcionSerializer
    filterset_fields = ["activo", "institucion"]
    search_fields = ["usuario__first_name", "usuario__last_name", "cargo"]
