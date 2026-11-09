"""Mapa en vivo de los conductores (modo de prueba).

El conductor con la sesión abierta transmite su posición cada pocos segundos y
el administrador la ve moverse en el mapa. Más adelante la app móvil reemplaza
la página web del conductor; este módulo no cambia las reglas de los envíos.
"""

from datetime import timedelta

from django.utils import timezone

from apps.cuentas.models import Rol
from apps.envios.servicios import conductor_de

from .models import PosicionEnVivo

# Sin posición nueva en este tiempo, el conductor deja de mostrarse.
VIGENCIA_SEG = 60


def actualizar_posicion(
    usuario, *, latitud, longitud, precision_m=None, velocidad_kmh=None, rumbo=None
):
    conductor = conductor_de(usuario)
    posicion, _ = PosicionEnVivo.objects.update_or_create(
        conductor=conductor,
        defaults={
            "latitud": latitud,
            "longitud": longitud,
            "precision_m": precision_m,
            "velocidad_kmh": velocidad_kmh,
            "rumbo": rumbo,
            "en_linea": True,
            "actualizado_en": timezone.now(),
        },
    )
    return posicion


def desconectar(usuario):
    """Al cerrar sesión el conductor desaparece del mapa."""
    if getattr(usuario, "rol", None) != Rol.CONDUCTOR:
        return
    PosicionEnVivo.objects.filter(conductor__usuario=usuario).update(en_linea=False)


def conductores_en_vivo():
    limite = timezone.now() - timedelta(seconds=VIGENCIA_SEG)
    posiciones = (
        PosicionEnVivo.objects.filter(
            en_linea=True, actualizado_en__gte=limite, conductor__activo=True
        )
        .select_related("conductor__usuario")
        .prefetch_related("conductor__vehiculos")
        .order_by("conductor__usuario__first_name")
    )
    resultado = []
    for p in posiciones:
        vehiculo = next((v for v in p.conductor.vehiculos.all() if v.activo), None)
        resultado.append(
            {
                "id": p.conductor_id,
                "nombre": p.conductor.usuario.get_full_name(),
                "telefono": p.conductor.telefono,
                "placa": vehiculo.placa if vehiculo else None,
                "posicion": [float(p.latitud), float(p.longitud)],
                "rumbo": p.rumbo,
                "velocidad_kmh": float(p.velocidad_kmh) if p.velocidad_kmh is not None else None,
                "precision_m": float(p.precision_m) if p.precision_m is not None else None,
                "actualizado_en": p.actualizado_en.isoformat(),
            }
        )
    return resultado
