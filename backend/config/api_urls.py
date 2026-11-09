"""API REST de PAEGo (numeral 3.2.3). La consumen la plataforma web y la
aplicación móvil Flutter (repositorio aparte)."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.auditoria.api import RegistroAuditoriaViewSet, ReporteView
from apps.catalogo.api import (
    ConductorViewSet,
    InstitucionViewSet,
    ResponsableRecepcionViewSet,
    VehiculoViewSet,
)
from apps.cuentas import api as cuentas
from apps.envios.api import EnvioViewSet
from apps.monitoreo import api as monitoreo
from apps.sincronizacion import api as sincronizacion

router = DefaultRouter()
router.register("usuarios", cuentas.UsuarioViewSet, basename="usuario")
router.register("instituciones", InstitucionViewSet, basename="institucion")
router.register("conductores", ConductorViewSet, basename="conductor")
router.register("vehiculos", VehiculoViewSet, basename="vehiculo")
router.register("responsables", ResponsableRecepcionViewSet, basename="responsable")
router.register("envios", EnvioViewSet, basename="envio")
router.register("auditoria", RegistroAuditoriaViewSet, basename="auditoria")

urlpatterns = [
    path("auth/token/", cuentas.InicioSesionView.as_view(), name="token"),
    path("auth/token/refresh/", cuentas.RenovarTokenView.as_view(), name="token_refresh"),
    path("auth/logout/", cuentas.CierreSesionView.as_view(), name="logout"),
    path("auth/yo/", cuentas.PerfilView.as_view(), name="perfil"),
    path(
        "auth/aceptar-tratamiento-datos/",
        cuentas.AceptarTratamientoDatosView.as_view(),
        name="aceptar_datos",
    ),
    path("auth/restablecer/", cuentas.SolicitarRestablecimientoView.as_view(), name="restablecer"),
    path(
        "auth/restablecer/confirmar/",
        cuentas.ConfirmarRestablecimientoView.as_view(),
        name="restablecer_confirmar",
    ),
    path("monitoreo/en-transito/", monitoreo.en_transito, name="monitoreo_en_transito"),
    path("monitoreo/alertas/", monitoreo.alertas, name="monitoreo_alertas"),
    path("monitoreo/novedades/", monitoreo.novedades_pendientes, name="monitoreo_novedades"),
    path(
        "monitoreo/novedades/<int:pk>/marcar-leida/",
        monitoreo.marcar_leida,
        name="monitoreo_marcar_leida",
    ),
    path("monitoreo/indicadores/", monitoreo.indicadores, name="monitoreo_indicadores"),
    path("monitoreo/mi-posicion/", monitoreo.mi_posicion, name="monitoreo_mi_posicion"),
    path(
        "monitoreo/conductores-en-vivo/",
        monitoreo.conductores_en_vivo,
        name="monitoreo_conductores_en_vivo",
    ),
    path("reportes/", ReporteView.as_view(), name="reportes"),
    path("sincronizacion/lote/", sincronizacion.lote, name="sincronizacion_lote"),
    path(
        "sincronizacion/configuracion/",
        sincronizacion.configuracion,
        name="sincronizacion_configuracion",
    ),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    path("", include(router.urls)),
]
