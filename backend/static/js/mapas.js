/* PAEGo — mapas vectoriales con MapLibre GL (RF-07, RF-29, RF-35).
 *
 * Inicialización declarativa: cualquier elemento con data-mapa se activa al
 * cargarse (también dentro del panel lateral, que llega por HTMX).
 *   data-mapa="selector"  coordenadas de una institución (RF-07)
 *   data-mapa="ruta"      ruta recorrida de un envío (RF-35)
 *   data-mapa="hoy"       operación del día en tiempo real (RF-29)
 *   data-vivo="<url>"     además, conductores en vivo que se mueven en el mapa
 *
 * Los datos llegan como [latitud, longitud]; MapLibre usa [longitud, latitud].
 */
(function () {
  "use strict";

  const PASTO = [1.2136, -77.2811];
  /* OpenFreeMap: teselas vectoriales de OpenStreetMap, gratis y sin clave. Se
   * parte del estilo "liberty" y se retoca al aspecto de las apps de transporte
   * (Uber, inDrive): fondo gris claro, calles blancas, avenidas en amarillo
   * suave, parques verdes y sin comercios ni íconos que distraigan. */
  const ESTILO = "https://tiles.openfreemap.org/styles/liberty";
  const C = {
    fondo: "#eef0f3", parque: "#d4ebcb", bosque: "#cfe6c4", agua: "#a8d4f5", otroSuelo: "#e8e6ef",
    edificio: "#e2e5ea", edificioBorde: "#d5d9e0", calle: "#ffffff", borde: "#d3d8df", peatonal: "#dfe3e8",
    principal: "#fde9b4", principalBorde: "#ecc979", autopista: "#fbd98a", autopistaBorde: "#e3b45a",
    ferrocarril: "#c9cdd4", texto: "#5b6270", textoLugar: "#3a3f48",
  };
  /* Relieve: elevación gratuita de Mapterhorn (sin clave). Pasto está entre
   * montañas, así que en 3D se ven el Galeras y las laderas. */
  // En Colombia hay datos hasta el nivel 12; más cerca, MapLibre amplía esas teselas.
  const ELEVACION = {
    type: "raster-dem",
    tiles: ["https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"],
    encoding: "terrarium",
    tileSize: 512,
    maxzoom: 12,
    attribution: '<a href="https://mapterhorn.com/attribution" target="_blank" rel="noopener">© Mapterhorn</a>',
  };
  const EXAGERACION = 1.3;
  const INCLINACION_3D = 55;
  const OCULTAR = /^(poi_|road_one_way|highway-shield|road_shield|landuse_residential|landcover_ice|landcover_wetland|aeroway_|airport|natural_earth|park_outline|road_area_pattern|.*rail_hatching)/;

  function estiloPaego(s) {
    s.layers = s.layers.filter((l) => !OCULTAR.test(l.id));
    s.layers.forEach((l) => {
      const p = (l.paint = l.paint || {});
      const id = l.id;
      if (l.type === "background") p["background-color"] = C.fondo;
      else if (/^(park|landcover_grass|landuse_pitch|landuse_cemetery)$/.test(id)) Object.assign(p, { "fill-color": C.parque, "fill-opacity": 1 });
      else if (id === "landcover_wood") Object.assign(p, { "fill-color": C.bosque, "fill-opacity": 1 });
      else if (/^(landuse_school|landuse_hospital|landuse_track|landcover_sand)$/.test(id)) Object.assign(p, { "fill-color": C.otroSuelo, "fill-opacity": 0.7 });
      else if (id === "water") p["fill-color"] = C.agua;
      else if (id.startsWith("waterway") && l.type === "line") p["line-color"] = C.agua;
      else if (id === "building") Object.assign(p, { "fill-color": C.edificio, "fill-outline-color": C.edificioBorde, "fill-opacity": 1 });
      else if (id === "building-3d") {
        // Edificios con su altura real; un poco más oscuros arriba para dar volumen.
        Object.assign(p, {
          "fill-extrusion-color": ["interpolate", ["linear"], ["get", "render_height"], 0, "#dfe3ea", 40, "#c9cfd9"],
          "fill-extrusion-opacity": 0.92,
          "fill-extrusion-vertical-gradient": true,
        });
      }
      else if (l["source-layer"] === "transportation" && l.type === "line") {
        const borde = id.endsWith("_casing");
        if (/rail/.test(id)) p["line-color"] = C.ferrocarril;
        else if (/path_pedestrian/.test(id)) p["line-color"] = borde ? C.borde : C.peatonal;
        else if (/motorway/.test(id)) p["line-color"] = borde ? C.autopistaBorde : C.autopista;
        else if (/trunk_primary/.test(id)) p["line-color"] = borde ? C.principalBorde : C.principal;
        else p["line-color"] = borde ? C.borde : C.calle;
      } else if (l.type === "symbol") {
        p["text-color"] = l["source-layer"] === "place" ? C.textoLugar : C.texto;
        p["text-halo-color"] = "rgba(255,255,255,0.95)";
        p["text-halo-width"] = 1.4;
      }
    });
    // Fuentes de elevación (una para el terreno 3D y otra para las sombras, como
    // recomienda MapLibre) y una capa de sombreado suave bajo las calles.
    s.sources.terreno = Object.assign({}, ELEVACION);
    s.sources.sombras = Object.assign({}, ELEVACION);
    const agua = s.layers.findIndex((l) => l.id === "water");
    s.layers.splice(agua < 0 ? 1 : agua, 0, {
      id: "relieve", type: "hillshade", source: "sombras",
      paint: {
        "hillshade-exaggeration": 0.35,
        "hillshade-shadow-color": "#8f99a8",
        "hillshade-highlight-color": "#ffffff",
        "hillshade-accent-color": "#aab2bf",
      },
    });
    s.sky = {
      "sky-color": "#b9d5f0", "horizon-color": "#e6edf5", "fog-color": C.fondo,
      "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.7, "fog-ground-blend": 0.35, "atmosphere-blend": 0,
    };
    return s;
  }

  /* El estilo se descarga y se retoca una sola vez por página, aunque haya
   * varios mapas; los mapas se crean cuando ya está listo. */
  let estiloListo = null;
  let estiloPromesa = null;
  function listo() {
    estiloPromesa =
      estiloPromesa ||
      fetch(ESTILO)
        .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then((s) => { estiloListo = estiloPaego(s); })
        .catch((error) => { estiloPromesa = null; throw error; });
    return estiloPromesa;
  }
  const INTERVALO_VIVO_MS = 3000;
  const ANIMACION_MS = 2500;
  const PUNTOS_ESTELA = 25;

  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const ll = (p) => [p[1], p[0]];
  const colorEstado = (estado) =>
    ({
      ASIGNADO: css("--e-asignado"),
      EN_TRANSITO: css("--e-transito"),
      ENTREGADO: css("--e-entregado"),
      CON_NOVEDAD: css("--e-novedad"),
      CANCELADO: css("--e-cancelado"),
    })[estado] || css("--tinta-3");

  function escapar(t) {
    const d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  const hora = (iso, segundos) =>
    iso
      ? new Date(iso).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", second: segundos ? "2-digit" : undefined })
      : "—";

  /* Vista 3D: terreno con relieve, cámara inclinada y edificios en altura.
   * Toda animación de cámara lleva freezeElevation: true; sin eso MapLibre 5.6
   * deja de ajustar la altura de la cámara al terreno y el mapa queda en blanco. */
  function vista3d(mapa, activa, animar) {
    mapa._3d = activa;
    // En 2D los edificios en altura vistos desde arriba dejan bordes raros.
    if (mapa.getLayer("building-3d")) mapa.setLayoutProperty("building-3d", "visibility", activa ? "visible" : "none");
    mapa.setTerrain(activa ? { source: "terreno", exaggeration: EXAGERACION } : null);
    const camara = { pitch: activa ? INCLINACION_3D : 0, bearing: activa ? mapa.getBearing() || -20 : 0 };
    if (animar) mapa.easeTo(Object.assign(camara, { duration: 900, freezeElevation: true }));
    else mapa.jumpTo(camara);
    if (mapa._boton3d) {
      mapa._boton3d.textContent = activa ? "2D" : "3D";
      mapa._boton3d.title = activa ? "Ver el mapa plano" : "Ver en 3D: relieve y edificios";
      mapa._boton3d.setAttribute("aria-pressed", String(activa));
    }
  }

  class Control3D {
    onAdd(mapa) {
      this.contenedor = document.createElement("div");
      this.contenedor.className = "maplibregl-ctrl maplibregl-ctrl-group";
      const boton = document.createElement("button");
      boton.type = "button";
      boton.className = "boton-3d";
      boton.addEventListener("click", () => vista3d(mapa, !mapa._3d, true));
      mapa._boton3d = boton;
      this.contenedor.appendChild(boton);
      return this.contenedor;
    }
    onRemove() { this.contenedor.remove(); }
  }

  /* opciones.tresD: abre en 3D (mapas de seguimiento); los formularios abren en 2D. */
  function crear(el, centro, zoom, opciones) {
    const tresD = !!(opciones && opciones.tresD);
    const mapa = new maplibregl.Map({
      container: el,
      style: structuredClone(estiloListo), // copia: cada mapa le agrega sus capas
      center: ll(centro || PASTO),
      zoom: zoom || 13,
      pitch: tresD ? INCLINACION_3D : 0,
      bearing: tresD ? -20 : 0,
      maxPitch: 70,
      attributionControl: { compact: true }, // la atribución de OSM viene en el estilo
    });
    mapa.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    mapa.addControl(new Control3D(), "top-right");
    mapa._3d = tresD;
    mapa.on("load", () => {
      mapa._cargado = true;
      vista3d(mapa, tresD, false);
    });
    mapa.on("error", (e) => console.warn("PAEGo mapa:", e.error && e.error.message));
    el._mapa = mapa;
    // El contenedor cambia de tamaño (panel lateral que se abre, mapa que se
    // oculta y se muestra, ventana redimensionada): recalcular siempre.
    if (window.ResizeObserver) new ResizeObserver(() => mapa.resize()).observe(el);
    else setTimeout(() => mapa.resize(), 300);
    return mapa;
  }

  /* Ejecuta fn cuando el estilo esté listo (las capas solo se agregan después). */
  function cuandoCargue(mapa, fn) {
    if (mapa._cargado) fn();
    else mapa.once("load", fn);
  }

  function punto(color, tamano, titulo) {
    const el = document.createElement("div");
    el.className = "punto-mapa";
    el.style.setProperty("--c", color);
    el.style.setProperty("--t", (tamano || 12) + "px");
    if (titulo) el.title = titulo;
    return el;
  }

  function marcador(mapa, posicion, elemento, popupHtml, opciones) {
    const m = new maplibregl.Marker(Object.assign({ element: elemento }, opciones || {}))
      .setLngLat(ll(posicion))
      .addTo(mapa);
    if (popupHtml) m.setPopup(new maplibregl.Popup({ offset: 14, closeButton: false, maxWidth: "260px" }).setHTML(popupHtml));
    return m;
  }

  /* Línea con borde blanco (estilo de las apps de navegación). Las líneas se
   * pasan como GeoJSON; el color va en properties.color. */
  function capaLineas(mapa, id, ancho, opacidad) {
    mapa.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    mapa.addLayer({
      id: id + "-borde", type: "line", source: id,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#ffffff", "line-width": ancho + 3, "line-opacity": opacidad },
    });
    mapa.addLayer({
      id: id, type: "line", source: id,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": ["get", "color"], "line-width": ancho, "line-opacity": opacidad },
    });
  }

  function lineas(mapa, id, lista) {
    const fuente = mapa.getSource(id);
    if (!fuente) return;
    fuente.setData({
      type: "FeatureCollection",
      features: lista
        .filter((l) => l.puntos.length > 1)
        .map((l) => ({
          type: "Feature",
          properties: { color: l.color },
          geometry: { type: "LineString", coordinates: l.puntos.map(ll) },
        })),
    });
  }

  function encuadrar(mapa, puntos, maxZoom, padding) {
    if (!puntos.length) return;
    if (puntos.length === 1) { mapa.jumpTo({ center: ll(puntos[0]), zoom: Math.min(maxZoom, 15) }); return; }
    const limites = new maplibregl.LngLatBounds(ll(puntos[0]), ll(puntos[0]));
    puntos.forEach((p) => limites.extend(ll(p)));
    // jumpTo y no fitBounds: con terreno 3D, las animaciones de MapLibre 5.6 sin
    // freezeElevation dejan la cámara a 0 m (Pasto está a ~2.500 m, bajo tierra).
    const camara = mapa.cameraForBounds(limites, { padding: padding || 40, maxZoom: maxZoom });
    if (camara) mapa.jumpTo({ center: camara.center, zoom: camara.zoom });
  }

  /* Vehículo de un envío en ruta: etiqueta con el código para reconocerlo sin abrirlo. */
  function vehiculoEnvio(codigo, retrasado) {
    const el = document.createElement("div");
    el.innerHTML =
      '<span class="marcador-vehiculo' + (retrasado ? " retrasado" : "") + '">' +
      '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M3 6h11v9H3zM14 9h4l3 3v3h-7z"/><circle cx="7" cy="17" r="2" fill="currentColor"/><circle cx="17" cy="17" r="2" fill="currentColor"/></svg>' +
      "<b>" + escapar(codigo.split("-").pop()) + "</b></span>";
    el.title = codigo;
    return el;
  }

  /* Auto visto desde arriba, apuntando al norte; MapLibre lo gira según el rumbo. */
  const SVG_AUTO =
    '<svg viewBox="0 0 24 40" width="26" height="43" aria-hidden="true">' +
    '<rect x="2" y="1" width="20" height="38" rx="7" fill="#004884" stroke="#fff" stroke-width="2"/>' +
    '<path d="M5.5 12 Q12 7.5 18.5 12 L17.5 16.5 H6.5 Z" fill="#d6e4f8"/>' +
    '<rect x="6.5" y="18" width="11" height="10" rx="2" fill="#1d63b0"/>' +
    '<path d="M6.5 30 H17.5 L18.5 33.5 Q12 36.5 5.5 33.5 Z" fill="#d6e4f8" opacity=".85"/>' +
    "</svg>";

  function elementoAuto(nombre) {
    const el = document.createElement("div");
    el.className = "auto-vivo";
    el.innerHTML = SVG_AUTO;
    el.title = nombre;
    return el;
  }

  /* Rumbo en grados (0 = norte) entre dos puntos [lat, lng]. */
  function rumboEntre(a, b) {
    const r = Math.PI / 180;
    const y = Math.sin((b[1] - a[1]) * r) * Math.cos(b[0] * r);
    const x = Math.cos(a[0] * r) * Math.sin(b[0] * r) - Math.sin(a[0] * r) * Math.cos(b[0] * r) * Math.cos((b[1] - a[1]) * r);
    return (Math.atan2(y, x) / r + 360) % 360;
  }

  function metrosEntre(a, b) {
    const r = Math.PI / 180;
    const dLat = (b[0] - a[0]) * r;
    const dLng = (b[1] - a[1]) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLng / 2) ** 2;
    return 12742000 * Math.asin(Math.sqrt(h));
  }

  /* Interpolación del ángulo por el camino más corto (de 350° a 10° gira 20°, no 340°). */
  function anguloIntermedio(a, b, t) {
    const d = ((b - a + 540) % 360) - 180;
    return (a + d * t + 360) % 360;
  }

  /* ---- conductores en vivo (modo de prueba) ----
   * Consulta la API cada 3 s y desliza cada auto de su posición anterior a la
   * nueva para que el movimiento sea continuo, como en Uber o inDrive. */
  function conductoresEnVivo(el, mapa, alPrimerDato) {
    const url = el.dataset.vivo;
    if (!url) return;
    const autos = {};
    const contador = document.createElement("div");
    contador.className = "mapa-en-vivo";
    contador.hidden = true;
    el.appendChild(contador);
    let animando = false;
    let estelaEn = 0;

    capaLineas(mapa, "estelas-vivo", 4, 0.55);

    function popup(c) {
      return (
        "<strong>" + escapar(c.nombre) + "</strong>" +
        (c.placa ? "<br>Vehículo " + escapar(c.placa) : "") +
        (c.velocidad_kmh != null ? "<br>" + Math.round(c.velocidad_kmh) + " km/h" : "") +
        "<br>Actualizado " + hora(c.actualizado_en, true) +
        (c.telefono ? '<br><a href="tel:' + escapar(c.telefono) + '">' + escapar(c.telefono) + "</a>" : "")
      );
    }

    function cuadro(ahora) {
      animando = false;
      Object.values(autos).forEach((a) => {
        if (!a.animacion) return;
        const t = Math.min(1, (ahora - a.animacion.inicio) / ANIMACION_MS);
        const s = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2; // suavizado
        const p = [
          a.animacion.desde[0] + (a.animacion.hasta[0] - a.animacion.desde[0]) * s,
          a.animacion.desde[1] + (a.animacion.hasta[1] - a.animacion.desde[1]) * s,
        ];
        a.actual = p;
        a.marcador.setLngLat(ll(p));
        a.angulo = anguloIntermedio(a.animacion.anguloDesde, a.animacion.anguloHasta, s);
        a.marcador.setRotation(a.angulo);
        if (t >= 1) a.animacion = null;
        else animando = true;
      });
      // La estela se redibuja como máximo cada 200 ms: hacerlo en cada cuadro
      // satura el worker de MapLibre y la línea se queda atrás del auto.
      if (!animando || ahora - estelaEn > 200) { pintarEstelas(); estelaEn = ahora; }
      if (animando) requestAnimationFrame(cuadro);
    }

    /* La estela termina donde va el auto, no en el punto al que se dirige. */
    function pintarEstelas() {
      lineas(mapa, "estelas-vivo", Object.values(autos).map((a) => ({ puntos: a.estela.slice(0, -1).concat([a.actual]), color: css("--accion") })));
    }

    function animar() {
      if (!animando) { animando = true; requestAnimationFrame(cuadro); }
    }

    function actualizar(lista) {
      const vistos = new Set();
      lista.forEach((c) => {
        vistos.add(c.id);
        let a = autos[c.id];
        if (!a) {
          a = autos[c.id] = {
            actual: c.posicion,
            angulo: c.rumbo || 0,
            estela: [c.posicion],
            marcador: marcador(mapa, c.posicion, elementoAuto(c.nombre), popup(c), {
              rotation: c.rumbo || 0,
              rotationAlignment: "map",
              pitchAlignment: "map", // en 3D el auto queda acostado sobre la calle
            }),
          };
        } else {
          a.marcador.getPopup().setHTML(popup(c));
          const ultimo = a.estela[a.estela.length - 1];
          const distancia = metrosEntre(ultimo, c.posicion);
          if (distancia > 0.5) {
            a.estela.push(c.posicion);
            if (a.estela.length > PUNTOS_ESTELA) a.estela.shift();
            // Rumbo del GPS si viene y el vehículo avanza; si no, el de los dos últimos puntos.
            let rumbo = a.angulo;
            if (c.rumbo != null && (c.velocidad_kmh || 0) > 3) rumbo = c.rumbo;
            else if (distancia > 3) rumbo = rumboEntre(ultimo, c.posicion);
            a.animacion = { desde: a.actual, hasta: c.posicion, anguloDesde: a.angulo, anguloHasta: rumbo, inicio: performance.now() };
            animar();
          }
        }
        a.marcador.getElement().title = c.nombre;
      });
      Object.keys(autos).forEach((id) => {
        if (vistos.has(Number(id))) return;
        autos[id].marcador.remove();
        delete autos[id];
      });
      pintarEstelas();
      contador.hidden = !lista.length;
      contador.textContent = lista.length === 1 ? "1 conductor en vivo" : lista.length + " conductores en vivo";
      if (lista.length && alPrimerDato) { alPrimerDato(lista.map((c) => c.posicion)); alPrimerDato = null; }
    }

    async function consultar() {
      if (!document.body.contains(el)) { clearInterval(temporizador); return; }
      if (document.hidden) return;
      try {
        const r = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
        if (r.ok) actualizar(await r.json());
      } catch (e) { /* sin conexión: se reintenta en el siguiente ciclo */ }
    }

    const temporizador = setInterval(consultar, INTERVALO_VIVO_MS);
    consultar();
    el._autos = autos;
  }

  /* ---- selector de coordenadas ---- */
  function selector(el) {
    const lat = document.getElementById(el.dataset.lat);
    const lng = document.getElementById(el.dataset.lng);
    const inicial = lat.value && lng.value ? [parseFloat(lat.value), parseFloat(lng.value)] : null;
    const mapa = crear(el, inicial || PASTO, inicial ? 16 : 13);
    let m = null;
    const escribir = (p) => { lat.value = p[0].toFixed(6); lng.value = p[1].toFixed(6); };
    const fijar = (p) => {
      if (m) { m.setLngLat(ll(p)); return; }
      m = marcador(mapa, p, punto(css("--accion"), 18, "Ubicación de la institución"), null, { draggable: true });
      m.on("dragend", () => { const q = m.getLngLat(); escribir([q.lat, q.lng]); });
    };
    if (inicial) fijar(inicial);
    mapa.on("click", (e) => {
      const p = [e.lngLat.lat, e.lngLat.lng];
      escribir(p);
      fijar(p);
    });
    [lat, lng].forEach((c) =>
      c.addEventListener("change", () => {
        const p = [parseFloat(lat.value), parseFloat(lng.value)];
        if (Number.isNaN(p[0]) || Number.isNaN(p[1])) return;
        fijar(p);
        mapa.flyTo({ center: ll(p), zoom: 16, freezeElevation: true });
      })
    );
  }

  /* ---- ruta recorrida de un envío ---- */
  function ruta(el) {
    const d = JSON.parse(el.dataset.datos);
    const mapa = crear(el, d.destino, 14);
    const limites = [d.destino];
    cuandoCargue(mapa, () => {
      capaLineas(mapa, "ruta", 5, 0.9);
      lineas(mapa, "ruta", [{ puntos: d.ruta, color: css("--accion") }]);
    });
    if (d.ruta.length > 1) limites.push(...d.ruta);
    if (d.salida) { marcador(mapa, d.salida, punto(css("--tinta-3"), 12, "Salida")); limites.push(d.salida); }
    if (d.ruta.length) marcador(mapa, d.ruta[d.ruta.length - 1], punto(css("--accion"), 14, "Última posición"));
    if (d.entrega) { marcador(mapa, d.entrega, punto(css("--e-entregado"), 14, "Recepción confirmada")); limites.push(d.entrega); }
    marcador(mapa, d.destino, punto(css("--tinta"), 14, d.destino_nombre));
    if (limites.length > 1) encuadrar(mapa, limites, 16, 28);
  }

  /* ---- operación del día ---- */
  function hoy(el) {
    const mapa = crear(el, PASTO, 13, { tresD: true });
    let marcadores = {}; // id del envío → marcador principal (vehículo o destino)
    let todos = [];
    let encuadrado = false;

    function pintar() {
      const fuente = document.getElementById(el.dataset.fuente);
      if (!fuente) return;
      let envios;
      try { envios = JSON.parse(fuente.textContent); } catch (e) { return; }
      todos.forEach((m) => m.remove());
      todos = [];
      marcadores = {};
      const limites = [];
      const rutas = [];
      envios.forEach((e) => {
        if (!Array.isArray(e.destino) || e.destino.some((v) => typeof v !== "number")) return;
        const color = colorEstado(e.estado);
        if (e.ruta && e.ruta.length > 1) rutas.push({ puntos: e.ruta, color: e.retrasado ? css("--error") : color });
        let principal = marcador(
          mapa, e.destino, punto(color, 14, e.codigo + " · " + e.institucion),
          "<strong>" + escapar(e.codigo) + "</strong><br>" + escapar(e.institucion)
        );
        todos.push(principal);
        limites.push(e.destino);
        if (e.posicion) {
          principal = marcador(
            mapa, e.posicion, vehiculoEnvio(e.codigo, e.retrasado),
            "<strong>" + escapar(e.codigo) + "</strong><br>" + escapar(e.conductor) +
              "<br>Hacia " + escapar(e.institucion) + "<br>Posición " + hora(e.posicion_en)
          );
          todos.push(principal);
          limites.push(e.posicion);
        }
        marcadores[e.id] = principal;
      });
      cuandoCargue(mapa, () => lineas(mapa, "rutas-hoy", rutas));
      if (!encuadrado && limites.length) {
        encuadrar(mapa, limites, 15, 48);
        encuadrado = true;
      }
    }

    cuandoCargue(mapa, () => {
      capaLineas(mapa, "rutas-hoy", 4, 0.85);
      pintar();
      // Si no hay envíos que encuadrar, el mapa va a donde estén los conductores en vivo.
      conductoresEnVivo(el, mapa, (puntos) => {
        if (!encuadrado) { encuadrar(mapa, puntos, 16, 60); encuadrado = true; }
      });
    });
    document.addEventListener("htmx:afterSwap", (e) => {
      if (e.detail.target.id === el.dataset.zona && mapa._cargado) pintar();
    });
    // Clic en una fila de la lista: centrar en el mapa.
    document.addEventListener("click", (e) => {
      const fila = e.target.closest("[data-envio-id]");
      if (!fila) return;
      const m = marcadores[fila.dataset.envioId];
      if (!m) return;
      mapa.flyTo({ center: m.getLngLat(), zoom: Math.max(mapa.getZoom(), 15), duration: 600, freezeElevation: true });
      if (m.getPopup() && !m.getPopup().isOpen()) m.togglePopup();
    });
  }

  const TIPOS = { selector, ruta, hoy };

  function iniciar(raiz) {
    raiz = raiz || document;
    const propios = raiz.matches && raiz.matches("[data-mapa]") ? [raiz] : [];
    propios.concat(Array.from(raiz.querySelectorAll("[data-mapa]"))).forEach((el) => {
      if (el._mapa) return;
      if (!window.maplibregl) {
        // Sin la librería (sin internet y sin caché): avisar en lugar de un recuadro gris.
        el.innerHTML = '<p class="mapa-sin-datos">No se pudo cargar el mapa. Revise la conexión a internet y recargue la página.</p>';
        return;
      }
      const tipo = TIPOS[el.dataset.mapa];
      if (!tipo) return;
      el._mapa = "cargando";
      listo().then(
        () => {
          try {
            tipo(el);
          } catch (error) {
            console.error("PAEGo: no se pudo dibujar el mapa", error);
            el.innerHTML = '<p class="mapa-sin-datos">No se pudo dibujar el mapa con los datos recibidos.</p>';
          }
        },
        () => {
          el._mapa = null;
          el.innerHTML = '<p class="mapa-sin-datos">No se pudo cargar el mapa. Revise la conexión a internet y recargue la página.</p>';
        }
      );
    });
  }

  if (window.htmx) htmx.onLoad(iniciar);
  else document.addEventListener("DOMContentLoaded", () => iniciar());

  window.PaegoMapas = { iniciar, listo, crear, cuandoCargue, capaLineas, lineas, marcador, elementoAuto, punto, rumboEntre, metrosEntre, PASTO };
})();
