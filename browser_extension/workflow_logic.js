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

  function projectKey(client) {
    return String(client || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/^cliente\s*:\s*|^cliente\s+/i, "").trim().replace(/[\s_-]+/g, " ").toUpperCase();
  }

  function isLine9Group(key) {
    return /^(?:L9|LI(?:NEA|NIA) ?9)$/.test(key);
  }

  function isLine9Client(client) {
    const key = projectKey(client);
    return isLine9Group(key) || /^CL9T[12]SVI$/.test(key);
  }

  function includeReportOrigin(client, preference) {
    const mode = preference?.mode;
    if (mode === "disabled") return false;
    if (mode === "all") return true;
    if (mode !== "selected" || !Array.isArray(preference.projects))
      return isAtmClient(client) || isLine9Client(client);
    const key = projectKey(client);
    return preference.projects.filter(project => typeof project === "string").map(projectKey).some(project =>
      project === key || (project === "ATM" && isAtmClient(client)) ||
      (isLine9Group(project) && isLine9Client(client)));
  }

  function originCompanyText(value) {
    return typeof value === "string" ? value.replace(/\s+/g, " ").trim().slice(0, 200) : "";
  }

  function originCompanyFromWorkorder(documentRoot) {
    const description = [...(documentRoot.querySelectorAll?.("input[aria-label]") || [])]
      .find(field => field.getAttribute("aria-label")?.trim().toLocaleLowerCase() ===
        "descripción de ubicación inicial" && (!field.getClientRects || field.getClientRects().length));
    const locationDescription = originCompanyText(description?.value) ||
      originCompanyText(labeledFieldValue(documentRoot, "Descripción de ubicación inicial", "mx88-tb2"));
    return locationDescription.replace(/^empresa(?:\s*:\s*|\s+|$)/i, "");
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
    if (!company) return;
    const existing = documentRoot.getElementById("md-origin-company");
    if (existing?.tagName === "TR") {
      existing.cells[1].textContent = company;
      return;
    }
    const normalize = text => String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ").trim().toLowerCase();
    const leaves = [...documentRoot.querySelectorAll("div, span, td, th")].filter(e => !e.children.length);
    const headings = leaves.filter(e => normalize(e.textContent) === "datos del equipo");
    const candidates = headings.map(heading => {
      const table = heading.closest("table");
      if (!table) return null;
      const rows = [...table.rows].filter(row => row.closest("table") === table);
      const start = rows.indexOf(heading.closest("tr"));
      const end = rows.findIndex((row, i) => i > start &&
        normalize(row.textContent) === "datos orden reparacion");
      const clientRows = rows.slice(start + 1, end).filter(row =>
        [...row.cells].some(cell => normalize(cell.textContent) === "cliente:"));
      if (end < 0 || clientRows.length !== 1) return null;
      return { row: rows[end], clientRow: clientRows[0] };
    }).filter(Boolean);
    if (candidates.length !== 1)
      throw new Error("No se pudo identificar «Datos del equipo» para insertar el origen en el parte.");
    const { row, clientRow } = candidates[0];
    const columns = [...clientRow.cells].reduce((total, cell) => total + cell.colSpan, 0);
    if (columns < 2) throw new Error("La tabla del equipo no tiene la estructura esperada.");
    const field = documentRoot.createElement("tr");
    field.id = "md-origin-company";
    field.style.verticalAlign = "top";
    const label = documentRoot.createElement("td"), value = documentRoot.createElement("td");
    label.className = clientRow.cells[0].className;
    value.className = clientRow.cells[1].className;
    label.style.cssText = "text-align:left;font-weight:bold";
    value.style.cssText = "text-align:left;overflow-wrap:anywhere";
    label.textContent = "Origen:";
    value.textContent = company;
    value.colSpan = columns - 1;
    field.append(label, value);
    row.parentNode.insertBefore(field, row);
    if (existing) existing.remove();
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
