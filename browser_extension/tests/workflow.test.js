const test = require("node:test");
const assert = require("node:assert/strict");

const { pageKind, containsOt, canPrintStatus, isBoixeresClient,
  clientFromWorkorder } = require("../workflow_logic.js");

test("only the Maximo WO page and the repair report windows are handled", () => {
  assert.equal(pageKind("https://eam.indraweb.net/maximo/ui/?event=loadapp"), "workorder");
  assert.equal(pageKind("https://eam.indraweb.net/maximo/report?__report=parte_reparacion.rptdesign"), "viewer");
  assert.equal(pageKind("https://eam.indraweb.net/maximo/output?__report=parte_reparacion.rptdesign"), "output");
  assert.equal(pageKind("https://eam.indraweb.net/maximo/report?__report=otro.rptdesign"), null);
  assert.equal(pageKind("https://example.com/maximo/ui/"), null);
});

test("the report must contain the exact OT, not a substring", () => {
  assert.equal(containsOt("Nº orden: 4228010", "4228010"), true);
  assert.equal(containsOt("Nº orden: 14228010", "4228010"), false);
  assert.equal(containsOt("Nº orden: 42280109", "4228010"), false);
  assert.equal(containsOt("Nº orden: 4228011", "4228010"), false);
});

test("a repair report remains available after warehouse closes the OT", () => {
  assert.equal(canPrintStatus("ISSUE"), true);
  assert.equal(canPrintStatus("CLOSE"), true);
  assert.equal(canPrintStatus(" close "), true);
  assert.equal(canPrintStatus("APPR"), false);
  assert.equal(canPrintStatus(""), false);
});

test("Boixeres client recognition ignores case, accents, and repeated spaces", () => {
  assert.equal(isBoixeresClient("TMB BOIXERES"), true);
  assert.equal(isBoixeresClient("  tmb   boixerès  "), true);
  assert.equal(isBoixeresClient("TMB"), false);
});

test("the exact mx47-tb field takes priority, with a Cliente row fallback", () => {
  assert.equal(clientFromWorkorder({ getElementById: id =>
    id === "mx47-tb" ? { value: "TMB BOIXERES" } : null }), "TMB BOIXERES");
  assert.equal(clientFromWorkorder({ getElementById: () => null }), "");
  const label = {
    innerText: "Cliente:",
    getClientRects: () => [1],
    closest: () => ({ innerText: "Cliente: TMB BOIXERES" })
  };
  assert.equal(clientFromWorkorder({ getElementById: () => null,
    querySelectorAll: () => [label] }), "Cliente: TMB BOIXERES");
});

function chromeHarness() {
  const session = new Map();
  const sent = [];
  const executions = [];
  const downloads = [];
  const removedTabs = [];
  let updatedListener;
  global.chrome = {
    storage: { session: {
      async get(key) { return { [key]: session.get(key) }; },
      async set(values) { for (const [key, value] of Object.entries(values)) session.set(key, value); },
      async remove(key) { session.delete(key); }
    } },
    tabs: {
      async sendMessage(tabId, message) { sent.push({ tabId, message }); },
      async remove(tabId) { removedTabs.push(tabId); },
      onUpdated: { addListener(listener) { updatedListener = listener; } }
    },
    downloads: { async download(options) { downloads.push(options); return 1; } },
    scripting: { async executeScript(options) {
      executions.push(options);
      return [{ result: { clicked: true, filled: true, buttonId: "mx654-pb", submitted: true,
        updated: true, maximoChanged: true } }];
    } },
    runtime: { onMessage: { addListener() {} } }
  };
  delete require.cache[require.resolve("../service_worker.js")];
  return { ...require("../service_worker.js"), session, sent, executions,
    downloads, removedTabs, updated: (...args) => updatedListener(...args) };
}

