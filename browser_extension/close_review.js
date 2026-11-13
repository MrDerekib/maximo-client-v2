/* Presentation only. Native writes run once, after explicit review in Python. */
(() => {
  function mount(dialog, data, onChange) {
    if (!data.records) return null;
    const records=data.records, existing=records.entries||[], references=records.references||[];
    const root=document.createElement('section');root.className='close-card close-records';
    const element=(tag,text,parent=root)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;parent.append(node);return node;};
    element('h3','Incidencia y trabajos realizados');
    element('p',records.complete?'Revisa lo existente y completa únicamente lo pendiente. Las entradas guardadas no se sobrescriben.':records.error||'No se pudo comprobar Registro. No se permite confirmar.').className='close-hint';
    if (existing.length) {
      const history=element('details');element('summary',`Registro existente · ${existing.length} entradas`,history);
      const list=element('div',undefined,history);list.className='close-record-history';
      for (const entry of existing) {
        const note=element('article',undefined,list);
        element('strong',entry.summary,note);
        if(entry.details)element('p',entry.details,note);
        element('small',[entry.type,entry.author,entry.date].filter(Boolean).join(' · '),note).className='close-hint';
      }
    }
    const label=element('label','Incidencia');label.className='close-label';label.htmlFor='maximo-close-reference';
    const reference=element('input');reference.id='maximo-close-reference';reference.type='text';reference.name='reference';reference.maxLength=100;
    reference.placeholder='Número o texto libre: stock, sin inc…';reference.value=references.length===1?references[0]:'';
    if(references.length>1)element('p','Hay varias incidencias. Elige la que corresponde; no se eliminará ninguna.').className='close-hint';
    if(references.length) {
      const choices=element('datalist');choices.id='maximo-close-references';reference.setAttribute('list',choices.id);
      for(const value of references){const option=element('option',undefined,choices);option.value=value;}
    }
    const extra=element('label');extra.className='close-record-check';extra.hidden=true;
    const extraAck=element('input',undefined,extra);extraAck.type='checkbox';extraAck.name='newReferenceAck';
    extra.append(document.createTextNode('Añadir esta incidencia sin sustituir las existentes.'));
    const acknowledged=element('label');acknowledged.className='close-record-check';acknowledged.hidden=!(records.notes||[]).length;
    const activityAck=element('input',undefined,acknowledged);activityAck.type='checkbox';activityAck.name='activityAck';
    acknowledged.append(document.createTextNode('Las entradas existentes documentan los trabajos o pruebas de esta reparación.'));
    const editor=element('details');editor.open=!(records.notes||[]).length;
    element('summary','Añadir trabajos, pruebas o diagnósticos',editor);
    const rows=element('div',undefined,editor);
    const add=element('button','Añadir entrada',editor);add.type='button';add.className='close-cancel';add.name='addEntry';
    function addRow() {
      const row=element('div',undefined,rows);row.className='close-new-entry';
      const summary=element('input',undefined,row);summary.type='text';summary.maxLength=100;summary.placeholder='Resumen del trabajo o prueba';summary.setAttribute('aria-label','Resumen del trabajo');
      const details=element('textarea',undefined,row);details.rows=2;details.maxLength=20000;details.placeholder='Detalles (opcional)';details.setAttribute('aria-label','Detalles del trabajo');
      const remove=element('button','Quitar entrada',row);remove.type='button';remove.className='close-cancel';
      remove.addEventListener('click',()=>{row.remove();onChange();});
      row.addEventListener('input',onChange);onChange();summary.focus();
    }
    add.addEventListener('click',()=>{if(rows.children.length<30)addRow();});
    if(!data.anomalies?.complete)element('p','Completa la clase de anomalía y las soluciones desde la ficha o «Cambiar anomalías» antes de cerrar.').className='close-error';
    else {
      const anomalies=element('details');element('summary','Anomalías y soluciones actuales',anomalies);
      element('p',[data.anomalies.class,...Object.values(data.anomalies.codes)].join(' → '),anomalies).className='close-hint';
    }
    const normalizeReference=()=>{const value=reference.value.trim().replace(/^(?:inc\s*:\s*)+/i,'').trim();return value?'inc: '+value:'';};
    const entries=()=>[...rows.children].map(row=>({summary:row.querySelector('input').value.trim(),details:row.querySelector('textarea').value.trim()})).filter(row=>row.summary||row.details);
    function refresh(){const value=normalizeReference();extra.hidden=!references.length||!value||references.includes(value);onChange();}
    reference.addEventListener('input',()=>{extraAck.checked=false;refresh();});
    activityAck.addEventListener('change',onChange);extraAck.addEventListener('change',onChange);
    dialog.querySelector('.close-body').insertBefore(root,dialog.querySelector('.close-body').children[1]);
    return {
      validate(){
        if(!records.complete)return 'No se pudo comprobar Registro completo. Revisa la ficha y vuelve a abrir el cierre.';
        if(!data.anomalies?.complete)return 'Falta completar anomalías o soluciones.';
        const value=normalizeReference(),notes=entries();
        if(!value)return 'Introduce o elige la incidencia (texto libre).';
        if(value.length>100||/[\x00-\x1f]/.test(value))return 'La incidencia no es válida o supera 100 caracteres.';
        extra.hidden=!references.length||references.includes(value);
        if(!extra.hidden&&!extraAck.checked)return 'Confirma que deseas añadir otra incidencia sin sustituir las existentes.';
        if(notes.some(row=>!row.summary))return 'Cada entrada nueva necesita un resumen.';
        if(notes.some(row=>/^inc\s*:/i.test(row.summary)))return 'Introduce la incidencia en su campo, no como trabajo realizado.';
        if(new Set(notes.map(row=>row.summary.toLocaleLowerCase())).size!==notes.length)return 'Evita resúmenes repetidos en las entradas nuevas.';
        if(!notes.length&&!activityAck.checked)return 'Añade los trabajos o confirma que las entradas existentes documentan esta reparación.';
        return '';
      },
      approval(){return {reference:normalizeReference(),entries:entries(),activity_confirmed:activityAck.checked,new_reference_confirmed:extraAck.checked};}
    };
  }
  globalThis.MaximoCloseRecordReview={mount};
})();
