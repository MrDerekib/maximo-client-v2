"use strict";

const JOB_KEY = "activePrintJob";
const JOB_TTL_MS = 3 * 60 * 1000;
let pdfDownloadInProgress = false;

function repairOutputUrl(raw) {
  try {
    const url = new URL(raw);
    return url.origin === "https://eam.indraweb.net" &&
      url.pathname === "/maximo/output" &&
      url.searchParams.get("__report") === "parte_reparacion.rptdesign";
  } catch (_) {
    return false;
  }
}

async function handlePdfOutput(tabId, changeInfo, tab) {
  if (pdfDownloadInProgress || !repairOutputUrl(changeInfo.url || tab?.url)) return;
  const job = await readJob();
  if (job?.outputFormat !== "pdf" || !job.viewerTabId ||
      tab?.openerTabId !== job.viewerTabId ||
      (job.outputTabId && job.outputTabId !== tabId)) return;
  pdfDownloadInProgress = true;
  try {
    job.outputTabId = tabId;
    await chrome.storage.session.set({ [JOB_KEY]: job });
    await chrome.downloads.download({
      url: changeInfo.url || tab.url,
      filename: `parte_reparacion_OT${job.ot}.pdf`,
      saveAs: true,
      conflictAction: "uniquify"
    });
    await chrome.storage.session.remove(JOB_KEY);
    await tellSource(job, "Selecciona dónde guardar el PDF del parte.");
  } catch (error) {
    await chrome.storage.session.remove(JOB_KEY);
    await tellSource(job, `No se pudo abrir Guardar como: ${error.message}. Puedes guardar el PDF desde la pestaña.`);
  } finally {
    pdfDownloadInProgress = false;
  }
}

async function readJob() {
  const stored = await chrome.storage.session.get(JOB_KEY);
  const job = stored[JOB_KEY];
  if (!job) return null;
  if (Date.now() - job.startedAt <= JOB_TTL_MS) return job;
  await chrome.storage.session.remove(JOB_KEY);
  return null;
}

async function tellSource(job, text, type = "STATUS") {
  if (!job) return;
  try {
    await chrome.tabs.sendMessage(job.sourceTabId, { type, text });
  } catch (_) {
    // The source tab may have been closed after submitting the report.
  }
}

