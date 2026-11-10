"""Genera un mes de operación realista para probar y mostrar la plataforma.

    python manage.py demo_mes [--dias 20] [--envios-dia 6-10] [--semilla 2026]
                              [--sin-ruteo] [--reiniciar] [--institucion TEXTO]

Crea instituciones y conductores reales de Pasto (apps/catalogo/datos_pasto.py) y
~un mes de envíos en distintos estados, con recorridos GPS por calles
(apps/monitoreo/ruteo.py), novedades y evidencias. Pasa por los mismos servicios
de dominio que la operación real, así que respeta estados, permisos y auditoría.

Es determinista (semilla fija) e idempotente: si ya hay envíos, no hace nada
salvo que se pase --reiniciar. Pensado para una base de datos limpia.
"""

import math
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.auditoria.servicios import hora_simulada
from apps.catalogo import datos_pasto
from apps.catalogo.models import Conductor, Institucion, ResponsableRecepcion, Vehiculo
from apps.cuentas.models import Rol
from apps.envios import servicios
from apps.envios.models import EvidenciaEntrega, Novedad, Ubicacion
from apps.monitoreo import ruteo
from apps.monitoreo.models import PosicionEnVivo

Usuario = get_user_model()
CLAVE = "Paego2026!"

COMPLEMENTOS = [
    ("Leche entera UHT 200 ml", "UNIDAD"),
    ("Pan integral", "UNIDAD"),
    ("Fruta (banano)", "KG"),
    ("Galleta integral", "PAQUETE"),
]
NOVEDADES_TRAYECTO = [
    ("RETRASO", "Congestión en la vía Panamericana."),
    ("INCIDENTE", "Pinchazo de una llanta; se repuso en el camino."),
    ("DANO", "Una caja se mojó por la lluvia; contenido sin afectación."),
]


