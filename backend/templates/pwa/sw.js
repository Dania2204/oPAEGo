{% load static %}/* PAEGo — service worker del panel web (RF-38 / RNF-21).
 *
 * - Guarda en caché la interfaz y los últimos datos consultados para poder
 *   verlos sin conexión.
 * - Si un formulario se envía y la red falla, lo guarda en la cola local
 *   (IndexedDB) para sincronizarlo después.
 * - Sincroniza en segundo plano (Background Sync) cuando el navegador lo permite.
 */
importScripts("{% static 'js/cola.js' %}");

const ESTATICOS = "paego-estaticos-v10";
const PAGINAS = "paego-paginas";
const PARCIALES = "paego-parciales";
const PRECARGA = [
  "{% static 'css/tokens.css' %}",
  "{% static 'css/base.css' %}",
  "{% static 'css/componentes.css' %}",
  "{% static 'js/app.js' %}",
  "{% static 'js/cola.js' %}",
  "{% static 'js/offline.js' %}",
  "{% static 'js/mapas.js' %}",
  "{% static 'js/indicadores.js' %}",
  "{% static 'img/icono.svg' %}",
  "https://cdnjs.cloudflare.com/ajax/libs/htmx/2.0.4/htmx.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/alpinejs/3.14.8/cdn.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.0/chart.umd.min.js",
  "https://cdn.jsdelivr.net/npm/maplibre-gl@5.6.0/dist/maplibre-gl.css",
  "https://cdn.jsdelivr.net/npm/maplibre-gl@5.6.0/dist/maplibre-gl.js",
  "{% static 'js/conductor.js' %}",
  "https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;500;600&display=swap",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(ESTATICOS).then((cache) => Promise.allSettled(PRECARGA.map((url) => cache.add(url))))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys().then((claves) =>
      Promise.all(claves.filter((c) => c.startsWith("paego-estaticos-") && c !== ESTATICOS).map((c) => caches.delete(c)))
    ).then(() => self.clients.claim())
  );
});