function isBoixeresClient(client) {
  return String(client || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ").trim().toUpperCase().includes("TMB BOIXERES");
}

async function closeViewerTab(job) {
  if (!job.closeTabs || !job.viewerTabId) return;
  try { await chrome.tabs.remove(job.viewerTabId); }
  catch (_) { /* The user may already have closed the BIRT tab. */ }
}

async function handleMessage(message, sender) {
  const tab = sender.tab;
  if (!tab?.id) throw new Error("No se ha identificado la pestaña de Maximo.");

  if (message.type === "START") {
    if (await readJob()) throw new Error("Ya hay un parte en preparación.");
    const ot = String(message.ot || "").trim();
    if (!/^\d{5,12}$/.test(ot)) throw new Error("El número de OT no es válido.");
    const outputFormat = message.outputFormat || "html";
    if (!["html", "pdf"].includes(outputFormat)) throw new Error("Formato de parte no válido.");
    const job = {
      id: crypto.randomUUID(), ot, outputFormat, sourceTabId: tab.id,
      viewerTabId: null, outputTabId: null, startedAt: Date.now(),
      variantIndex: 0,
      variantCount: outputFormat === "html" && isBoixeresClient(message.client) ? 2 : 1,
      closeTabs: outputFormat === "html" && message.closeTabs === true
    };
    await chrome.storage.session.set({ [JOB_KEY]: job });
    return { jobId: job.id, ot, variantIndex: job.variantIndex, variantCount: job.variantCount };
  }

  const job = await readJob();
  if (!job) throw new Error("No hay un parte solicitado o ha caducado la espera.");

  if (message.type === "ACTIVATE_SOURCE") {
    if (message.jobId !== job.id || tab.id !== job.sourceTabId) {
      throw new Error("La ficha no pertenece a la OT solicitada.");
    }
    const source = await chrome.tabs.update(job.sourceTabId, { active: true });
    await chrome.windows.update(source.windowId, { focused: true });
    return { activated: true };
  }

  if (message.type === "CLICK_REPORT_MENU") {
    if (message.jobId !== job.id || tab.id !== job.sourceTabId) {
      throw new Error("El menú no pertenece a la OT solicitada.");
    }
    const [execution] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      func: () => {
        const anchor = [...document.querySelectorAll("a[eventtype='RUNREPORTS']")]
          .find(element => element.getClientRects().length);
        if (!anchor) return { clicked: false };
        const label = anchor.querySelector("span[id$='_RUNREPORTS_OPTION_a_tnode']");
        (label || anchor).click();
        return { clicked: true };
      }
    });
    if (!execution?.result?.clicked) throw new Error("No se encontró «Ejecutar informes» en la ficha.");
    return { clicked: true };
  }

  if (message.type === "CLICK_REPAIR_REPORT") {
    if (message.jobId !== job.id || tab.id !== job.sourceTabId) {
      throw new Error("La lista de informes no pertenece a la OT solicitada.");
    }
    const [execution] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      func: () => {
        const dialog = document.getElementById("reportFilesWO_TR-dialog_inner");
        if (!dialog || !dialog.getClientRects().length) return { clicked: false, reason: "dialog" };
        const textMatches = element => element.getClientRects().length &&
          element.textContent.replace(/\s+/g, " ").trim() === "Parte de reparación";
        const candidates = [...dialog.querySelectorAll("[id$='_ttxt-lb[R:1]']")];
        const target = candidates.find(element =>
          element.id.includes("_tdrow_") && textMatches(element));
        if (!target) return { clicked: false, reason: "report" };
        target.scrollIntoView({ block: "center" });
        target.focus?.();
        const eventOptions = { bubbles: true, cancelable: true, composed: true, button: 0 };
        if (typeof PointerEvent === "function") {
          target.dispatchEvent(new PointerEvent("pointerdown", { ...eventOptions, buttons: 1, pointerId: 1, pointerType: "mouse", isPrimary: true }));
        }
        target.dispatchEvent(new MouseEvent("mousedown", { ...eventOptions, buttons: 1 }));
        if (typeof PointerEvent === "function") {
          target.dispatchEvent(new PointerEvent("pointerup", { ...eventOptions, buttons: 0, pointerId: 1, pointerType: "mouse", isPrimary: true }));
        }
        target.dispatchEvent(new MouseEvent("mouseup", { ...eventOptions, buttons: 0 }));
        target.click();
        return { clicked: true, targetId: target.id };
      }
    });
    if (!execution?.result?.clicked) {
      throw new Error(execution?.result?.reason === "dialog"
        ? "Ya no está abierta «Informes y programaciones»."
        : "No se encontró «Parte de reparación» en la lista de informes.");
    }
    return { clicked: true };
  }

  if (message.type === "FILL_REPORT_OT") {
    if (message.jobId !== job.id || tab.id !== job.sourceTabId) {
      throw new Error("La solicitud del informe no pertenece a la OT solicitada.");
    }
    const [execution] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      args: [job.ot],
      func: ot => {
        // An inactive document can show the inserted value without dispatching
        // blur, leaving Maximo's server-side parameter empty.
        if (!document.hasFocus()) return { filled: false, reason: "focus" };
        const visible = element => Boolean(element?.getClientRects().length);
        const field = [...document.querySelectorAll("input[aria-labelledby]")].find(input =>
          visible(input) && input.getAttribute("aria-labelledby").split(/\s+/).some(id =>
            /work order number/i.test(document.getElementById(id)?.textContent || "")));
        if (!field) return { filled: false, reason: "field" };
        const buttonId = field.getAttribute("db");
        field.focus();
        field.select();
        // Browser text insertion fires the input path Maximo expects from a
        // user edit. Assigning `value` alone only changed what was displayed.
        let inserted = false;
        try { inserted = document.execCommand?.("insertText", false, ot) || false; } catch (_) { /* Use input-event fallback. */ }
        if (!inserted || field.value !== ot) {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
          if (setter) setter.call(field, ot);
          else field.value = ot;
          field.dispatchEvent(new InputEvent("input", {
            bubbles: true, data: ot, inputType: "insertText"
          }));
        }
        field.dispatchEvent(new KeyboardEvent("keyup", {
          bubbles: true, key: ot.at(-1)
        }));
        field.dispatchEvent(new Event("change", { bubbles: true }));
        field.blur();
        return { filled: true, buttonId };
      }
    });
    if (execution?.result?.filled === false)
      throw new Error(execution.result.reason === "focus"
        ? "La ficha de OT no tiene el foco; no se introdujo el número del parte."
        : "No se encontró el campo «Work order number».");
    // Maximo may redraw the form during blur and drop the injected function's
    // return value; the content script verifies the field after this call.
    return { filled: true };
  }

  if (message.type === "SET_REPAIR_INFO") {
    if (message.jobId !== job.id || tab.id !== job.sourceTabId || job.variantCount !== 2 ||
        !["S", "N"].includes(message.value)) {
      throw new Error("El parámetro de la variante no pertenece a este parte.");
    }
    const [execution] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      args: [message.value],
      func: async value => {
        const visible = element => Boolean(element?.getClientRects().length);
        const labelPattern = /incluir nombre y tiempo reparaci[oó]n/i;
        const controls = [...document.querySelectorAll("input, textarea, select")].filter(visible);
        const field = controls.find(element => {
          const labelledBy = (element.getAttribute("aria-labelledby") || "").split(/\s+/);
          if (labelledBy.some(id => labelPattern.test(document.getElementById(id)?.textContent || "")))
            return true;

          if ([...document.querySelectorAll("label[for]")].some(label =>
            label.htmlFor === element.id && labelPattern.test(label.textContent || ""))) return true;

          const row = element.closest("tr, [role='row']");
          if (row && labelPattern.test(row.innerText || row.textContent || "")) return true;

          const labelId = element.id?.replace(/-tb$/, "-lb");
          return Boolean(labelId && labelPattern.test(document.getElementById(labelId)?.textContent || ""));
        });
        if (!field) return { updated: false, reason: "field" };
        if (String(field.value || "").trim() === value) return { updated: true, alreadySet: true };

        const lookupId = field.getAttribute("linkedimage");
        const lookup = lookupId && document.getElementById(lookupId);
        if (!lookup || !visible(lookup)) return { updated: false, reason: "lookup" };
        lookup.click();

        const normalize = text => String(text || "").replace(/\s+/g, " ").trim().toUpperCase();
        const started = Date.now();
        while (Date.now() - started < 10000) {
          const choices = [...document.querySelectorAll(
            "span[id^='lookup_page'][id*='_tdrow_'][id*='_ttxt-lb']"
          )].filter(option => visible(option) && normalize(option.textContent) === value);
          if (choices.length === 1) {
            const option = choices[0];
            // Mark the exact Maximo link for Selenium. WebDriver can produce a
            // trusted browser click; synthetic DOM events are ignored here.
            document.documentElement.dataset.maximoNativeLookupClick = option.id;
            return { updated: true, pendingNativeClick: true, method: "lookup" };
          }
          if (choices.length > 1) return { updated: false, reason: "ambiguous" };
          await new Promise(resolve => setTimeout(resolve, 150));
        }
        return { updated: false, reason: "option" };
      }
    });
    if (execution?.result?.updated !== true) {
      const reasons = {
        field: "No se encontró el parámetro «Incluir nombre y tiempo reparación» del informe.",
        lookup: "No se encontró la lupa del parámetro del parte.",
        option: "La lupa no mostró una opción «N» reconocible; no se envió el informe.",
        ambiguous: "La lupa mostró varias opciones «N»; no se envió el informe.",
      };
      throw new Error(reasons[execution?.result?.reason] ||
        "Maximo no confirmó la selección «N» en la lupa; no se envió el informe.");
    }
    return { updated: true, maximoChanged: execution?.result?.maximoChanged === true };
  }

  if (message.type === "CLICK_REPORT_SUBMIT") {
    if (message.jobId !== job.id || tab.id !== job.sourceTabId) {
      throw new Error("El botón Enviar no pertenece a la OT solicitada.");
    }
    const [execution] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: "MAIN",
      args: [message.buttonId],
      func: defaultButtonId => {
        const visible = element => Boolean(element?.getClientRects().length);
        const isSendButton = element => visible(element) &&
          (element.value || element.textContent || "").replace(/\s+/g, " ").trim() === "Enviar";
        const linked = defaultButtonId && document.getElementById(defaultButtonId);
        const submit = isSendButton(linked) ? linked :
          [...document.querySelectorAll("button")].find(isSendButton);
        if (!submit) return { submitted: false, reason: "button" };
        submit.scrollIntoView({ block: "center" });
        const eventOptions = { bubbles: true, cancelable: true, composed: true, button: 0 };
        if (typeof PointerEvent === "function") {
          submit.dispatchEvent(new PointerEvent("pointerdown", { ...eventOptions, buttons: 1, pointerId: 1, pointerType: "mouse", isPrimary: true }));
        }
        submit.dispatchEvent(new MouseEvent("mousedown", { ...eventOptions, buttons: 1 }));
        if (typeof PointerEvent === "function") {
          submit.dispatchEvent(new PointerEvent("pointerup", { ...eventOptions, buttons: 0, pointerId: 1, pointerType: "mouse", isPrimary: true }));
        }
        submit.dispatchEvent(new MouseEvent("mouseup", { ...eventOptions, buttons: 0 }));
        submit.click();
        return { submitted: true };
      }
    });
    if (execution?.result?.submitted === false)
      throw new Error("No se encontró el botón «Enviar» al intentar pulsarlo.");
    // Maximo can replace the dialog and invalidate the execution context as it submits.
    // An absent result is therefore inconclusive; the source page waits for the BIRT viewer.
    return { submitted: true };
  }

  if (message.type === "CLAIM_VIEWER") {
    if (job.viewerTabId && job.viewerTabId !== tab.id) throw new Error("Visor inesperado.");
    if (tab.openerTabId != null && tab.openerTabId !== job.sourceTabId) {
      throw new Error("El visor no pertenece a la OT solicitada.");
    }
    job.viewerTabId = tab.id;
    await chrome.storage.session.set({ [JOB_KEY]: job });
    await tellSource(job, job.outputFormat === "pdf"
      ? "Parte generado; preparando PDF…"
      : job.variantCount > 1
        ? `Parte ${job.variantIndex + 1}/2 generado; preparando impresión…`
        : "Parte generado; preparando impresión…", "PROGRESS");
    return { ot: job.ot, jobId: job.id, outputFormat: job.outputFormat,
      variantIndex: job.variantIndex, variantCount: job.variantCount };
  }

  if (message.type === "CLAIM_OUTPUT") {
    if (!job.viewerTabId) throw new Error("No se ha reconocido el visor BIRT.");
    if (job.outputTabId && job.outputTabId !== tab.id) throw new Error("Salida inesperada.");
    if (tab.openerTabId != null && tab.openerTabId !== job.viewerTabId) {
      throw new Error("La salida no procede del visor del parte.");
    }
    job.outputTabId = tab.id;
    await chrome.storage.session.set({ [JOB_KEY]: job });
    return { ot: job.ot, jobId: job.id };
  }

  if (message.type === "FINISH" || message.type === "FAIL") {
    if (message.jobId && message.jobId !== job.id) throw new Error("Operación caducada.");
    if (message.type === "FINISH" && tab.id !== job.outputTabId) {
      throw new Error("La vista de impresión no pertenece al parte solicitado.");
    }
    if (message.type === "FINISH" && job.variantCount === 2 && job.variantIndex === 0) {
      await closeViewerTab(job);
      job.variantIndex = 1;
      job.viewerTabId = null;
      job.outputTabId = null;
      job.startedAt = Date.now();
      await chrome.storage.session.set({ [JOB_KEY]: job });
      try {
        await chrome.tabs.sendMessage(job.sourceTabId, {
          type: "NEXT_VARIANT", jobId: job.id, variantIndex: 1,
          variantCount: job.variantCount,
          text: "Primera copia lista; preparando la variante sin técnico ni tiempo…"
        });
      } catch (_) {
        await chrome.storage.session.remove(JOB_KEY);
        throw new Error("No se pudo iniciar la segunda variante del parte.");
      }
      return { ok: true, nextVariant: true, closeTabs: job.closeTabs };
    }
    if (message.type === "FINISH") await closeViewerTab(job);
    await chrome.storage.session.remove(JOB_KEY);
    await tellSource(job, message.type === "FINISH"
      ? "Parte preparado. Comprueba el diálogo o la cola de impresión."
      : `No se pudo preparar el parte: ${message.reason || "error desconocido"}`);
    return { ok: true, closeTabs: message.type === "FINISH" && job.closeTabs };
  }
  throw new Error("Mensaje desconocido.");
}

if (typeof chrome !== "undefined") {
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    handlePdfOutput(tabId, changeInfo, tab).catch(console.error);
  });
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    handleMessage(message, sender).then(
      value => respond({ ok: true, value }),
      error => respond({ ok: false, error: error.message })
    );
    return true;
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { handleMessage, handlePdfOutput, JOB_KEY, JOB_TTL_MS };
}