test("Maximo's report menu is clicked in the page's JavaScript world", async () => {
  const { handleMessage, executions } = chromeHarness();
  const source = { tab: { id: 1 } };
  const started = await handleMessage({ type: "START", ot: "4228010" }, source);
  await handleMessage({ type: "CLICK_REPORT_MENU", jobId: started.jobId }, source);
  assert.equal(executions.length, 1);
  assert.equal(executions[0].world, "MAIN");
  assert.equal(executions[0].target.tabId, 1);
  await handleMessage({ type: "CLICK_REPAIR_REPORT", jobId: started.jobId }, source);
  assert.equal(executions.length, 2);
  assert.equal(executions[1].world, "MAIN");
  assert.equal(executions[1].target.tabId, 1);
  await assert.rejects(
    handleMessage({ type: "CLICK_REPORT_MENU", jobId: started.jobId }, { tab: { id: 9 } }),
    /no pertenece/
  );
  await assert.rejects(
    handleMessage({ type: "CLICK_REPAIR_REPORT", jobId: started.jobId }, { tab: { id: 9 } }),
    /no pertenece/
  );
});

test("the repair report click targets Maximo's report-row label", async () => {
  const { handleMessage, executions } = chromeHarness();
  const source = { tab: { id: 1 } };
  const { jobId } = await handleMessage({ type: "START", ot: "4228010" }, source);
  await handleMessage({ type: "CLICK_REPAIR_REPORT", jobId }, source);
  const clicked = [];
  const events = [];
  const label = {
    id: "mx1015_tdrow_[C:0]_ttxt-lb[R:1]",
    textContent: "Parte de reparación",
    getClientRects: () => [1],
    scrollIntoView: () => {},
    focus: () => {},
    dispatchEvent: event => events.push(event.type),
    click: () => clicked.push("Parte de reparación")
  };
  const previousDocument = global.document;
  const previousMouseEvent = global.MouseEvent;
  const previousPointerEvent = global.PointerEvent;
  global.MouseEvent = class { constructor(type) { this.type = type; } };
  global.PointerEvent = class { constructor(type) { this.type = type; } };
  global.document = { getElementById: () => ({
    getClientRects: () => [1],
    querySelectorAll: () => [label]
  }) };
  try {
    assert.deepEqual(executions[0].func(), { clicked: true, targetId: label.id });
    assert.deepEqual(clicked, ["Parte de reparación"]);
    assert.deepEqual(events, ["pointerdown", "mousedown", "pointerup", "mouseup"]);
  } finally {
    global.document = previousDocument;
    global.MouseEvent = previousMouseEvent;
    global.PointerEvent = previousPointerEvent;
  }
});

test("the request fills the OT and clicks Enviar in separate page-script calls", async () => {
  const { handleMessage, executions } = chromeHarness();
  const source = { tab: { id: 1 } };
  const { jobId } = await handleMessage({ type: "START", ot: "4228010" }, source);
  assert.deepEqual(await handleMessage({ type: "FILL_REPORT_OT", jobId }, source),
    { filled: true });
  await handleMessage({ type: "CLICK_REPORT_SUBMIT", jobId, buttonId: "mx654-pb" }, source);
  assert.equal(executions[0].world, "MAIN");
  assert.deepEqual(executions[0].args, ["4228010"]);
  assert.equal(executions[1].world, "MAIN");
  assert.deepEqual(executions[1].args, ["mx654-pb"]);
  const previousDocument = global.document;
  const previousInput = global.HTMLInputElement;
  const previousMouseEvent = global.MouseEvent;
  const previousPointerEvent = global.PointerEvent;
  const previousKeyboardEvent = global.KeyboardEvent;
  const events = [];
  let clicked = false;
  class Input {
    set value(value) { this.currentValue = value; }
    get value() { return this.currentValue || ""; }
  }
  const field = new Input();
  Object.assign(field, {
    getClientRects: () => [1],
    getAttribute: name => name === "aria-labelledby" ? "mx2042-lb" :
      name === "db" ? "mx654-pb" : null,
    dispatchEvent: event => events.push(event.type),
    blur: () => {},
    focus: () => {},
    select: () => {}
  });
  const submit = {
    value: "Enviar", getClientRects: () => [1],
    scrollIntoView: () => {}, dispatchEvent: event => events.push(event.type),
    click: () => { clicked = true; }
  };
  global.HTMLInputElement = Input;
  global.MouseEvent = class { constructor(type) { this.type = type; } };
  global.PointerEvent = class { constructor(type) { this.type = type; } };
  global.KeyboardEvent = class { constructor(type) { this.type = type; } };
  global.document = {
    execCommand: (command, _showUi, value) => {
      assert.equal(command, "insertText");
      field.value = value;
      events.push("input");
      return true;
    },
    querySelectorAll: () => [field],
    getElementById: id => id === "mx2042-lb" ? { textContent: "Work order number:" } :
      id === "mx654-pb" ? submit : null
  };
  try {
    assert.deepEqual(executions[0].func("4228010"), { filled: true, buttonId: "mx654-pb" });
    assert.equal(field.value, "4228010");
    assert.equal(clicked, false);
    assert.deepEqual(executions[1].func("mx654-pb"), { submitted: true });
    assert.equal(clicked, true);
    assert.deepEqual(events, ["input", "keyup", "change", "pointerdown", "mousedown", "pointerup", "mouseup"]);
  } finally {
    global.document = previousDocument;
    global.HTMLInputElement = previousInput;
    global.MouseEvent = previousMouseEvent;
    global.PointerEvent = previousPointerEvent;
    global.KeyboardEvent = previousKeyboardEvent;
  }
});

