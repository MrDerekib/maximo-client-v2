import {validOt,linksFor,mailParts} from './core.mjs';
const $ = id => document.getElementById(id);
let generation = 0;
function status(text) { $('status').textContent = text; }
function updateLinks() {
  const ot = $('ot').value.trim();
  const valid = validOt(ot);
  const links = valid ? linksFor(ot, $('development').checked) : {};
  const bridge = new URL('launch.html',location.href);
  bridge.search = new URLSearchParams({ot,dev:$('development').checked ? '1' : '0'});
  for (const [id,href] of [['web',links.web],['md',links.md],['bridge',bridge.href]]) {
    $(id).setAttribute('aria-disabled',String(!valid));
    if (valid) $(id).href=href; else $(id).removeAttribute('href');
  }
}
function showCandidates(candidates) {
  $('candidates').replaceChildren();
  if (candidates.length > 1) {
    const prompt = document.createElement('option');prompt.value='';prompt.textContent='Elegir la OT que quieres abrir';$('candidates').append(prompt);
  }
  for (const ot of candidates) { const option=document.createElement('option');option.value=ot;option.textContent=`OT ${ot}`;$('candidates').append(option); }
  $('candidates').hidden=$('candidates-label').hidden=candidates.length<2;
  $('ot').value=candidates.length===1?candidates[0]:'';
  $('detection').textContent=candidates.length===1?'OT detectada en el mensaje.':candidates.length>1?'Hay varias OTs, posiblemente en el historial del correo. Elige una.':'No se ha detectado una OT. Puedes introducir su número.';
  updateLinks();
}
function readMessage() {
  const token=++generation;
  showCandidates([]);status('');
  const item=globalThis.Office?.context?.mailbox?.item;
  if (!item?.body) { $('context').textContent='Selecciona un correo de Maximo.'; return; }
  $('context').textContent='Correo seleccionado';$('detection').textContent='Leyendo el mensaje…';
  item.body.getAsync(Office.CoercionType.Html, result=>{
    if(token!==generation || Office.context.mailbox.item!==item) return;
    if(result.status!==Office.AsyncResultStatus.Succeeded) { $('detection').textContent='No se pudo leer el mensaje. Puedes introducir la OT manualmente.';return; }
    showCandidates(mailParts(result.value,item.subject || ''));
  });
}
$('ot').addEventListener('input',()=>{generation++;updateLinks();status('');});
$('candidates').addEventListener('change',()=>{$('ot').value=$('candidates').value;updateLinks();status('');});
$('development').addEventListener('change',updateLinks);
for(const id of ['web','md','bridge']) $(id).addEventListener('click',event=>{
  if($(id).getAttribute('aria-disabled')==='true'){event.preventDefault();return;}
  status(id==='md'?'Se ha solicitado abrir MD. Si no se abre, prueba el enlace del navegador.':'Se ha solicitado abrir el navegador. Si no aparece, comprueba el bloqueo de ventanas.');
});
$('refresh').addEventListener('click',readMessage);
$('parse-demo').addEventListener('click',()=>{generation++;showCandidates(mailParts($('sample').value));status('');});
updateLinks();
if(new URLSearchParams(location.search).get('demo')==='1') {
  $('demo').hidden=false;$('context').textContent='Prueba local · sin conexión a Outlook';$('refresh').hidden=true;
  showCandidates(mailParts($('sample').value));
} else {
  const script=document.createElement('script');script.src='https://appsforoffice.microsoft.com/lib/1/hosted/office.js';
  script.onload=()=>Office.onReady(()=>{
    if(!Office.context?.mailbox){$('context').textContent='Abre este panel desde Outlook o utiliza ?demo=1.';showCandidates([]);return;}
    Office.context.mailbox.addHandlerAsync(Office.EventType.ItemChanged,readMessage,result=>{
      if(result.status!==Office.AsyncResultStatus.Succeeded) status('No se pudo activar el cambio automático de correo. Usa «Volver a leer el correo».');
    });
    readMessage();
  });
  script.onerror=()=>{$('context').textContent='No se pudo cargar la conexión con Outlook. Comprueba el acceso a Office.js.';showCandidates([]);};
  document.head.append(script);
}
