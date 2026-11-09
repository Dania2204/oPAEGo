/* PAEGo — el conductor comparte su ubicación en vivo (modo de prueba).
 *
 * Mientras la sesión está abierta y el conductor no lo detiene, la posición
 * del GPS se envía a la API cada 3 s y el administrador la ve moverse en el
 * mapa de «Hoy». Más adelante esto lo hará la app móvil.
 */
(function () {
  "use strict";

  const CFG = window.PAEGO_CONDUCTOR;
  const INTERVALO_MS = 3000;
  const estado = document.getElementById("estado");
  const detalle = document.getElementById("detalle");
  const boton = document.getElementById("alternar");
  const contenedor = document.getElementById("mapa-conductor");

  let compartiendo = false;
  let vigilancia = null;
  let temporizador = null;
  let ultima = null; // última lectura del GPS
  let enviadaEn = null;
  let bloqueo = null;
  let seguir = true;

  /* ---- mapa propio ---- */
  let mapa = null;
  let yo = null;
  const sinMapa = () => {
    contenedor.innerHTML = '<p class="mapa-sin-datos">No se pudo cargar el mapa. La ubicación se comparte igual.</p>';
  };
  if (window.maplibregl && window.PaegoMapas) {
    PaegoMapas.listo().then(() => {
      mapa = PaegoMapas.crear(contenedor, ultima ? [ultima.latitud, ultima.longitud] : PaegoMapas.PASTO, ultima ? 17 : 14, { tresD: true });
      // Si el conductor mueve el mapa con el dedo, deja de seguirlo hasta que lo recentre.
      mapa.on("dragstart", () => { seguir = false; });
      const recentrar = new maplibregl.GeolocateControl({ trackUserLocation: false, showUserLocation: false });
      recentrar.on("geolocate", () => { seguir = true; });
      mapa.addControl(recentrar, "top-right");
      if (ultima) pintarPropia(ultima);
    }, sinMapa);
  } else {
    sinMapa();
  }

  function pintarPropia(p) {
    if (!mapa) return;
    const lnglat = [p.longitud, p.latitud];
    if (!yo) {
      const el = document.createElement("div");
      el.className = "punto-propio";
      yo = new maplibregl.Marker({ element: el }).setLngLat(lnglat).addTo(mapa);
      mapa.jumpTo({ center: lnglat, zoom: 17 });
    } else {
      yo.setLngLat(lnglat);
      if (seguir) {
        // Como en las apps de navegación: en 3D el mapa gira hacia donde avanza el vehículo.
        const camara = { center: lnglat, duration: 800, freezeElevation: true };
        if (mapa._3d && p.rumbo != null && (p.velocidad_kmh || 0) > 5) camara.bearing = p.rumbo;
        mapa.easeTo(camara);
      }
    }
  }

  function mostrar(texto, clase, extra) {
    estado.textContent = texto;
    estado.className = "conductor-estado" + (clase ? " " + clase : "");
    if (extra !== undefined) detalle.textContent = extra;
  }

  const redondear = (v, d) => (v == null || Number.isNaN(v) ? null : Number(v.toFixed(d)));

  function leer(pos) {
    const c = pos.coords;
    ultima = {
      latitud: redondear(c.latitude, 6),
      longitud: redondear(c.longitude, 6),
      precision_m: c.accuracy != null ? Math.min(redondear(c.accuracy, 2), 99999) : null,
      velocidad_kmh: c.speed != null && !Number.isNaN(c.speed) ? redondear(c.speed * 3.6, 2) : null,
      rumbo: c.heading != null && !Number.isNaN(c.heading) ? Math.round(c.heading) % 360 : null,
    };
    pintarPropia(ultima);
  }

  function errorGps(err) {
    const textos = {
      1: "Permiso de ubicación denegado. Actívelo en la configuración del navegador para este sitio.",
      2: "No se pudo obtener la ubicación. Revise que el GPS esté encendido.",
      3: "El GPS tardó demasiado en responder. Se sigue intentando…",
    };
    mostrar("Sin ubicación", "error", textos[err.code] || "Error de ubicación.");
    if (err.code === 1) detener();
  }

  async function enviar() {
    if (!compartiendo || !ultima) return;
    try {
      const r = await fetch(CFG.urlPosicion, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CFG.csrf },
        body: JSON.stringify(ultima),
      });
      if (r.status === 401 || r.status === 403) {
        // Sesión vencida o cerrada: volver a ingresar.
        window.location.href = CFG.urlLogin;
        return;
      }
      if (!r.ok) {
        mostrar("Compartiendo ubicación", "error", "El servidor rechazó la posición (" + r.status + ").");
        return;
      }
      enviadaEn = new Date();
      const precision = ultima.precision_m != null ? " · precisión " + Math.round(ultima.precision_m) + " m" : "";
      const velocidad = ultima.velocidad_kmh != null ? " · " + Math.round(ultima.velocidad_kmh) + " km/h" : "";
      mostrar(
        "Compartiendo ubicación",
        "activo",
        "Enviada " + enviadaEn.toLocaleTimeString("es-CO") + precision + velocidad
      );
    } catch (e) {
      mostrar("Compartiendo ubicación", "error", "Sin conexión. Se reintenta en unos segundos…");
    }
  }

  async function mantenerPantalla() {
    try {
      if ("wakeLock" in navigator && compartiendo && document.visibilityState === "visible") {
        bloqueo = await navigator.wakeLock.request("screen");
      }
    } catch (e) { /* el navegador no lo permite: no es indispensable */ }
  }

  function iniciar() {
    if (!window.isSecureContext) {
      mostrar("Sin ubicación", "error", "El navegador solo entrega la ubicación en sitios con HTTPS.");
      return;
    }
    if (!("geolocation" in navigator)) {
      mostrar("Sin ubicación", "error", "Este navegador no permite obtener la ubicación.");
      return;
    }
    compartiendo = true;
    boton.textContent = "Dejar de compartir";
    boton.classList.add("peligro");
    mostrar("Buscando señal GPS…", "activo", "");
    vigilancia = navigator.geolocation.watchPosition(leer, errorGps, {
      enableHighAccuracy: true,
      maximumAge: 2000,
      timeout: 20000,
    });
    // Se envía aunque el vehículo esté quieto: así el administrador sabe que sigue conectado.
    temporizador = setInterval(enviar, INTERVALO_MS);
    mantenerPantalla();
  }

  function detener() {
    compartiendo = false;
    if (vigilancia != null) navigator.geolocation.clearWatch(vigilancia);
    clearInterval(temporizador);
    vigilancia = temporizador = null;
    if (bloqueo) { bloqueo.release().catch(() => {}); bloqueo = null; }
    boton.textContent = "Compartir mi ubicación";
    boton.classList.remove("peligro");
    if (!estado.classList.contains("error")) mostrar("Ubicación detenida", "", "La entidad dejará de verlo en el mapa en menos de un minuto.");
  }

  boton.addEventListener("click", () => (compartiendo ? detener() : iniciar()));
  document.addEventListener("visibilitychange", mantenerPantalla);

  // Al abrir la sesión empieza a compartir de inmediato (el navegador pide permiso).
  iniciar();
})();