test("a missing click result is not misreported as a missing Enviar button", async () => {
  const { handleMessage } = chromeHarness();
  const source = { tab: { id: 1 } };
  const { jobId } = await handleMessage({ type: "START", ot: "4228010" }, source);
  chrome.scripting.executeScript = async () => [{ result: undefined }];
  assert.deepEqual(await handleMessage({ type: "CLICK_REPORT_SUBMIT", jobId,
    buttonId: "mx654-pb" }, source), { submitted: true });
});

test("a missing fill result is left for the source page to verify", async () => {
  const { handleMessage } = chromeHarness();
  const source = { tab: { id: 1 } };
  const { jobId } = await handleMessage({ type: "START", ot: "4228010" }, source);
  chrome.scripting.executeScript = async () => [{ result: undefined }];
  assert.deepEqual(await handleMessage({ type: "FILL_REPORT_OT", jobId }, source),
    { filled: true });
});

test("the source, viewer and HTML output form one print job", async () => {
  const { handleMessage, session, sent, JOB_KEY } = chromeHarness();
  const source = { tab: { id: 1 } };
  const viewer = { tab: { id: 2, openerTabId: 1 } };
  const output = { tab: { id: 3, openerTabId: 2 } };
  const started = await handleMessage({ type: "START", ot: "4228010" }, source);
  assert.equal((await handleMessage({ type: "CLAIM_VIEWER" }, viewer)).ot, "4228010");
  assert.equal((await handleMessage({ type: "CLAIM_OUTPUT" }, output)).ot, "4228010");
  await handleMessage({ type: "FINISH", jobId: started.jobId }, output);
  assert.equal(session.has(JOB_KEY), false);
  assert.equal(sent.at(-1).tabId, 1);
  assert.match(sent.at(-1).message.text, /Parte preparado/);
});

