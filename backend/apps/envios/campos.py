import base64
import binascii
import uuid

from django.core.files.base import ContentFile
from rest_framework import serializers


class ImagenBase64Field(serializers.ImageField):
    """Acepta un archivo (multipart) o una imagen en base64.

    El base64 permite que la app móvil guarde la foto en su cola sin conexión
    y la envíe dentro del JSON de sincronización (RF-38).
    """

    def to_internal_value(self, data):
        if isinstance(data, str):
            if data.startswith("data:") and ";base64," in data:
                cabecera, data = data.split(";base64,", 1)
                extension = cabecera.split("/")[-1] or "jpg"
            else:
                extension = "jpg"
            try:
                contenido = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError) as error:
                raise serializers.ValidationError("La imagen en base64 no es válida.") from error
            data = ContentFile(contenido, name=f"{uuid.uuid4().hex}.{extension[:4]}")
        return super().to_internal_value(data)
