"""Genera un HTML autónomo con las pantallas reales del panel PAEGo.

Recorre la aplicación en ejecución, toma el contenido renderizado de cada
pantalla y lo empaqueta con el CSS y los scripts de mapas e indicadores en un
solo archivo que se abre con doble clic.

Uso (con el servidor corriendo en el puerto 8011 y los datos de `seed_demo`):

    cd backend
    python manage.py runserver 8011
    python ../scripts/presentacion/generar_presentacion.py . \
        ../docs/presentacion/PAEGo-presentacion.html

Con PAEGO_URL=https://... se genera desde la plataforma desplegada.

Requiere Playwright y Google Chrome (`pip install playwright`).
"""

import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

# URL de la plataforma; por defecto el servidor local.
BASE = os.environ.get("PAEGO_URL", "http://127.0.0.1:8011").rstrip("/")
BACKEND = sys.argv[1]
SALIDA = sys.argv[2]

PANTALLAS = [
    # (id de la sección en el HTML, ruta en el servidor)
    ("hoy", "/panel/"),
    ("envios", "/envios/"),
    ("detalle", None),  # se resuelve con el envío entregado
    ("novedades", "/novedades/"),
    ("programar", "/envios/programar/"),
    ("instituciones", "/instituciones/"),
    ("responsables", "/responsables/"),
    ("conductores", "/conductores/"),
    ("vehiculos", "/vehiculos/"),
    ("indicadores", "/indicadores/"),
    ("reportes", "/reportes/"),
    ("auditoria", "/auditoria/"),
    ("usuarios", "/usuarios/"),
]


def leer(ruta):
    return open(os.path.join(BACKEND, ruta), encoding="utf-8").read()


def limpiar(html):
    # Scripts ejecutables del servidor fuera; los datos JSON se conservan.
    html = re.sub(r"<script(?![^>]*application/json)[^>]*>.*?</script>", "", html, flags=re.S)
    html = re.sub(r"\scsrfmiddlewaretoken[^>]*", "", html)
    html = re.sub(r'<input type="hidden" name="csrfmiddlewaretoken"[^>]*>', "", html)
    return html


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, service_workers="block")
    pg = ctx.new_page()

    pg.goto(BASE + "/ingresar/")
    acceso = pg.eval_on_selector("main.acceso-pagina", "e => e.outerHTML")
    pg.fill("input[type=email]", "admin@paego.local")
    pg.fill("input[type=password]", "Paego2026!")
    if pg.locator("input[name=acepta_datos]").count():
        pg.check("input[name=acepta_datos]")
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")

    pg.goto(BASE + "/envios/")
    enlaces = pg.eval_on_selector_all(
        "a[href^='/envios/']", "es => es.map(e => e.getAttribute('href'))"
    )
    detalle_url = None
    for href in enlaces:
        if re.fullmatch(r"/envios/\d+/", href):
            detalle_url = href  # el último de la lista es el entregado (más antiguo)
    print("detalle:", detalle_url)

    secciones = {}
    rutas = {}
    for clave, ruta in PANTALLAS:
        ruta = ruta or detalle_url
        rutas[ruta] = clave
        pg.goto(BASE + ruta)
        pg.wait_for_load_state("networkidle")
        secciones[clave] = limpiar(pg.eval_on_selector("main#principal", "e => e.innerHTML"))

    pg.goto(BASE + "/panel/")
    iconos = pg.eval_on_selector("body > svg", "e => e.outerHTML")
    cabecera = limpiar(pg.eval_on_selector("header.cabecera", "e => e.outerHTML"))
    nav = pg.eval_on_selector("nav.nav", "e => e.outerHTML")
    b.close()

# El menú lateral apunta a las secciones del documento.
for ruta, clave in rutas.items():
    nav = nav.replace(f'href="{ruta}"', f'href="#{clave}" data-pantalla="{clave}"')
nav = re.sub(r'\saria-current="page"', "", nav)
cabecera = cabecera.replace('href="/panel/"', 'href="#hoy"').replace(" x-cloak", "")

css = "\n".join(leer(f"static/css/{n}.css") for n in ("tokens", "base", "componentes"))
mapas = leer("static/js/mapas.js")
indicadores = leer("static/js/indicadores.js")
icono = leer("static/img/icono.svg").strip()
icono_uri = "data:image/svg+xml," + icono.replace("#", "%23").replace('"', "'")


def con_icono(html):
    return re.sub(r'src="/static/img/icono(?:\.[0-9a-f]+)?\.svg"', f'src="{icono_uri}"', html)


cabecera, acceso = con_icono(cabecera), con_icono(acceso)
for k in secciones:
    secciones[k] = con_icono(secciones[k])

acceso = re.sub(
    r'<form method="post" class="formulario"[^>]*>',
    '<form class="formulario" data-ingresar novalidate>',
    acceso,
    count=1,
)
acceso = re.sub(
    r'(<input[^>]*type="email"[^>]*?)(\s*/?>)', r'\1 value="admin@paego.local"\2', acceso, count=1
)
acceso = re.sub(
    r'(<input[^>]*type="password"[^>]*?)(\s*/?>)', r'\1 value="Paego2026!"\2', acceso, count=1
)
acceso = acceso.replace('name="acepta_datos"', 'name="acepta_datos" checked', 1)

cuerpo_pantallas = "\n".join(
    f'<section class="pantalla" id="{k}" hidden>{v}</section>' for k, v in secciones.items()
)

plantilla = open(
    os.path.join(os.path.dirname(__file__), "plantilla_presentacion.html"), encoding="utf-8"
).read()
html = (
    plantilla.replace("/*__CSS__*/", css)
    .replace("<!--__ICONOS__-->", iconos)
    .replace("<!--__ACCESO__-->", acceso)
    .replace("<!--__CABECERA__-->", cabecera)
    .replace("<!--__NAV__-->", nav)
    .replace("<!--__PANTALLAS__-->", cuerpo_pantallas)
    .replace("/*__MAPAS__*/", mapas)
    .replace("/*__INDICADORES__*/", indicadores)
    .replace("__RUTAS__", json.dumps(rutas))
    .replace("__ICONO__", icono_uri)
)
os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
open(SALIDA, "w", encoding="utf-8", newline="\n").write(html)
print("escrito", SALIDA, len(html) // 1024, "KB")
