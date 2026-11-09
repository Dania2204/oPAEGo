from django.urls import path

from . import views

app_name = "envios"

urlpatterns = [
    path("envios/", views.EnvioListaView.as_view(), name="lista"),
    path("envios/nuevo/", views.EnvioFormularioView.as_view(), name="nuevo"),
    path("envios/programar/", views.ProgramarView.as_view(), name="programar"),
    path("envios/<int:pk>/", views.EnvioDetalleView.as_view(), name="detalle"),
    path("envios/<int:pk>/editar/", views.EnvioFormularioView.as_view(), name="editar"),
    path("envios/<int:pk>/reasignar/", views.ReasignarView.as_view(), name="reasignar"),
    path("envios/<int:pk>/cancelar/", views.CancelarView.as_view(), name="cancelar"),
    path("envios/<int:pk>/cerrar/", views.CerrarConNovedadView.as_view(), name="cerrar"),
]
