"""Códigos del Anexo 6A de SIMAT (matrícula) y sus etiquetas legibles.

El archivo de matrícula del Ministerio usa códigos numéricos para el grado y la
jornada (codificación DANE/SIMAT). Aquí se traducen a texto para los mensajes del
comando de importación y el reporte de cobertura. Un código desconocido se muestra
tal cual, de modo que un cambio en la codificación nunca oculta información.

Nota de privacidad: este módulo y todo el flujo de importación trabajan solo con
conteos agregados. Los datos personales de los estudiantes (nombre, documento,
dirección, etc.) nunca se almacenan (minimización de datos, Ley 1581).
"""

# Grado (columna GRADO). Preescolar en negativos, básica y media 0–11,
# ciclos de educación para adultos (CLEI) 21–26.
GRADOS = {
    "-2": "Prejardín",
    "-1": "Jardín",
    "0": "Transición",
    "1": "1°",
    "2": "2°",
    "3": "3°",
    "4": "4°",
    "5": "5°",
    "6": "6°",
    "7": "7°",
    "8": "8°",
    "9": "9°",
    "10": "10°",
    "11": "11°",
    "21": "CLEI 1 (adultos)",
    "22": "CLEI 2 (adultos)",
    "23": "CLEI 3 (adultos)",
    "24": "CLEI 4 (adultos)",
    "25": "CLEI 5 (adultos)",
    "26": "CLEI 6 (adultos)",
    "99": "Sin definir",
}

# Jornada (columna TIPO_JORNADA), codificación DANE/SIMAT.
JORNADAS = {
    "1": "Mañana",
    "2": "Tarde",
    "3": "Noche",
    "4": "Completa",
    "5": "Fin de semana",
    "6": "Única",
}


def etiqueta_grado(codigo):
    codigo = str(codigo)
    return GRADOS.get(codigo, f"Grado {codigo}")


def etiqueta_jornada(codigo):
    codigo = str(codigo)
    return JORNADAS.get(codigo, f"Jornada {codigo}")
