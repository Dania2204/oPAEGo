/* PAEGo — funcionamiento sin conexión del panel web (RF-38 / RNF-21).
 *
 * - Registra el service worker (la web funciona como PWA).
 * - Sin conexión, los formularios marcados con data-offline-tipo (incluidos
 *   los que llegan al panel lateral por HTMX) se guardan en la cola local.
 * - Al volver la conexión la cola se sincroniza sola; el indicador de la
 *   cabecera muestra pendientes, resultado y operaciones rechazadas.
 */
(function () {
  "use strict";
  const cfg = window.PAEGO || {};
  const boton = document.getElementById("estado-conexion");
  const detalle = document.getElementById("detalle-conexion");
  const avisar = (t, tipo) => window.PaegoAvisar && window.PaegoAvisar(t, tipo);

  function cookie(nombre) {
    const par = document.cookie.split("; ").find((c) => c.startsWith(nombre + "="));
    return par ? decodeURIComponent(par.split("=")[1]) : "";
  }

  function mostrar(clase, etiqueta, texto) {
    if (!boton) return;
    boton.className = "conexion " + (clase || "");
    boton.textContent = etiqueta;
    detalle.textContent = texto;
  }

  async function refrescarEstado() {
    const pendientes = (await PaegoCola.pendientes(cfg.usuarioId)).length;
    const rechazadas = (await PaegoCola.rechazadas()).filter((r) => r.usuario === cfg.usuarioId).length;
    if (!navigator.onLine) {
      mostrar("sin-red", "Sin conexión" + (pendientes ? " · " + pendientes : ""),
        "Puede seguir registrando: " + pendientes + " cambio(s) guardado(s) en este equipo se enviarán al volver internet.");
    } else if (pendientes) {
      mostrar("pendiente", pendientes + " por enviar", pendientes + " cambio(s) registrados sin conexión esperan sincronizarse.");
    } else if (rechazadas) {
      mostrar("error", rechazadas + " rechazada(s)", "El servidor no aceptó " + rechazadas + " operación(es) registradas sin conexión. Revíselas.");
    } else {
      mostrar("", "En línea", "Todos los cambios están guardados en el servidor.");
    }
  }

  async function sincronizar() {
    if (!navigator.onLine) return refrescarEstado();
    const pendientes = await PaegoCola.pendientes(cfg.usuarioId);
    if (!pendientes.length) return refrescarEstado();
    mostrar("pendiente", "Sincronizando…", "Enviando " + pendientes.length + " cambio(s) al servidor.");
    const r = await PaegoCola.sincronizar(cfg.urlLote, cfg.usuarioId);
    if (r.estado === "sin-sesion") {
      mostrar("error", "Inicie sesión", "Su sesión venció. Ingrese de nuevo para sincronizar; los cambios siguen guardados en este equipo.");
      avisar("Su sesión venció: ingrese de nuevo para enviar los cambios guardados sin conexión.", "error");
      return;
    }
    if (r.estado === "ok") {
      avisar(
        r.enviadas + " cambio(s) registrados sin conexión se enviaron al servidor." +
          (r.rechazadas ? " " + r.rechazadas + " fueron rechazados." : ""),
        r.rechazadas ? "error" : ""
      );
      document.body.dispatchEvent(new Event("envios-actualizados"));
      document.body.dispatchEvent(new Event("catalogo-actualizado"));
    }
    return refrescarEstado();
  }

  /* ---- formularios: campos internos para la cola ---- */
  const SELECTOR = "form[data-offline-tipo]";
  function formulariosEn(raiz) {
    raiz = raiz || document;
    const propios = raiz.matches && raiz.matches(SELECTOR) ? [raiz] : [];
    return propios.concat(Array.from(raiz.querySelectorAll(SELECTOR)));
  }

  // Campos que la cola necesita, tomados de los atributos del formulario
  // (sirven también al service worker cuando el envío normal falla).
  function camposInternos(form) {
    const campos = { _tipo_operacion: form.dataset.offlineTipo, _volver: form.dataset.offlineVolver || location.pathname };
    if (form.dataset.offline === "no") campos._offline_no = "1";
    return campos;
  }

  function prepararFormularios(raiz) {
    formulariosEn(raiz).forEach((form) => {
      if (form.dataset.offlineListo) return;
      form.dataset.offlineListo = "1";
      Object.entries(camposInternos(form)).forEach(([nombre, valor]) => {
        const input = document.createElement("input");
        input.type = "hidden"; input.name = nombre; input.value = valor;
        form.appendChild(input);
      });
    });
  }

  async function encolarFormulario(form) {
    try {
      const datos = new FormData(form);
      Object.entries(camposInternos(form)).forEach(([nombre, valor]) => datos.set(nombre, valor));
      const operaciones = PaegoCola.operacionesDesdeFormulario(datos, cfg.usuarioId);
      for (const op of operaciones) await PaegoCola.encolar(op);
      avisar(
        (operaciones.length > 1 ? operaciones.length + " envíos guardados" : "Guardado") +
          " sin conexión. Se enviará automáticamente al recuperar internet."
      );
      if (form.closest("#panel") && window.Alpine) Alpine.store("panel").cerrar();
      else form.reset();
    } catch (error) {
      avisar(error.message, "error");
    }
    refrescarEstado();
  }

  // Fase de captura: se adelanta a HTMX y al envío normal del navegador.
  document.addEventListener(
    "submit",
    (e) => {
      const form = e.target;
      if (navigator.onLine || !form.matches("form[data-offline-tipo]")) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      encolarFormulario(form);
    },
    true
  );

  async function iniciar() {
    const csrf = cookie("csrftoken");
    if (csrf) await PaegoCola.guardarConfig("csrf", csrf);
    // El service worker los usa para encolar y sincronizar en segundo plano.
    await PaegoCola.guardarConfig("usuario", cfg.usuarioId);
    await PaegoCola.guardarConfig("urlLote", cfg.urlLote);
    prepararFormularios();
    if (window.htmx) htmx.onLoad((raiz) => prepararFormularios(raiz));

    if ("serviceWorker" in navigator) {
      try {
        const registro = await navigator.serviceWorker.register("/sw.js");
        navigator.serviceWorker.addEventListener("message", (e) => {
          if (e.data && e.data.tipo === "cola-actualizada") refrescarEstado();
        });
        window.addEventListener("online", () => {
          if (registro.sync) registro.sync.register("paego-sincronizar").catch(() => {});
        });
      } catch (e) { /* sin service worker la cola sigue funcionando */ }
    }

    window.addEventListener("online", sincronizar);
    window.addEventListener("offline", refrescarEstado);
    document.getElementById("boton-sincronizar").addEventListener("click", sincronizar);
    const dialogo = document.getElementById("dialogo-rechazadas");
    document.getElementById("ver-rechazadas").addEventListener("click", async () => {
      const lista = document.getElementById("lista-rechazadas");
      lista.innerHTML = "";
      const rechazadas = await PaegoCola.rechazadas();
      if (!rechazadas.length) {
        const li = document.createElement("li");
        li.textContent = "No hay operaciones rechazadas.";
        lista.appendChild(li);
      }
      rechazadas.forEach((r) => {
        const li = document.createElement("li");
        li.textContent = r.tipo + " (" + new Date(r.ocurrido_en).toLocaleString("es-CO") + "): " + JSON.stringify(r.motivo);
        lista.appendChild(li);
      });
      dialogo.showModal();
    });
    document.getElementById("limpiar-rechazadas").addEventListener("click", async () => {
      await PaegoCola.limpiarRechazadas();
      dialogo.close();
      refrescarEstado();
    });

    // Al cerrar sesión se borra la caché de páginas (datos del panel en el equipo).
    document.querySelectorAll('form[action$="/salir/"]').forEach((f) =>
      f.addEventListener("submit", () => { if (window.caches) { caches.delete("paego-paginas"); caches.delete("paego-parciales"); } })
    );

    await sincronizar();
    setInterval(sincronizar, 30000);
  }

  iniciar();
})();
