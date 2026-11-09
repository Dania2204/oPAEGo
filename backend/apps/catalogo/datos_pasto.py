"""Datos maestros reales de Pasto para la demostración (`demo_mes`).

Instituciones educativas municipales (IEM) reales de Pasto con coordenadas
aproximadas reales, conductores con placas de Nariño y el punto de bodega desde
donde salen los recorridos. Sirven para que el demo luzca como la operación real;
no se usan en las pruebas de dominio (esas tienen sus propias fixtures).
"""

from decimal import Decimal

# Punto de salida de los envíos (zona central de Pasto).
BODEGA = (Decimal("1.213600"), Decimal("-77.278100"))

# (lat, lng) aproximados reales dentro del casco de Pasto.
INSTITUCIONES = [
    {
        "nombre": "Escuela Normal Superior de Pasto",
        "sede": "Principal",
        "direccion": "Calle 18 # 41-60",
        "latitud": Decimal("1.216800"),
        "longitud": Decimal("-77.288300"),
        "beneficiarios": 1240,
        "contacto": ("Rectoría", "6027310001"),
    },
    {
        "nombre": "I.E.M. Luis Delfín Insuasty Rodríguez (INEM)",
        "sede": "Principal",
        "direccion": "Avenida Panamericana, barrio Las Cuadras",
        "latitud": Decimal("1.198600"),
        "longitud": Decimal("-77.270600"),
        "beneficiarios": 2480,
        "contacto": ("Coordinación", "6027310002"),
    },
    {
        "nombre": "I.E.M. Ciudad de Pasto",
        "sede": "Principal",
        "direccion": "Carrera 19 # 12-45",
        "latitud": Decimal("1.208900"),
        "longitud": Decimal("-77.264200"),
        "beneficiarios": 1560,
        "contacto": ("Almacén", "6027310003"),
    },
    {
        "nombre": "I.E.M. Técnico Industrial",
        "sede": "Principal",
        "direccion": "Calle 20 # 28-15",
        "latitud": Decimal("1.211200"),
        "longitud": Decimal("-77.276500"),
        "beneficiarios": 980,
        "contacto": ("Coordinación", "6027310004"),
    },
    {
        "nombre": "I.E.M. Libertad",
        "sede": "Principal",
        "direccion": "Barrio La Libertad, Calle 6",
        "latitud": Decimal("1.230500"),
        "longitud": Decimal("-77.285800"),
        "beneficiarios": 1320,
        "contacto": ("Rectoría", "6027310005"),
    },
    {
        "nombre": "I.E.M. Ciudadela Educativa de Pasto",
        "sede": "Principal",
        "direccion": "Barrio Niño Jesús de Praga",
        "latitud": Decimal("1.195200"),
        "longitud": Decimal("-77.263900"),
        "beneficiarios": 1870,
        "contacto": ("Coordinación", "6027310006"),
    },
    {
        "nombre": "I.E.M. Mercedario",
        "sede": "Principal",
        "direccion": "Barrio Mercedario, Carrera 3E",
        "latitud": Decimal("1.223700"),
        "longitud": Decimal("-77.271900"),
        "beneficiarios": 760,
        "contacto": ("Almacén", "6027310007"),
    },
    {
        "nombre": "I.E.M. Chambú",
        "sede": "Principal",
        "direccion": "Barrio Chambú, Calle 19",
        "latitud": Decimal("1.200800"),
        "longitud": Decimal("-77.282200"),
        "beneficiarios": 1130,
        "contacto": ("Coordinación", "6027310008"),
    },
    {
        "nombre": "I.E.M. Pedagógico",
        "sede": "Principal",
        "direccion": "Carrera 22 # 15-30",
        "latitud": Decimal("1.215600"),
        "longitud": Decimal("-77.274900"),
        "beneficiarios": 640,
        "contacto": ("Rectoría", "6027310009"),
    },
    {
        "nombre": "I.E.M. Obonuco",
        "sede": "Principal",
        "direccion": "Corregimiento de Obonuco",
        "latitud": Decimal("1.196900"),
        "longitud": Decimal("-77.313900"),
        "beneficiarios": 410,
        "contacto": ("Coordinación", "6027310010"),
    },
]

# Conductores reales-plausibles con placas de Nariño (prefijos OCW/OCV/OCX…).
CONDUCTORES = [
    ("Carlos", "Pérez Rosero", "1085210011", "3104650011", "OCW231", "Furgón", 1500),
    ("Luisa", "Gómez Narváez", "1085210022", "3104650022", "OCV118", "Camión", 3500),
    ("Jairo", "Burbano Chamorro", "1085210033", "3104650033", "OCX472", "Furgón", 1800),
    ("Marcela", "Ortega Riascos", "1085210044", "3104650044", "OCW905", "Camioneta", 900),
    ("Diego", "Benavides Erazo", "1085210055", "3104650055", "OCV640", "Furgón", 1600),
    ("Yaneth", "Delgado Muñoz", "1085210066", "3104650066", "OCX087", "Camión", 3200),
]
