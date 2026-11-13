/* Serialized into the page's MAIN world. Presentation only; reuse MD actions. */
function maximoPanelBridge(request) {
  "use strict";
  try {
  request = request || {};
  if (location.origin !== "https://eam.indraweb.net" || !/^\/maximo\/ui\/?$/i.test(location.pathname))
    throw new Error("Selecciona una ficha de OT en Maximo.");
  const visible = node => Boolean(node && node.getClientRects().length &&
    getComputedStyle(node).visibility !== "hidden");
  const normalize = text => String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ").trim().replace(/:$/, "").toLowerCase();
  const field = (caption, fallback) => {
    const label = [...document.querySelectorAll("label[for]")].find(node =>
      visible(node) && normalize(node.textContent) === normalize(caption));
    const input = label ? document.getElementById(label.htmlFor) : document.getElementById(fallback);
    return visible(input) ? String(input.value || "").trim() : "";
  };
  const ot = field("Orden de trabajo", "mx45-tb");
  const status = field("Estado", "mx73-tb").toUpperCase();
  const specs = [
    ["start", "Iniciar OT", "maximo-desktop-start-ot", ["APPR"], "primary"],
    ["choose", "Elegir anomalías…", "maximo-desktop-start-options", ["APPR"], "prepare"],
    ["change", "Cambiar anomalías", "maximo-desktop-change-anomalies", ["INPRG"], "prepare"],
    ["close", "Cerrar OT…", "maximo-desktop-close-ot", ["INPRG"], "primary"],
    ["print", "Imprimir parte", "maximo-desktop-print-part", ["ISSUE", "CLOSE"], "documents"]
  ];
  const blocking = [...document.querySelectorAll("[role=dialog],#warndiv")].some(node => {
    if (!visible(node)) return false;
    for (let parent = node; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (parent.getAttribute("aria-hidden") === "true" || style.display === "none" ||
          ["hidden", "collapse"].includes(style.visibility) || Number(style.opacity) === 0) return false;
    }
    return true;
  });
  const actions = specs.flatMap(([key, label, id, statuses, group]) => {
    const button = document.getElementById(id);
    if (!button || button.hidden || !statuses.includes(status)) return [];
    return [{ key, label, group, enabled: !button.disabled && !blocking,
      text: button.textContent.trim(), hint: button.title || "" }];
  });
  const buttons = specs.map(spec => document.getElementById(spec[2])).filter(Boolean);
  const progress = buttons.filter(button => button.dataset.busy === "true").map(button => button.textContent.trim());
  const print = document.getElementById("maximo-desktop-print-part");
  if (print?.dataset.panelBusy === "true") progress.push(print.textContent.trim());
  // Progress survives Maximo's validation reloads; never stores reviewed fields.
  if (typeof sessionStorage !== "undefined") {
    try {
      const running = JSON.parse(sessionStorage.getItem("maximoDesktop.closeProgress") || "null");
      if (running?.ot === ot && Date.now()-running.at < 10*60*1000 && running.text)
        progress.push(running.text);
    } catch (_) { /* Ignore expired/invalid presentation state. */ }
  }
  const expectedLabels = ["Iniciar OT", "Elegir anomalías…", "Cambiar anomalías", "Cerrar OT", "Imprimir parte"];
  const messages = buttons.map(button => button.textContent.trim()).filter(text => text && !expectedLabels.includes(text));
  const valid = /^\d{1,20}$/.test(ot);
  if (request.action) {
    if (!valid || request.ot !== ot || request.status !== status)
      throw new Error("La OT o su estado cambiaron. Revisa el panel antes de continuar.");
    const action = actions.find(item => item.key === request.action);
    if (!action?.enabled || progress.length)
      throw new Error("La acción no está disponible. Revisa la ficha y los diálogos abiertos.");
    // Return focus to the page before workflows which validate edits on blur.
    if (typeof window !== "undefined") window.focus();
    const button = document.getElementById(specs.find(spec => spec[0] === request.action)[2]);
    // Call the DOM control, not a global function from another JS world.
    button.click();
    if (request.action === "close" && button.dataset.busy !== "true")
      throw new Error("MD no recibió la revisión de cierre. Cierra MD y su Edge y abre una sesión nueva para cargar los cambios.");
  }
  return { ot: valid ? ot : "", status, client: field("Cliente", "mx47-tb"),
    description: field("Descripción"), actions: valid ? actions : [],
    blocking, progress, messages, printText: print?.textContent.trim() || "" };
  } catch (error) {
    // Edge may omit InjectionResult.result when an injected function throws.
    return { panelError: String(error?.message || error) };
  }
}
if (typeof module !== "undefined") module.exports = { maximoPanelBridge };
