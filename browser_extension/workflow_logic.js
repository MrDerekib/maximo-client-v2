(function (root) {
  "use strict";

  const BIRT_RESOURCE_NOTICE = "The resource of this report item is not reachable.";

  function pageKind(url) {
    const parsed = new URL(url);
    if (parsed.origin !== "https://eam.indraweb.net") return null;
    if (/^\/maximo\/ui\/?$/i.test(parsed.pathname)) return "workorder";
    if (!/parte_reparacion\.rptdesign/i.test(parsed.searchParams.get("__report") || "")) return null;
    if (/^\/maximo\/report\/?$/i.test(parsed.pathname)) return "viewer";
    if (/^\/maximo\/output\/?$/i.test(parsed.pathname)) return "output";
    return null;
  }

  function containsOt(text, ot) {
    const number = String(ot || "").trim();
    if (!/^\d{5,12}$/.test(number)) return false;
    return new RegExp(`(^|\\D)${number}(?!\\d)`).test(String(text || ""));
  }

  function canPrintStatus(status) {
    return ["ISSUE", "CLOSE"].includes(String(status || "").trim().toUpperCase());
  }

  function labeledFieldValue(documentRoot, caption, fallbackId) {
    const normalize = value => String(value || "").normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ")
      .replace(/[:：]\s*$/, "").trim().toLocaleLowerCase();
    const visible = element => element &&
      (!element.getClientRects || element.getClientRects().length > 0) &&
      (!element.getAttribute || element.getAttribute("aria-hidden") !== "true");

    const matchingLabel = [...(documentRoot?.querySelectorAll?.("label[for]") || [])]
      .find(label => visible(label) && normalize(label.textContent) === normalize(caption));
    const labeled = matchingLabel && documentRoot.getElementById(matchingLabel.htmlFor);
    if (visible(labeled) && String(labeled.value || "").trim())
      return String(labeled.value).trim();

    const ariaLabeled = [...(documentRoot?.querySelectorAll?.("input[aria-labelledby], textarea[aria-labelledby]") || [])]
      .find(field => visible(field) && (field.getAttribute("aria-labelledby") || "").split(/\s+/)
        .some(id => normalize(documentRoot.getElementById(id)?.textContent) === normalize(caption)));
    if (visible(ariaLabeled) && String(ariaLabeled.value || "").trim())
      return String(ariaLabeled.value).trim();

    const fallback = fallbackId && documentRoot?.getElementById?.(fallbackId);
    return visible(fallback) ? String(fallback.value || "").trim() : "";
  }

  function isAtmClient(client) {
    return /^(?:cliente\s*:?\s*)?atm(?:\s|$)/i.test(String(client || "").trim());
  }

  function includeReportOrigin(client, preference) {
    const mode = preference?.mode;
    if (mode === "disabled") return false;
    if (mode === "all") return true;
    if (mode !== "selected" || !Array.isArray(preference.projects)) return isAtmClient(client);
    const key = String(client || "").replace(/^cliente\s*:?\s*/i, "").trim().toUpperCase();
    return preference.projects.some(project => typeof project === "string" &&
      (project.trim().toUpperCase() === key || (project.trim().toUpperCase() === "ATM" && isAtmClient(client))));
  }

  function originCompanyText(value) {
    return typeof value === "string" ? value.replace(/\s+/g, " ").trim().slice(0, 200) : "";
  }

  function originCompanyFromWorkorder(documentRoot) {
    const primary = labeledFieldValue(documentRoot, "Ubicación inicial", "mx88-tb");
    if (primary) return originCompanyText(primary);
    const description = [...(documentRoot.querySelectorAll?.("input[aria-label]") || [])]
      .find(field => field.getAttribute("aria-label")?.trim().toLocaleLowerCase() ===
        "descripción de ubicación inicial" && (!field.getClientRects || field.getClientRects().length));
    const backup = description?.value ||
      labeledFieldValue(documentRoot, "Descripción de ubicación inicial", "mx88-tb2");
    return originCompanyText(backup).replace(/^empresa\s*:?\s+/i, "");
  }

  function removeBirtResourceNotices(documentRoot) {
    for (const element of documentRoot.querySelectorAll("body *")) {
      if (element.tagName === "IFRAME") {
        const frame = element.contentDocument;
        if (frame) removeBirtResourceNotices(frame);
      } else if (element.tagName === "IMG" && element.alt.trim() === BIRT_RESOURCE_NOTICE) {
        element.alt = "";
        if (!element.naturalWidth) element.style.visibility = "hidden";
      } else if (element.textContent.trim() === BIRT_RESOURCE_NOTICE &&
        ![...element.children].some(child => child.textContent.trim() === BIRT_RESOURCE_NOTICE)) {
        element.textContent = "";
      }
    }
  }

  function insertOriginCompany(documentRoot, company) {
    if (!company || documentRoot.getElementById("md-origin-company")) return;
    const field = documentRoot.createElement("div");
    field.id = "md-origin-company";
    field.textContent = "Empresa / Ubicación inicial: " + company;
    field.style.cssText = "display:block;position:relative;margin:0 0 8px;" +
      "font:bold 12px Arial,sans-serif;color:#000;overflow-wrap:anywhere";
    documentRoot.body.prepend(field);
  }

  function isBoixeresClient(client) {
    return String(client || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ").trim().toUpperCase().includes("TMB BOIXERES");
  }

  function clientFromWorkorder(documentRoot) {
    const fieldValue = String(documentRoot?.getElementById("mx47-tb")?.value || "").trim();
    if (fieldValue) return fieldValue;

    const labels = [...(documentRoot?.querySelectorAll?.("td, span, label, div") || [])]
      .filter(element => (!element.getClientRects || element.getClientRects().length) &&
        /^cliente\s*:?$/i.test((element.innerText || element.textContent || "")
          .replace(/\s+/g, " ").trim()));
    for (const label of labels) {
      const row = label.closest?.("tr");
      if (row) return String(row.innerText || row.textContent || "").trim();
    }
    return "";
  }

  const logic = { pageKind, containsOt, canPrintStatus, labeledFieldValue,
    isBoixeresClient, isAtmClient, clientFromWorkorder, originCompanyText,
    includeReportOrigin, originCompanyFromWorkorder, insertOriginCompany,
    BIRT_RESOURCE_NOTICE, removeBirtResourceNotices };
  root.MaximoPartLogic = logic;
  if (typeof module !== "undefined" && module.exports) module.exports = logic;
})(typeof globalThis !== "undefined" ? globalThis : this);