function pagina(titulo, mensaje, volver) {
  const html = `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>${titulo} · PAEGo</title>
<link rel="stylesheet" href="{% static 'css/tokens.css' %}"><link rel="stylesheet" href="{% static 'css/base.css' %}">
<link rel="stylesheet" href="{% static 'css/componentes.css' %}"></head><body>
<div class="govco"><a href="https://www.gov.co">GOV.CO</a></div>
<main class="principal" style="max-width:560px;margin:48px auto"><div class="bloque"><div class="bloque-cuerpo">
<h1 style="margin-bottom:12px">${titulo}</h1><p>${mensaje}</p>
<a class="boton" href="${volver || "/panel/"}">Continuar</a></div></div></main></body></html>`;
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

async function avisarClientes() {
  const clientes = await self.clients.matchAll({ includeUncontrolled: true });
  clientes.forEach((c) => c.postMessage({ tipo: "cola-actualizada" }));
}

/* POST de formulario sin red -> cola local. */
async function enviarFormulario(peticion) {
  const copia = peticion.clone();
  try {
    return await fetch(peticion);
  } catch (error) {
    let datos;
    try { datos = await copia.formData(); } catch (e) { datos = null; }
    if (!datos) return pagina("Sin conexión", "No fue posible enviar la información.", "/panel/");
    const volver = datos.get("_volver") || "/panel/";
    try {
      const usuario = await PaegoCola.leerConfig("usuario");
      for (const op of PaegoCola.operacionesDesdeFormulario(datos, usuario)) await PaegoCola.encolar(op);
      await avisarClientes();
      return pagina(
        "Guardado sin conexión",
        "El cambio quedó guardado en este equipo y se enviará automáticamente cuando vuelva la conexión.",
        volver
      );
    } catch (e) {
      return pagina("Requiere conexión", e.message, volver);
    }
  }
}

/* Páginas: red primero; sin red, la última versión guardada. */
async function navegar(peticion) {
  try {
    const respuesta = await fetch(peticion);
    const esLogin = new URL(respuesta.url).pathname.startsWith("/ingresar");
    if (respuesta.ok && !esLogin) {
      const cache = await caches.open(PAGINAS);
      cache.put(peticion, respuesta.clone());
    }
    return respuesta;
  } catch (error) {
    const guardada = await caches.match(peticion, { cacheName: PAGINAS });
    if (guardada) return guardada;
    return pagina(
      "Sin conexión",
      "Esta página no está disponible sin conexión porque no se había consultado antes en este equipo. " +
        "Los cambios que registre se guardarán y se enviarán al volver la conexión.",
      "/panel/"
    );
  }
}

/* Datos de la API para mapas e indicadores: red primero, caché de respaldo. */
async function datosApi(peticion) {
  try {
    const respuesta = await fetch(peticion);
    if (respuesta.ok) (await caches.open(PAGINAS)).put(peticion, respuesta.clone());
    return respuesta;
  } catch (error) {
    const guardada = await caches.match(peticion, { cacheName: PAGINAS });
    return guardada || new Response("[]", { headers: { "Content-Type": "application/json" } });
  }
}

/* Fragmentos HTMX (panel lateral, listas): red primero; sin red, el último
 * fragmento guardado para esa URL y ese destino. */
async function parcial(peticion) {
  const clave = peticion.url + "#hx=" + (peticion.headers.get("HX-Target") || "");
  try {
    const respuesta = await fetch(peticion);
    if (respuesta.ok) (await caches.open(PARCIALES)).put(clave, respuesta.clone());
    return respuesta;
  } catch (error) {
    const guardada = await caches.match(clave, { cacheName: PARCIALES });
    if (guardada) return guardada;
    return new Response(
      '<div class="panel-cuerpo"><p class="vacio">Sin conexión: este contenido no se había consultado antes en este equipo.</p></div>',
      { headers: { "Content-Type": "text/html; charset=utf-8" } }
    );
  }
}

/* Archivos propios (/static/): red primero, para que una corrección llegue de
 * inmediato; sin red, la copia guardada. */
async function propio(peticion) {
  const cache = await caches.open(ESTATICOS);
  try {
    const respuesta = await fetch(peticion);
    if (respuesta.ok) cache.put(peticion, respuesta.clone());
    return respuesta;
  } catch (error) {
    const guardada = await cache.match(peticion);
    if (guardada) return guardada;
    throw error;
  }
}

/* Librerías versionadas del CDN y teselas del mapa: caché primero,
 * actualizando en segundo plano. */
async function estatico(peticion) {
  const cache = await caches.open(ESTATICOS);
  const guardada = await cache.match(peticion);
  const red = fetch(peticion)
    .then((r) => { if (r.ok || r.type === "opaque") cache.put(peticion, r.clone()); return r; })
    .catch(() => guardada);
  return guardada || red;
}

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  const url = new URL(peticion.url);

  if (peticion.method === "POST" && peticion.mode === "navigate") {
    evento.respondWith(enviarFormulario(peticion));
    return;
  }
  if (peticion.method !== "GET") return;

  if (peticion.mode === "navigate") {
    evento.respondWith(navegar(peticion));
  } else if (url.origin === self.location.origin && peticion.headers.get("HX-Request") === "true") {
    evento.respondWith(parcial(peticion));
  } else if (url.origin === self.location.origin && url.pathname.startsWith("/api/monitoreo/") && !url.pathname.endsWith("/conductores-en-vivo/")) {
    // Las posiciones en vivo nunca se sirven desde la caché: serían viejas.
    evento.respondWith(datosApi(peticion));
  } else if (url.origin === self.location.origin && url.pathname.startsWith("/static/")) {
    evento.respondWith(propio(peticion));
  } else if (
    url.hostname === "cdnjs.cloudflare.com" ||
    url.hostname === "fonts.googleapis.com" ||
    url.hostname === "fonts.gstatic.com" ||
    url.hostname === "cdn.jsdelivr.net" ||
    url.hostname === "tiles.openfreemap.org" ||
    url.hostname === "tiles.mapterhorn.com"
  ) {
    evento.respondWith(estatico(peticion));
  }
});

self.addEventListener("sync", (evento) => {
  if (evento.tag !== "paego-sincronizar") return;
  evento.waitUntil(
    (async () => {
      const usuario = await PaegoCola.leerConfig("usuario");
      const urlLote = await PaegoCola.leerConfig("urlLote");
      if (urlLote) await PaegoCola.sincronizar(urlLote, usuario);
      await avisarClientes();
    })()
  );
});
