from django.urls import path

from . import views

app_name = "estudiantes"

urlpatterns = [
    path("estudiantes/", views.EstudiantesView.as_view(), name="lista"),
    path("estudiantes/exportar/", views.ExportarView.as_view(), name="exportar"),
    path("estudiantes/<int:pk>/", views.EstudianteDetalleView.as_view(), name="detalle"),
]
