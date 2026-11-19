"use strict";
const PANEL_MESSAGES = ["OPEN_PANEL", "PANEL_CONTEXT", "PANEL_ACTION", "PANEL_LAUNCHER_STATE"];
function isMaximoWorkorderUrl(raw) {
  try { const url=new URL(raw);return url.origin==="https://eam.indraweb.net"&&/^\/maximo\/ui\/?$/i.test(url.pathname); }
  catch(_){return false;}
}
async function handlePanelMessage(message,sender) {
  if(message.type==="PANEL_LAUNCHER_STATE") {
    if(!sender.tab?.id||!isMaximoWorkorderUrl(sender.tab.url))throw new Error("Ficha de Maximo no válida.");
    return {open:await panelIsOpen(sender.tab)};
  }
  if(message.type==="OPEN_PANEL") {
    if(!sender.tab?.id||!isMaximoWorkorderUrl(sender.tab.url))throw new Error("Abre el panel desde una ficha de Maximo.");
    if(!chrome.sidePanel?.open)throw new Error("Esta versión de Edge no admite el panel lateral. Actualiza Edge.");
    // Keep open() directly in the message's user gesture; no await before it.
    await chrome.sidePanel.open({tabId:sender.tab.id});
    return {opened:true};
  }
  if(sender.id!==chrome.runtime.id||sender.url!==chrome.runtime.getURL("sidepanel.html"))
    throw new Error("Solicitud de panel no válida.");
  if(!Number.isInteger(message.windowId))throw new Error("No se ha identificado la ventana de Edge.");
  const [tab]=await chrome.tabs.query({active:true,windowId:message.windowId});
  if(!tab?.id||!isMaximoWorkorderUrl(tab.url))throw new Error("Selecciona la pestaña de la OT en Maximo para ver sus acciones.");
  if(message.type==="PANEL_ACTION"&&tab.id!==message.tabId)
    throw new Error("Cambiaste de pestaña. Revisa la OT antes de continuar.");
  const request=message.type==="PANEL_ACTION"?{action:message.action,ot:message.ot,status:message.status}:{};
  if(message.type==="PANEL_ACTION"&&!["start","choose","change","close","print"].includes(request.action))
    throw new Error("Acción desconocida.");
  const [execution]=await chrome.scripting.executeScript({target:{tabId:tab.id},world:"MAIN",func:maximoPanelBridge,args:[request]});
  if(execution?.result?.panelError)throw new Error(execution.result.panelError);
  if(!execution?.result)throw new Error("No se pudo leer la ficha de la OT. La página pudo cambiar durante la solicitud; revisa su estado antes de repetir.");
  return {...execution.result,tabId:tab.id};
}
if(typeof chrome!=="undefined"&&chrome.sidePanel) {
  chrome.sidePanel.setPanelBehavior({openPanelOnActionClick:true}).catch(console.error);
  chrome.tabs.onUpdated.addListener((tabId,change,tab)=>{
    if(change.url||change.status==="complete")chrome.sidePanel.setOptions({tabId,path:"sidepanel.html",enabled:isMaximoWorkorderUrl(tab.url)}).catch(console.error);
  });
}
if(typeof module!=="undefined")module.exports={handlePanelMessage,isMaximoWorkorderUrl};
