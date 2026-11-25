"""API de estudiantes PAE para la app móvil (supervisor e institución).

Solo lectura: la escritura (registrar la entrega por QR o manual) viaja por la
cola sin conexión, `POST /api/sincronizacion/lote/` (RF-38).
"""

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.cuentas.models import Rol
from apps.cuentas.permisos import _PorRol

from . import consultas, servicios
from .models import EntregaEstudiante
from .serializers import EntregaSerializer, EstudianteSerializer


class PuedeVerEstudiantes(_PorRol):
    roles = (Rol.SUPERVISOR, Rol.ADMINISTRADOR, Rol.INSTITUCION)


class PaginaEstudiantes(PageNumberPagination):
    """La app descarga un colegio completo para trabajar sin red."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 2000


def _fecha(request):
    valor = request.query_params.get("fecha")
    if not valor:
        return timezone.localdate()
    fecha = parse_date(valor)
    if fecha is None:
        raise ValidationError({"fecha": "Use el formato AAAA-MM-DD."})
    return fecha


class EstudianteViewSet(viewsets.ReadOnlyModelViewSet):
    """Estudiantes activos de la institución del usuario, con su estado del día.

    Filtros: `grado`, `grupo`, `q` (nombre o documento), `fecha` (AAAA-MM-DD).
    """

    serializer_class = EstudianteSerializer
    permission_classes = [PuedeVerEstudiantes]
    pagination_class = PaginaEstudiantes
    filter_backends = []

    def _base(self):
        return servicios.estudiantes_visibles(self.request.user, lectura=True)

    def get_queryset(self):
        qs = self._base().filter(activo=True)
        p = self.request.query_params
        if p.get("grado"):
            qs = qs.filter(grado=p["grado"])
        if p.get("grupo"):
            qs = qs.filter(grupo=p["grupo"])
        if p.get("q"):
            texto = p["q"].strip()
            qs = qs.filter(
                Q(nombres__icontains=texto)
                | Q(apellidos__icontains=texto)
                | Q(numero_documento__startswith=texto)
            )
        return consultas.con_estado_del_dia(qs, _fecha(self.request))

    @action(detail=False)
    def cursos(self, request):
        """Avance por curso: activos y cuántos recibieron (en `fecha`)."""
        fecha = _fecha(request)
        base = self._base()
        return Response(
            {
                "fecha": fecha,
                "cobertura": consultas.cobertura(base, fecha),
                "cursos": consultas.resumen_cursos(base, fecha),
            }
        )

    @action(detail=False)
    def historial(self, request):
        """Entregas registradas. El supervisor ve las suyas; admin e institución, las visibles.

        Filtros: `desde`, `hasta` (AAAA-MM-DD), `grado`, `grupo`.
        """
        qs = EntregaEstudiante.objects.filter(estudiante__in=self._base()).select_related(
            "estudiante", "supervisor"
        )
        if request.user.rol == Rol.SUPERVISOR:
            qs = qs.filter(supervisor=request.user)
        p = request.query_params
        for campo, filtro in (("desde", "fecha__gte"), ("hasta", "fecha__lte")):
            if p.get(campo):
                valor = parse_date(p[campo])
                if valor is None:
                    raise ValidationError({campo: "Use el formato AAAA-MM-DD."})
                qs = qs.filter(**{filtro: valor})
        if p.get("grado"):
            qs = qs.filter(estudiante__grado=p["grado"])
        if p.get("grupo"):
            qs = qs.filter(estudiante__grupo=p["grupo"])
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(EntregaSerializer(pagina, many=True).data)
