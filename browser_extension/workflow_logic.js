(function (root) {
  "use strict";

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

  const logic = { pageKind, containsOt, canPrintStatus };
  root.MaximoPartLogic = logic;
  if (typeof module !== "undefined" && module.exports) module.exports = logic;
})(typeof globalThis !== "undefined" ? globalThis : this);
