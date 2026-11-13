"use strict";
(() => {
  if (!chrome.runtime.connect) return;
  let port, windowId, leaving = false;
  const publish = () => {
    if (port && windowId !== undefined)
      try { port.postMessage({windowId, visible:!document.hidden && !leaving}); } catch (_) {}
  };
  function connect() {
    if (leaving) return;
    port = chrome.runtime.connect({name:"md-panel-presence"});
    port.onDisconnect.addListener(() => { port = null; if (!leaving) setTimeout(connect,500); });
    chrome.windows.getCurrent().then(window => { windowId = window.id; publish(); }).catch(() => {});
  }
  document.addEventListener("visibilitychange",publish);
  window.addEventListener("pagehide",() => {leaving=true;publish();port?.disconnect();});
  window.addEventListener("pageshow",() => {if (leaving) {leaving=false;connect();}});
  connect();
})();
