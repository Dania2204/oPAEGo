"""Importa los estudiantes de una institución desde el Anexo 6A de SIMAT.

    python manage.py importar_estudiantes <archivo.xlsx> --dane 152001000661 \\
            --institucion "Normal Superior" [--dry-run]

Para registrar la entrega del PAE por estudiante se necesita saber quiénes son.
Del Anexo solo se leen las columnas de identidad mínima (PER_ID, documento,
nombres, apellidos, grado, grupo, jornada y sede): `leer_anexo` nunca entrega las
demás (dirección, teléfono, SISBÉN, víctima, discapacidad, etnia, fecha de
nacimiento, ...). Ley 1581: minimización de datos de menores.

Idempotente por PER_ID: actualiza a quien ya existe, crea a los nuevos y da de
baja (inactivo y sin plantillas faciales) a quien ya no aparece en el archivo.
El archivo de SIMAT nunca se guarda en el repositorio (carpeta bd/ en .gitignore).
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogo.models import Institucion
from apps.catalogo.simat import AnexoInvalido, etiqueta_grado, leer_anexo
from apps.estudiantes import servicios
from apps.estudiantes.models import Estudiante

COLUMNAS = [
    "PER_ID",
    "CODIGO_DANE",
    "CONS_SEDE",
    "TIPO_DOCUMENTO",
    "NRO_DOCUMENTO",
    "APELLIDO1",
    "APELLIDO2",
    "NOMBRE1",
    "NOMBRE2",
    "GRADO",
    "GRUPO",
    "TIPO_JORNADA",
]


def _texto(valor):
    """Celda de Excel como texto: 1085123456.0 → «1085123456»."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return str(valor).strip()


def _nombre(*partes):
    return " ".join(_texto(p).title() for p in partes if _texto(p))


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
            "--dry-run",
            action="store_true",
            help="Solo muestra el resumen; no escribe en la base de datos.",
        )

    def handle(self, *args, **opciones):
        archivo = Path(opciones["archivo"])
        if not archivo.exists():
            raise CommandError(f"No existe el archivo: {archivo}")
        institucion = self._institucion(opciones["institucion"])
        danes = {str(d).strip() for d in opciones["dane"]}

        leidos = {}
        try:
            for fila in leer_anexo(archivo, COLUMNAS):
                if _texto(fila["CODIGO_DANE"]) not in danes:
                    continue
                per_id = _texto(fila["PER_ID"])
                if not per_id:
                    continue
                leidos[per_id] = {
                    "tipo_documento": _texto(fila["TIPO_DOCUMENTO"])[:10],
                    "numero_documento": _texto(fila["NRO_DOCUMENTO"])[:20],
                    "nombres": _nombre(fila["NOMBRE1"], fila["NOMBRE2"])[:100],
                    "apellidos": _nombre(fila["APELLIDO1"], fila["APELLIDO2"])[:100],
                    "grado": _texto(fila["GRADO"])[:4],
                    "grupo": _texto(fila["GRUPO"])[:10],
                    "jornada": _texto(fila["TIPO_JORNADA"])[:2],
                    "sede_simat": _texto(fila["CONS_SEDE"])[:20],
                }
        except AnexoInvalido as exc:
            raise CommandError(str(exc)) from exc

        if not leidos:
            raise CommandError(
                f"No se encontraron estudiantes para los CODIGO_DANE {', '.join(sorted(danes))}."
            )
        self._resumen(institucion, leidos)
        if opciones["dry_run"]:
            self.stdout.write(self.style.WARNING("Simulación (--dry-run): no se escribió nada."))
            return
        nuevos, actualizados, bajas = self._guardar(institucion, leidos)
        self.stdout.write(
            self.style.SUCCESS(
                f"Listo: {nuevos} nuevos, {actualizados} actualizados, {bajas} dados de baja."
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

    def _resumen(self, institucion, leidos):
        por_grado = {}
        for datos in leidos.values():
            por_grado[datos["grado"]] = por_grado.get(datos["grado"], 0) + 1
        self.stdout.write(f"{len(leidos)} estudiantes para {institucion}:")
        for grado in sorted(por_grado, key=lambda g: int(g) if g.lstrip("-").isdigit() else 99):
            self.stdout.write(f"  {etiqueta_grado(grado)}: {por_grado[grado]}")

    @transaction.atomic
    def _guardar(self, institucion, leidos):
        existentes = {e.simat_per_id: e for e in Estudiante.objects.filter(simat_per_id__in=leidos)}
        nuevos = actualizados = 0
        for per_id, datos in leidos.items():
            estudiante = existentes.get(per_id)
            if estudiante is None:
                Estudiante.objects.create(simat_per_id=per_id, institucion=institucion, **datos)
                nuevos += 1
                continue
            cambios = {k: v for k, v in datos.items() if getattr(estudiante, k) != v}
            if estudiante.institucion_id != institucion.pk:
                cambios["institucion"] = institucion
            if not estudiante.activo:
                cambios["activo"] = True
            if cambios:
                for campo, valor in cambios.items():
                    setattr(estudiante, campo, valor)
                estudiante.save()
                actualizados += 1

        bajas = 0
        retirados = Estudiante.objects.filter(institucion=institucion, activo=True).exclude(
            simat_per_id__in=leidos
        )
        for estudiante in retirados:
            servicios.dar_de_baja(estudiante)
            bajas += 1
        return nuevos, actualizados, bajas
