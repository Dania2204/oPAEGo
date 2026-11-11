"""Importa la matrícula del Anexo 6A de SIMAT como conteos agregados por sede.

    python manage.py importar_simat <archivo.xlsx> --dane 152001000661 \
            --sedes catalogo_sedes.csv [--anio 2026] [--dry-run]

El archivo de SIMAT trae una fila por estudiante con datos personales sensibles
de menores. Este comando **solo cuenta**: agrupa por sede (CONS_SEDE), grado y
jornada, y descarta toda la información personal. La app nunca almacena datos de
estudiantes (minimización de datos, Ley 1581).

Como el Anexo no trae el nombre de la institución ni sus coordenadas, estas se
toman de un CSV aparte (`--sedes`) con las columnas:

    consecutivo_sede,nombre,sede,direccion,latitud,longitud

El comando es idempotente: volver a ejecutarlo reemplaza los conteos de cada
sede y año sin duplicar instituciones ni filas de matrícula.
"""

import csv
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogo.models import Institucion, MatriculaSede
from apps.catalogo.simat import AnexoInvalido, etiqueta_grado, etiqueta_jornada, leer_anexo

# Columnas del Anexo 6A que se usan. El resto (identidad de los estudiantes) se ignora.
COL_ANIO = "ANO_INF"
COL_DANE = "CODIGO_DANE"
COL_SEDE = "CONS_SEDE"
COL_GRADO = "GRADO"
COL_JORNADA = "TIPO_JORNADA"
COL_ZONA = "ZONA"
COLUMNAS_REQUERIDAS = [COL_ANIO, COL_DANE, COL_SEDE, COL_GRADO, COL_JORNADA, COL_ZONA]


