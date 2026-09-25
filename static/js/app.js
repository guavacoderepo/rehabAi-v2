/* RehadAI — client-side behaviour.
   Everything here is presentation only. All scoring, prediction and
   persistence happen server-side in model.py / app.py. */

(function () {
  "use strict";

  /* ---------------------------------------------------------------
     Sparklines on the patient list.
     Each row carries its WPI history in data-trend="12,18,25,..."
     --------------------------------------------------------------- */
  function drawSparklines() {
    document.querySelectorAll("[data-trend]").forEach(function (box) {
      var v = box.dataset.trend.split(",").map(Number);

      if (v.length < 2) return;

      var w = 110,
          h = 34,
          mn = Math.min.apply(null, v),
          mx = Math.max.apply(null, v),
          r = (mx - mn) || 1;

      var pts = v.map(function (x, i) {
        return [
          i / (v.length - 1) * w,
          h - 3 - ((x - mn) / r) * (h - 8)
        ];
      });

      var d = pts.map(function (q, i) {
        return (i ? "L" : "M") +
          q[0].toFixed(1) +
          " " +
          q[1].toFixed(1);
      }).join(" ");

      var up = v[v.length - 1] >= v[0];
      var c = up ? "var(--good)" : "var(--bad)";

      box.innerHTML =
        '<svg width="' + w + '" height="' + h + '" style="overflow:visible">' +
        '<path d="' +
        d +
        " L " +
        w +
        " " +
        h +
        " L 0 " +
        h +
        '" fill="' +
        c +
        '" opacity=".08"/>' +

        '<path d="' +
        d +
        '" fill="none" stroke="' +
        c +
        '" stroke-width="2.2" ' +
        'stroke-linecap="round" stroke-linejoin="round"/>' +

        '<circle cx="' +
        pts[pts.length - 1][0] +
        '" cy="' +
        pts[pts.length - 1][1] +
        '" r="3.4" fill="' +
        c +
        '"/></svg>';
    });
  }


  /* ---------------------------------------------------------------
     Progress chart on the patient record.
     Data comes from <div id="chartbox" data-chart='[...]'>
     --------------------------------------------------------------- */
  var chartState = {
    metric: "wpi"
  };


  function drawChart() {
    var box = document.getElementById("chartbox");

    if (!box) return;

    var data = JSON.parse(box.dataset.chart || "[]");

    if (!data.length) return;

    var key = chartState.metric,
        pct = key === "walk" || key === "risk",
        W = 1000,
        H = 290,
        P = {
          l: 44,
          r: 18,
          t: 16,
          b: 32
        },
        vals = data.map(function (d) {
          return d[key];
        }),
        mn = pct ? 0 : Math.min.apply(null, vals),
        mx = pct ? 100 : Math.max.apply(null, vals);


    if (!pct) {
      var pad = Math.max(
        4,
        (mx - mn) * 0.25
      );

      mn = Math.max(
        0,
        mn - pad
      );

      mx = mx + pad;
    }


    var X = function (i) {
      return P.l +
        (data.length < 2
          ? 0.5
          : i / (data.length - 1)
        ) *
        (W - P.l - P.r);
    };


    var Y = function (v) {
      return P.t +
        (1 - (v - mn) / ((mx - mn) || 1)) *
        (H - P.t - P.b);
    };


    var col =
      key === "risk"
        ? "var(--bad)"
        : "var(--pink)";


    var grid = "";

    for (var i = 0; i <= 4; i++) {
      var v =
        mn +
        (mx - mn) * i / 4;

      var y = Y(v);

      grid +=
        '<line x1="' +
        P.l +
        '" y1="' +
        y +
        '" x2="' +
        (W - P.r) +
        '" y2="' +
        y +
        '" stroke="var(--line)" stroke-width="1"/>' +

        '<text x="' +
        (P.l - 10) +
        '" y="' +
        (y + 4) +
        '" text-anchor="end" ' +
        'font-size="12" fill="var(--ink-3)" ' +
        'font-family="Instrument Sans">' +

        (
          pct
            ? Math.round(v) + "%"
            : Math.round(v)
        ) +

        "</text>";
    }


    var line = data.map(function (d, i) {
      return (
        i ? "L" : "M"
      ) +
        X(i).toFixed(1) +
        " " +
        Y(d[key]).toFixed(1);
    }).join(" ");


    var area =
      line +
      " L " +
      X(data.length - 1).toFixed(1) +
      " " +
      (H - P.b) +
      " L " +
      X(0).toFixed(1) +
      " " +
      (H - P.b) +
      " Z";


    var dots = data.map(function (d, i) {
      return (
        '<circle cx="' +
        X(i) +
        '" cy="' +
        Y(d[key]) +
        '" r="6" fill="#fff" stroke="' +
        col +
        '" stroke-width="3"/>'
      );
    }).join("");


    var labels = data.map(function (d, i) {
      return (
        '<text x="' +
        X(i) +
        '" y="' +
        (H - 8) +
        '" text-anchor="middle" font-size="12" ' +
        'fill="var(--ink-3)" font-family="Instrument Sans">' +
        d.label +
        "</text>"
      );
    }).join("");


    var hits = data.map(function (d, i) {
      return (
        '<rect x="' +
        (X(i) - 26) +
        '" y="0" width="52" height="' +
        H +
        '" fill="transparent" data-i="' +
        i +
        '"/>'
      );
    }).join("");


    box.innerHTML =
      '<svg viewBox="0 0 ' +
      W +
      " " +
      H +
      '" preserveAspectRatio="none" ' +
      'style="height:290px;overflow:visible">' +

      '<defs>' +
      '<linearGradient id="gr" x1="0" y1="0" x2="0" y2="1">' +

      '<stop offset="0%" stop-color="' +
      col +
      '" stop-opacity=".2"/>' +

      '<stop offset="100%" stop-color="' +
      col +
      '" stop-opacity="0"/>' +

      '</linearGradient>' +
      '</defs>' +

      grid +

      '<path d="' +
      area +
      '" fill="url(#gr)"/>' +

      '<path d="' +
      line +
      '" fill="none" stroke="' +
      col +
      '" stroke-width="3.2" ' +
      'stroke-linecap="round" stroke-linejoin="round"/>' +

      dots +
      labels +
      hits +

      '</svg>' +

      '<div class="tt" id="tt"></div>';


    var tt = document.getElementById("tt");


    box.querySelectorAll("rect[data-i]").forEach(function (r) {

      r.addEventListener("mouseenter", function () {

        var i = +r.dataset.i,
            d = data[i],
            rect = box.getBoundingClientRect();


        tt.innerHTML =
          "<b>" +
          (
            pct
              ? d[key].toFixed(1) + "%"
              : d[key]
          ) +
          "</b>" +

          d.long +

          '<br><span style="opacity:.75">' +
          "Walking " +
          d.walk.toFixed(1) +
          "% · Risk " +
          d.risk.toFixed(1) +
          "/10</span>";


        tt.style.left =
          (X(i) / W * rect.width) +
          "px";


        tt.style.top =
          (Y(d[key]) / H * 290) +
          "px";


        tt.classList.add("on");
      });


      r.addEventListener("mouseleave", function () {
        tt.classList.remove("on");
      });

    });
  }


  /* ---------------------------------------------------------------
     Metric toggle on patient progress chart
     --------------------------------------------------------------- */
  function bindMetricToggle() {

    var seg =
      document.getElementById("metricSeg");

    if (!seg) return;


    seg.addEventListener("click", function (e) {

      var b =
        e.target.closest("button[data-metric]");

      if (!b) return;


      chartState.metric =
        b.dataset.metric;


      seg.querySelectorAll("button").forEach(function (x) {

        x.classList.toggle(
          "on",
          x === b
        );

      });


      document.querySelectorAll("[data-hint]").forEach(function (h) {

        h.classList.toggle(
          "hide",
          h.dataset.hint !== chartState.metric
        );

      });


      drawChart();

    });
  }


  /* ---------------------------------------------------------------
     Prediction history: expand / collapse
     --------------------------------------------------------------- */
  function bindTimeline() {

    document.querySelectorAll(".ehead").forEach(function (h) {

      h.addEventListener("click", function () {

        h.closest(".entry").classList.toggle(
          "open"
        );

      });

    });

  }


  /* ---------------------------------------------------------------
     Prediction form: live progress tracking, domain status,
     answer text
     --------------------------------------------------------------- */
  function bindForm() {

    var form =
      document.getElementById("predictForm");

    if (!form) return;


    var total =
      +form.dataset.total || 28;

    var counters =
      document.querySelectorAll(".cnt");

    var progressBars =
      document.querySelectorAll(".mini i");

    var submitBtn =
      document.getElementById("submitBtn");

    var domainStatuses =
      document.querySelectorAll(".domain-filled");


    function updateProgress() {

      var answered = 0;

      var domainData = {};


      /* -----------------------------------------------------------
         Track answered questions per domain
         ----------------------------------------------------------- */
      document.querySelectorAll(".q").forEach(function (q) {

        var domain =
          q.dataset.domain;

        var checked =
          q.querySelector("input:checked");

        var ans =
          q.querySelector(".ans");


        /* Update answer text */
        if (!checked) {

          if (ans) {
            ans.textContent =
              "⚠️ Not answered yet";

            ans.classList.add("empty");
          }

        } else {

          answered++;


          if (ans) {
            ans.textContent =
              checked.dataset.anchor ||
              checked.value;

            ans.classList.remove("empty");
          }

        }


        /* Track domain progress */
        if (!domainData[domain]) {

          domainData[domain] = {
            total: 0,
            filled: 0
          };

        }


        domainData[domain].total += 1;


        if (checked) {
          domainData[domain].filled += 1;
        }

      });


      var percent =
        (answered / total) * 100;


      /* -----------------------------------------------------------
         Update all counters
         ----------------------------------------------------------- */
      counters.forEach(function (counter) {

        counter.textContent =
          answered +
          " of " +
          total +
          " answered";

      });


      /* -----------------------------------------------------------
         Update all progress bars
         ----------------------------------------------------------- */
      progressBars.forEach(function (bar) {

        bar.style.width =
          percent + "%";


        if (answered === total) {

          bar.style.background =
            "var(--good)";

          bar.classList.add(
            "complete"
          );

        } else {

          bar.style.background =
            "var(--pink)";

          bar.classList.remove(
            "complete"
          );

        }

      });


      /* -----------------------------------------------------------
         Update domain statuses
         ----------------------------------------------------------- */
      domainStatuses.forEach(function (status) {

        var sec =
          status.closest(".sec");

        if (!sec) return;


        var heading =
          sec.querySelector("h2");

        if (!heading) return;


        var domainId =
          heading.textContent.trim();


        var domainMap = {

          "Mobility": "mob",

          "ADL": "adl",

          "Cognitive / Communicative": "cog",

          "Physical Impairment": "phys"

        };


        var key =
          domainMap[domainId] ||
          domainId.toLowerCase();


        if (domainData[key]) {

          status.textContent =
            domainData[key].filled;

        }

      });


      /* -----------------------------------------------------------
         Enable / disable submit button
         ----------------------------------------------------------- */
      if (submitBtn) {

        submitBtn.disabled =
          answered < total;

      }


      /* -----------------------------------------------------------
         Update sticky footer if it exists
         ----------------------------------------------------------- */
      var foot =
        document.getElementById("foot");


      if (foot) {

        var cnt =
          foot.querySelector(".cnt");


        var mini =
          foot.querySelector(".mini i");


        if (cnt) {

          cnt.textContent =
            answered +
            " of " +
            total +
            " answered";

        }


        if (mini) {

          mini.style.width =
            percent + "%";


          if (answered === total) {

            mini.style.background =
              "var(--good)";

          } else {

            mini.style.background =
              "var(--pink)";

          }

        }


        var submit =
          foot.querySelector(".submit");


        if (submit) {

          submit.disabled =
            answered < total;

        }

      }

    }


    /* -----------------------------------------------------------
       Listen for changes on all radio buttons
       ----------------------------------------------------------- */
    form.querySelectorAll(
      'input[type="radio"]'
    ).forEach(function (radio) {

      radio.addEventListener(
        "change",
        updateProgress
      );

    });


    /* Initial update */
    updateProgress();

  }


  /* ---------------------------------------------------------------
     Domain status update helper
     --------------------------------------------------------------- */
  function updateDomainStatuses() {

    var domainData = {};


    document.querySelectorAll(".q").forEach(function (q) {

      var domain =
        q.dataset.domain;

      var checked =
        q.querySelector("input:checked");


      if (!domainData[domain]) {

        domainData[domain] = {
          total: 0,
          filled: 0
        };

      }


      domainData[domain].total += 1;


      if (checked) {

        domainData[domain].filled += 1;

      }

    });


    document.querySelectorAll(
      ".domain-filled"
    ).forEach(function (status) {

      var sec =
        status.closest(".sec");

      if (!sec) return;


      var heading =
        sec.querySelector("h2");

      if (!heading) return;


      var domainId =
        heading.textContent.trim();


      var domainMap = {

        "Mobility": "mob",

        "ADL": "adl",

        "Cognitive / Communicative": "cog",

        "Physical Impairment": "phys"

      };


      var key =
        domainMap[domainId] ||
        domainId.toLowerCase();


      if (domainData[key]) {

        status.textContent =
          domainData[key].filled;

      }

    });

  }


  /* ---------------------------------------------------------------
     Clear all prefilled values
     --------------------------------------------------------------- */
  function bindClearAll() {

    var clearLink =
      document.querySelector(".tipbar a");


    if (!clearLink) return;


    clearLink.addEventListener(
      "click",
      function (e) {

        e.preventDefault();


        document.querySelectorAll(
          '.q input[type="radio"]'
        ).forEach(function (radio) {

          radio.checked = false;

        });


        /* Trigger update */
        var form =
          document.getElementById(
            "predictForm"
          );


        if (form) {

          form.dispatchEvent(
            new Event("change")
          );

        }

      }
    );

  }


  /* ---------------------------------------------------------------
     Prediction result tabs
     
     Tabs:
       1. Interpretation
       2. Explore similar patients

     The HTML buttons should use:
       data-tab="interpretation"
       data-tab="similar"

     This avoids inline onclick handlers and keeps the tab logic
     inside this IIFE.
     --------------------------------------------------------------- */
function bindPredictionTabs() {
  var tabs = document.querySelectorAll(".prediction-tab");

  if (!tabs.length) return;

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {

      var target = tab.dataset.tab;

      var interpretationTab =
        document.getElementById("interpretation-tab");

      var assessmentsTab =
        document.getElementById("assessments-tab");

      var similarTab =
        document.getElementById("similar-tab");

      var interpretationPanel =
        document.getElementById("interpretation-panel");

      var assessmentsPanel =
        document.getElementById("assessments-panel");

      var similarPanel =
        document.getElementById("similar-panel");


      /*
       * Make sure all elements exist.
       */
      if (
        !interpretationTab ||
        !assessmentsTab ||
        !similarTab ||
        !interpretationPanel ||
        !assessmentsPanel ||
        !similarPanel
      ) {
        return;
      }


      /*
       * Determine which tab is active.
       */
      var showInterpretation =
        target === "interpretation";

      var showAssessments =
        target === "assessments";

      var showSimilar =
        target === "similar";


      /*
       * Update active tab styling.
       */
      interpretationTab.classList.toggle(
        "active",
        showInterpretation
      );

      assessmentsTab.classList.toggle(
        "active",
        showAssessments
      );

      similarTab.classList.toggle(
        "active",
        showSimilar
      );


      /*
       * Update accessibility state.
       */
      interpretationTab.setAttribute(
        "aria-selected",
        String(showInterpretation)
      );

      assessmentsTab.setAttribute(
        "aria-selected",
        String(showAssessments)
      );

      similarTab.setAttribute(
        "aria-selected",
        String(showSimilar)
      );


      /*
       * Show the correct panel.
       */
      interpretationPanel.hidden =
        !showInterpretation;

      assessmentsPanel.hidden =
        !showAssessments;

      similarPanel.hidden =
        !showSimilar;

    });
  });


  /*
   * Set the initial state.
   */
  var interpretationPanel =
    document.getElementById("interpretation-panel");

  var assessmentsPanel =
    document.getElementById("assessments-panel");

  var similarPanel =
    document.getElementById("similar-panel");


  if (interpretationPanel) {
    interpretationPanel.hidden = false;
  }

  if (assessmentsPanel) {
    assessmentsPanel.hidden = true;
  }

  if (similarPanel) {
    similarPanel.hidden = true;
  }
}


function bindMeasureTabs() {
  var tabs = document.querySelectorAll(".assessment-measure-tab");
  var contents = document.querySelectorAll(".assessment-measure-content");

  if (!tabs.length || !contents.length) return;

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {

      var target = tab.dataset.measureTab;

      tabs.forEach(function (item) {
        item.classList.toggle("active", item === tab);
      });

      contents.forEach(function (content) {
        var isActive =
          content.dataset.measureContent === target;

        content.hidden = !isActive;
        content.classList.toggle("active", isActive);
      });

    });
  });
}


  /* ---------------------------------------------------------------
     Initialise all client-side behaviour
     --------------------------------------------------------------- */

  document.addEventListener("DOMContentLoaded", function () {
  drawSparklines();
  bindMetricToggle();
  drawChart();
  bindTimeline();
  bindForm();
  bindClearAll();
  bindPredictionTabs();
  bindMeasureTabs();
});

})();