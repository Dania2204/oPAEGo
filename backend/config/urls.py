from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("api/", include(("config.api_urls", "api"), namespace="api")),
    # PWA (RF-38): el service worker debe servirse desde la raíz para
    # controlar todas las páginas del panel.
    path(
        "sw.js",
        TemplateView.as_view(template_name="pwa/sw.js", content_type="application/javascript"),
        name="service_worker",
    ),
    path(
        "manifest.webmanifest",
        TemplateView.as_view(
            template_name="pwa/manifest.webmanifest", content_type="application/manifest+json"
        ),
        name="manifest",
    ),
    path("", include("apps.cuentas.urls")),
    path("", include("apps.monitoreo.urls")),
    path("", include("apps.catalogo.urls")),
    path("", include("apps.envios.urls")),
    path("", include("apps.auditoria.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
