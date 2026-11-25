/* PAEGo — fotos del acceso (login): se desvanecen y aparecen una por una.
 * Mejora progresiva: sin JS queda la primera foto. Con "reducir movimiento"
 * no avanza sola, pero los puntos permiten verlas. Se pausa con la pestaña oculta. */
(function () {
  "use strict";
  const galeria = document.querySelector("[data-galeria]");
  if (!galeria) return;
  const fotos = Array.from(galeria.querySelectorAll(".acceso-foto"));
  const texto = document.querySelector("[data-leyenda-texto]");
  const num = document.querySelector("[data-num]");
  const puntos = document.querySelector("[data-puntos]");
  if (fotos.length < 2) return;

  const DURACION = 6000;
  const quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let actual = 0;
  let reloj = null;

  const botones = fotos.map((foto, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("aria-label", "Foto " + (i + 1) + " de " + fotos.length);
    b.addEventListener("click", () => { mostrar(i); programar(); });
    puntos.appendChild(b);
    return b;
  });
  puntos.hidden = false;

  function mostrar(i) {
    if (i === actual && fotos[i].classList.contains("activa")) return marcar();
    fotos[actual].classList.remove("activa");
    actual = (i + fotos.length) % fotos.length;
    const foto = fotos[actual];
    foto.classList.add("activa");
    // La leyenda también se desvanece: sale, cambia el texto y vuelve.
    texto.parentElement.classList.add("cambiando");
    setTimeout(() => {
      texto.textContent = foto.dataset.leyenda || "";
      num.textContent = String(actual + 1).padStart(2, "0");
      texto.parentElement.classList.remove("cambiando");
    }, quieto ? 0 : 350);
    marcar();
    // Precarga la siguiente para que el desvanecido no muestre un hueco.
    const sig = fotos[(actual + 1) % fotos.length].querySelector("img");
    if (sig && !sig.complete) sig.decode().catch(() => {});
  }

  function marcar() {
    botones.forEach((b, i) => b.setAttribute("aria-current", i === actual ? "true" : "false"));
  }

  function programar() {
    clearInterval(reloj);
    if (quieto || document.hidden) return;
    reloj = setInterval(() => mostrar(actual + 1), DURACION);
  }

  document.addEventListener("visibilitychange", programar);
  marcar();
  programar();
})();
