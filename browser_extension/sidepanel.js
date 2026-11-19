"use strict";
const $ = id => document.getElementById(id);
let context = null, windowId, polling = false, submitting = false, renderKey = "";
const statusNames = {APPR:"Sin iniciar",INPRG:"En curso",ISSUE:"Pendiente de salida",CLOSE:"Cerrada"};
async function send(type, payload = {}) {
  const response = await chrome.runtime.sendMessage({ type, windowId, ...payload });
  if (!response?.ok) throw new Error(response?.error || "No se pudo conectar con MD.");
  return response.value;
}
function render(value) {
  context = value;
  $("ot").textContent = value.ot ? `OT ${value.ot}` : "Selecciona una OT";
  $("status").hidden = !value.status;
  $("status").textContent = statusNames[value.status] || value.status || "";
  $("client").textContent = value.client || "";
  $("notice").textContent = !value.ot ? "Abre una ficha de OT en la pestaña activa de Maximo." :
    value.blocking ? "Completa o cancela el diálogo abierto en la ficha de Maximo." :
    value.actions.length ? "Acciones disponibles para el estado actual de la OT." :
    "Esperando los controles de MD. Revisa que las acciones estén habilitadas en Configuración.";
  const activity = [...new Set([...(value.progress || []), ...(value.messages || [])])];
  $("activity").hidden = !activity.length;
  $("progress").textContent = activity.join(" · ");
  $("review-hint").textContent = value.blocking ? "La revisión continúa en la ficha; el panel no confirma operaciones por ti." : "";
  const key = JSON.stringify([value.tabId, value.ot, value.status, value.actions, Boolean(value.progress?.length),submitting]);
  if (key === renderKey) return;
  renderKey = key;
  const root = $("actions"); root.replaceChildren();
  const groups = {};
  const order = {primary:0, prepare:1, documents:2};
  for (const action of [...value.actions].sort((a,b)=>order[a.group]-order[b.group])) {
    let parent = root;
    if (action.group !== "primary") {
      if (!groups[action.group]) {
        const section = document.createElement("section");section.className="group";
        const title=document.createElement("h3");title.textContent=action.group==="documents"?"Documentos":"Preparar";
        section.append(title);root.append(section);groups[action.group]=section;
      }
      parent=groups[action.group];
    }
    const button=document.createElement("button");button.type="button";
    button.dataset.action=action.key;
    if(action.group==="primary")button.className="primary";
    button.disabled=!action.enabled||submitting||Boolean(value.progress?.length);
    button.title=action.hint;
    const icon=document.createElement("span");icon.className="icon";icon.setAttribute("aria-hidden","true");
    icon.textContent=({start:"▷",choose:"≡",change:"≡",close:"↗",print:"▤"})[action.key];
    const label=document.createElement("span");label.textContent=action.label;button.append(icon,label);
    if(action.group!=="primary"){const arrow=document.createElement("span");arrow.className="arrow";arrow.textContent="›";arrow.setAttribute("aria-hidden","true");button.append(arrow);}
    // Capture the exact context displayed when this control was rendered.
    button.addEventListener("click",()=>run(action.key,{tabId:value.tabId,ot:value.ot,status:value.status}));
    parent.append(button);
  }
}
async function run(action, expected) {
  if(submitting)return;
  submitting=true;$("error").hidden=true;
  render(context);
  try {
    await send("PANEL_ACTION",{...expected,action});
    $("activity").hidden=false;
    $("progress").textContent="Solicitud enviada a MD. Esperando la revisión o el progreso…";
  } catch(error){$("error").hidden=false;$("error").textContent=error.message;}
  finally{submitting=false;await refresh();}
}
async function refresh(){
  if(polling||windowId===undefined)return;
  polling=true;
  try{render(await send("PANEL_CONTEXT"));}
  catch(error){context=null;renderKey="";$("actions").replaceChildren();$("ot").textContent="Selecciona una OT";
    $("status").hidden=true;$("client").textContent="";$("activity").hidden=true;$("notice").textContent=error.message;}
  finally{polling=false;}
}
chrome.windows.getCurrent().then(value=>{windowId=value.id;refresh();}).catch(error=>{$("notice").textContent=error.message;});
chrome.tabs.onActivated.addListener(refresh);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
setInterval(()=>{if(!document.hidden)refresh();},900);
