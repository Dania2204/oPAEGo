"""Códigos del Anexo 6A de SIMAT (matrícula) y sus etiquetas legibles.

El archivo de matrícula del Ministerio usa códigos numéricos para el grado y la
jornada (codificación DANE/SIMAT). Aquí se traducen a texto para los mensajes del
comando de importación y el reporte de cobertura. Un código desconocido se muestra
tal cual, de modo que un cambio en la codificación nunca oculta información.

Nota de privacidad (Ley 1581, minimización): `importar_simat` solo guarda conteos.
`importar_estudiantes` (entrega del PAE por estudiante) guarda únicamente la
identidad mínima: documento, nombres, apellidos y curso. `leer_anexo` solo entrega
las columnas que se le piden, así que el resto del Anexo (dirección, teléfono,
SISBÉN, víctima, discapacidad, etnia, ...) nunca sale del archivo.
"""

import openpyxl


class AnexoInvalido(ValueError):
    """El archivo no es un Anexo 6A utilizable."""


def leer_anexo(archivo, columnas):
    """Itera las filas del Anexo 6A como diccionarios con SOLO `columnas` (streaming)."""
    wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)
    try:
        it = wb.active.iter_rows(values_only=True)
        try:
            cabecera = [str(c).strip() if c is not None else "" for c in next(it)]
        except StopIteration:
            raise AnexoInvalido("El archivo está vacío.") from None
        faltan = [c for c in columnas if c not in cabecera]
        if faltan:
            raise AnexoInvalido(f"Al archivo le faltan columnas: {', '.join(faltan)}")
        indices = {c: cabecera.index(c) for c in columnas}
        for valores in it:
            if valores is None:
                continue
            yield {c: valores[i] for c, i in indices.items()}
    finally:
        wb.close()


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
