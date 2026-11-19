/* The presentation is separate from the existing workflow controls. */
(() => {
  if (globalThis.MaximoPartLogic?.pageKind(location.href) !== "workorder") return;
  document.documentElement.dataset.maximoPresentation = "sidepanel";
  let panelOpen = false;
  function setPanelOpen(open) {
    panelOpen = open === true;
    const button = document.getElementById("maximo-desktop-panel-launcher");
    if (button) button.hidden = panelOpen;
  }
  chrome.runtime.onMessage.addListener(message => {
    if (message.type === "PANEL_VISIBILITY") setPanelOpen(message.open);
  });
  function ensureLauncher() {
    const existing = document.getElementById("maximo-desktop-panel-launcher");
    if (existing) {
      const print = document.getElementById("maximo-desktop-print-part");
      const busy = print?.dataset.panelBusy === "true";
      const failed = print?.textContent.startsWith("No se pudo preparar:");
      existing.textContent = busy ? print.textContent : failed ? "Error al preparar parte · Ver detalle" : "MD · Acciones";
      existing.title = busy || failed ? print.textContent : "Abrir las acciones de esta OT en el panel lateral";
      return;
    }
    const button = document.createElement("button");
    button.id = "maximo-desktop-panel-launcher";
    button.type = "button";
    button.hidden = panelOpen;
    button.textContent = "MD · Acciones";
    button.title = "Abrir las acciones de esta OT en el panel lateral";
    button.addEventListener("click", () => {
      chrome.runtime.sendMessage({ type: "OPEN_PANEL" }).then(response => {
        if (!response?.ok) throw new Error(response?.error || "No se pudo abrir el panel.");
        button.textContent = "MD · Acciones";
      }).catch(error => { button.textContent = "Reintentar panel"; button.title = error.message; });
    });
    document.body.appendChild(button);
    // Recover the native panel state after a Maximo reload or tab redraw.
    chrome.runtime.sendMessage({type:"PANEL_LAUNCHER_STATE"}).then(response => {
      if (response?.ok) setPanelOpen(response.value?.open);
    }).catch(() => {});
  }
  ensureLauncher();
  // Maximo can replace the body while changing tabs.
  setInterval(ensureLauncher, 1000);
})();
