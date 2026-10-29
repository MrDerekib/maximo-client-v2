const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const logic = require("../workflow_logic.js");
const content = fs.readFileSync(require.resolve("../content.js"), "utf8");

// Each document has new DOM nodes, while tab session storage survives reloads.
// Run the real content script and capture START before any report is generated.
async function loadDocument(storage, rootPreference) {
  const elements = new Map();
  const intervals = [];
  const messages = [];
  const field = value => ({ value, getClientRects: () => [1] });
  elements.set("mx45-tb", field("4384025"));
  elements.set("mx73-tb", field("ISSUE"));
  const document = {
    documentElement: { dataset: rootPreference === undefined ? {} :
      { maximoCloseReportTabs: rootPreference } },
    getElementById: id => elements.get(id),
    querySelectorAll: () => [],
    createElement: () => ({ dataset: {}, style: {},
      addEventListener(_event, handler) { this.click = handler; } }),
    body: { contains: () => true,
      appendChild(element) { elements.set(element.id, element); } }
  };
  vm.runInNewContext(content, {
    MaximoPartLogic: logic, document,
    location: { href: "https://eam.indraweb.net/maximo/ui/" },
    sessionStorage: { getItem: key => storage.get(key) ?? null },
    setInterval(fn) { intervals.push(fn); return intervals.length; },
    clearInterval() {}, setTimeout() {}, clearTimeout() {}, console,
    chrome: { runtime: { onMessage: { addListener() {} },
      async sendMessage(message) {
        messages.push(message);
        return { ok: false, error: "Stop before generating or printing a report" };
      } } }
  });
  intervals[0]();
  await new Promise(resolve => setImmediate(resolve));
  return { button: elements.get("maximo-desktop-print-part"), messages };
}

test("printing still requests window cleanup after an OT closure reload", async () => {
  const storage = new Map([["maximoDesktop.closeReportTabs", "true"]]);
  const original = await loadDocument(storage, "true");
  await original.button.click();
  assert.equal(original.messages[0].closeTabs, true);
  // Both validation reloads remove the original document and its dataset.
  await loadDocument(storage);
  const reloaded = await loadDocument(storage);
  await reloaded.button.click();
  assert.equal(reloaded.messages[0].type, "START");
  assert.equal(reloaded.messages[0].closeTabs, true);
});

test("a new session or dialog mode leaves report windows open", async () => {
  for (const storage of [new Map(), new Map([["maximoDesktop.closeReportTabs", "false"]])]) {
    const page = await loadDocument(storage);
    await page.button.click();
    assert.equal(page.messages[0].closeTabs, false);
  }
});

test("explicit desktop overrides and PDF requests preserve their cleanup policy", async () => {
  const storage = new Map([["maximoDesktop.closeReportTabs", "true"]]);
  const overridden = await loadDocument(storage);
  overridden.button.dataset.maximoCloseReportTabs = "false";
  await overridden.button.click();
  assert.equal(overridden.messages[0].closeTabs, false);
  const pdf = await loadDocument(storage);
  pdf.button.dataset.maximoReportAction = "pdf";
  await pdf.button.click();
  assert.equal(pdf.messages[0].outputFormat, "pdf");
  assert.equal(pdf.messages[0].closeTabs, false);
});
