from django.urls import path, register_converter

from . import views


class ModuloConverter:
    regex = "|".join(views.MODULOS)

    def to_python(self, valor):
        return valor

    def to_url(self, valor):
        return valor


register_converter(ModuloConverter, "modulo")

app_name = "catalogo"

urlpatterns = [
    path("<modulo:modulo>/", views.ListaView.as_view(), name="lista"),
    path("<modulo:modulo>/nuevo/", views.FormularioView.as_view(), name="nuevo"),
    path("<modulo:modulo>/<int:pk>/editar/", views.FormularioView.as_view(), name="editar"),
    path("<modulo:modulo>/<int:pk>/estado/", views.CambiarEstadoView.as_view(), name="estado"),
]
