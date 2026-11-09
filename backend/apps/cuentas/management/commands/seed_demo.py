"""Datos de demostración para desarrollo y pruebas del piloto.

    python manage.py seed_demo

Crea un administrador, dos conductores, dos instituciones de Pasto con sus
responsables, vehículos y envíos en distintos estados, y un conductor de prueba
para el mapa en vivo. Es idempotente.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Conductor, Institucion, ResponsableRecepcion, Vehiculo
from apps.cuentas.models import Rol
from apps.envios import servicios
from apps.envios.models import Envio, ItemEnvio

Usuario = get_user_model()

CLAVE = "Paego2026!"

ITEMS = [
    {"producto": "Leche entera UHT", "cantidad": Decimal("320"), "unidad": ItemEnvio.Unidad.UNIDAD},
    {"producto": "Pan integral", "cantidad": Decimal("320"), "unidad": ItemEnvio.Unidad.UNIDAD},
    {"producto": "Fruta (banano)", "cantidad": Decimal("40"), "unidad": ItemEnvio.Unidad.KG},
]


def usuario(email, nombres, apellidos, rol):
    obj, creado = Usuario.objects.get_or_create(
        email=email, defaults={"first_name": nombres, "last_name": apellidos, "rol": rol}
    )
    if creado:
        obj.set_password(CLAVE)
        obj.save()
    return obj


class Command(BaseCommand):
    help = "Carga datos de demostración de PAEGo (idempotente)."

    @transaction.atomic
    def handle(self, *args, **opciones):
        admin = usuario("admin@paego.local", "Ana", "Administradora", Rol.ADMINISTRADOR)
        if not admin.is_superuser:
            admin.is_staff = admin.is_superuser = True
            admin.save()

        normal, _ = Institucion.objects.get_or_create(
            nombre="Escuela Normal Superior de Pasto",
            sede="Principal",
            defaults={
                "direccion": "Calle 18 # 41-60, Pasto, Nariño",
                "latitud": Decimal("1.216800"),
                "longitud": Decimal("-77.288300"),
                "contacto_nombre": "Rectoría",
                "contacto_telefono": "6027000000",
            },
        )
        libertad, _ = Institucion.objects.get_or_create(
            nombre="I.E.M. Ciudadela de la Paz",
            sede="Principal",
            defaults={
                "direccion": "Barrio La Paz, Pasto, Nariño",
                "latitud": Decimal("1.199900"),
                "longitud": Decimal("-77.262800"),
                "contacto_nombre": "Coordinación",
                "contacto_telefono": "6027000001",
            },
        )

        conductores = []
        for i, (nombres, apellidos, documento, placa) in enumerate(
            [
                ("Carlos", "Pérez", "1085000001", "ABC123"),
                ("Luisa", "Gómez", "1085000002", "XYZ789"),
            ],
            start=1,
        ):
            u = usuario(f"conductor{i}@paego.local", nombres, apellidos, Rol.CONDUCTOR)
            conductor, _ = Conductor.objects.get_or_create(
                usuario=u, defaults={"numero_documento": documento, "telefono": f"30000000{i}"}
            )
            Vehiculo.objects.get_or_create(
                placa=placa,
                defaults={
                    "tipo": "Furgón",
                    "capacidad_kg": Decimal("1500"),
                    "conductor": conductor,
                },
            )
            conductores.append(conductor)

        # Conductor para probar el mapa en vivo: inicia sesión en la web desde el
        # celular y el administrador lo ve moverse en «Hoy». No tiene envíos.
        u = usuario("conductor.prueba@paego.local", "Conductor", "de Prueba", Rol.CONDUCTOR)
        prueba, _ = Conductor.objects.get_or_create(
            usuario=u, defaults={"numero_documento": "1085000099", "telefono": "3000000099"}
        )
        Vehiculo.objects.get_or_create(
            placa="PRU001",
            defaults={"tipo": "Camioneta", "capacidad_kg": Decimal("800"), "conductor": prueba},
        )

        for i, (institucion, cargo) in enumerate(
            [(normal, "Almacenista"), (libertad, "Coordinador")], 1
        ):
            u = usuario(
                f"institucion{i}@paego.local",
                "Responsable",
                institucion.nombre[:20],
                Rol.INSTITUCION,
            )
            ResponsableRecepcion.objects.get_or_create(
                usuario=u, defaults={"institucion": institucion, "cargo": cargo}
            )

        if not Envio.objects.exists():
            self._envios(admin, conductores, normal, libertad)

        self.stdout.write(
            self.style.SUCCESS("Datos de demostración listos. Contraseña de todos: " + CLAVE)
        )
        for u in Usuario.objects.filter(email__endswith="@paego.local").order_by("rol", "email"):
            self.stdout.write(f"  {u.get_rol_display():<22} {u.email}")

    def _envios(self, admin, conductores, normal, libertad):
        ahora = timezone.now()
        c1, c2 = conductores
        u1, u2 = c1.usuario, c2.usuario
        resp_normal = normal.responsables.first().usuario

        # Entregado a tiempo, con evidencia.
        e1 = servicios.crear_envio(
            admin,
            institucion=normal,
            conductor=c1,
            vehiculo=c1.vehiculos.first(),
            programado_para=ahora - timedelta(hours=5),
            items=ITEMS,
            ocurrido_en=ahora - timedelta(hours=8),
        )
        servicios.registrar_salida(
            u1,
            e1,
            latitud=Decimal("1.208000"),
            longitud=Decimal("-77.277000"),
            ocurrido_en=ahora - timedelta(hours=5, minutes=40),
        )
        for k in range(1, 6):
            servicios.registrar_ubicacion(
                u1,
                e1,
                latitud=Decimal("1.208000") + Decimal("0.0017") * k,
                longitud=Decimal("-77.277000") - Decimal("0.0022") * k,
                ocurrido_en=ahora - timedelta(hours=5, minutes=40 - k * 6),
            )
        servicios.registrar_llegada(
            u1,
            e1,
            latitud=normal.latitud,
            longitud=normal.longitud,
            ocurrido_en=ahora - timedelta(hours=5, minutes=5),
        )
        servicios.confirmar_recepcion(
            resp_normal,
            e1,
            items_recibidos=[
                {"item": i.pk, "cantidad_recibida": i.cantidad} for i in e1.items.all()
            ],
            recibido_por_nombre="María Rosero",
            recibido_por_cargo="Almacenista",
            codigo_verificacion=e1.codigo_verificacion,
            latitud=normal.latitud,
            longitud=normal.longitud,
            ocurrido_en=ahora - timedelta(hours=5),
        )

        # En tránsito (aparece en el mapa).
        e2 = servicios.crear_envio(
            admin,
            institucion=libertad,
            conductor=c2,
            vehiculo=c2.vehiculos.first(),
            programado_para=ahora + timedelta(minutes=40),
            items=ITEMS[:2],
        )
        servicios.registrar_salida(
            u2,
            e2,
            latitud=Decimal("1.214000"),
            longitud=Decimal("-77.281000"),
            ocurrido_en=ahora - timedelta(minutes=20),
        )
        for k in range(1, 5):
            servicios.registrar_ubicacion(
                u2,
                e2,
                latitud=Decimal("1.214000") - Decimal("0.0025") * k,
                longitud=Decimal("-77.281000") + Decimal("0.0030") * k,
                ocurrido_en=ahora - timedelta(minutes=20 - k * 4),
            )
        servicios.reportar_novedad(
            u2,
            e2,
            tipo="RETRASO",
            descripcion="Cierre vial en la avenida Panamericana.",
            latitud=Decimal("1.206000"),
            longitud=Decimal("-77.272000"),
            ocurrido_en=ahora - timedelta(minutes=6),
        )

        # Asignado para mañana.
        servicios.crear_envio(
            admin,
            institucion=normal,
            conductor=c1,
            vehiculo=c1.vehiculos.first(),
            programado_para=timezone.localtime(ahora + timedelta(days=1)).replace(
                hour=7, minute=30, second=0, microsecond=0
            ),
            items=ITEMS,
            observaciones="Entregar por la portería del almacén.",
        )
        # Retrasado (genera alerta RF-30).
        servicios.crear_envio(
            admin,
            institucion=libertad,
            conductor=c1,
            programado_para=ahora - timedelta(hours=2),
            items=ITEMS[1:],
        )
