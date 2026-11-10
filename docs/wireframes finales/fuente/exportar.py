"""Exporta los wireframes HTML de esta carpeta a PNG @2x.

Uso (desde oPAEGo/backend, con el .venv que trae Playwright):
    python "../docs/wireframes finales/fuente/exportar.py"
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent

WEB = {
    "w18": "18-estudiantes-pae.png",
    "w19": "19-estudiante-autorizacion.png",
    "w20": "20-estudiante-autorizado.png",
    "w21": "21-supervisores-pae.png",
    "w22": "22-nuevo-supervisor.png",
}
MOVIL = {
    "m01": "M01-supervisor-cursos.png",
    "m02": "M02-supervisor-curso.png",
    "m03": "M03-supervisor-acciones.png",
    "m04": "M04-supervisor-entrega-manual.png",
    "m05": "M05-supervisor-autorizacion.png",
    "m06": "M06-supervisor-inscribir-rostro.png",
    "m07": "M07-supervisor-reconocer.png",
    "m08": "M08-supervisor-historial.png",
    "m09": "M09-institucion-estudiantes-hoy.png",
}


def exportar(pagina, html, figuras, destino, ancho):
    destino.mkdir(exist_ok=True)
    pagina.set_viewport_size({"width": ancho, "height": 1000})
    pagina.goto(html.as_uri())
    pagina.wait_for_load_state("networkidle")
    pagina.evaluate("document.fonts.ready")
    for ident, archivo in figuras.items():
        pagina.locator(f"#{ident}").screenshot(path=str(destino / archivo))
        print(destino.name, archivo)


with sync_playwright() as p:
    navegador = p.chromium.launch(channel="chrome")
    pagina = navegador.new_page(device_scale_factor=2)
    exportar(pagina, AQUI / "web.html", WEB, RAIZ / "web", 1440)
    exportar(pagina, AQUI / "movil.html", MOVIL, RAIZ / "movil", 390)
    navegador.close()
