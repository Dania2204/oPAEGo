from django.urls import path

from . import views

app_name = "monitoreo"

urlpatterns = [
    path("panel/", views.HoyView.as_view(), name="panel"),
    path("monitoreo/", views.MapaView.as_view(), name="mapa"),
    path("conductor/", views.ConductorEnVivoView.as_view(), name="conductor"),
    path("indicadores/", views.IndicadoresView.as_view(), name="indicadores"),
    path("cobertura/", views.CoberturaView.as_view(), name="cobertura"),
    path("novedades/", views.NovedadesView.as_view(), name="novedades"),
    path("novedades/<int:pk>/", views.NovedadesView.as_view(), name="novedad"),
]
