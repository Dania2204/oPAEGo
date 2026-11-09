from django.urls import path

from . import views

app_name = "auditoria"

urlpatterns = [
    path("auditoria/", views.AuditoriaView.as_view(), name="lista"),
    path("reportes/", views.ReportesView.as_view(), name="reportes"),
]