class Command(BaseCommand):
    help = "Importa la matrícula de SIMAT (Anexo 6A) como conteos agregados por sede."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta del Anexo 6A de SIMAT (.xlsx).")
        parser.add_argument(
            "--dane",
            action="append",
            required=True,
            metavar="CODIGO_DANE",
            help="CODIGO_DANE a importar (repetir para varias instituciones).",
        )
        parser.add_argument(
            "--sedes",
            help="CSV con consecutivo_sede,nombre,sede,direccion,latitud,longitud.",
        )
        parser.add_argument(
            "--anio",
            type=int,
            help="Filtrar por año (ANO_INF). Por defecto importa todos los años del archivo.",
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
        danes = {str(d).strip() for d in opciones["dane"]}
        anio_filtro = opciones.get("anio")
        catalogo = self._leer_catalogo_sedes(opciones.get("sedes"))

        # (consecutivo_sede, dane, anio, grado, jornada, zona) -> conteo.
        conteos = Counter()
        sedes_dane = {}  # consecutivo_sede -> dane (para reportar)
        leidas = 0
        for fila in self._filas(archivo):
            dane = str(fila[COL_DANE]).strip()
            if dane not in danes:
                continue
            anio = _entero(fila[COL_ANIO])
            if anio_filtro and anio != anio_filtro:
                continue
            sede = str(fila[COL_SEDE]).strip()
            clave = (
                sede,
                anio,
                str(fila[COL_GRADO]).strip(),
                str(fila[COL_JORNADA]).strip(),
                str(fila[COL_ZONA] or "").strip(),
            )
            conteos[clave] += 1
            sedes_dane[sede] = dane
            leidas += 1

        if not conteos:
            raise CommandError(
                "No se encontraron estudiantes para los CODIGO_DANE indicados "
                f"({', '.join(sorted(danes))})."
            )

        self.stdout.write(
            f"Estudiantes contados: {leidas} · sedes: {len(sedes_dane)} "
            f"· DANE: {', '.join(sorted(danes))}" + (f" · año {anio_filtro}" if anio_filtro else "")
        )

        if opciones["dry_run"]:
            self._resumen(conteos, sedes_dane, catalogo)
            self.stdout.write(self.style.WARNING("Simulación (--dry-run): no se escribió nada."))
            return

        self._guardar(conteos, sedes_dane, catalogo)

    # ------------------------------------------------------------------ lectura
    def _filas(self, archivo):
        """Itera las filas del xlsx como diccionarios, en streaming."""
        try:
            yield from leer_anexo(archivo, COLUMNAS_REQUERIDAS)
        except AnexoInvalido as exc:
            raise CommandError(str(exc)) from exc

    def _leer_catalogo_sedes(self, ruta):
        """CSV consecutivo_sede -> {nombre, sede, direccion, latitud, longitud}."""
        if not ruta:
            return {}
        ruta = Path(ruta)
        if not ruta.exists():
            raise CommandError(f"No existe el CSV de sedes: {ruta}")
        catalogo = {}
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            requeridas = {"consecutivo_sede", "nombre", "latitud", "longitud"}
            if not requeridas.issubset({c.strip() for c in (lector.fieldnames or [])}):
                raise CommandError(
                    "El CSV de sedes debe tener al menos las columnas: "
                    "consecutivo_sede, nombre, latitud, longitud."
                )
            for fila in lector:
                clave = (fila.get("consecutivo_sede") or "").strip()
                if not clave:
                    continue
                catalogo[clave] = {
                    "nombre": (fila.get("nombre") or "").strip(),
                    "sede": (fila.get("sede") or "Principal").strip() or "Principal",
                    "direccion": (fila.get("direccion") or "").strip(),
                    "latitud": _decimal(fila.get("latitud")),
                    "longitud": _decimal(fila.get("longitud")),
                }
        return catalogo

    # -------------------------------------------------------------- escritura
    @transaction.atomic
    def _guardar(self, conteos, sedes_dane, catalogo):
        # Agrupar los conteos por sede.
        por_sede = {}
        for (sede, anio, grado, jornada, zona), total in conteos.items():
            por_sede.setdefault(sede, []).append((anio, grado, jornada, zona, total))

        creadas = actualizadas = omitidas = 0
        for sede, filas in sorted(por_sede.items()):
            institucion = self._upsert_institucion(sede, sedes_dane[sede], catalogo.get(sede))
            if institucion is None:
                omitidas += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  Sede {sede} omitida: sin coordenadas (falta en --sedes y no existía)."
                    )
                )
                continue
            creada = institucion._creada  # marca puesta por _upsert_institucion
            anios = {anio for anio, *_ in filas}
            MatriculaSede.objects.filter(institucion=institucion, anio__in=anios).delete()
            MatriculaSede.objects.bulk_create(
                MatriculaSede(
                    institucion=institucion,
                    anio=anio,
                    grado=grado,
                    jornada=jornada,
                    zona=zona,
                    total=total,
                )
                for anio, grado, jornada, zona, total in filas
            )
            institucion.beneficiarios_total = sum(t for *_, t in filas)
            institucion.save(update_fields=["beneficiarios_total", "actualizado_en"])
            creadas += int(creada)
            actualizadas += int(not creada)
            self.stdout.write(
                f"  {institucion} · DANE {institucion.codigo_dane} · "
                f"{institucion.beneficiarios_total} beneficiarios"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo: {creadas} sede(s) creada(s), {actualizadas} actualizada(s)"
                + (f", {omitidas} omitida(s)." if omitidas else ".")
            )
        )

    def _upsert_institucion(self, sede, dane, datos):
        """Busca la sede por consecutivo; si no, por (nombre, sede) del catálogo;
        si tampoco, la crea. Devuelve None si no hay coordenadas para crearla."""
        institucion = Institucion.objects.filter(consecutivo_sede=sede).first()
        if institucion is None and datos and datos["nombre"]:
            institucion = Institucion.objects.filter(
                nombre=datos["nombre"], sede=datos["sede"]
            ).first()

        if institucion is not None:
            institucion._creada = False
            institucion.codigo_dane = dane
            institucion.consecutivo_sede = sede
            if datos:
                if datos["nombre"]:
                    institucion.nombre = datos["nombre"]
                    institucion.sede = datos["sede"]
                if datos["direccion"]:
                    institucion.direccion = datos["direccion"]
                if datos["latitud"] is not None and datos["longitud"] is not None:
                    institucion.latitud = datos["latitud"]
                    institucion.longitud = datos["longitud"]
            institucion.save()
            return institucion

        # Crear requiere nombre y coordenadas del catálogo.
        if not datos or not datos["nombre"]:
            return None
        if datos["latitud"] is None or datos["longitud"] is None:
            return None
        institucion = Institucion.objects.create(
            nombre=datos["nombre"],
            sede=datos["sede"],
            direccion=datos["direccion"],
            latitud=datos["latitud"],
            longitud=datos["longitud"],
            codigo_dane=dane,
            consecutivo_sede=sede,
        )
        institucion._creada = True
        return institucion

    # ----------------------------------------------------------------- resumen
    def _resumen(self, conteos, sedes_dane, catalogo):
        por_sede = Counter()
        por_grado = Counter()
        por_jornada = Counter()
        for (sede, _anio, grado, jornada, _zona), total in conteos.items():
            por_sede[sede] += total
            por_grado[grado] += total
            por_jornada[jornada] += total
        self.stdout.write("Sedes detectadas:")
        for sede, total in sorted(por_sede.items()):
            datos = catalogo.get(sede)
            nombre = datos["nombre"] if datos and datos["nombre"] else "(sin nombre en --sedes)"
            marca = "" if (datos and datos["latitud"] is not None) else "  ⚠ sin coordenadas"
            self.stdout.write(f"  {sede} · {nombre} · {total} beneficiarios{marca}")
        self.stdout.write("Por grado:")
        for grado, total in sorted(por_grado.items()):
            self.stdout.write(f"  {etiqueta_grado(grado)}: {total}")
        self.stdout.write("Por jornada:")
        for jornada, total in sorted(por_jornada.items()):
            self.stdout.write(f"  {etiqueta_jornada(jornada)}: {total}")


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _decimal(valor):
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
