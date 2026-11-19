import {linksFor} from './core.mjs';
try {
  const params=new URLSearchParams(location.search);const ot=params.get('ot');
  const links=linksFor(ot,params.get('dev')==='1',params.get('action') || 'open');
  document.getElementById('title').textContent=`OT ${ot}`;
  for(const [id,href] of [['launch',links.md],['web',links.web]]) { const a=document.getElementById(id);a.href=href;a.setAttribute('aria-disabled','false'); }
  document.getElementById('launch').addEventListener('click',()=>{document.getElementById('status').textContent='Solicitud enviada a Windows. Comprueba la apertura de MD.';});
} catch { document.getElementById('title').textContent='Número de OT no válido'; }
