from django.urls import path

from . import views

app_name = "estudiantes"

urlpatterns = [
    path("estudiantes/", views.EstudiantesView.as_view(), name="lista"),
    path("estudiantes/nuevo/", views.EstudianteNuevoView.as_view(), name="nuevo"),
    path("estudiantes/importar/", views.ImportarView.as_view(), name="importar"),
    path("estudiantes/importar/<int:pk>/", views.ImportacionView.as_view(), name="importacion"),
    path("estudiantes/exportar/", views.ExportarView.as_view(), name="exportar"),
    path("estudiantes/carnes/", views.CarnesView.as_view(), name="carnes"),
    path("estudiantes/<int:pk>/", views.EstudianteDetalleView.as_view(), name="detalle"),
]
