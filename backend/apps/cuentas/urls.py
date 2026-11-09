from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("ingresar/", views.InicioSesionView.as_view(), name="login"),
    path("salir/", views.cerrar_sesion, name="logout"),
    path("restablecer/", views.SolicitarRestablecimientoView.as_view(), name="restablecer"),
    path(
        "restablecer/<uidb64>/<token>/",
        views.ConfirmarRestablecimientoView.as_view(),
        name="restablecer_confirmar",
    ),
    path("usuarios/", views.UsuarioListaView.as_view(), name="usuarios"),
    path("usuarios/nuevo/", views.UsuarioFormularioView.as_view(), name="usuario_nuevo"),
    path("usuarios/<int:pk>/editar/", views.UsuarioFormularioView.as_view(), name="usuario_editar"),
    path("usuarios/<int:pk>/estado/", views.cambiar_estado_usuario, name="usuario_estado"),
]
