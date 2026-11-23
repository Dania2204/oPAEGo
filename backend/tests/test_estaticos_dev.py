"""En desarrollo cada estático lleva su versión en la URL (evita JS/CSS viejos en caché)."""

import re

from config.estaticos_dev import EstaticosVersionados


def test_url_lleva_version_del_archivo():
    s = EstaticosVersionados()
    assert re.fullmatch(r"/static/js/app\.js\?v=\d+", s.url("js/app.js"))


def test_archivo_inexistente_queda_sin_version():
    assert EstaticosVersionados().url("js/no-existe.js") == "/static/js/no-existe.js"
