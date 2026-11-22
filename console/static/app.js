(function () {
  "use strict";
  var root = document.documentElement;

  // Gettone CSRF su ogni richiesta HTMX.
  document.addEventListener("htmx:configRequest", function (event) {
    var meta = document.querySelector('meta[name="csrf"]');
    if (meta) event.detail.headers["X-CSRF-Token"] = meta.content;
  });

  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-azione]");
    if (!target) return;
    var action = target.dataset.azione;
    if (action === "tema") {
      var dark = root.dataset.tema ? root.dataset.tema === "scuro" : window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.tema = dark ? "chiaro" : "scuro";
      try { localStorage.setItem("tema", root.dataset.tema); } catch (e) { /* ignora */ }
    } else if (action === "menu") {
      document.body.classList.toggle("menu-aperto");
    } else if (action === "scheda") {
      var group = target.closest("[data-schede]");
      group.querySelectorAll("[data-azione=scheda]").forEach(function (b) { b.setAttribute("aria-selected", String(b === target)); });
      group.querySelectorAll("[data-pannello]").forEach(function (p) { p.hidden = p.dataset.pannello !== target.dataset.mostra; });
    } else if (action === "copia") {
      navigator.clipboard && navigator.clipboard.writeText(target.dataset.testo || "").then(function () {
        target.classList.add("copiato");
        setTimeout(function () { target.classList.remove("copiato"); }, 1200);
      });
    }
  });

  // Nome del file scelto nell'area di caricamento.
  document.addEventListener("change", function (event) {
    var input = event.target;
    if (input.matches("[data-file]")) {
      var label = document.querySelector(input.dataset.file);
      if (label && input.files.length) label.textContent = input.files[0].name + " · " + Math.max(1, Math.round(input.files[0].size / 1024)) + " kB";
    }
  });

  // Un solo invio per modulo: evita doppi inserimenti.
  document.addEventListener("submit", function (event) {
    var button = event.target.querySelector("button[type=submit]");
    if (button && !event.target.hasAttribute("hx-get")) { button.disabled = true; button.classList.add("in-attesa"); }
  });
})();
