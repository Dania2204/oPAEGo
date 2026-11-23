"""Herramientas de solo lectura que el asistente (Claude) puede llamar.

Cada herramienta reutiliza las consultas del panel y devuelve un dict pequeño
(agregados primero, a lo sumo LIMITE_FILAS filas). Ninguna escribe en la base
de datos ni devuelve nombres o documentos de estudiantes (Ley 1581): de ellos
solo salen conteos por curso.
"""

import json
from datetime import date, timedelta
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import Accion, RegistroAuditoria
from apps.catalogo.models import Conductor, Institucion, Vehiculo
from apps.envios.estados import Estado
from apps.envios.models import Envio, Novedad
from apps.estudiantes import consultas as consultas_estudiantes
from apps.estudiantes.models import EntregaEstudiante, Estudiante
from apps.monitoreo import consultas, kpis

LIMITE_FILAS = 50
MAX_DIAS = 400
TEXTO_MAX = 300


class HerramientaError(Exception):
    """Error que se le devuelve a Claude como tool_result con is_error."""


# --------------------------------------------------------------- utilidades
def _fecha(valor, por_defecto):
    if not valor:
        return por_defecto
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError as exc:
        raise HerramientaError(f"Fecha inválida: {valor!r}. Use AAAA-MM-DD.") from exc


def _periodo(entrada, dias_por_defecto=30):
    hoy = timezone.localdate()
    hasta = _fecha(entrada.get("hasta"), hoy)
    desde = _fecha(entrada.get("desde"), hasta - timedelta(days=dias_por_defecto - 1))
    if desde > hasta:
        raise HerramientaError("La fecha inicial es posterior a la final.")
    if (hasta - desde).days > MAX_DIAS:
        raise HerramientaError(f"El periodo es demasiado largo (máximo {MAX_DIAS} días).")
    return desde, hasta


def _limite(entrada):
    try:
        n = int(entrada.get("limite") or 20)
    except (TypeError, ValueError):
        n = 20
    return max(1, min(n, LIMITE_FILAS))


def _texto(valor, maximo=TEXTO_MAX):
    valor = (valor or "").strip()
    return valor if len(valor) <= maximo else valor[: maximo - 1] + "…"


