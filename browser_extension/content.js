(function () {
  "use strict";

  const logic = globalThis.MaximoPartLogic;
  const page = logic.pageKind(location.href);
  if (!page) return;

  function visible(element) {
    return Boolean(element && element.getClientRects().length &&
      getComputedStyle(element).visibility !== "hidden");
  }

  function waitFor(find, description, timeout = 20000) {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const timer = setInterval(() => {
        let result;
        try { result = find(); } catch (_) { result = null; }
        if (result) {
          clearInterval(timer);
          resolve(result);
        } else if (Date.now() - started >= timeout) {
          clearInterval(timer);
          reject(new Error(`Tiempo agotado: ${description}`));
        }
      }, 200);
    });
  }

  async function send(type, payload = {}) {
    const response = await chrome.runtime.sendMessage({ type, ...payload });
    if (!response?.ok) throw new Error(response?.error || "La extensión no respondió.");
    return response.value;
  }

  function textInFrames(documentRoot) {
    let text = documentRoot.body?.innerText || "";
    for (const frame of documentRoot.querySelectorAll("iframe")) {
      try {
        if (frame.contentDocument) text += `\n${textInFrames(frame.contentDocument)}`;
      } catch (_) { /* A cross-origin frame is not part of this report. */ }
    }
    return text;
  }

  function inputValue(id) {
    const element = document.getElementById(id);
    return String(element?.value || "").trim();
  }

  function requestWorkOrderField() {
    return [...document.querySelectorAll("input[aria-labelledby]")].find(input =>
      visible(input) && input.getAttribute("aria-labelledby").split(/\s+/).some(id =>
        /work order number/i.test(document.getElementById(id)?.textContent || "")));
  }

  function repairInfoField() {
    const labelPattern = /incluir nombre y tiempo reparaci[oó]n/i;
    const controls = [...document.querySelectorAll("input, textarea, select")].filter(visible);
    return controls.find(element => {
      const labelledBy = (element.getAttribute("aria-labelledby") || "").split(/\s+/);
      if (labelledBy.some(id => labelPattern.test(document.getElementById(id)?.textContent || "")))
        return true;

      const matchingLabel = [...document.querySelectorAll("label[for]")]
        .some(label => label.htmlFor === element.id && labelPattern.test(label.textContent || ""));
      if (matchingLabel) return true;

      // Maximo often renders the visible field caption in the same table row
      // without exposing an aria-labelledby relationship.
      const row = element.closest("tr, [role='row']");
      if (row && labelPattern.test(row.innerText || row.textContent || "")) return true;

      // Some Maximo versions use the conventional mxNNNN-tb / mxNNNN-lb pair.
      const labelId = element.id?.replace(/-tb$/, "-lb");
      return Boolean(labelId && labelPattern.test(document.getElementById(labelId)?.textContent || ""));
    });
  }

  function repairClient() {
    return logic.clientFromWorkorder(document);
  }

  async function submitReportVariant(jobId, targetButton, variantIndex, variantCount) {
    await waitFor(() => [...document.querySelectorAll("a[eventtype='RUNREPORTS']")]
      .find(visible), "menú Ejecutar informes");
    targetButton.textContent = "Abriendo informes…";
    await send("CLICK_REPORT_MENU", { jobId });
    try {
      await waitFor(() => {
        const element = document.getElementById("reportFilesWO_TR-dialog_inner");
        return visible(element) ? element : null;
      }, "ventana Informes y programaciones", 15000);
    } catch (_) {
      throw new Error("Maximo no abrió «Informes y programaciones» al pulsar «Ejecutar informes».");
    }
    targetButton.textContent = "Seleccionando parte…";
    await send("CLICK_REPAIR_REPORT", { jobId });
    const requestField = await waitFor(requestWorkOrderField, "campo Work order number", 15000);
    const initialButtonId = requestField.getAttribute("db");
    targetButton.textContent = "Introduciendo OT…";
    await send("FILL_REPORT_OT", { jobId });
    await waitFor(() => {
      const field = requestWorkOrderField();
      return field && [field.value, field.getAttribute("originalvalue"),
        field.getAttribute("prekeyvalue")].includes(inputValue("mx45-tb")) ? field : null;
    }, "confirmación del número de OT", 5000);
    if (variantCount > 1) {
      const includeTechnicianAndTime = variantIndex === 0 ? "S" : "N";
      targetButton.textContent = variantIndex === 0
        ? "Configurando parte 1/2…" : "Configurando parte 2/2…";
      const currentField = repairInfoField();
      if (!currentField) throw new Error("No se encontró el parámetro «Incluir nombre y tiempo reparación» del informe.");
      if (currentField.value !== includeTechnicianAndTime) {
        await send("SET_REPAIR_INFO", { jobId, value: includeTechnicianAndTime });
        await waitFor(() => repairInfoField()?.value === includeTechnicianAndTime
          ? repairInfoField() : null,
        `confirmación de la selección ${includeTechnicianAndTime} en la lupa`, 20000);
      }
    }
    await new Promise(resolve => setTimeout(resolve, 1500));
    await waitFor(() => {
      const currentField = requestWorkOrderField();
      const id = currentField?.getAttribute("db") || initialButtonId;
      const linked = id && document.getElementById(id);
      if (visible(linked) && linked.textContent.trim() === "Enviar") return linked;
      return [...document.querySelectorAll("button")]
        .find(element => visible(element) && element.textContent.trim() === "Enviar");
    }, "botón Enviar del informe", 15000);
    targetButton.textContent = "Enviando solicitud…";
    await send("CLICK_REPORT_SUBMIT", {
      jobId, buttonId: requestWorkOrderField()?.getAttribute("db") || initialButtonId
    });
    targetButton.textContent = variantCount > 1
      ? `Esperando visor ${variantIndex + 1}/2…` : "Esperando el visor BIRT…";
  }

  async function workorderPage() {
    await waitFor(() => document.getElementById("mx45-tb") &&
      document.getElementById("mx73-tb"), "ficha de OT", 45000);
    const button = document.createElement("button");
    button.id = "maximo-desktop-print-part";
    button.type = "button";
    button.textContent = "Imprimir parte";
    Object.assign(button.style, {
      position: "fixed", right: "20px", bottom: "20px", zIndex: "2147483647",
      padding: "9px 14px", border: "1px solid #1155a0", borderRadius: "6px",
      background: "#1769c2", color: "#fff", font: "600 13px Arial, sans-serif",
      boxShadow: "0 3px 12px #0004", cursor: "pointer"
    });
    document.body.appendChild(button);

    let running = false;
    let reportTimeout;
    let reportErrorWatcher;

    function armReportWait(jobId) {
      clearTimeout(reportTimeout);
      clearInterval(reportErrorWatcher);
      reportErrorWatcher = setInterval(async () => {
        if (!running) return clearInterval(reportErrorWatcher);
        if (!/BMXAA3556E/.test(document.body?.innerText || "")) return;
        clearInterval(reportErrorWatcher);
        clearTimeout(reportTimeout);
        const reason = "Maximo rechazó la OT del informe: el campo figura como vacío.";
        await send("FAIL", { jobId, reason }).catch(() => {});
        button.textContent = reason;
        running = false;
        setTimeout(() => { button.textContent = "Imprimir parte"; refresh(); }, 8000);
      }, 500);
      reportTimeout = setTimeout(async () => {
        const reason = "Maximo no abrió el visor BIRT tras enviar el informe.";
        await send("FAIL", { jobId, reason }).catch(() => {});
        button.textContent = reason;
        running = false;
        setTimeout(() => { button.textContent = "Imprimir parte"; refresh(); }, 8000);
      }, 60000);
    }
    function refresh() {
      if (running) return;
      const ot = inputValue("mx45-tb");
      const status = inputValue("mx73-tb");
      button.hidden = !/^\d{5,12}$/.test(ot);
      button.disabled = !logic.canPrintStatus(status);
      button.style.opacity = button.disabled ? "0.6" : "1";
      button.title = button.disabled
        ? "Disponible cuando la OT está pendiente de salida (ISSUE) o cerrada (CLOSE)."
        : `Generar el parte de la OT ${ot} y abrir la impresión.`;
    }
    refresh();
    setInterval(refresh, 800);
    chrome.runtime.onMessage.addListener(message => {
      if (message.type === "PROGRESS") {
        clearTimeout(reportTimeout);
        clearInterval(reportErrorWatcher);
        button.textContent = message.text;
        button.title = message.text;
      }
      if (message.type === "NEXT_VARIANT" && running) {
        clearTimeout(reportTimeout);
        clearInterval(reportErrorWatcher);
        button.textContent = message.text;
        submitReportVariant(message.jobId, button, message.variantIndex,
          message.variantCount).then(() => armReportWait(message.jobId)).catch(async error => {
          await send("FAIL", { jobId: message.jobId, reason: error.message }).catch(() => {});
          button.textContent = `No se pudo preparar: ${error.message}`;
          running = false;
          setTimeout(() => { button.textContent = "Imprimir parte"; refresh(); }, 8000);
        });
      }
      if (message.type === "STATUS") {
        clearTimeout(reportTimeout);
        clearInterval(reportErrorWatcher);
        button.textContent = message.text;
        button.title = message.text;
        running = false;
        setTimeout(() => { button.textContent = "Imprimir parte"; refresh(); }, 6000);
      }
    });

    button.addEventListener("click", async () => {
      const ot = inputValue("mx45-tb");
      if (running || !logic.canPrintStatus(inputValue("mx73-tb")) || !/^\d{5,12}$/.test(ot)) return;
      let jobId;
      running = true;
      button.disabled = true;
      button.textContent = "Preparando parte…";
      try {
        const outputFormat = button.dataset.maximoReportAction === "pdf" ? "pdf" : "html";
        const closeTabs = outputFormat === "html" &&
          (button.dataset.maximoCloseReportTabs === "true" ||
            document.documentElement.dataset.maximoCloseReportTabs === "true");
        delete button.dataset.maximoReportAction;
        delete button.dataset.maximoCloseReportTabs;
        const job = await send("START", { ot, outputFormat, client: repairClient(), closeTabs });
        jobId = job.jobId;
        button.textContent = job.variantCount > 1 ? "Preparando parte 1/2…" : "Preparando parte…";
        await submitReportVariant(jobId, button, job.variantIndex, job.variantCount);
        armReportWait(jobId);
      } catch (error) {
        clearTimeout(reportTimeout);
        clearInterval(reportErrorWatcher);
        if (jobId) await send("FAIL", { jobId, reason: error.message }).catch(() => {});
        button.textContent = `No se pudo preparar: ${error.message}`;
        running = false;
        setTimeout(() => { button.textContent = "Imprimir parte"; refresh(); }, 8000);
      }
    });
  }

  async function viewerPage() {
    let job;
    try {
      job = await send("CLAIM_VIEWER");
      await waitFor(() => logic.containsOt(textInFrames(document), job.ot),
        `OT ${job.ot} en el visor BIRT`, 45000);
      const print = await waitFor(() => [...document.querySelectorAll("input[name='print']")]
        .find(element => visible(element) && element.title === "Imprimir informe"),
      "botón Imprimir informe");
      print.click();
      const pdf = job.outputFormat === "pdf";
      const format = await waitFor(() => {
        const element = document.getElementById(pdf ? "printAsPDF" : "printAsHTML");
        return visible(element) ? element : null;
      }, pdf ? "opción PDF" : "opción HTML");
      format.click();
      if (!format.checked) throw new Error(`No se pudo seleccionar ${pdf ? "PDF" : "HTML"}.`);
      const accept = await waitFor(() => [...document.querySelectorAll("input[type='button']")]
        .find(element => visible(element) && element.value === "Aceptar" &&
          element.title === "Aceptar"), `Aceptar formato ${pdf ? "PDF" : "HTML"}`);
      accept.click();
    } catch (error) {
      if (job) await send("FAIL", { jobId: job.jobId, reason: error.message }).catch(() => {});
      console.error("Maximo Desktop - parte:", error);
    }
  }

  async function outputPage() {
    let job;
    try {
      job = await send("CLAIM_OUTPUT");
      await waitFor(() => logic.containsOt(textInFrames(document), job.ot),
        `OT ${job.ot} en el parte HTML`, 45000);
      window.print();
      const result = await send("FINISH", { jobId: job.jobId });
      if (result?.closeTabs) window.close();
    } catch (error) {
      if (job) await send("FAIL", { jobId: job.jobId, reason: error.message }).catch(() => {});
      console.error("Maximo Desktop - parte:", error);
    }
  }

  if (page === "workorder") workorderPage().catch(console.error);
  if (page === "viewer") viewerPage();
  if (page === "output") outputPage();
})();
