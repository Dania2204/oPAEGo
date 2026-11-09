/* PAEGo — comportamiento general del panel: panel lateral, atajos y avisos. */
(function () {
  "use strict";
  const cfg = window.PAEGO || {};

  /* ---------- panel lateral (store de Alpine) ---------- */
  document.addEventListener("alpine:init", () => {
    Alpine.store("panel", {
      abierto: false,
      abrir() {
        this.abierto = true;
      },
      cerrar() {
        if (!this.abierto) return;
        this.abierto = false;
        document.querySelectorAll("tr.seleccionada").forEach((f) => f.classList.remove("seleccionada"));
        // La URL vuelve a la de la página (el panel había publicado la suya).
        const base = document.body.dataset.urlBase;
        if (base && location.pathname + location.search !== base) history.pushState({}, "", base);
        setTimeout(() => { const c = document.getElementById("panel-contenido"); if (c && !this.abierto) c.innerHTML = ""; }, 200);
      },
    });
  });

  const panel = () => window.Alpine && Alpine.store("panel");

  document.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target.id === "panel-contenido") {
      panel() && panel().abrir();
      const titulo = e.detail.target.querySelector("h2");
      if (titulo) { titulo.setAttribute("tabindex", "-1"); titulo.focus({ preventScroll: true }); }
    }
  });

  // Fila seleccionada en tablas que abren el panel.
  document.addEventListener("htmx:beforeRequest", (e) => {
    const fila = e.detail.elt.closest && e.detail.elt.closest("tr.clic");
    if (fila) {
      fila.parentElement.querySelectorAll("tr.seleccionada").forEach((f) => f.classList.remove("seleccionada"));
      fila.classList.add("seleccionada");
    }
  });

  // Eventos enviados por el servidor con HX-Trigger.
  document.body.addEventListener("cerrar-panel", () => panel() && panel().cerrar());

  // Las navegaciones normales (filtros, pestañas, paginación) actualizan la URL
  // base; las del panel no, para poder volver a ella al cerrarlo.
  let ultimaFuePanel = false;
  document.addEventListener("htmx:beforeSwap", (e) => {
    ultimaFuePanel = e.detail.target && e.detail.target.id === "panel-contenido";
  });
  document.addEventListener("htmx:pushedIntoHistory", (e) => {
    if (!ultimaFuePanel && e.detail.path) document.body.dataset.urlBase = e.detail.path;
  });

  // Errores de red de HTMX: aviso visible en lugar de no hacer nada.
  document.addEventListener("htmx:sendError", () => avisar("Sin conexión con el servidor. Se muestra la última información disponible.", "error"));
  document.addEventListener("htmx:responseError", (e) => {
    if (e.detail.xhr.status === 401 || e.detail.xhr.status === 403) { location.href = cfg.urlLogin + "?next=" + encodeURIComponent(location.pathname); return; }
    avisar("No se pudo completar la acción (error " + e.detail.xhr.status + ").", "error");
  });

  // Zonas que se recargan con la URL actual de la página cuando el servidor
  // avisa un cambio (p. ej. data-refrescar="envios-actualizados").
  ["envios-actualizados", "catalogo-actualizado", "usuarios-actualizados"].forEach((evento) =>
    document.body.addEventListener(evento, () => {
      document.querySelectorAll('[data-refrescar="' + evento + '"]').forEach((zona) => {
        const url = document.body.dataset.urlBase || location.pathname + location.search;
        htmx.ajax("GET", url, { target: zona, swap: "innerHTML" });
      });
    })
  );

  /* ---------- avisos ---------- */
  function avisar(texto, tipo) {
    const zona = document.getElementById("avisos");
    if (!zona) return;
    const div = document.createElement("div");
    div.className = "aviso " + (tipo || "");
    div.setAttribute("role", "status");
    div.dataset.autoCerrar = "";
    const span = document.createElement("span");
    span.textContent = texto;
    const cerrar = document.createElement("button");
    cerrar.type = "button"; cerrar.textContent = "×"; cerrar.setAttribute("aria-label", "Cerrar aviso");
    cerrar.onclick = () => div.remove();
    div.append(span, cerrar);
    zona.appendChild(div);
    programarCierre(div);
  }
  function programarCierre(el) {
    if (el.classList.contains("error")) return; // los errores se cierran a mano
    setTimeout(() => el.remove(), 6000);
  }
  window.PaegoAvisar = avisar;
  function revisarAvisos(raiz) {
    (raiz || document).querySelectorAll("[data-auto-cerrar]").forEach((el) => {
      if (el.dataset.programado) return;
      el.dataset.programado = "1";
      programarCierre(el);
    });
  }
  document.addEventListener("DOMContentLoaded", () => revisarAvisos());
  document.addEventListener("htmx:oobAfterSwap", () => revisarAvisos());
  document.addEventListener("htmx:afterSettle", () => revisarAvisos());

  /* ---------- atajos de teclado ---------- */
  function escribiendo(e) {
    const t = e.target;
    return t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName);
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && panel() && panel().abierto && !document.querySelector("dialog[open]")) {
      panel().cerrar();
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey || escribiendo(e)) return;
    if (e.key === "/") {
      const buscar = document.querySelector("[data-buscar]");
      if (buscar) { e.preventDefault(); buscar.focus(); buscar.select && buscar.select(); }
    } else if (e.key === "n" && cfg.urlNuevoEnvio) {
      e.preventDefault();
      htmx.ajax("GET", cfg.urlNuevoEnvio, { target: "#panel-contenido" }).then(() => history.pushState({}, "", cfg.urlNuevoEnvio));
    } else if (e.key === "p" && cfg.urlProgramar) {
      location.href = cfg.urlProgramar;
    } else if (e.key === "?") {
      const d = document.getElementById("dialogo-atajos");
      if (d) d.showModal();
    }
  });

  /* ---------- editor de alimentos (envío y programación) ---------- */
  htmxListo(() =>
    htmx.onLoad((raiz) => {
      const propios = raiz.matches && raiz.matches("[data-items]") ? [raiz] : [];
      propios.concat(Array.from(raiz.querySelectorAll("[data-items]"))).forEach((editor) => {
        if (editor.dataset.listo) return;
        editor.dataset.listo = "1";
        const cuerpo = editor.querySelector("tbody");
        const plantilla = editor.querySelector("template");
        const agregar = () => {
          cuerpo.appendChild(plantilla.content.cloneNode(true));
          const ultimo = cuerpo.lastElementChild && cuerpo.lastElementChild.querySelector("input");
          return ultimo;
        };
        editor.querySelector("[data-agregar]").addEventListener("click", () => { const i = agregar(); if (i) i.focus(); });
        cuerpo.addEventListener("click", (e) => {
          if (e.target.closest("[data-quitar]") && cuerpo.rows.length > 1) e.target.closest("tr").remove();
        });
        if (!cuerpo.rows.length) agregar();

        /* RF-14: sugerir una fila "Ración escolar" con los beneficiarios de la
           institución elegida. Reutiliza una fila vacía y no pisa otros alimentos. */
        const form = editor.closest("form");
        const sel = form && form.querySelector("select[name=institucion]");
        if (sel && editor.dataset.raciones) {
          let mapa = {};
          try { mapa = JSON.parse(editor.dataset.raciones); } catch (_) { mapa = {}; }
          let filaRacion = null;
          sel.addEventListener("change", () => {
            const n = mapa[sel.value];
            if (!n) return;
            if (!filaRacion || !cuerpo.contains(filaRacion)) {
              filaRacion = Array.from(cuerpo.rows).find((r) => {
                const p = r.querySelector("[name=item_producto]");
                const c = r.querySelector("[name=item_cantidad]");
                return p && !p.value.trim() && c && !c.value;
              });
              if (!filaRacion) { agregar(); filaRacion = cuerpo.lastElementChild; }
              filaRacion.querySelector("[name=item_producto]").value = "Ración escolar";
              const u = filaRacion.querySelector("[name=item_unidad]");
              if (u) u.value = "RACION";
            }
            filaRacion.querySelector("[name=item_cantidad]").value = n;
          });
        }
      });
    })
  );

  function htmxListo(fn) {
    if (window.htmx) fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }
})();
