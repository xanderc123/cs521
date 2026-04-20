(function () {
  try {
    var root = (window.parent && window.parent.document) ? window.parent.document : document;

    var REST = 0.45;
    var HOVER = 1.0;
    var DELAY_MS = 1000;

    function setFillOpacity(el, v) {
      if (!el) return;
      el.setAttribute("fill-opacity", String(v));
      el.style.fillOpacity = String(v);
    }

    function hookLegend(g) {
      if (!g || g.getAttribute("data-fillopacity-hook")) return;
      var bg = g.querySelector("rect.bg") || g.querySelector("rect");
      if (!bg) return;
      g.setAttribute("data-fillopacity-hook", "1");
      bg.style.transition = "fill-opacity 0.2s ease";
      setFillOpacity(bg, REST);
      var timer = null;
      g.addEventListener("mouseenter", function () {
        if (timer) { clearTimeout(timer); timer = null; }
        setFillOpacity(bg, HOVER);
      });
      g.addEventListener("mouseleave", function () {
        if (timer) clearTimeout(timer);
        timer = setTimeout(function () {
          setFillOpacity(bg, REST);
          timer = null;
        }, DELAY_MS);
      });
    }

    function scan() {
      root.querySelectorAll('[data-testid="stPlotlyChart"] svg g.legend').forEach(hookLegend);
    }

    if (!root.__plotlyLegendFillOpacityObs) {
      root.__plotlyLegendFillOpacityObs = true;
      var obs = new MutationObserver(scan);
      if (root.body) obs.observe(root.body, { childList: true, subtree: true });
      setInterval(scan, 1200);
    }
    scan();
  } catch (e) {}
})();

(function () {
  try {
    var root = (window.parent && window.parent.document) ? window.parent.document : document;

    function paintInteractiveActionButtons() {
      root.querySelectorAll('[data-testid="stButton"] button').forEach(function (btn) {
        if (btn.getAttribute("data-sl-style")) return;
        var t = (btn.textContent || "").replace(/\s+/g, " ").trim();
        if (t.indexOf("Honest Miner") !== -1) {
          btn.setAttribute("data-sl-style", "honest");
          btn.style.setProperty("background", "linear-gradient(135deg, #0f766e, #14b8a6)", "important");
          btn.style.setProperty("color", "#ecfdf5", "important");
          btn.style.setProperty("border", "1px solid #5eead4", "important");
          btn.querySelectorAll("p, span, div").forEach(function (n) {
            n.style.setProperty("color", "#ecfdf5", "important");
          });
        } else if (t.indexOf("Reset Simulation") !== -1) {
          btn.setAttribute("data-sl-style", "reset");
          btn.style.setProperty("background", "linear-gradient(135deg, #334155, #64748b)", "important");
          btn.style.setProperty("color", "#f8fafc", "important");
          btn.style.setProperty("border", "1px solid #94a3b8", "important");
          btn.querySelectorAll("p, span, div").forEach(function (n) {
            n.style.setProperty("color", "#f8fafc", "important");
          });
        }
      });
    }

    if (!root.__stInteractiveActionBtnPaint) {
      root.__stInteractiveActionBtnPaint = true;
      var obs = new MutationObserver(paintInteractiveActionButtons);
      if (root.body) obs.observe(root.body, { childList: true, subtree: true });
      setInterval(paintInteractiveActionButtons, 1200);
    }
    paintInteractiveActionButtons();
  } catch (e) {}
})();
