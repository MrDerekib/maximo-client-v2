"use strict";
const PANEL_VISIBILITY_KEY = "mdSidePanelVisibility";
let panelVisibilityUpdates = Promise.resolve();
function panelContextKey(info) {
  return `${info.windowId}:${Number.isInteger(info.tabId) ? info.tabId : "global"}`;
}
function panelMatchesTab(context, tab) {
  return context.windowId === tab.windowId &&
    (!Number.isInteger(context.tabId) || context.tabId === tab.id);
}
async function panelIsOpen(tab) {
  await panelVisibilityUpdates.catch(() => {});
  const stored = await chrome.storage.session.get(PANEL_VISIBILITY_KEY);
  return Object.values(stored[PANEL_VISIBILITY_KEY] || {}).some(context => panelMatchesTab(context, tab));
}
function setPanelVisibility(info, open) {
  if (!Number.isInteger(info.windowId) || (info.path && info.path !== "sidepanel.html")) return Promise.resolve();
  const context = {windowId: info.windowId};
  if (Number.isInteger(info.tabId)) context.tabId = info.tabId;
  panelVisibilityUpdates = panelVisibilityUpdates.catch(() => {}).then(async () => {
    const stored = await chrome.storage.session.get(PANEL_VISIBILITY_KEY);
    const contexts = {...(stored[PANEL_VISIBILITY_KEY] || {})};
    if (open) contexts[panelContextKey(context)] = context;
    else delete contexts[panelContextKey(context)];
    await chrome.storage.session.set({[PANEL_VISIBILITY_KEY]: contexts});
    const tabs = await chrome.tabs.query({windowId: context.windowId});
    await Promise.allSettled(tabs.map(tab => chrome.tabs.sendMessage(tab.id, {
      type: "PANEL_VISIBILITY", open: Object.values(contexts).some(item => panelMatchesTab(item, tab))
    })));
  });
  return panelVisibilityUpdates;
}
if (typeof chrome !== "undefined" && chrome.sidePanel) {
  chrome.sidePanel.onOpened?.addListener(info => { setPanelVisibility(info, true).catch(console.error); });
  chrome.sidePanel.onClosed?.addListener(info => { setPanelVisibility(info, false).catch(console.error); });
}
// Some Edge builds expose the native events but do not fire them reliably.
// A visible panel also holds a connection; destroying/hiding it restores the launcher.
if (typeof chrome !== "undefined" && chrome.runtime?.onConnect) {
  const panels = new Map();
  const updateWindow = windowId => {
    if (!Number.isInteger(windowId)) return;
    const open = [...panels.values()].some(panel => panel.windowId === windowId && panel.visible);
    setPanelVisibility({windowId}, open).catch(console.error);
  };
  chrome.runtime.onConnect.addListener(port => {
    if (port.name !== "md-panel-presence" || port.sender?.id !== chrome.runtime.id ||
        port.sender?.url !== chrome.runtime.getURL("sidepanel.html")) return;
    panels.set(port, {});
    port.onMessage.addListener(message => {
      if (!Number.isInteger(message.windowId)) return;
      const previous = panels.get(port)?.windowId;
      panels.set(port, {windowId:message.windowId, visible:message.visible === true});
      if (previous !== message.windowId) updateWindow(previous);
      updateWindow(message.windowId);
    });
    port.onDisconnect.addListener(() => {
      const windowId = panels.get(port)?.windowId;
      panels.delete(port); updateWindow(windowId);
    });
  });
}
if (typeof module !== "undefined") module.exports = {panelIsOpen, setPanelVisibility, PANEL_VISIBILITY_KEY};
