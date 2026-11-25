"""Cambio de biometría facial a código QR por estudiante.

- Cada estudiante recibe un `codigo_qr` aleatorio y único (los existentes también).
- Se eliminan la autorización biométrica y las plantillas faciales (borrado real de
  los vectores) y la similitud de la entrega.
- Las entregas ya registradas como FACIAL se conservan: son inmutables y el método
  queda como etiqueta histórica.
"""

import secrets

from django.db import migrations, models

import apps.estudiantes.models


def asignar_codigos(apps, schema_editor):
    Estudiante = apps.get_model("estudiantes", "Estudiante")
    usados = set()
    for estudiante in Estudiante.objects.filter(codigo_qr__isnull=True).iterator():
        codigo = secrets.token_urlsafe(16)
        while codigo in usados:
            codigo = secrets.token_urlsafe(16)
        usados.add(codigo)
        estudiante.codigo_qr = codigo
        estudiante.save(update_fields=["codigo_qr"])


class Migration(migrations.Migration):
    dependencies = [
        ("estudiantes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="estudiante",
            name="codigo_qr",
            field=models.CharField(editable=False, max_length=32, null=True),
        ),
        migrations.RunPython(asignar_codigos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="estudiante",
            name="codigo_qr",
            field=models.CharField(
                default=apps.estudiantes.models.nuevo_codigo_qr,
                editable=False,
                max_length=32,
                unique=True,
                verbose_name="código QR",
            ),
        ),
        migrations.DeleteModel(name="PlantillaFacial"),
        migrations.DeleteModel(name="AutorizacionBiometrica"),
        migrations.RemoveField(model_name="entregaestudiante", name="similitud"),
        migrations.AlterField(
            model_name="entregaestudiante",
            name="metodo",
            field=models.CharField(
                choices=[
                    ("QR", "Código QR"),
                    ("MANUAL", "Registro manual"),
                    ("FACIAL", "Reconocimiento facial"),
                ],
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="entregaestudiante",
            name="motivo",
            field=models.TextField(
                blank=True,
                help_text="Obligatorio en el registro manual (por qué sin el código QR).",
            ),
        ),
    ]