test("TMB BOIXERES HTML jobs advance from the standard part to the stripped variant", async () => {
  const { handleMessage, session, sent, removedTabs, JOB_KEY } = chromeHarness();
  const source = { tab: { id: 1 } };
  const firstViewer = { tab: { id: 2, openerTabId: 1 } };
  const firstOutput = { tab: { id: 3, openerTabId: 2 } };
  const secondViewer = { tab: { id: 4, openerTabId: 1 } };
  const secondOutput = { tab: { id: 5, openerTabId: 4 } };
  const started = await handleMessage({ type: "START", ot: "4228010", outputFormat: "html",
    client: "TMB BOIXERES" }, source);
  assert.equal(started.variantCount, 2);
  assert.equal((await handleMessage({ type: "CLAIM_VIEWER" }, firstViewer)).variantIndex, 0);
  await handleMessage({ type: "CLAIM_OUTPUT" }, firstOutput);
  assert.deepEqual(await handleMessage({ type: "FINISH", jobId: started.jobId }, firstOutput),
    { ok: true, nextVariant: true, closeTabs: false });
  assert.equal(session.get(JOB_KEY).variantIndex, 1);
  assert.equal(session.get(JOB_KEY).viewerTabId, null);
  assert.equal(sent.at(-1).message.type, "NEXT_VARIANT");
  assert.equal((await handleMessage({ type: "CLAIM_VIEWER" }, secondViewer)).variantIndex, 1);
  await handleMessage({ type: "CLAIM_OUTPUT" }, secondOutput);
  await handleMessage({ type: "FINISH", jobId: started.jobId }, secondOutput);
  assert.equal(session.has(JOB_KEY), false);
  assert.equal(sent.at(-1).message.type, "STATUS");
  assert.deepEqual(removedTabs, [], "manual-dialog jobs leave both BIRT tabs open");
});

test("direct-print cleanup closes the BIRT tab only when enabled", async () => {
  const { handleMessage, removedTabs, session, JOB_KEY } = chromeHarness();
  const source = { tab: { id: 1 } };
  const viewer = { tab: { id: 2, openerTabId: 1 } };
  const output = { tab: { id: 3, openerTabId: 2 } };
  const started = await handleMessage({ type: "START", ot: "4228010", outputFormat: "html",
    closeTabs: true }, source);
  await handleMessage({ type: "CLAIM_VIEWER" }, viewer);
  await handleMessage({ type: "CLAIM_OUTPUT" }, output);
  assert.deepEqual(await handleMessage({ type: "FINISH", jobId: started.jobId }, output),
    { ok: true, closeTabs: true });
  assert.deepEqual(removedTabs, [2]);
  assert.equal(session.has(JOB_KEY), false);
});

test("direct Boixeres printing closes each BIRT tab between both variants", async () => {
  const { handleMessage, removedTabs, session, JOB_KEY } = chromeHarness();
  const source = { tab: { id: 1 } };
  const firstViewer = { tab: { id: 2, openerTabId: 1 } };
  const firstOutput = { tab: { id: 3, openerTabId: 2 } };
  const secondViewer = { tab: { id: 4, openerTabId: 1 } };
  const secondOutput = { tab: { id: 5, openerTabId: 4 } };
  const started = await handleMessage({ type: "START", ot: "4228010", outputFormat: "html",
    client: "TMB BOIXERES", closeTabs: true }, source);
  await handleMessage({ type: "CLAIM_VIEWER" }, firstViewer);
  await handleMessage({ type: "CLAIM_OUTPUT" }, firstOutput);
  assert.deepEqual(await handleMessage({ type: "FINISH", jobId: started.jobId }, firstOutput),
    { ok: true, nextVariant: true, closeTabs: true });
  assert.deepEqual(removedTabs, [2]);
  await handleMessage({ type: "CLAIM_VIEWER" }, secondViewer);
  await handleMessage({ type: "CLAIM_OUTPUT" }, secondOutput);
  assert.deepEqual(await handleMessage({ type: "FINISH", jobId: started.jobId }, secondOutput),
    { ok: true, closeTabs: true });
  assert.deepEqual(removedTabs, [2, 4]);
  assert.equal(session.has(JOB_KEY), false);
});

test("PDF jobs stay single even for TMB BOIXERES", async () => {
  const { handleMessage } = chromeHarness();
  const job = await handleMessage({ type: "START", ot: "4228010", outputFormat: "pdf",
    client: "TMB BOIXERES" }, { tab: { id: 1 } });
  assert.equal(job.variantCount, 1);
});

test("repair report variants set Maximo's include-technician parameter in the page context", async () => {
  const { handleMessage, executions } = chromeHarness();
  const source = { tab: { id: 1 } };
  const { jobId, variantCount } = await handleMessage({ type: "START", ot: "4228010",
    outputFormat: "html", client: "TMB BOIXERES" }, source);
  assert.equal(variantCount, 2);
  assert.deepEqual(await handleMessage({ type: "SET_REPAIR_INFO", jobId, value: "N" }, source),
    { updated: true, maximoChanged: true });
  assert.equal(executions[0].world, "MAIN");
  assert.deepEqual(executions[0].args, ["N"]);
});