class Command(BaseCommand):
    help = "Genera un mes de operación realista (instituciones, envíos, recorridos, evidencias)."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=20, help="Días hábiles hacia atrás.")
        parser.add_argument(
            "--envios-dia", default="6-10", help="Rango de envíos por día, «min-max»."
        )
        parser.add_argument("--semilla", type=int, default=2026, help="Semilla (reproducible).")
        parser.add_argument(
            "--sin-ruteo",
            action="store_true",
            help="Recorridos sintéticos (sin pedir rutas por internet).",
        )
        parser.add_argument(
            "--reiniciar",
            action="store_true",
            help="Borra los envíos existentes antes de generar (requiere BD sin auditoría).",
        )
        parser.add_argument(
            "--institucion",
            default="",
            help="Solo las instituciones cuyo nombre contenga este texto "
            "(p. ej. «Normal Superior» para el piloto).",
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        import random

        self.rnd = random.Random(opciones["semilla"])
        self.usar_red = not opciones["sin_ruteo"]
        try:
            emin, emax = (int(x) for x in opciones["envios_dia"].split("-"))
        except ValueError as exc:
            raise CommandError("--envios-dia debe ser «min-max», p. ej. 6-10.") from exc

        filtro = opciones["institucion"].strip().lower()
        self.catalogo = [d for d in datos_pasto.INSTITUCIONES if filtro in d["nombre"].lower()]
        if not self.catalogo:
            raise CommandError(f"Ninguna institución coincide con «{opciones['institucion']}».")

        from apps.envios.models import Envio

        if Envio.objects.exists():
            if not opciones["reiniciar"]:
                self.stdout.write(
                    self.style.WARNING(
                        "Ya hay envíos; no se genera nada. Use --reiniciar en una BD limpia."
                    )
                )
                return
            try:
                Envio.objects.all().delete()
            except ProtectedError as exc:
                raise CommandError(
                    "No se pueden borrar los envíos: tienen auditoría inmutable. "
                    "Para reiniciar, recree la base de datos."
                ) from exc

        admin = self._cuenta("admin@paego.local", "Ana", "Administradora", Rol.ADMINISTRADOR)
        if not admin.is_superuser:
            admin.is_staff = admin.is_superuser = True
            admin.save()

        instituciones = self._instituciones()
        conductores = self._conductores()
        self._responsables(instituciones)

        total = self._generar(admin, instituciones, conductores, opciones["dias"], emin, emax)

        self.stdout.write(self.style.SUCCESS(f"Listo: {total} envíos generados. Clave: {CLAVE}"))

    # ------------------------------------------------------------- maestros
    def _cuenta(self, email, nombres, apellidos, rol):
        obj, creado = Usuario.objects.get_or_create(
            email=email, defaults={"first_name": nombres, "last_name": apellidos, "rol": rol}
        )
        if creado:
            obj.set_password(CLAVE)
            obj.save()
        return obj

    def _instituciones(self):
        creadas = []
        for datos in self.catalogo:
            contacto_nombre, contacto_telefono = datos["contacto"]
            inst, _ = Institucion.objects.get_or_create(
                nombre=datos["nombre"],
                sede=datos["sede"],
                defaults={
                    "direccion": datos["direccion"],
                    "latitud": datos["latitud"],
                    "longitud": datos["longitud"],
                    "contacto_nombre": contacto_nombre,
                    "contacto_telefono": contacto_telefono,
                },
            )
            # Beneficiarios: respeta los importados de SIMAT si ya existen.
            if not inst.beneficiarios_total:
                inst.beneficiarios_total = datos["beneficiarios"]
                inst.save(update_fields=["beneficiarios_total"])
            creadas.append(inst)
        return creadas

    def _conductores(self):
        conductores = []
        for nombres, apellidos, doc, tel, placa, tipo, cap in datos_pasto.CONDUCTORES:
            correo = f"conductor{len(conductores) + 1}@paego.local"
            u = self._cuenta(correo, nombres, apellidos, Rol.CONDUCTOR)
            c, _ = Conductor.objects.get_or_create(
                usuario=u, defaults={"numero_documento": doc, "telefono": tel}
            )
            Vehiculo.objects.get_or_create(
                placa=placa,
                defaults={"tipo": tipo, "capacidad_kg": Decimal(cap), "conductor": c},
            )
            conductores.append(c)
        # Conductor para el mapa en vivo (modo de prueba).
        u = self._cuenta("conductor.prueba@paego.local", "Conductor", "de Prueba", Rol.CONDUCTOR)
        Conductor.objects.get_or_create(
            usuario=u, defaults={"numero_documento": "1085000099", "telefono": "3000000099"}
        )
        return conductores

    def _responsables(self, instituciones):
        for i, inst in enumerate(instituciones, 1):
            u = self._cuenta(
                f"institucion{i}@paego.local", "Responsable", inst.nombre[:20], Rol.INSTITUCION
            )
            ResponsableRecepcion.objects.get_or_create(
                usuario=u, defaults={"institucion": inst, "cargo": "Almacenista"}
            )

    # -------------------------------------------------------------- envíos
    def _generar(self, admin, instituciones, conductores, dias, emin, emax):
        ahora = timezone.now()
        hoy = timezone.localdate()
        total = 0

        # Días anteriores: operación completa ya cerrada.
        for atras in range(dias, 0, -1):
            dia = hoy - timedelta(days=atras)
            if dia.weekday() >= 5:  # sábado/domingo sin operación
                continue
            cuantos = min(self.rnd.randint(emin, emax), len(instituciones))
            for inst in self.rnd.sample(instituciones, cuantos):
                total += self._envio_historico(admin, inst, conductores, dia)

        # Hoy: una jornada en curso para que «Hoy» y el mapa estén activos.
        total += self._envios_de_hoy(admin, instituciones, conductores, ahora)
        return total

    def _hora(self, dia, hh, mm):
        return timezone.make_aware(datetime.combine(dia, time(hh, mm)))

    def _items(self, inst):
        """Ración por beneficiarios (RF-14) + un par de complementos."""
        items = [
            {
                "producto": "Ración escolar",
                "cantidad": Decimal(inst.beneficiarios_total or 300),
                "unidad": "RACION",
            }
        ]
        for producto, unidad in self.rnd.sample(COMPLEMENTOS, 2):
            cantidad = Decimal(self.rnd.randint(20, 60))
            items.append({"producto": producto, "cantidad": cantidad, "unidad": unidad})
        return items

    def _envio_historico(self, admin, inst, conductores, dia):
        conductor = self.rnd.choice(conductores)
        programado = self._hora(dia, self.rnd.randint(6, 8), self.rnd.choice([0, 15, 30, 45]))
        creado = programado - timedelta(hours=self.rnd.randint(14, 20))
        with hora_simulada(creado):
            envio = servicios.crear_envio(
                admin,
                institucion=inst,
                conductor=conductor,
                vehiculo=conductor.vehiculos.first(),
                programado_para=programado,
                items=self._items(inst),
                ocurrido_en=creado,
            )

        categoria = self._categoria()
        if categoria == "cancelado":
            cancelado = programado - timedelta(hours=self.rnd.randint(1, 10))
            with hora_simulada(cancelado):
                servicios.cancelar_envio(
                    admin,
                    envio,
                    motivo=self.rnd.choice(
                        ["Cierre de la institución por jornada pedagógica.", "Cambio de menú."]
                    ),
                    ocurrido_en=cancelado,
                )
            self._retrofechar(envio, creado, cancelado)
            return 1

        salida = programado - timedelta(minutes=self.rnd.randint(20, 35))
        tarde = categoria == "tarde"
        viaje = self.rnd.randint(75, 120) if tarde else self.rnd.randint(15, 40)
        llegada = salida + timedelta(minutes=viaje)
        entregado = llegada + timedelta(minutes=self.rnd.randint(1, 5))

        self._salida_y_ruta(envio, conductor, inst, salida, llegada)

        if categoria == "novedad" and self.rnd.random() < 0.5:
            tipo, desc = self.rnd.choice(NOVEDADES_TRAYECTO)
            medio = salida + (llegada - salida) / 2
            punto = self._punto_intermedio(conductor, inst)
            with hora_simulada(medio):
                servicios.reportar_novedad(
                    conductor.usuario,
                    envio,
                    tipo=tipo,
                    descripcion=desc,
                    latitud=punto[0],
                    longitud=punto[1],
                    ocurrido_en=medio,
                )

        with hora_simulada(llegada):
            servicios.registrar_llegada(
                conductor.usuario,
                envio,
                latitud=inst.latitud,
                longitud=inst.longitud,
                ocurrido_en=llegada,
            )

        con_faltante = categoria == "novedad"
        self._confirmar(envio, inst, entregado, con_faltante)
        self._retrofechar(envio, creado, entregado)
        return 1

    def _categoria(self):
        r = self.rnd.random()
        if r < 0.03:
            return "cancelado"
        if r < 0.15:
            return "novedad"
        if r < 0.27:
            return "tarde"
        return "a_tiempo"

    def _salida_y_ruta(self, envio, conductor, inst, salida, llegada):
        with hora_simulada(salida):
            servicios.registrar_salida(
                conductor.usuario,
                envio,
                latitud=datos_pasto.BODEGA[0],
                longitud=datos_pasto.BODEGA[1],
                ocurrido_en=salida,
            )
        puntos = self._muestrear(
            ruteo.ruta(
                (float(datos_pasto.BODEGA[0]), float(datos_pasto.BODEGA[1])),
                (float(inst.latitud), float(inst.longitud)),
                usar_red=self.usar_red,
            )
        )
        n = len(puntos)
        duracion = (llegada - salida).total_seconds()
        anterior = None
        for i, (lat, lng) in enumerate(puntos):
            momento = salida + timedelta(seconds=duracion * i / max(n - 1, 1))
            rumbo, velocidad = self._rumbo_velocidad(anterior, (lat, lng), duracion / max(n - 1, 1))
            servicios.registrar_ubicacion(
                conductor.usuario,
                envio,
                latitud=_dec(lat),
                longitud=_dec(lng),
                precision_m=Decimal(self.rnd.randint(4, 15)),
                velocidad_kmh=velocidad,
                rumbo=rumbo,
                ocurrido_en=momento,
            )
            anterior = (lat, lng)

    def _confirmar(self, envio, inst, entregado, con_faltante):
        items = list(envio.items.all())
        recibidos = []
        for it in items:
            cantidad = it.cantidad
            if con_faltante and it.unidad == "RACION":
                cantidad = it.cantidad - Decimal(self.rnd.randint(5, 30))
            recibidos.append({"item": it.pk, "cantidad_recibida": cantidad})
        responsable = inst.responsables.first()
        nombre = responsable.usuario.get_full_name() if responsable else "Responsable de recepción"
        with hora_simulada(entregado):
            servicios.confirmar_recepcion(
                responsable.usuario if responsable else None,
                envio,
                items_recibidos=recibidos,
                recibido_por_nombre=nombre,
                recibido_por_cargo="Almacenista",
                codigo_verificacion=envio.codigo_verificacion,
                latitud=inst.latitud,
                longitud=inst.longitud,
                ocurrido_en=entregado,
            )

    def _envios_de_hoy(self, admin, instituciones, conductores, ahora):
        total = 0
        elegidas = self.rnd.sample(instituciones, min(6, len(instituciones)))
        casos = list(enumerate(elegidas))
        if len(elegidas) == 1:
            # Una sola institución: un envío en tránsito ahora y el de mañana asignado.
            casos = [(0, elegidas[0]), (3, elegidas[0])]
        for i, inst in casos:
            conductor = self.rnd.choice(conductores)
            if i < 2:
                # En tránsito ahora (uno de ellos ya retrasado → alerta RF-30).
                atraso = 70 if i == 0 else -20
                programado = ahora - timedelta(minutes=atraso)
                creado = programado - timedelta(hours=14)
                with hora_simulada(creado):
                    envio = servicios.crear_envio(
                        admin,
                        institucion=inst,
                        conductor=conductor,
                        vehiculo=conductor.vehiculos.first(),
                        programado_para=programado,
                        items=self._items(inst),
                        ocurrido_en=creado,
                    )
                salida = ahora - timedelta(minutes=self.rnd.randint(15, 35))
                self._salida_y_ruta_parcial(envio, conductor, inst, salida, ahora)
                self._retrofechar(envio, creado, ahora, cerrar=False)
            else:
                # Asignado para más tarde hoy o mañana.
                dia = timezone.localdate() + timedelta(days=0 if i == 2 else 1)
                programado = self._hora(dia, self.rnd.choice([10, 11, 13, 14]), 0)
                creado = ahora - timedelta(hours=2)
                with hora_simulada(creado):
                    envio = servicios.crear_envio(
                        admin,
                        institucion=inst,
                        conductor=conductor,
                        vehiculo=conductor.vehiculos.first(),
                        programado_para=programado,
                        items=self._items(inst),
                        ocurrido_en=creado,
                    )
                self._retrofechar(envio, creado, creado, cerrar=False)
            total += 1

        # Posición en vivo del conductor de prueba (capa del mapa en vivo).
        prueba = Conductor.objects.filter(usuario__email="conductor.prueba@paego.local").first()
        if prueba:
            PosicionEnVivo.objects.update_or_create(
                conductor=prueba,
                defaults={
                    "latitud": Decimal("1.210000"),
                    "longitud": Decimal("-77.275000"),
                    "rumbo": 120,
                    "velocidad_kmh": Decimal("28"),
                    "en_linea": True,
                    "actualizado_en": ahora,
                },
            )
        return total

    def _salida_y_ruta_parcial(self, envio, conductor, inst, salida, ahora):
        """Como _salida_y_ruta pero se detiene a mitad de camino (va en tránsito)."""
        with hora_simulada(salida):
            servicios.registrar_salida(
                conductor.usuario,
                envio,
                latitud=datos_pasto.BODEGA[0],
                longitud=datos_pasto.BODEGA[1],
                ocurrido_en=salida,
            )
        puntos = self._muestrear(
            ruteo.ruta(
                (float(datos_pasto.BODEGA[0]), float(datos_pasto.BODEGA[1])),
                (float(inst.latitud), float(inst.longitud)),
                usar_red=self.usar_red,
            )
        )
        recorridos = puntos[: max(2, len(puntos) * 2 // 3)]
        n = len(recorridos)
        duracion = (ahora - salida).total_seconds()
        anterior = None
        for i, (lat, lng) in enumerate(recorridos):
            momento = salida + timedelta(seconds=duracion * i / max(n - 1, 1))
            rumbo, velocidad = self._rumbo_velocidad(anterior, (lat, lng), duracion / max(n - 1, 1))
            servicios.registrar_ubicacion(
                conductor.usuario,
                envio,
                latitud=_dec(lat),
                longitud=_dec(lng),
                precision_m=Decimal(self.rnd.randint(4, 15)),
                velocidad_kmh=velocidad,
                rumbo=rumbo,
                ocurrido_en=momento,
            )
            anterior = (lat, lng)

    # ----------------------------------------------------------- utilidades
    def _muestrear(self, puntos, maximo=28):
        if len(puntos) <= maximo:
            return puntos
        paso = len(puntos) / maximo
        muestra = [puntos[int(i * paso)] for i in range(maximo)]
        muestra[-1] = puntos[-1]
        return muestra

    def _punto_intermedio(self, conductor, inst):
        return (
            _dec((float(datos_pasto.BODEGA[0]) + float(inst.latitud)) / 2),
            _dec((float(datos_pasto.BODEGA[1]) + float(inst.longitud)) / 2),
        )

    def _rumbo_velocidad(self, anterior, actual, segundos):
        if anterior is None or segundos <= 0:
            return self.rnd.randint(0, 359), Decimal(0)
        metros = _haversine(anterior, actual)
        velocidad = Decimal(round(min(metros / segundos * 3.6, 80), 2))
        return _rumbo(anterior, actual), velocidad

    def _retrofechar(self, envio, creado, ultimo, cerrar=True):
        """Ajusta los auto_now_add no inmutables para que el dato sea histórico."""
        from apps.envios.models import Envio

        Envio.objects.filter(pk=envio.pk).update(creado_en=creado, actualizado_en=ultimo)
        Ubicacion.objects.filter(envio=envio).update(recibido_en=F("ocurrido_en"))
        Novedad.objects.filter(envio=envio).update(recibido_en=F("ocurrido_en"))
        EvidenciaEntrega.objects.filter(envio=envio).update(recibido_en=F("ocurrido_en"))


def _dec(valor):
    return Decimal(str(round(valor, 6)))


def _haversine(a, b):
    r = 6_371_000
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _rumbo(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return int((math.degrees(math.atan2(x, y)) + 360) % 360)
