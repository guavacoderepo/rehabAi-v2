/* RehabAI — charts.
   Every chart is declared in a template as
     <canvas data-chart="gauge" data-config='{...}'>
   and built here with Chart.js. Colours are passed as design-token names
   ("pink", "good", "warn"...) and resolved from the CSS variables, so the
   charts always match style.css. */

(function () {
  "use strict";

  if (!window.Chart) return;

  var styles = getComputedStyle(document.documentElement);

  function token(name) {
    if (!name) return undefined;
    if (name.charAt(0) === "#" || name.indexOf("rgb") === 0) return name;
    return styles.getPropertyValue("--" + name).trim() || name;
  }

  function alpha(color, a) {
    var hex = token(color).replace("#", "");
    if (hex.length !== 6) return token(color);
    var n = parseInt(hex, 16);
    return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
  }

  function fmt(value, decimals, unit) {
    if (value === null || value === undefined) return "—";
    return Number(value).toFixed(decimals === undefined ? 1 : decimals) + (unit || "");
  }

  function shortDate(iso) {
    return new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  }

  function longDate(iso) {
    return new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  }

  /* ---------- Global defaults ---------- */

  Chart.defaults.font.family = token("sans");
  Chart.defaults.font.size = 12;
  Chart.defaults.color = token("ink-3");
  Chart.defaults.borderColor = token("border");
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.tooltip.backgroundColor = "#252525";
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;

  /* Text in the middle of doughnuts / gauges. */
  Chart.register({
    id: "centerText",
    afterDraw: function (chart, _args, opts) {
      if (!opts || opts.text === undefined || opts.text === null) return;

      var meta = chart.getDatasetMeta(chart.data.datasets.length - 1);
      var arc = meta && meta.data[0];
      if (!arc) return;

      var ctx = chart.ctx;
      var sans = token("sans");
      // Half gauges: keep both lines above the flat bottom edge.
      var y = opts.half ? arc.y - (opts.sub ? 24 : 6) : arc.y + (opts.sub ? -6 : 4);

      ctx.save();
      ctx.textAlign = "center";
      ctx.fillStyle = token(opts.color || "ink-1");
      ctx.font = "600 " + (opts.size || 26) + "px " + sans;
      ctx.fillText(opts.text, arc.x, y);

      if (opts.sub) {
        ctx.font = "600 11.5px " + sans;
        ctx.fillStyle = token(opts.subColor || "ink-3");
        ctx.fillText(opts.sub, arc.x, y + 19);
      }
      ctx.restore();
    }
  });

  /* ---------- Builders ---------- */

  var builders = {};

  /* Half-circle gauge meter. Optional coloured band ring on the outside. */
  builders.gauge = function (canvas, cfg) {
    var max = cfg.max || 100;
    var raw = cfg.value === null || cfg.value === undefined ? null : Number(cfg.value);
    var value = raw === null ? 0 : Math.min(Math.max(raw, 0), max);
    var datasets = [];

    if (cfg.bands) {
      var previous = 0;
      datasets.push({
        data: cfg.bands.map(function (b) { var v = b.to - previous; previous = b.to; return v; }),
        backgroundColor: cfg.bands.map(function (b) { return token(b.var); }),
        borderColor: "#fff",
        borderWidth: 2,
        weight: 0.16
      });
      datasets.push({ data: [1], backgroundColor: ["transparent"], borderWidth: 0, weight: 0.1 });
    }

    datasets.push({
      data: [value, max - value],
      backgroundColor: [token(cfg.color || "pink"), token("track")],
      borderWidth: 0,
      borderRadius: 4,
      weight: 1
    });

    return new Chart(canvas, {
      type: "doughnut",
      data: { datasets: datasets },
      options: {
        rotation: -90,
        circumference: 180,
        cutout: "70%",
        events: [],
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false },
          centerText: {
            text: fmt(raw, cfg.decimals, cfg.unit),
            sub: cfg.sub || ("of " + max + (cfg.unit === "%" ? "%" : "")),
            half: true,
            size: 28
          }
        }
      }
    });
  };

  /* Doughnut with total in the centre. Legend is usually rendered in HTML. */
  builders.doughnut = function (canvas, cfg) {
    var total = cfg.values.reduce(function (a, b) { return a + b; }, 0);

    return new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: cfg.labels,
        datasets: [{
          data: cfg.values,
          backgroundColor: cfg.colors.map(token),
          borderColor: "#fff",
          borderWidth: 2,
          hoverOffset: 4
        }]
      },
      options: {
        cutout: "68%",
        plugins: {
          legend: { display: !!cfg.legend, position: "bottom" },
          centerText: { text: String(total), sub: cfg.centerLabel || "patients", size: 24 },
          tooltip: {
            callbacks: {
              label: function (c) {
                var pct = total ? Math.round(c.parsed / total * 100) : 0;
                return " " + c.label + ": " + c.parsed + " (" + pct + "%)";
              }
            }
          }
        }
      }
    });
  };

  /* Bar chart (vertical or horizontal, one or more series). */
  builders.bar = function (canvas, cfg) {
    var horizontal = !!cfg.horizontal;
    var valueAxis = {
      beginAtZero: true,
      max: cfg.max,
      grid: { color: token("border") },
      ticks: {
        precision: cfg.integer ? 0 : undefined,
        callback: function (v) { return v + (cfg.suffix || ""); }
      }
    };
    var categoryAxis = { grid: { display: false } };

    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: cfg.labels,
        datasets: cfg.datasets.map(function (d) {
          return {
            label: d.label,
            data: d.data,
            backgroundColor: token(d.color || "pink"),
            borderRadius: 5,
            maxBarThickness: horizontal ? 22 : 34
          };
        })
      },
      options: {
        indexAxis: horizontal ? "y" : "x",
        scales: horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis },
        plugins: {
          legend: { display: cfg.datasets.length > 1, position: "bottom" },
          tooltip: {
            callbacks: {
              label: function (c) {
                var v = horizontal ? c.parsed.x : c.parsed.y;
                return " " + (c.dataset.label ? c.dataset.label + ": " : "") + (v === null ? "—" : v + (cfg.suffix || ""));
              }
            }
          }
        }
      }
    });
  };

  /* Monthly trend: average WPI (left axis) and walking probability (right). */
  builders.trend = function (canvas, cfg) {
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: cfg.labels,
        datasets: [
          {
            label: "Average WPI",
            data: cfg.wpi,
            yAxisID: "y",
            borderColor: token("pink"),
            backgroundColor: alpha("pink", 0.12),
            fill: true,
            tension: 0.35,
            pointRadius: 4,
            pointBackgroundColor: "#fff",
            pointBorderWidth: 2.5
          },
          {
            label: "Average walking probability",
            data: cfg.walk,
            yAxisID: "y1",
            borderColor: token("good"),
            borderDash: [5, 4],
            tension: 0.35,
            pointRadius: 3,
            pointBackgroundColor: token("good")
          }
        ]
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, title: { display: true, text: "WPI (lower is better)" } },
          y1: {
            position: "right",
            min: 0,
            max: 100,
            grid: { display: false },
            ticks: { callback: function (v) { return v + "%"; } }
          }
        },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              afterBody: function (items) {
                var n = cfg.count[items[0].dataIndex];
                return n + " assessment" + (n === 1 ? "" : "s");
              }
            }
          }
        }
      }
    });
  };

  /* Patient progress with a WPI / Walking toggle (.seg buttons). */
  builders.progress = function (canvas, cfg) {
    var points = cfg.points;
    var metrics = {
      wpi: { key: "wpi", label: "WPI", suffix: "", color: "pink", min: undefined, max: undefined },
      walk: { key: "walk", label: "Walking probability", suffix: "%", color: "good", min: 0, max: 100 }
    };

    function dataset(m) {
      return {
        label: m.label,
        data: points.map(function (p) { return p[m.key]; }),
        borderColor: token(m.color),
        backgroundColor: alpha(m.color, 0.14),
        fill: true,
        tension: 0.3,
        borderWidth: 3,
        pointRadius: 6,
        pointHoverRadius: 7,
        pointBackgroundColor: "#fff",
        pointBorderWidth: 3
      };
    }

    var current = metrics.wpi;

    var chart = new Chart(canvas, {
      type: "line",
      data: { labels: points.map(function (p) { return shortDate(p.date); }), datasets: [dataset(current)] },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false } },
          y: { ticks: { callback: function (v) { return v + current.suffix; } } }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) { return longDate(points[items[0].dataIndex].date); },
              label: function (c) {
                var p = points[c.dataIndex];
                return [
                  " WPI " + p.wpi.toFixed(1),
                  " Walking " + p.walk.toFixed(1) + "%",
                  " Barrier " + p.barrier.toFixed(1) + "/10"
                ];
              }
            }
          }
        }
      }
    });

    var seg = cfg.toggle && document.querySelector(cfg.toggle);
    if (!seg) return chart;

    seg.addEventListener("click", function (e) {
      var button = e.target.closest("button[data-metric]");
      if (!button) return;

      current = metrics[button.dataset.metric];

      seg.querySelectorAll("button").forEach(function (b) { b.classList.toggle("on", b === button); });
      document.querySelectorAll("[data-hint]").forEach(function (h) {
        h.classList.toggle("d-none", h.dataset.hint !== current.key);
      });

      chart.data.datasets = [dataset(current)];
      chart.options.scales.y.min = current.min;
      chart.options.scales.y.max = current.max;
      chart.update();
    });

    return chart;
  };

  /* ---------- Boot ---------- */

  function init() {
    document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var build = builders[canvas.dataset.chart];
      if (!build) return;

      try {
        build(canvas, JSON.parse(canvas.dataset.config || "{}"));
      } catch (err) {
        console.error("Chart failed:", canvas.dataset.chart, err);
      }
    });
  }

  /* Charts inside hidden Bootstrap tabs need a resize once visible. */
  document.addEventListener("shown.bs.tab", function (e) {
    var pane = document.querySelector(e.target.dataset.bsTarget);
    if (!pane) return;
    pane.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var chart = Chart.getChart(canvas);
      if (chart) chart.resize();
    });
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
