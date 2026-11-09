"""Recorridos (polilíneas) para los datos de demostración.

`ruta(origen, destino)` devuelve una lista de puntos `[lat, lng]` que, idealmente,
sigue las calles reales de Pasto. El orden de preferencia es:

1. Caché versionada (`data/rutas_demo.json`): offline y reproducible.
2. OSRM público (sin clave), si hay red; el resultado se guarda en la caché.
3. Ruta sintética (interpolación con leve ruido), determinista, si no hay red.

Solo lo usa el comando `demo_mes`; no interviene en la operación real.
"""

import json
import math
import random
import urllib.error
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "data" / "rutas_demo.json"
OSRM = (
    "https://router.project-osrm.org/route/v1/driving/"
    "{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
)


def _clave(origen, destino):
    return (
        f"{round(origen[0], 5)},{round(origen[1], 5)}|{round(destino[0], 5)},{round(destino[1], 5)}"
    )


def _cargar_cache():
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_cache(datos):
    try:
        CACHE.write_text(
            json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    except OSError:
        pass


def _osrm(origen, destino):
    url = OSRM.format(lon1=origen[1], lat1=origen[0], lon2=destino[1], lat2=destino[0])
    try:
        with urllib.request.urlopen(url, timeout=8) as respuesta:  # noqa: S310 (URL fija de OSRM)
            datos = json.load(respuesta)
        coords = datos["routes"][0]["geometry"]["coordinates"]  # [lon, lat]
        return [[round(lat, 6), round(lon, 6)] for lon, lat in coords]
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError, OSError):
        return None


def _sintetica(origen, destino, puntos=24, ruido=0.0006):
    """Línea entre origen y destino con dos waypoints desviados; determinista."""
    rnd = random.Random(_clave(origen, destino))
    lat1, lng1 = origen
    lat2, lng2 = destino
    # Desvío lateral para que no sea una recta perfecta.
    dx, dy = (lat2 - lat1), (lng2 - lng1)
    desvio = (-dy, dx)
    ruta_puntos = []
    for i in range(puntos + 1):
        t = i / puntos
        curva = math.sin(t * math.pi) * ruido * 4
        lat = lat1 + dx * t + desvio[0] * curva
        lng = lng1 + dy * t + desvio[1] * curva
        if 0 < i < puntos:
            lat += (rnd.random() - 0.5) * ruido
            lng += (rnd.random() - 0.5) * ruido
        ruta_puntos.append([round(lat, 6), round(lng, 6)])
    return ruta_puntos


def ruta(origen, destino, *, usar_red=True):
    """origen y destino son (lat, lng). Devuelve [[lat, lng], ...]."""
    cache = _cargar_cache()
    clave = _clave(origen, destino)
    if clave in cache:
        return cache[clave]
    puntos = _osrm(origen, destino) if usar_red else None
    if puntos is None:
        return _sintetica(origen, destino)
    cache[clave] = puntos
    _guardar_cache(cache)
    return puntos
