/* HTML only: preserve the original BIRT content and never cover report data. */
(function (root) {
  function insert(doc) {
    const id = "md-irreparable-stamp";
    if (doc.getElementById(id)) return;
    const stamp = doc.createElement("div");
    stamp.id = id;
    stamp.textContent = "IRREPARABLE";
    stamp.setAttribute("aria-label", "Equipo declarado irreparable");
    stamp.style.cssText =
      "position:absolute;top:32px;right:32px;z-index:9999;pointer-events:none;" +
      "transform:rotate(-8deg);border:5px double #b3151b;border-radius:5px;" +
      "padding:8px 18px;color:#b3151b;background:transparent;" +
      "font:bold 34px 'Courier New',monospace;letter-spacing:2px;line-height:1.1;" +
      "opacity:.9;-webkit-print-color-adjust:exact;print-color-adjust:exact";
    doc.body.appendChild(stamp);
  }
  root.MaximoReportStamp = { insert };
  if (typeof module !== "undefined") module.exports = root.MaximoReportStamp;
})(globalThis);
