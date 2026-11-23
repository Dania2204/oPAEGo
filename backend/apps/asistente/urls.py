from django.urls import path

from . import views

app_name = "asistente"

urlpatterns = [
    path("asistente/", views.AsistenteView.as_view(), name="chat"),
]