def _hora(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M") if dt else None


def _nombre_institucion(i):
    return f"{i.nombre} (sede {i.sede})" if i.sede and i.sede != "Principal" else i.nombre


def _conductor_nombre(c):
    return c.usuario.get_full_name() or c.usuario.email


def _institucion(texto, *, obligatoria=False):
    """Busca una institución por id o por parte del nombre/sede."""
    if texto in (None, ""):
        if obligatoria:
            raise HerramientaError("Indique la institución.")
        return None
    qs = Institucion.objects.all()
    if str(texto).isdigit():
        encontrada = qs.filter(pk=int(texto)).first()
        if encontrada:
            return encontrada
    palabras = str(texto).split()
    for p in palabras:
        qs = qs.filter(Q(nombre__icontains=p) | Q(sede__icontains=p))
    candidatas = list(qs.order_by("-activo", "nombre")[:6])
    if len(candidatas) == 1:
        return candidatas[0]
    if not candidatas:
        raise HerramientaError(
            f"No hay ninguna institución que coincida con {texto!r}. "
            "Use la herramienta catalogo para ver las instituciones."
        )
    nombres = "; ".join(f"{_nombre_institucion(i)} (id {i.pk})" for i in candidatas)
    raise HerramientaError(f"Varias instituciones coinciden con {texto!r}: {nombres}.")


def _conductor(texto):
    if texto in (None, ""):
        return None
    conductores = list(Conductor.objects.select_related("usuario"))
    if str(texto).isdigit():
        for c in conductores:
            if c.pk == int(texto):
                return c
    palabras = [p.lower() for p in str(texto).split()]
    candidatos = [
        c
        for c in conductores
        if all(p in f"{_conductor_nombre(c)} {c.usuario.email}".lower() for p in palabras)
    ]
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        raise HerramientaError(f"No hay ningún conductor que coincida con {texto!r}.")
    nombres = "; ".join(f"{_conductor_nombre(c)} (id {c.pk})" for c in candidatos[:6])
    raise HerramientaError(f"Varios conductores coinciden con {texto!r}: {nombres}.")


def _filtros_usados(desde, hasta, institucion=None, conductor=None, **otros):
    filtros = {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
    if institucion:
        filtros["institucion"] = _nombre_institucion(institucion)
    if conductor:
        filtros["conductor"] = _conductor_nombre(conductor)
    filtros.update({k: v for k, v in otros.items() if v not in (None, "", [], False)})
    return filtros


def _resumen_kpi(k):
    return {
        "total_envios": k.total_envios,
        "entregas": k.total_entregas,
        "pct_registro_completo": k.porcentaje_registro_completo,
        "pct_a_tiempo": k.porcentaje_a_tiempo,
        "pct_con_evidencia": k.porcentaje_con_evidencia,
        "novedades": k.novedades,
    }


def _fila_envio(e):
    return {
        "codigo": e.codigo,
        "programado_para": _hora(e.programado_para),
        "institucion": _nombre_institucion(e.institucion),
        "conductor": _conductor_nombre(e.conductor),
        "vehiculo": e.vehiculo.placa if e.vehiculo else None,
        "estado": Estado(e.estado).label,
        "entregado_en": _hora(e.entregado_en),
        "a_tiempo": e.entregado_a_tiempo,
        "retrasado": e.esta_retrasado,
    }


# ---------------------------------------------------------- herramientas
def indicadores(entrada):
    """Indicadores de la Tabla 3 (RF-32) con desglose opcional."""
    desde, hasta = _periodo(entrada, 30)
    institucion = _institucion(entrada.get("institucion"))
    conductor = _conductor(entrada.get("conductor"))
    agrupar = entrada.get("agrupar_por") or "ninguno"
    total = kpis.calcular(desde, hasta, institucion, conductor)
    resultado = {
        "filtros": _filtros_usados(desde, hasta, institucion, conductor),
        "total": total.como_dict(),
        "definiciones": (
            "Entregas = envíos entregados (con o sin novedad). Registro completo: salida, "
            "llegada, ubicación y evidencia. A tiempo: entregado antes de la hora programada "
            "más la tolerancia. Con evidencia: evidencia íntegra (huella SHA-256)."
        ),
    }
    periodo = Envio.objects.filter(
        programado_para__date__gte=desde, programado_para__date__lte=hasta
    )
    if agrupar == "semana":
        semanas = []
        inicio = desde - timedelta(days=desde.weekday())
        while inicio <= hasta:
            lunes, domingo = max(inicio, desde), min(inicio + timedelta(days=6), hasta)
            k = kpis.calcular(lunes, domingo, institucion, conductor)
            semanas.append({"semana": f"{lunes} a {domingo}", **_resumen_kpi(k)})
            inicio += timedelta(days=7)
        resultado["por_semana"] = semanas[-LIMITE_FILAS:]
    elif agrupar == "institucion":
        filas = []
        ids = periodo.values("institucion")
        for i in Institucion.objects.filter(pk__in=ids).order_by("nombre"):
            if institucion and i != institucion:
                continue
            k = kpis.calcular(desde, hasta, i, conductor)
            filas.append({"institucion": _nombre_institucion(i), **_resumen_kpi(k)})
        resultado["por_institucion"] = filas[:LIMITE_FILAS]
    elif agrupar == "conductor":
        filas = []
        ids = periodo.values("conductor")
        for c in Conductor.objects.filter(pk__in=ids).select_related("usuario"):
            if conductor and c != conductor:
                continue
            k = kpis.calcular(desde, hasta, institucion, c)
            filas.append({"conductor": _conductor_nombre(c), **_resumen_kpi(k)})
        filas.sort(key=lambda f: f["conductor"])
        resultado["por_conductor"] = filas[:LIMITE_FILAS]
    return resultado


def listar_envios(entrada):
    desde, hasta = _periodo(entrada, 7)
    institucion = _institucion(entrada.get("institucion"))
    conductor = _conductor(entrada.get("conductor"))
    envios = kpis.envios_del_periodo(desde, hasta, institucion, conductor)
    estados = [e for e in entrada.get("estados") or [] if e in Estado.values]
    if estados:
        envios = envios.filter(estado__in=estados)
    if entrada.get("codigo"):
        envios = envios.filter(codigo__icontains=entrada["codigo"])
    envios = list(envios.order_by("programado_para"))
    if entrada.get("solo_retrasados"):
        envios = [e for e in envios if e.esta_retrasado or e.entregado_a_tiempo is False]
    limite = _limite(entrada)
    por_estado = {}
    for e in envios:
        etiqueta = Estado(e.estado).label
        por_estado[etiqueta] = por_estado.get(etiqueta, 0) + 1
    return {
        "filtros": _filtros_usados(
            desde,
            hasta,
            institucion,
            conductor,
            estados=estados,
            solo_retrasados=entrada.get("solo_retrasados"),
        ),
        "total": len(envios),
        "por_estado": por_estado,
        "mostrados": min(limite, len(envios)),
        "envios": [_fila_envio(e) for e in envios[:limite]],
    }


def detalle_envio(entrada):
    codigo = (entrada.get("codigo") or "").strip()
    envio = (
        Envio.objects.select_related("institucion", "conductor__usuario", "vehiculo")
        .prefetch_related("items", "novedades")
        .filter(codigo__iexact=codigo)
        .first()
    )
    if envio is None:
        raise HerramientaError(f"No existe un envío con código {codigo!r}.")
    evidencia = getattr(envio, "evidencia", None)
    return {
        **_fila_envio(envio),
        "salida_en": _hora(envio.salida_en),
        "llegada_en": _hora(envio.llegada_en),
        "cancelado_en": _hora(envio.cancelado_en),
        "motivo_cancelacion": _texto(envio.motivo_cancelacion),
        "observaciones": _texto(envio.observaciones),
        "registro_completo": envio.tiene_registro_completo,
        "evidencia": (
            {
                "registrada": True,
                "integra": evidencia.es_integra,
                "con_foto": bool(evidencia.foto),
                "hora": _hora(evidencia.ocurrido_en),
            }
            if evidencia
            else {"registrada": False}
        ),
        "items": [
            {
                "producto": i.producto,
                "cantidad": float(i.cantidad),
                "unidad": i.get_unidad_display(),
                "recibida": float(i.cantidad_recibida) if i.cantidad_recibida is not None else None,
            }
            for i in envio.items.all()
        ],
        "novedades": [
            {
                "tipo": n.get_tipo_display(),
                "origen": n.get_origen_display(),
                "ocurrido_en": _hora(n.ocurrido_en),
                "descripcion": _texto(n.descripcion),
                "atendida": n.leida_en is not None,
            }
            for n in envio.novedades.all()
        ],
    }


def novedades(entrada):
    desde, hasta = _periodo(entrada, 30)
    institucion = _institucion(entrada.get("institucion"))
    conductor = _conductor(entrada.get("conductor"))
    qs = Novedad.objects.select_related(
        "envio", "envio__institucion", "envio__conductor__usuario"
    ).filter(ocurrido_en__date__gte=desde, ocurrido_en__date__lte=hasta)
    if institucion:
        qs = qs.filter(envio__institucion=institucion)
    if conductor:
        qs = qs.filter(envio__conductor=conductor)
    tipo = entrada.get("tipo")
    if tipo in Novedad.Tipo.values:
        qs = qs.filter(tipo=tipo)
    if entrada.get("solo_pendientes"):
        qs = qs.filter(leida_en__isnull=True)
    por_tipo = {
        Novedad.Tipo(f["tipo"]).label: f["n"] for f in qs.values("tipo").annotate(n=Count("id"))
    }
    por_conductor = {}
    por_institucion = {}
    filas = list(qs.order_by("-ocurrido_en"))
    for n in filas:
        c = _conductor_nombre(n.envio.conductor)
        i = _nombre_institucion(n.envio.institucion)
        por_conductor[c] = por_conductor.get(c, 0) + 1
        por_institucion[i] = por_institucion.get(i, 0) + 1
    limite = _limite(entrada)
    return {
        "filtros": _filtros_usados(
            desde,
            hasta,
            institucion,
            conductor,
            tipo=tipo,
            solo_pendientes=entrada.get("solo_pendientes"),
        ),
        "total": len(filas),
        "pendientes": sum(1 for n in filas if n.leida_en is None),
        "por_tipo": por_tipo,
        "por_conductor": dict(sorted(por_conductor.items(), key=lambda x: -x[1])),
        "por_institucion": dict(sorted(por_institucion.items(), key=lambda x: -x[1])),
        "mostradas": min(limite, len(filas)),
        "novedades": [
            {
                "envio": n.envio.codigo,
                "tipo": n.get_tipo_display(),
                "origen": n.get_origen_display(),
                "ocurrido_en": _hora(n.ocurrido_en),
                "institucion": _nombre_institucion(n.envio.institucion),
                "conductor": _conductor_nombre(n.envio.conductor),
                "descripcion": _texto(n.descripcion),
                "atendida": n.leida_en is not None,
            }
            for n in filas[:limite]
        ],
    }


def situacion_actual(entrada):
    en_transito = consultas.envios_en_transito()
    retrasados = list(consultas.alertas_retraso()[:LIMITE_FILAS])
    sin_leer = consultas.novedades_sin_leer()
    hoy = timezone.localdate()
    de_hoy = Envio.objects.filter(programado_para__date=hoy)
    return {
        "ahora": _hora(timezone.now()),
        "envios_de_hoy": {
            Estado(f["estado"]).label: f["n"]
            for f in de_hoy.values("estado").annotate(n=Count("id"))
        },
        "en_transito": [
            {
                "codigo": e["codigo"],
                "institucion": e["institucion"],
                "conductor": e["conductor"],
                "vehiculo": e["vehiculo"],
                "retrasado": e["retrasado"],
                "ultima_posicion_en": e["posicion_en"],
            }
            for e in en_transito[:LIMITE_FILAS]
        ],
        "retrasados": [_fila_envio(e) for e in retrasados],
        "novedades_sin_atender": sin_leer.count(),
    }


def cobertura_pae(entrada):
    """Entrega del PAE a estudiantes: solo conteos (Ley 1581)."""
    institucion = _institucion(entrada.get("institucion"))
    hoy = timezone.localdate()
    estudiantes = Estudiante.objects.all()
    if institucion:
        estudiantes = estudiantes.filter(institucion=institucion)
    if entrada.get("fecha"):
        desde = hasta = _fecha(entrada["fecha"], hoy)
    else:
        desde, hasta = _periodo(entrada, 7)
    resultado = {
        "filtros": _filtros_usados(desde, hasta, institucion),
        "nota": "Solo conteos; el asistente no tiene acceso a nombres ni documentos.",
        "estudiantes_activos": estudiantes.filter(activo=True).count(),
    }
    entregas = EntregaEstudiante.objects.filter(
        estudiante__in=estudiantes, fecha__gte=desde, fecha__lte=hasta
    )
    por_dia = {
        f["fecha"]: f
        for f in entregas.values("fecha").annotate(n=Count("estudiante", distinct=True))
    }
    activos = resultado["estudiantes_activos"]
    dias = []
    dia = desde
    while dia <= hasta:
        n = por_dia.get(dia, {}).get("n", 0)
        if n or desde == hasta:
            dias.append(
                {
                    "fecha": dia.isoformat(),
                    "recibieron": n,
                    "porcentaje": round(100 * n / activos, 1) if activos else None,
                }
            )
        dia += timedelta(days=1)
    resultado["dias_con_entregas"] = dias[-LIMITE_FILAS:]
    resultado["dias_sin_entregas"] = (hasta - desde).days + 1 - len(por_dia)
    resultado["por_metodo"] = {
        etiqueta: entregas.filter(metodo=valor).count()
        for valor, etiqueta in EntregaEstudiante._meta.get_field("metodo").choices
        if entregas.filter(metodo=valor).exists()
    }
    if entrada.get("por_curso"):
        cursos = consultas_estudiantes.resumen_cursos(estudiantes, hasta)
        grado = entrada.get("grado")
        if grado not in (None, ""):
            cursos = [c for c in cursos if str(c["grado"]) == str(grado)]
        resultado["por_curso_el_dia"] = hasta.isoformat()
        resultado["por_curso"] = [
            {
                "institucion": c["institucion_nombre"],
                "curso": c["curso"],
                "activos": c["activos"],
                "recibieron": c["recibieron"],
                "porcentaje": (
                    round(100 * c["recibieron"] / c["activos"], 1) if c["activos"] else None
                ),
            }
            for c in cursos
        ][: LIMITE_FILAS * 2]
    return resultado


def catalogo(entrada):
    tipo = entrada.get("tipo") or "instituciones"
    buscar = (entrada.get("buscar") or "").strip()
    if tipo == "instituciones":
        qs = Institucion.objects.annotate(
            estudiantes_activos=Count("estudiantes", filter=Q(estudiantes__activo=True))
        ).order_by("-activo", "nombre")
        if buscar:
            qs = qs.filter(Q(nombre__icontains=buscar) | Q(sede__icontains=buscar))
        filas = [
            {
                "id": i.pk,
                "nombre": i.nombre,
                "sede": i.sede,
                "codigo_dane": i.codigo_dane,
                "direccion": i.direccion,
                "activa": i.activo,
                "beneficiarios_matricula": i.beneficiarios_total,
                "estudiantes_con_qr": i.estudiantes_activos,
            }
            for i in qs[:LIMITE_FILAS]
        ]
    elif tipo == "conductores":
        qs = Conductor.objects.select_related("usuario").annotate(
            vehiculos_activos=Count("vehiculos", filter=Q(vehiculos__activo=True))
        )
        filas = [
            {
                "id": c.pk,
                "nombre": _conductor_nombre(c),
                "telefono": c.telefono,
                "activo": c.activo,
                "vehiculos_activos": c.vehiculos_activos,
            }
            for c in qs
            if not buscar or buscar.lower() in _conductor_nombre(c).lower()
        ][:LIMITE_FILAS]
    elif tipo == "vehiculos":
        qs = Vehiculo.objects.select_related("conductor__usuario").order_by("placa")
        if buscar:
            qs = qs.filter(Q(placa__icontains=buscar) | Q(tipo__icontains=buscar))
        filas = [
            {
                "placa": v.placa,
                "tipo": v.tipo,
                "capacidad_kg": float(v.capacidad_kg),
                "conductor": _conductor_nombre(v.conductor) if v.conductor else None,
                "activo": v.activo,
            }
            for v in qs[:LIMITE_FILAS]
        ]
    else:
        raise HerramientaError("tipo debe ser instituciones, conductores o vehiculos.")
    return {"tipo": tipo, "buscar": buscar or None, "total": len(filas), "filas": filas}


def matricula_simat(entrada):
    """Matrícula agregada del Anexo 6A (beneficiarios por grado y jornada)."""
    anio = entrada.get("anio")
    datos = consultas.cobertura(int(anio) if str(anio or "").isdigit() else None)
    instituciones = []
    for fila in datos.get("instituciones", [])[:LIMITE_FILAS]:
        inst = fila.get("institucion")
        instituciones.append(
            {
                "institucion": _nombre_institucion(inst) if inst else None,
                "total": fila.get("total"),
                "por_grado": dict(fila.get("grados") or []),
            }
        )
    return {
        "anio": datos.get("anio"),
        "anios_disponibles": datos.get("anios"),
        "total": datos.get("total"),
        "por_grado": dict(datos.get("por_grado") or []),
        "por_jornada": dict(datos.get("por_jornada") or []),
        "instituciones": instituciones,
    }


ACCIONES_DE_ESTUDIANTES = {
    Accion.ENTREGA_ESTUDIANTE,
    Accion.QR_REGENERADO,
    Accion.ESTUDIANTE_AGREGADO,
    Accion.ROSTRO_INSCRITO,
    Accion.ROSTRO_BORRADO,
    Accion.AUTORIZACION_BIOMETRICA,
    Accion.AUTORIZACION_REVOCADA,
}


def auditoria(entrada):
    desde, hasta = _periodo(entrada, 7)
    qs = RegistroAuditoria.objects.select_related("usuario", "envio").filter(
        ocurrido_en__date__gte=desde, ocurrido_en__date__lte=hasta
    )
    accion = entrada.get("accion")
    if accion in Accion.values:
        qs = qs.filter(accion=accion)
    if entrada.get("usuario"):
        u = entrada["usuario"]
        qs = qs.filter(
            Q(usuario__email__icontains=u)
            | Q(usuario__first_name__icontains=u)
            | Q(usuario__last_name__icontains=u)
        )
    por_accion = {
        Accion(f["accion"]).label: f["n"]
        for f in qs.values("accion").annotate(n=Count("id")).order_by("-n")
    }
    limite = _limite(entrada)
    filas = []
    for r in qs.order_by("-ocurrido_en")[:limite]:
        de_estudiante = r.accion in ACCIONES_DE_ESTUDIANTES or r.entidad == "estudiante"
        filas.append(
            {
                "ocurrido_en": _hora(r.ocurrido_en),
                "usuario": str(r.usuario) if r.usuario else "Sistema",
                "accion": Accion(r.accion).label,
                "envio": r.envio.codigo if r.envio else None,
                # Las descripciones de acciones sobre estudiantes traen su nombre.
                "descripcion": "(dato de estudiante omitido)"
                if de_estudiante
                else _texto(r.descripcion, 200),
                "sin_conexion": r.diferido,
            }
        )
    return {
        "filtros": _filtros_usados(desde, hasta, accion=accion, usuario=entrada.get("usuario")),
        "total": qs.count(),
        "por_accion": por_accion,
        "mostrados": len(filas),
        "registros": filas,
    }


def enlace_reporte(entrada):
    desde, hasta = _periodo(entrada, 30)
    institucion = _institucion(entrada.get("institucion"))
    conductor = _conductor(entrada.get("conductor"))
    parametros = {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
    if institucion:
        parametros["institucion"] = institucion.pk
    if conductor:
        parametros["conductor"] = conductor.pk
    base = reverse("auditoria:reportes")
    return {
        "filtros": _filtros_usados(desde, hasta, institucion, conductor),
        "ver": f"{base}?{urlencode(parametros)}",
        "pdf": f"{base}?{urlencode({**parametros, 'formato': 'pdf'})}",
        "excel": f"{base}?{urlencode({**parametros, 'formato': 'xlsx'})}",
    }


# ------------------------------------------------------ definiciones (API)
_FECHAS = {
    "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD (incluida)."},
    "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (incluida)."},
}
_INSTITUCION = {
    "type": "string",
    "description": "Nombre (o parte), sede o id de la institución educativa.",
}
_CONDUCTOR = {"type": "string", "description": "Nombre (o parte) o id del conductor."}
_LIMITE = {"type": "integer", "description": f"Filas a devolver (1-{LIMITE_FILAS})."}


def _esquema(propiedades, requeridas=()):
    return {
        "type": "object",
        "properties": propiedades,
        "required": list(requeridas),
        "additionalProperties": False,
    }


HERRAMIENTAS = {
    "indicadores": (
        indicadores,
        "Indicadores de la Tabla 3 (RF-32) de un periodo: total de envíos y entregas, "
        "porcentaje con registro completo, a tiempo y con evidencia, novedades por tipo y "
        "envíos por estado. Puede desglosar por semana, institución o conductor. "
        "Por defecto, los últimos 30 días.",
        _esquema(
            {
                **_FECHAS,
                "institucion": _INSTITUCION,
                "conductor": _CONDUCTOR,
                "agrupar_por": {
                    "type": "string",
                    "enum": ["ninguno", "semana", "institucion", "conductor"],
                },
            }
        ),
    ),
    "listar_envios": (
        listar_envios,
        "Lista envíos de alimentos programados en un periodo (por defecto los últimos 7 "
        "días) con conteo por estado. Filtra por estado, institución, conductor, código o "
        "solo los retrasados / entregados tarde.",
        _esquema(
            {
                **_FECHAS,
                "estados": {"type": "array", "items": {"type": "string", "enum": Estado.values}},
                "institucion": _INSTITUCION,
                "conductor": _CONDUCTOR,
                "codigo": {"type": "string"},
                "solo_retrasados": {"type": "boolean"},
                "limite": _LIMITE,
            }
        ),
    ),
    "detalle_envio": (
        detalle_envio,
        "Detalle de un envío por su código: horas de salida, llegada y entrega, alimentos "
        "enviados y recibidos, evidencia y novedades.",
        _esquema({"codigo": {"type": "string"}}, ["codigo"]),
    ),
    "novedades": (
        novedades,
        "Novedades (retrasos, daños, faltantes, incidentes, entregas incompletas) de un "
        "periodo, con conteos por tipo, conductor e institución. Por defecto, 30 días.",
        _esquema(
            {
                **_FECHAS,
                "tipo": {"type": "string", "enum": Novedad.Tipo.values},
                "institucion": _INSTITUCION,
                "conductor": _CONDUCTOR,
                "solo_pendientes": {"type": "boolean"},
                "limite": _LIMITE,
            }
        ),
    ),
    "situacion_actual": (
        situacion_actual,
        "Situación en este momento: envíos de hoy por estado, vehículos en tránsito, "
        "envíos retrasados y novedades sin atender.",
        _esquema({}),
    ),
    "cobertura_pae": (
        cobertura_pae,
        "Entrega del PAE a estudiantes (registrada por el supervisor con QR o manual): "
        "estudiantes activos y cuántos recibieron por día, y opcionalmente por curso. Solo "
        "conteos. Use fecha para un día o desde/hasta para un periodo (por defecto 7 días).",
        _esquema(
            {
                "institucion": _INSTITUCION,
                "fecha": {"type": "string", "description": "Un solo día AAAA-MM-DD."},
                **_FECHAS,
                "por_curso": {
                    "type": "boolean",
                    "description": "Desglose por curso del último día del periodo.",
                },
                "grado": {"type": "string", "description": "Código de grado SIMAT, p. ej. 7."},
            }
        ),
    ),
    "catalogo": (
        catalogo,
        "Catálogo: instituciones (DANE, sede, beneficiarios, estudiantes con QR), "
        "conductores o vehículos.",
        _esquema(
            {
                "tipo": {"type": "string", "enum": ["instituciones", "conductores", "vehiculos"]},
                "buscar": {"type": "string"},
            },
            ["tipo"],
        ),
    ),
    "matricula_simat": (
        matricula_simat,
        "Matrícula del Anexo 6A de SIMAT (beneficiarios) por institución y grado, del año "
        "indicado o el más reciente.",
        _esquema({"anio": {"type": "integer"}}),
    ),
    "auditoria": (
        auditoria,
        "Registro de auditoría (quién hizo qué y cuándo) de un periodo, con conteo por "
        f"acción. Acciones: {', '.join(Accion.values)}. Por defecto, 7 días.",
        _esquema(
            {
                **_FECHAS,
                "accion": {"type": "string", "enum": Accion.values},
                "usuario": {"type": "string", "description": "Correo o nombre del usuario."},
                "limite": _LIMITE,
            }
        ),
    ),
    "enlace_reporte": (
        enlace_reporte,
        "Enlaces al reporte oficial de envíos (RF-36) en PDF, Excel o pantalla con los "
        "filtros dados. Úsela cuando pidan descargar o exportar un reporte.",
        _esquema({**_FECHAS, "institucion": _INSTITUCION, "conductor": _CONDUCTOR}),
    ),
}


def definiciones():
    """Lista de herramientas para la API (orden fijo: no rompe la caché)."""
    return [
        {"name": nombre, "description": descripcion, "input_schema": esquema}
        for nombre, (_, descripcion, esquema) in HERRAMIENTAS.items()
    ]


def ejecutar(nombre, entrada):
    """Ejecuta la herramienta y devuelve (texto_json, es_error)."""
    if nombre not in HERRAMIENTAS:
        return f"La herramienta {nombre!r} no existe.", True
    if not isinstance(entrada, dict):
        return "Los parámetros deben ser un objeto JSON.", True
    try:
        resultado = HERRAMIENTAS[nombre][0](entrada)
    except HerramientaError as exc:
        return str(exc), True
    return json.dumps(resultado, ensure_ascii=False, default=str), False
