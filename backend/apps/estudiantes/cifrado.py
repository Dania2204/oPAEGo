"""Cifrado de las plantillas faciales (dato sensible, Ley 1581 art. 5).

El vector se empaqueta como float32 y se cifra con Fernet (AES-128-CBC + HMAC)
usando `settings.BIOMETRIA_CLAVE`. Sin la clave, lo que hay en la base de datos
no sirve para reconstruir ni comparar caras.
"""

import math
import struct

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

DIMENSIONES_VALIDAS = range(64, 1025)


class BiometriaNoConfigurada(Exception):
    """Falta BIOMETRIA_CLAVE: la biometría está deshabilitada."""


class VectorInvalido(ValueError):
    pass


def _fernet():
    clave = getattr(settings, "BIOMETRIA_CLAVE", "")
    if not clave:
        raise BiometriaNoConfigurada(
            "La biometría no está configurada en el servidor (BIOMETRIA_CLAVE)."
        )
    return Fernet(clave)


def validar_vector(valores):
    """Lista de números finitos con una dimensión razonable; devuelve floats."""
    if not isinstance(valores, (list, tuple)) or len(valores) not in DIMENSIONES_VALIDAS:
        raise VectorInvalido("El vector facial no tiene una dimensión válida.")
    try:
        vector = [float(v) for v in valores]
    except (TypeError, ValueError) as exc:
        raise VectorInvalido("El vector facial debe contener solo números.") from exc
    if not all(math.isfinite(v) for v in vector):
        raise VectorInvalido("El vector facial contiene valores no finitos.")
    if not any(vector):
        raise VectorInvalido("El vector facial está vacío.")
    return vector


def cifrar_vector(valores):
    vector = validar_vector(valores)
    datos = struct.pack(f"<{len(vector)}f", *vector)
    return _fernet().encrypt(datos).decode()


def descifrar_vector(token):
    try:
        datos = _fernet().decrypt(token.encode())
    except InvalidToken as exc:
        raise VectorInvalido("No se pudo descifrar la plantilla (¿cambió la clave?).") from exc
    return list(struct.unpack(f"<{len(datos) // 4}f", datos))


def similitud_coseno(a, b):
    if len(a) != len(b):
        raise VectorInvalido("Los vectores tienen dimensiones distintas.")
    producto = sum(x * y for x, y in zip(a, b, strict=True))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return producto / norma if norma else 0.0
