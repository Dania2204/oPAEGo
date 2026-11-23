"""Importa los estudiantes de una institución desde el Anexo 6A de SIMAT.

    python manage.py importar_estudiantes <archivo.xlsx> --dane 152001000661 \\
            --institucion "Normal Superior" [--grados 0,1,...,11] [--dry-run]

Mismas reglas que «Actualizar desde SIMAT» del panel web (ver
`apps/estudiantes/importacion.py`): solo identidad mínima, idempotente por PER_ID,
crea a los nuevos con su código QR y da de baja a quien ya no aparece.
`--grados` limita la importación a esos códigos de grado; por defecto, todos.
El archivo de SIMAT nunca se guarda en el repositorio (carpeta bd/ en .gitignore).
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalogo.models import Institucion
from apps.catalogo.simat import AnexoInvalido
from apps.estudiantes import importacion


class Command(BaseCommand):
    help = "Importa los estudiantes (identidad mínima) de una institución desde SIMAT."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta del Anexo 6A de SIMAT (.xlsx).")
        parser.add_argument(
            "--dane",
            action="append",
            required=True,
            metavar="CODIGO_DANE",
            help="CODIGO_DANE de la institución (repetir si tiene varios).",
        )
        parser.add_argument(
            "--institucion",
            required=True,
            help="Nombre (o parte) de la institución en PAEGo a la que se asignan.",
        )
        parser.add_argument(
            "--grados",
            help="Códigos de grado SIMAT a importar, separados por coma (p. ej. 0,1,2,...,11). "
            "Por defecto, todos.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo muestra el resumen; no escribe en la base de datos.",
        )

    def handle(self, *args, **opciones):
        archivo = Path(opciones["archivo"])
        if not archivo.exists():
            raise CommandError(f"No existe el archivo: {archivo}")
        institucion = self._institucion(opciones["institucion"])
        grados = (
            {g.strip() for g in opciones["grados"].split(",") if g.strip()}
            if opciones.get("grados")
            else None
        )
        try:
            leidos = importacion.leer(archivo, opciones["dane"], grados)
        except AnexoInvalido as exc:
            raise CommandError(str(exc)) from exc

        if opciones["dry_run"]:
            self._resumen(institucion, importacion.planear(institucion, leidos))
            self.stdout.write(self.style.WARNING("Simulación (--dry-run): no se escribió nada."))
            return
        r = importacion.aplicar(institucion, leidos, nombre_archivo=archivo.name)
        self._resumen(institucion, r)
        actualizados = r["cambian_curso"] + r["reactivados"] + r["corregidos"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Listo: {r['nuevos']} nuevos, {actualizados} actualizados, "
                f"{r['bajas']} dados de baja."
            )
        )

    def _institucion(self, texto):
        coincidencias = list(Institucion.objects.filter(nombre__icontains=texto.strip()))
        if len(coincidencias) != 1:
            nombres = ", ".join(str(i) for i in coincidencias) or "ninguna"
            raise CommandError(
                f"«{texto}» debe coincidir con exactamente una institución (coinciden: {nombres})."
            )
        return coincidencias[0]

    def _resumen(self, institucion, r):
        self.stdout.write(f"{r['leidos']} estudiantes en el archivo para {institucion}:")
        for clave, texto in [
            ("nuevos", "nuevos"),
            ("cambian_curso", "cambian de curso"),
            ("reactivados", "vuelven a la matrícula"),
            ("corregidos", "con datos corregidos"),
            ("sin_cambios", "sin cambios"),
            ("bajas", "salen de la matrícula"),
        ]:
            self.stdout.write(f"  {texto}: {r[clave]}")
