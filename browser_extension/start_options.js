/* Configurable, per-OT start action injected by Maximo Desktop. */
(function () {
  "use strict";

  const VERSION = "start-options-v1";
  const prior = globalThis.MaximoDesktopStartOptions;
  if (prior?.version === VERSION) return;

  function install(catalog, defaultSelection, configuredMode) {
    const normalize = text => String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ").trim().replace(/:$/, "").toLowerCase();
    const visible = element => Boolean(element && element.getClientRects().length &&
      getComputedStyle(element).visibility !== "hidden");
    const field = caption => {
      const label = [...document.querySelectorAll("label[for]")].find(element =>
        visible(element) && normalize(element.textContent) === normalize(caption));
      return label ? document.getElementById(label.htmlFor) : null;
    };
    const activeTab = () => [...document.querySelectorAll("a[role=tab]")]
      .find(element => visible(element) && element.getAttribute("aria-expanded") === "true")
      ?.textContent.trim() || "";
    const current = () => ({ot: String(field("Orden de trabajo")?.value || "").trim(),
      status: String(field("Estado")?.value || "").trim()});
    const hasBlockingDialog = () => [...document.querySelectorAll("[role=dialog],#warndiv")].some(root => {
      const panel=root.id==="warndiv"?(root.querySelector("#warndiv_inner")||root):root;
      if(!visible(panel))return false;
      for(let node=panel;node;node=node.parentElement){const style=getComputedStyle(node);
        if(node.getAttribute("aria-hidden")==="true"||style.display==="none"||
          ["hidden","collapse"].includes(style.visibility)||Number(style.opacity)===0)return false;}
      return true;
    });
    const state = {catalog, defaultSelection, configuredMode,
      request: "", busy: false, modal: null};
    state.modeValid=["only","configured"].includes(configuredMode);
    const buttonStyle = {zIndex:"2147483647",padding:"8px 12px",maxWidth:"190px",overflow:"hidden",
      textOverflow:"ellipsis",
      border:"1px solid #1155a0",borderRadius:"6px",background:"#1769c2",color:"#fff",
      font:"600 13px Arial,sans-serif",boxShadow:"0 3px 12px #0004",cursor:"pointer",whiteSpace:"nowrap"};
    function ensureButton(id, text, handler, parent) {
      let button = document.getElementById(id);
      if (!button) {
        button = document.createElement("button"); button.id = id; button.type = "button";
        button.textContent = text; Object.assign(button.style, buttonStyle);
        button.addEventListener("click", handler); parent.appendChild(button);
      }
      return button;
    }
    function setButtonMessage(message) {
      const button = document.getElementById("maximo-desktop-start-ot");
      if (button) { button.textContent = message; button.title = message; }
    }
    function capture(mode, selection, opened = null) {
      const now = current();
      if (!/^\d{1,20}$/.test(now.ot) || now.status !== "APPR") {
        if (opened) showModalError("Iniciar OT solo está disponible en una OT APPR.");
        else setButtonMessage("Iniciar OT solo está disponible en una OT APPR");
        setTimeout(() => refresh(), 4000); return;
      }
      if (opened && (opened.ot !== now.ot || opened.status !== now.status)) {
        showModalError("La OT o su estado cambiaron. Cierra esta ventana y vuelve a abrir la selección.");
        return;
      }
      state.request = JSON.stringify({ot:now.ot, returnTab:activeTab(), mode, selection});
      state.busy = true;
      const main=document.getElementById("maximo-desktop-start-ot");
      if(main) main.dataset.busy="true";
      setButtonMessage("Iniciando OT…");
      refresh();
    }
    function labelFor(element, text) {
      const label = document.createElement("label"); label.textContent = text;
      label.style.cssText = "display:block;font-weight:600;margin:10px 0 5px;color:#173b60";
      element.appendChild(label); return label;
    }
    function showModalError(text) {
      const node = document.getElementById("maximo-start-options-error");
      if (node) node.textContent = text;
    }
    function openModal() {
      if (state.busy || state.modal) return;
      const opened = current();
      if (!/^\d{1,20}$/.test(opened.ot) || opened.status !== "APPR") return;
      const overlay = document.createElement("div"); overlay.id = "maximo-start-options-overlay";
      Object.assign(overlay.style, {position:"fixed",inset:"0",zIndex:"2147483647",background:"#10243b88",
        display:"grid",placeItems:"center",font:"14px Arial,sans-serif",color:"#173b60"});
      const panel = document.createElement("section");
      Object.assign(panel.style, {width:"min(560px, calc(100vw - 32px))",maxHeight:"min(82vh, 720px)",
        overflow:"auto",boxSizing:"border-box",background:"#fff",border:"1px solid #bfd2e8",
        borderRadius:"12px",boxShadow:"0 16px 48px #0005",padding:"22px"});
      overlay.appendChild(panel);
      const heading = document.createElement("h2"); heading.textContent = `Iniciar OT ${opened.ot}`;
      heading.style.cssText = "margin:0 0 8px;font-size:20px;color:#153c65"; panel.appendChild(heading);
      const intro = document.createElement("p"); intro.textContent = "Elige la configuración para esta OT. La selección manual solo se aplica a esta ejecución.";
      intro.style.cssText = "margin:0 0 16px;color:#526a83;line-height:1.4"; panel.appendChild(intro);
      const modeGroup = document.createElement("fieldset");
      modeGroup.style.cssText = "border:1px solid #cbd9e8;border-radius:8px;padding:12px 14px;margin:0 0 12px";
      const legend = document.createElement("legend"); legend.textContent = "Acción"; legend.style.fontWeight="600";
      modeGroup.appendChild(legend);
      const configured = document.createElement("input"); configured.type="radio"; configured.name="maximo-start-mode"; configured.value="configured"; configured.checked=true;
      const only = document.createElement("input"); only.type="radio"; only.name="maximo-start-mode"; only.value="only";
      for (const [radio, text] of [[configured,"Aplicar una combinación de anomalías"],[only,"Solo iniciar OT; conservar anomalías actuales"]]) {
        const label=document.createElement("label"); label.style.cssText="display:flex;gap:8px;align-items:center;margin:6px 0;cursor:pointer";
        label.append(radio,document.createTextNode(text));modeGroup.appendChild(label);
      }
      panel.appendChild(modeGroup);
      const selectionBox=document.createElement("div"); panel.appendChild(selectionBox);
      const error=document.createElement("div"); error.id="maximo-start-options-error";
      error.style.cssText="min-height:18px;color:#a52a1a;font-weight:600;margin:10px 0"; panel.appendChild(error);
      const summary=document.createElement("div");
      summary.style.cssText="padding:10px;background:#f1f6fc;border-radius:6px;color:#365a7c;line-height:1.4"; panel.appendChild(summary);
      const buttons=document.createElement("div"); buttons.style.cssText="display:flex;justify-content:flex-end;gap:8px;margin-top:18px";
      const cancel=document.createElement("button"); cancel.type="button"; cancel.textContent="Cancelar";
      const confirm=document.createElement("button"); confirm.type="button"; confirm.textContent="Iniciar OT";
      for (const button of [cancel,confirm]) Object.assign(button.style,{padding:"8px 14px",borderRadius:"6px",border:"1px solid #b7cbe1",background:button===confirm?"#1769c2":"#fff",color:button===confirm?"#fff":"#173b60",fontWeight:"600",cursor:"pointer"});
      buttons.append(cancel,confirm); panel.appendChild(buttons);
      const selection={classKey:"",optionKeys:[],complete:false,label:""};
      function clearSelection() { selection.classKey="";selection.optionKeys=[];selection.complete=false;selection.label=""; }
      function renderChoices() {
        selectionBox.replaceChildren(); clearSelection(); summary.textContent="Selecciona una ruta completa o elige «Solo iniciar OT».";
        if (only.checked) { selection.complete=true;update();return; }
        labelFor(selectionBox,"Clase de anomalía");
        const classSelect=document.createElement("select");
        Object.assign(classSelect.style,{width:"100%",padding:"8px",border:"1px solid #b7cbe1",borderRadius:"6px",background:"#fff"});
        const prompt=document.createElement("option");prompt.value="";prompt.textContent="Selecciona una clase…";classSelect.appendChild(prompt);
        for(const item of (catalog.classes||[])) { const option=document.createElement("option");option.value=item.key;option.textContent=`${item.code} — ${item.description||item.organization||""}`;classSelect.appendChild(option); }
        selectionBox.appendChild(classSelect);
        const levels=document.createElement("div");selectionBox.appendChild(levels);
        function renderLevel(ref, index) {
          if(!ref) { selection.complete=selection.optionKeys.length>0; update(); return; }
          const options=catalog.option_sets?.[ref]||[];
          if(!options.length) { selection.complete=selection.optionKeys.length>0; update(); return; }
          const wrapper=document.createElement("div"); levels.appendChild(wrapper);
          const levelType=options[0]?.type;
          const levelLabels={PROBLEM:"Síntoma",CAUSE:"Causa",REMEDY:"Resolución"};
          const sameTypeCount=[...levels.querySelectorAll("select")].filter(select=>
            select.dataset.failureType===levelType).length;
          labelFor(wrapper,`${levelLabels[levelType]||"Código"}${sameTypeCount?` ${sameTypeCount+1}`:""}`);
          const select=document.createElement("select");
          select.dataset.failureType=levelType||"";
          Object.assign(select.style,{width:"100%",padding:"8px",border:"1px solid #b7cbe1",borderRadius:"6px",background:"#fff"});
          const empty=document.createElement("option");empty.value="";empty.textContent="Selecciona una opción…";select.appendChild(empty);
          const seen=new Map();
          for(const item of options) { const count=(seen.get(item.code)||0)+1;seen.set(item.code,count); }
        const organization=(catalog.classes||[]).find(item=>item.key===selection.classKey)?.organization;
        for(const item of options) { const option=document.createElement("option");option.value=item.key;
            const occurrence=seen.get(item.code)>1?` (ocurrencia ${options.filter(x=>x.code===item.code).findIndex(x=>x.key===item.key)+1})`:"";
            const description=item.description||catalog.descriptions?.[organization]?.[item.code]||"";
            option.textContent=`${item.code}${description?` — ${description}`:""}${occurrence} · ${item.type}`;select.appendChild(option); }
          wrapper.appendChild(select);
          select.addEventListener("change",()=>{ selection.optionKeys=selection.optionKeys.slice(0,index);selection.complete=false;
            [...levels.children].slice(index+1).forEach(child=>child.remove());
            const picked=options.find(item=>item.key===select.value);if(!picked){update();return;}
            selection.optionKeys.push(picked.key);selection.label=[...selectionBox.querySelectorAll("select")].map(s=>s.selectedOptions[0]?.textContent).filter(Boolean).join(" → ");
            renderLevel(picked.children_ref,index+1); });
        }
        classSelect.addEventListener("change",()=>{levels.replaceChildren();clearSelection();const item=(catalog.classes||[]).find(x=>x.key===classSelect.value);
          selection.classKey=item?.key||"";selection.label=item?`${item.code}`:"";renderLevel(item?.options_ref,0);});
        const defaultClass=(catalog.classes||[]).find(item=>item.key===defaultSelection?.class_key);
        if(defaultClass){classSelect.value=defaultClass.key;classSelect.dispatchEvent(new Event("change"));
          // Preselect the configured default path, but keep each step conditional.
          const defaultKeys=Array.isArray(defaultSelection?.option_keys)?defaultSelection.option_keys:[];
          for(const key of defaultKeys){
            const selects=levels.querySelectorAll("select");const select=selects[selects.length-1];if(!select)break;
            select.value=key;if(select.value!==key)break;select.dispatchEvent(new Event("change"));
          }
        }
        update();
      }
      function update() {
        const useOnly=only.checked;
        selectionBox.hidden=useOnly;
        selection.complete=useOnly || (Boolean(selection.classKey)&&selection.optionKeys.length>0&&selection.complete);
        confirm.disabled=!selection.complete;confirm.style.opacity=confirm.disabled?"0.55":"1";
        summary.textContent=useOnly?"Se conservarán la clase y los códigos actuales de la OT.":
          (selection.label?`Selección para esta OT: ${selection.label}`:"Completa la ruta de códigos para habilitar el inicio.");
      }
      configured.addEventListener("change",renderChoices);only.addEventListener("change",update);
      cancel.addEventListener("click",()=>{overlay.remove();state.modal=null;});
      confirm.addEventListener("click",()=>{
        if(confirm.disabled)return;
        const mode=only.checked?"only":"configured";
        const spec=mode==="only"?null:{class_key:selection.classKey,option_keys:[...selection.optionKeys]};
        capture(mode,spec,opened);
        if(state.request){overlay.remove();state.modal=null;}
      });
      document.body.appendChild(overlay);state.modal=overlay;renderChoices();
    }
    function refresh() {
      const now=current();
      let group=document.getElementById("maximo-desktop-start-actions");
      if(!group){group=document.createElement("div");group.id="maximo-desktop-start-actions";
        Object.assign(group.style,{position:"fixed",right:"20px",bottom:"65px",zIndex:"2147483647",
          display:"flex",alignItems:"center",gap:"8px"});document.body.appendChild(group);}
      const main=ensureButton("maximo-desktop-start-ot", "Iniciar OT",()=>{
        if(state.busy)return;
        if(!state.modeValid){setButtonMessage("Revisa configuración de inicio en MD");return;}
        capture(state.configuredMode,state.configuredMode==="only"?null:defaultSelection);
      },group);
      const choose=ensureButton("maximo-desktop-start-options", "Elegir anomalías…",openModal,group);
      const usable=/^\d{1,20}$/.test(now.ot)&&now.status==="APPR"&&!hasBlockingDialog();
      main.hidden=choose.hidden=!usable;
      main.title=state.modeValid?(state.configuredMode==="only"?
        "Iniciar la OT conservando sus códigos de anomalía actuales.":"Aplicar la selección configurada e iniciar la OT."):
        "Revisa configuración de inicio en MD; puedes elegir una opción manual para esta OT.";
      for(const button of [main,choose]) { button.disabled=!usable||state.busy||Boolean(state.modal)||(button===main&&!state.modeValid);
        button.style.opacity=button.disabled?"0.6":"1"; }
      if(!state.modeValid)main.textContent="Revisar inicio en MD";
      return state.request;
    }
    globalThis.MaximoDesktopStartOptions={version:VERSION,installed:true,refresh,poll(){const request=state.request;state.request="";refresh();return request;},
      message(text){const main=document.getElementById("maximo-desktop-start-ot");
        if(main){main.textContent=String(text||"");main.title=String(text||"");}},
      complete(message){state.busy=false;const main=document.getElementById("maximo-desktop-start-ot");
        if(main){main.dataset.busy="false";setButtonMessage(message);setTimeout(()=>{if(main.isConnected){main.textContent="Iniciar OT";refresh();}},8000);}refresh();}};
    refresh();
  }

  globalThis.MaximoDesktopStartOptions = {version: VERSION, install};
})();
