/* PAEGo — animaciones de la página pública.
 *
 * Mejora progresiva: sin este script (o sin GSAP, o con movimiento reducido) la
 * página se ve completa y estática.
 */
(function () {
  "use strict";

  var reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --------------------------------------------------- pasos: medio activo
  var pasos = Array.prototype.slice.call(document.querySelectorAll("[data-paso]"));
  var medios = document.querySelectorAll("[data-medio]");

  function activar(n) {
    pasos.forEach(function (p) { p.classList.toggle("activo", p.dataset.paso === n); });
    medios.forEach(function (m) { m.classList.toggle("activo", m.dataset.medio === n); });
  }

  // ------------------------------------------------- cabecera que se compacta
  var cabecera = document.querySelector("[data-cabecera]");
  function revisarCabecera() {
    if (cabecera) cabecera.classList.toggle("compacta", window.scrollY > 24);
  }
  window.addEventListener("scroll", revisarCabecera, { passive: true });
  revisarCabecera();

  // ------------------------------------------- video: botón de reproducir
  var video = document.querySelector("[data-video-principal] video");
  var play = document.querySelector("[data-video-play]");
  if (video && play) {
    // Mientras no se reproduce, solo el botón: los controles nativos lo tapaban.
    play.hidden = false;
    video.controls = false;
    play.addEventListener("click", function () { video.controls = true; video.play(); });
    video.addEventListener("play", function () { play.hidden = true; video.controls = true; });
    video.addEventListener("ended", function () { play.hidden = false; video.controls = false; });
  }

  // ------------------------------------------- sin GSAP: pasos con observer
  function pasosSinGsap() {
    if (!("IntersectionObserver" in window)) return;
    var obs = new IntersectionObserver(
      function (entradas) {
        entradas.forEach(function (e) {
          if (e.isIntersecting) activar(e.target.dataset.paso);
        });
      },
      { rootMargin: "-45% 0px -45% 0px" }
    );
    pasos.forEach(function (p) { obs.observe(p); });
  }

  // ------------------------------------------------------- con GSAP
  function animar() {
    var gsap = window.gsap;
    var ScrollTrigger = window.ScrollTrigger;
    if (reducido || !gsap || !ScrollTrigger) {
      document.documentElement.classList.remove("l-anima");
      pasosSinGsap();
      return;
    }
    gsap.registerPlugin(ScrollTrigger);

    // Titular por líneas.
    gsap.to(".l-titular .linea > span", {
      y: 0, duration: 0.9, ease: "power3.out", stagger: 0.12, delay: 0.1,
    });

    // Revelados al entrar en pantalla (en grupos, para que fluyan juntos).
    ScrollTrigger.batch("[data-revelar]", {
      start: "top 88%",
      once: true,
      onEnter: function (lote) {
        gsap.to(lote, { opacity: 1, y: 0, duration: 0.8, ease: "power2.out", stagger: 0.08 });
      },
    });

    // Parallax suave de la foto del hero.
    var foto = document.querySelector("[data-parallax]");
    if (foto) {
      gsap.fromTo(foto, { yPercent: -6 }, {
        yPercent: 4, ease: "none",
        scrollTrigger: { trigger: ".l-hero", start: "top top", end: "bottom top", scrub: true },
      });
    }

    // Contadores.
    document.querySelectorAll("[data-cifra]").forEach(function (dd) {
      var meta = parseInt(dd.dataset.cifra, 10) || 0;
      var estado = { n: 0 };
      var formato = new Intl.NumberFormat("es-CO");
      ScrollTrigger.create({
        trigger: dd, start: "top 90%", once: true,
        onEnter: function () {
          gsap.to(estado, {
            n: meta, duration: 1.6, ease: "power2.out",
            onUpdate: function () { dd.textContent = formato.format(Math.round(estado.n)); },
          });
        },
      });
    });

    // Pasos: el medio fijo cambia según el paso que cruza el centro.
    pasos.forEach(function (p) {
      ScrollTrigger.create({
        trigger: p, start: "top 55%", end: "bottom 55%",
        onToggle: function (st) { if (st.isActive) activar(p.dataset.paso); },
      });
    });
    var barra = document.querySelector("[data-progreso]");
    if (barra) {
      gsap.to(barra, {
        scaleY: 1, ease: "none",
        scrollTrigger: { trigger: ".l-pasos-lista", start: "top 55%", end: "bottom 55%", scrub: true },
      });
    }

    // El video principal crece levemente al entrar.
    var marco = document.querySelector("[data-video-principal]");
    if (marco) {
      gsap.fromTo(marco, { scale: 0.94 }, {
        scale: 1, ease: "none",
        scrollTrigger: { trigger: marco, start: "top bottom", end: "top 35%", scrub: true },
      });
    }
  }

  // Los scripts son `defer`: GSAP ya está cargado (o falló) cuando corre esto.
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", animar);
  else animar();
})();
