const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const logic = require("../workflow_logic.js");
const content = fs.readFileSync(require.resolve("../content.js"), "utf8");

// Each document has new DOM nodes, while tab session storage survives reloads.
// Run the real content script and capture START before any report is generated.
async function loadDocument(storage, rootPreference, client = "TMB", origin = "", description = "") {
  const elements = new Map();
  const intervals = [];
  const messages = [];
  const field = value => ({ value, getClientRects: () => [1] });
  elements.set("mx45-tb", field("4384025"));
  elements.set("mx73-tb", field("ISSUE"));
  elements.set("mx47-tb", field(client));
  elements.set("mx88-tb", field(origin));
  elements.set("mx88-tb2", field(description));
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


test("only verified discarded OTs in this session request the HTML stamp", async () => {
  for (const [stored, expected] of [[undefined,false],['["4384025"]',true],['["4384026"]',false],['bad json',false]]) {
    const page=await loadDocument(new Map(stored ? [["maximoDesktop.discardedOts",stored]] : []));
    await page.button.click();
    assert.equal(page.messages[0].irreparableStamp,expected);
  }
  const page=await loadDocument(new Map([["maximoDesktop.discardedOts",'["4384025"]']]));
  page.button.dataset.maximoReportAction="pdf";
  await page.button.click();
  assert.equal(page.messages[0].irreparableStamp,false);
});

test("ATM sends the company from the current work order and refuses a blank location", async () => {
  const page = await loadDocument(new Map(), undefined, "ATM", " SARBUS ");
  await page.button.click();
  assert.equal(page.messages[0].originCompany, "SARBUS");
  const missing = await loadDocument(new Map(), undefined, "ATM");
  await missing.button.click();
  assert.equal(missing.messages.length, 0);
  assert.match(missing.button.textContent, /empresa o ubicación inicial/);
  const settings = new Map([["maximoDesktop.reportOrigin", '{"mode":"disabled"}']]);
  const disabled = await loadDocument(settings, undefined, "ATM", "SARBUS");
  await disabled.button.click();
  assert.equal(disabled.messages[0].includeOriginCompany, false);
  assert.equal(disabled.messages[0].originCompany, "");
  settings.set("maximoDesktop.reportOrigin", '{"mode":"selected","projects":["FGC"]}');
  const selected = await loadDocument(settings, undefined, "FGC", "TALLER");
  await selected.button.click();
  assert.equal(selected.messages[0].includeOriginCompany, true);
  assert.equal(selected.messages[0].originCompany, "TALLER");
});

test("Line 9 sends the initial location description instead of its inventory code", async () => {
  const storage = new Map([["maximoDesktop.reportOrigin", '{"mode":"selected","projects":["Línea 9"]}']]);
  const location = "Stock Lìnia 9 - Tramo I";
  for (const client of ["LINEA-9", "CL9T1SVI", "CL9T2SVI"]) {
    const page = await loadDocument(storage, undefined, client, "ISTOCK", location);
    await page.button.click();
    assert.equal(page.messages[0].includeOriginCompany, true);
    assert.equal(page.messages[0].originCompany, location);
  }
  const fallback = await loadDocument(new Map(), undefined, "LINEA-9", "ISTOCK");
  await fallback.button.click();
  assert.equal(fallback.messages[0].originCompany, "ISTOCK");
  storage.set("maximoDesktop.reportOrigin", '{"mode":"selected","projects":["ATM"]}');
  const excluded = await loadDocument(storage, undefined, "LINEA-9", "ISTOCK", location);
  await excluded.button.click();
  assert.equal(excluded.messages[0].includeOriginCompany, false);
});

test("the HTML stamp is inserted once and leaves BIRT data intact", () => {
  const {insert}=require("../report_stamp.js");
  const nodes=new Map();
  const original={textContent:"original BIRT report"};
  const doc={getElementById:id=>nodes.get(id),
    createElement:()=>({style:{},setAttribute(){}}),
    body:{appendChild(node){nodes.set(node.id,node);}}};
  nodes.set("birt-report",original);
  insert(doc);insert(doc);
  assert.equal(nodes.size,2);
  assert.equal(nodes.get("birt-report"),original);
  const stamp=nodes.get("md-irreparable-stamp");
  assert.equal(stamp.textContent,"IRREPARABLE");
  assert.match(stamp.style.cssText,/color:#b3151b/);
});


test("output printing applies the stamp before print, and never for ordinary reports", async () => {
  for(const enabled of [false,true]) {
    const events=[];
    const intervals=[];
    const warning = { textContent: logic.BIRT_RESOURCE_NOTICE, children: [] };
    vm.runInNewContext(content,{
      MaximoPartLogic:logic,MaximoReportStamp:{insert(){events.push("stamp");}},
      document:{
        getElementById: () => null,
        createElement: () => ({ style: {} }),
        body: { innerText: "OT 4443840", prepend(node) { events.push(node.textContent); } },
        querySelectorAll: selector => selector === "body *" ? [warning] : []
      },
      location:{href:"https://eam.indraweb.net/maximo/output?__report=parte_reparacion.rptdesign"},
      window:{print(){assert.equal(warning.textContent, ""); events.push("print");}},
      chrome:{runtime:{async sendMessage(message){
        events.push(message.type);
        return {ok:true,value:message.type==="CLAIM_OUTPUT" ?
          {ot:"4443840",jobId:"test",irreparableStamp:enabled,originCompany:enabled ? "SARBUS" : ""}:
          {closeTabs:false}};
      }}},console,
      setInterval(fn){intervals.push(fn);return intervals.length;},clearInterval(){}
    });
    await new Promise(resolve=>setImmediate(resolve));
    intervals[0]();
    await new Promise(resolve=>setImmediate(resolve));
    assert.deepEqual(events,enabled ? ["CLAIM_OUTPUT","Empresa / Ubicación inicial: SARBUS","stamp","print","FINISH"]:
      ["CLAIM_OUTPUT","print","FINISH"]);
  }
});
