/* PAEGo — cola de operaciones sin conexión (RF-38 / RNF-21).
 *
 * Se usa desde la página (offline.js) y desde el service worker (sw.js):
 *  - convierte un formulario del panel en una operación de la API,
 *  - la guarda en IndexedDB con su uuid_cliente y la hora real del evento,
 *  - y la envía a /api/sincronizacion/lote/ cuando vuelve la conexión.
 * El servidor es idempotente por uuid_cliente: reenviar nunca duplica.
 */
(function (global) {
  "use strict";

  const BD = "paego-offline";
  const VERSION = 1;
  const CAMPOS_INTERNOS = ["csrfmiddlewaretoken", "uuid_cliente", "_tipo_operacion", "_volver", "_offline_no"];

  function abrir() {
    return new Promise((resolver, rechazar) => {
      const peticion = indexedDB.open(BD, VERSION);
      peticion.onupgradeneeded = () => {
        const bd = peticion.result;
        if (!bd.objectStoreNames.contains("cola")) bd.createObjectStore("cola", { keyPath: "uuid_cliente" });
        if (!bd.objectStoreNames.contains("rechazadas")) bd.createObjectStore("rechazadas", { keyPath: "uuid_cliente" });
        if (!bd.objectStoreNames.contains("config")) bd.createObjectStore("config");
      };
      peticion.onsuccess = () => resolver(peticion.result);
      peticion.onerror = () => rechazar(peticion.error);
    });
  }

  async function transaccion(almacen, modo, accion) {
    const bd = await abrir();
    return new Promise((resolver, rechazar) => {
      const tx = bd.transaction(almacen, modo);
      const resultado = accion(tx.objectStore(almacen));
      tx.oncomplete = () => resolver(resultado && "result" in resultado ? resultado.result : resultado);
      tx.onerror = () => rechazar(tx.error);
    });
  }

  const todos = (almacen) => transaccion(almacen, "readonly", (s) => s.getAll());
  const guardar = (almacen, valor) => transaccion(almacen, "readwrite", (s) => s.put(valor));
  const borrar = (almacen, clave) => transaccion(almacen, "readwrite", (s) => s.delete(clave));
  const limpiar = (almacen) => transaccion(almacen, "readwrite", (s) => s.clear());
  const leerConfig = (clave) => transaccion("config", "readonly", (s) => s.get(clave));
  const guardarConfig = (clave, valor) => transaccion("config", "readwrite", (s) => s.put(valor, clave));

  function uuid() {
    if (global.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
  }

  /* FormData del panel -> {tipo, datos}. Lanza Error con un mensaje para el
   * usuario cuando la operación no puede guardarse sin conexión. */
  function operacionDesdeFormulario(formData, usuarioId) {
    const tipo = formData.get("_tipo_operacion");
    if (!tipo) throw new Error("Este formulario no admite trabajo sin conexión.");
    if (formData.get("_offline_no")) {
      throw new Error("Crear usuarios requiere conexión: la contraseña no se guarda en el dispositivo.");
    }
    const datos = {};
    const listas = {};
    for (const [clave, valor] of formData.entries()) {
      if (CAMPOS_INTERNOS.includes(clave) || valor instanceof Blob) continue;
      if (clave.startsWith("item_")) {
        (listas[clave] = listas[clave] || []).push(valor);
        continue;
      }
      datos[clave] = valor;
    }
    if (datos.password) {
      throw new Error("Cambiar contraseñas requiere conexión: no se guardan en el dispositivo.");
    }
    delete datos.password;
    if (listas.item_producto) {
      datos.items = listas.item_producto
        .map((producto, i) => ({
          producto: producto.trim(),
          cantidad: (listas.item_cantidad || [])[i],
          unidad: (listas.item_unidad || [])[i],
        }))
        .filter((it) => it.producto || it.cantidad);
    }
    if (datos.programado_para) {
      // datetime-local (hora local del navegador) -> ISO con zona horaria.
      datos.programado_para = new Date(datos.programado_para).toISOString();
    }
    return {
      uuid_cliente: formData.get("uuid_cliente") || uuid(),
      tipo: tipo,
      ocurrido_en: new Date().toISOString(),
      datos: datos,
      usuario: usuarioId,
      volver: formData.get("_volver") || "/",
    };
  }

  /* Como operacionDesdeFormulario, pero devuelve una lista: «Programar envíos»
   * (envio.lote) se convierte en un envio.crear por institución marcada. */
  function operacionesDesdeFormulario(formData, usuarioId) {
    if (formData.get("_tipo_operacion") !== "envio.lote") {
      return [operacionDesdeFormulario(formData, usuarioId)];
    }
    const instituciones = formData.getAll("instituciones");
    if (!instituciones.length) throw new Error("Seleccione al menos una institución.");
    const fecha = formData.get("fecha");
    const hora = formData.get("hora");
    if (!fecha || !hora) throw new Error("Indique la fecha y la hora.");
    const items = [];
    const productos = formData.getAll("item_producto");
    const cantidades = formData.getAll("item_cantidad");
    const unidades = formData.getAll("item_unidad");
    productos.forEach((p, i) => {
      if (p.trim() || cantidades[i]) items.push({ producto: p.trim(), cantidad: cantidades[i], unidad: unidades[i] });
    });
    if (!items.length) throw new Error("Registre al menos un alimento del menú.");
    const ocurrido = new Date().toISOString();
    const programado = new Date(fecha + "T" + hora).toISOString();
    return instituciones.map((id) => ({
      uuid_cliente: uuid(),
      tipo: "envio.crear",
      ocurrido_en: ocurrido,
      datos: {
        institucion: id,
        conductor: formData.get("conductor_" + id),
        vehiculo: formData.get("vehiculo_" + id) || null,
        programado_para: programado,
        observaciones: formData.get("observaciones") || "",
        items: items,
      },
      usuario: usuarioId,
      volver: formData.get("_volver") || "/",
    }));
  }

  async function encolar(operacion) {
    await guardar("cola", operacion);
    return operacion;
  }

  async function pendientes(usuarioId) {
    const cola = await todos("cola");
    return cola
      .filter((op) => usuarioId == null || op.usuario === usuarioId)
      .sort((a, b) => a.ocurrido_en.localeCompare(b.ocurrido_en));
  }

  /* Envía la cola. Devuelve {enviadas, rechazadas, estado}. estado:
   * "vacia" | "ok" | "sin-conexion" | "sin-sesion" | "error". */
  let enCurso = null;
  function sincronizar(urlLote, usuarioId) {
    if (enCurso) return enCurso;
    enCurso = (async () => {
      const cola = await pendientes(usuarioId);
      if (!cola.length) return { estado: "vacia", enviadas: 0, rechazadas: 0 };
      const csrf = await leerConfig("csrf");
      let respuesta;
      try {
        respuesta = await fetch(urlLote, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf || "" },
          body: JSON.stringify({
            operaciones: cola.slice(0, 500).map((op) => ({
              uuid_cliente: op.uuid_cliente, tipo: op.tipo, ocurrido_en: op.ocurrido_en, datos: op.datos,
            })),
          }),
        });
      } catch (e) {
        return { estado: "sin-conexion", enviadas: 0, rechazadas: 0 };
      }
      if (respuesta.status === 401 || respuesta.status === 403) {
        return { estado: "sin-sesion", enviadas: 0, rechazadas: 0 };
      }
      if (!respuesta.ok) return { estado: "error", enviadas: 0, rechazadas: 0 };
      const { resultados } = await respuesta.json();
      let enviadas = 0;
      let rechazadas = 0;
      for (const r of resultados) {
        const op = cola.find((o) => o.uuid_cliente === r.uuid_cliente);
        await borrar("cola", r.uuid_cliente);
        if (r.resultado === "rechazado") {
          rechazadas += 1;
          await guardar("rechazadas", Object.assign({}, op, { motivo: r.respuesta, rechazada_en: new Date().toISOString() }));
        } else {
          enviadas += 1;
        }
      }
      return { estado: "ok", enviadas, rechazadas };
    })().finally(() => { enCurso = null; });
    return enCurso;
  }

  global.PaegoCola = {
    operacionDesdeFormulario, operacionesDesdeFormulario, encolar, pendientes, sincronizar, uuid,
    rechazadas: () => todos("rechazadas"),
    limpiarRechazadas: () => limpiar("rechazadas"),
    guardarConfig, leerConfig,
  };
})(typeof self !== "undefined" ? self : window);
