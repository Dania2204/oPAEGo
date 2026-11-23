"""Estáticos siempre frescos en desarrollo.

`runserver` sirve /static/ sin `Cache-Control`; Chrome aplica caché heurística
y, tras un F5 normal, puede seguir usando un `app.js` viejo (con comportamiento
ya corregido). Aquí `{% static %}` añade `?v=<fecha de modificación>`, así cada
cambio produce una URL nueva. En producción no hace falta: WhiteNoise sirve
nombres con hash (ManifestStaticFilesStorage).
"""

import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class EstaticosVersionados(StaticFilesStorage):
    def url(self, name):
        url = super().url(name)
        ruta = finders.find(name) if name else None
        if not ruta or isinstance(ruta, list):
            return url
        return f"{url}?v={int(os.path.getmtime(ruta))}"
