/* PAEGo — tendencias semanales de los indicadores (RF-32).
 *
 * Pequeños múltiplos: un gráfico de una sola serie por indicador, en el azul
 * institucional. Sin leyenda (el título de la cifra nombra la serie), sin doble
 * eje y con tooltip al pasar el cursor. La tabla «Datos por semana» es la
 * alternativa accesible.
 */
(function () {
  "use strict";
  const graficos = [];
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function dibujar() {
    graficos.splice(0).forEach((g) => g.destroy());
    const fuente = document.getElementById("serie-indicadores");
    if (!fuente || !window.Chart) return;
    const serie = JSON.parse(fuente.textContent);
    const etiquetas = serie.map((s) => s.semana);
    const color = css("--accion");
    const rejilla = css("--borde");

    document.querySelectorAll("canvas[data-serie]").forEach((lienzo) => {
      const clave = lienzo.dataset.serie;
      const unidad = lienzo.dataset.unidad;
      const esPorcentaje = unidad === "%";
      const valores = serie.map((s) => s[clave]);
      graficos.push(
        new Chart(lienzo, {
          type: esPorcentaje ? "line" : "bar",
          data: {
            labels: etiquetas,
            datasets: [{
              data: valores,
              borderColor: color,
              backgroundColor: color,
              borderWidth: 2,
              // Con pocas semanas con datos la línea no se ve: se marcan los puntos.
              pointRadius: valores.filter((v) => v != null).length < 4 ? 3 : 0,
              pointHoverRadius: 4,
              pointBackgroundColor: color,
              spanGaps: true,
              tension: 0,
              borderRadius: 2,
              maxBarThickness: 14,
            }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: { display: false },
              tooltip: {
                displayColors: false,
                callbacks: {
                  title: (items) => "Semana del " + items[0].label,
                  label: (item) => (item.raw == null ? "Sin entregas" : item.raw + (esPorcentaje ? " %" : " novedades")),
                },
              },
            },
            layout: { padding: { top: 6, right: 6, bottom: 2, left: 2 } },
            scales: {
              x: { display: false },
              y: {
                // Las cifras exactas están en el tooltip y en «Datos por semana».
                display: true,
                min: esPorcentaje ? 0 : undefined,
                max: esPorcentaje ? 100 : undefined,
                beginAtZero: true,
                ticks: { display: false, maxTicksLimit: 3 },
                grid: { color: rejilla, drawTicks: false },
                border: { display: false },
              },
            },
          },
        })
      );
    });
  }

  document.addEventListener("DOMContentLoaded", dibujar);
  document.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target.id === "resultado-indicadores") dibujar();
  });
})();