test("repair parameter uses Maximo's YORN lookup to choose N", async () => {
  const { handleMessage, executions } = chromeHarness();
  const source = { tab: { id: 1 } };
  const { jobId } = await handleMessage({ type: "START", ot: "4228010",
    outputFormat: "html", client: "TMB BOIXERES" }, source);
  await handleMessage({ type: "SET_REPAIR_INFO", jobId, value: "N" }, source);

  let lookupOpened = false;
  let selected = false;
  const field = {
    id: "mx396-ta", value: "S", title: "S", attributes: { linkedimage: "mx396-img" },
    getClientRects: () => [1], getAttribute(name) { return this.attributes[name] || null; },
    closest() { return null; }
  };
  const option = {
    textContent: "N", innerText: "N", getClientRects: () => [1],
    closest: () => null, scrollIntoView() {}, click() {
      selected = true;
      field.value = "N";
      field.title = "N";
      field.attributes.changed_by_user = "true";
    }
  };
  const popup = { contains: element => element === field ? false : true,
    getClientRects: () => [1], querySelectorAll: () => [option] };
  const lookup = { getClientRects: () => [1], click() { lookupOpened = true; } };
  const label = { htmlFor: "mx396-ta", textContent: "Incluir nombre y tiempo reparacion:" };
  const previousDocument = global.document;
  global.document = {
    querySelectorAll(selector) {
      if (selector === "input, textarea, select") return [field];
      if (selector === "label[for]") return [label];
      if (selector.includes("role='dialog'")) return lookupOpened ? [popup] : [];
      return [];
    },
    getElementById(id) { return id === "mx396-img" ? lookup : null; }
  };
  try {
    assert.deepEqual(await executions[0].func("N"), {
      updated: true, maximoChanged: true, method: "lookup"
    });
    assert.equal(lookupOpened, true);
    assert.equal(selected, true);
  } finally {
    global.document = previousDocument;
  }
});

test("PDF output requests Save As for BIRT's native PDF from the correct viewer", async () => {
  const { handleMessage, handlePdfOutput, session, downloads, JOB_KEY } = chromeHarness();
  const source = { tab: { id: 1 } };
  const viewer = { tab: { id: 2, openerTabId: 1 } };
  await handleMessage({ type: "START", ot: "4228010", outputFormat: "pdf" }, source);
  assert.equal((await handleMessage({ type: "CLAIM_VIEWER" }, viewer)).outputFormat, "pdf");
  const url = "https://eam.indraweb.net/maximo/output?__report=parte_reparacion.rptdesign&__requestid=123";
  await handlePdfOutput(3, { url }, { id: 3, openerTabId: 99, url });
  assert.equal(downloads.length, 0);
  await handlePdfOutput(3, { url }, { id: 3, openerTabId: 2, url });
  assert.deepEqual(downloads, [{ url, filename: "parte_reparacion_OT4228010.pdf",
    saveAs: true, conflictAction: "uniquify" }]);
  assert.equal(session.has(JOB_KEY), false);
});

test("an unrelated report window cannot claim or finish the job", async () => {
  const { handleMessage } = chromeHarness();
  const started = await handleMessage({ type: "START", ot: "4228010" }, { tab: { id: 1 } });
  await assert.rejects(
    handleMessage({ type: "CLAIM_VIEWER" }, { tab: { id: 9, openerTabId: 8 } }),
    /no pertenece/
  );
  await handleMessage({ type: "CLAIM_VIEWER" }, { tab: { id: 2, openerTabId: 1 } });
  await handleMessage({ type: "CLAIM_OUTPUT" }, { tab: { id: 3, openerTabId: 2 } });
  await assert.rejects(
    handleMessage({ type: "FINISH", jobId: started.jobId }, { tab: { id: 9 } }),
    /no pertenece/
  );
});
