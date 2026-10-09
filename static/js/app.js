/* RehabAI — page behaviour.
   Presentation only: all scoring, prediction and storage happen server-side.
   Tabs, collapses, dropdowns and modals come from Bootstrap. */

(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /* ---------------------------------------------------------------
     Clickable table rows: <tr data-href="...">
     --------------------------------------------------------------- */
  function bindRowLinks() {
    document.addEventListener("click", function (e) {
      var row = e.target.closest("tr[data-href]");
      if (!row || e.target.closest("a, button, input, select, label")) return;
      window.location.href = row.dataset.href;
    });

    document.addEventListener("keydown", function (e) {
      var row = e.target.closest && e.target.closest("tr[data-href]");
      if (row && e.key === "Enter") window.location.href = row.dataset.href;
    });
  }

  /* ---------------------------------------------------------------
     Selects marked data-autosubmit submit their form on change
     (hospital picker, sort order).
     --------------------------------------------------------------- */
  function bindAutoSubmit() {
    document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
      el.addEventListener("change", function () {
        if (el.form) el.form.submit();
      });
    });
  }

  /* ---------------------------------------------------------------
     New assessment form
     --------------------------------------------------------------- */
  function bindPredictForm() {
    var form = document.getElementById("predictForm");
    if (!form) return;

    var total = Number(form.dataset.total) || 28;
    var questions = Array.prototype.slice.call(form.querySelectorAll(".q"));
    var countEl = document.getElementById("answeredCount");
    var trackEl = document.getElementById("answeredTrack");
    var reviewBtn = document.getElementById("reviewBtn");
    var modalEl = document.getElementById("previewModal");
    var confirmBtn = document.getElementById("confirmSubmit");
    var modal = modalEl && window.bootstrap ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;

    function answeredCount() {
      return questions.filter(function (q) { return q.querySelector("input:checked"); }).length;
    }

    function isComplete() {
      return answeredCount() === total && !!form.querySelector('input[name="walking_status"]:checked');
    }

    function updateProgress() {
      var perDomain = {};

      questions.forEach(function (q) {
        var checked = q.querySelector("input:checked");
        var ans = q.querySelector(".ans");
        var domain = q.dataset.domain;

        perDomain[domain] = (perDomain[domain] || 0) + (checked ? 1 : 0);

        if (ans) {
          ans.textContent = checked ? (checked.dataset.anchor || checked.value) : "Not answered yet";
          ans.classList.toggle("empty", !checked);
        }
      });

      var answered = answeredCount();

      if (countEl) countEl.textContent = answered + " of " + total + " answered";

      if (trackEl) {
        trackEl.style.width = (answered / total * 100) + "%";
        trackEl.parentElement.classList.toggle("good", answered === total);
      }

      document.querySelectorAll(".domain-filled[data-domain]").forEach(function (el) {
        el.textContent = perDomain[el.dataset.domain] || 0;
      });

      if (reviewBtn) reviewBtn.disabled = !isComplete();
    }

    /* ---------- Preview modal ---------- */

    function domainAttainment(items) {
      var got = 0;
      var span = 0;

      items.forEach(function (it) {
        var range = it.max - it.min;
        got += it.dir > 0 ? it.value - it.min : it.max - it.value;
        span += range;
      });

      return span ? Math.round(got / span * 100) : 0;
    }

    function buildPreview() {
      var dateInput = form.querySelector('[name="assessed_on"]');
      var walking = form.querySelector('input[name="walking_status"]:checked');
      var html = "";

      form.querySelectorAll(".domain-block").forEach(function (block) {
        var items = [];
        var rows = "";

        block.querySelectorAll(".q").forEach(function (q) {
          var checked = q.querySelector("input:checked");
          if (!checked) return;

          var item = {
            value: Number(checked.value),
            min: Number(q.dataset.min),
            max: Number(q.dataset.max),
            dir: Number(q.dataset.dir)
          };
          items.push(item);

          rows +=
            "<tr>" +
            "<td>" + escapeHtml(q.dataset.label) + ' <span class="text-ink-3 small">' + escapeHtml(q.dataset.tag) + "</span></td>" +
            '<td class="val">' + item.value + "</td>" +
            '<td class="anchor">' + escapeHtml(checked.dataset.anchor) + "</td>" +
            "</tr>";
        });

        var pct = domainAttainment(items);

        html +=
          '<div class="preview-domain">' +
          "<h3>" + escapeHtml(block.dataset.name) +
          '<span class="pill p-pink ms-auto">' + pct + "% functional attainment</span></h3>" +
          '<div class="track mb-2"><i style="width:' + pct + '%"></i></div>' +
          '<table class="table table-sm preview-table"><tbody>' + rows + "</tbody></table>" +
          "</div>";
      });

      document.getElementById("previewDate").textContent = dateInput && dateInput.value
        ? new Date(dateInput.value + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
        : "—";

      document.getElementById("previewWalking").textContent = walking
        ? walking.value.charAt(0).toUpperCase() + walking.value.slice(1)
        : "—";

      document.getElementById("previewBody").innerHTML = html;
    }

    function openPreview() {
      if (!isComplete()) {
        form.reportValidity();
        return;
      }
      buildPreview();
      if (modal) modal.show();
    }

    /* The form is only submitted from the modal's confirm button. */
    var confirmed = false;

    form.addEventListener("submit", function (e) {
      if (confirmed) return;
      e.preventDefault();
      openPreview();
    });

    if (reviewBtn) reviewBtn.addEventListener("click", openPreview);

    if (confirmBtn) {
      confirmBtn.addEventListener("click", function (e) {
        // Ignore implicit "Enter" submissions that target this button
        // while the modal is closed.
        if (!modalEl.classList.contains("show")) {
          e.preventDefault();
          openPreview();
          return;
        }

        confirmed = true;
        confirmBtn.disabled = true;
        confirmBtn.innerHTML =
          '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Predicting…';
        form.submit();
      });
    }

    /* Clear prefilled answers */
    var clearLink = document.getElementById("clearAll");
    if (clearLink) {
      clearLink.addEventListener("click", function (e) {
        e.preventDefault();
        form.querySelectorAll('.q input[type="radio"]').forEach(function (r) { r.checked = false; });
        updateProgress();
        var tip = clearLink.closest(".tipbar");
        if (tip) tip.remove();
      });
    }

    form.addEventListener("change", updateProgress);
    updateProgress();
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindRowLinks();
    bindAutoSubmit();
    bindPredictForm();
  });
})();
