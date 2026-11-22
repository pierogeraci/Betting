// Applica il tema salvato prima del primo disegno, per evitare il lampo di colore.
(function () {
  try {
    var saved = localStorage.getItem("tema");
    if (saved === "chiaro" || saved === "scuro") document.documentElement.dataset.tema = saved;
  } catch (e) { /* senza archivio locale si segue il sistema */ }
})();
