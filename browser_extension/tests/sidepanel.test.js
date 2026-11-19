const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const bridgeSource = fs.readFileSync(require.resolve('../panel_bridge.js'),'utf8');
function page(status='INPRG') {
  const elements = new Map(), clicks=[];
  for(const [id,value] of [['mx45-tb','4400123'],['mx73-tb',status],['mx47-tb','TMB BOIXERES']])
    elements.set(id,{value,getClientRects:()=>[1]});
  for(const [key,id,label] of [['start','start-ot','Iniciar OT'],['choose','start-options','Elegir anomalías…'],
    ['change','change-anomalies','Cambiar anomalías'],['close','close-ot','Cerrar OT'],['print','print-part','Imprimir parte']])
    elements.set('maximo-desktop-'+id,{hidden:false,disabled:false,dataset:{},textContent:label,title:label,click:()=>clicks.push(key)});
  let dialogs=[];
  const scope = vm.createContext({location:{origin:'https://eam.indraweb.net',pathname:'/maximo/ui/'},
    document:{getElementById:id=>elements.get(id),querySelectorAll:selector=>selector==='label[for]'?[]:dialogs},
    getComputedStyle:()=>({visibility:'visible',display:'block',opacity:'1'})});
  vm.runInContext(bridgeSource,scope);
  elements.get('maximo-desktop-close-ot').click=()=>{clicks.push('prepare-close');elements.get('maximo-desktop-close-ot').dataset.busy='true';};
  return {setProgress:value=>{scope.sessionStorage={getItem:()=>JSON.stringify(value)};},read:request=>{const result=scope.maximoPanelBridge(request);if(result.panelError)throw new Error(result.panelError);return result;},elements,clicks,
    block:()=>dialogs=[{getClientRects:()=>[1],getAttribute:()=>null,parentElement:null}]};
}
test('panel offers only actions matching the live OT state',()=>{
  for(const [status,expected] of [['APPR',['start','choose']],['INPRG',['change','close']],['ISSUE',['print']],['CLOSE',['print']],['WAPPR',[]]]) {
    const p=page(status);assert.deepEqual(Array.from(p.read().actions,a=>a.key),expected);
    assert.deepEqual(p.clicks,[]);
  }
});
test('changing OT, status or availability rejects dispatch without any click',()=>{
  const p=page();
  for(const request of [{action:'close',ot:'OTHER',status:'INPRG'},{action:'close',ot:'4400123',status:'APPR'},
    {action:'print',ot:'4400123',status:'INPRG'},{action:'unknown',ot:'4400123',status:'INPRG'}])
    assert.throws(()=>p.read(request));
  p.elements.get('maximo-desktop-close-ot').disabled=true;
  assert.throws(()=>p.read({action:'close',ot:'4400123',status:'INPRG'}));assert.deepEqual(p.clicks,[]);
});
test('native dialogs and busy jobs prevent a second action',()=>{
  for(const busy of [false,true]) {
    const p=page();if(busy)p.elements.get('maximo-desktop-change-anomalies').dataset.busy='true';else p.block();
    assert.throws(()=>p.read({action:'close',ot:'4400123',status:'INPRG'}));assert.deepEqual(p.clicks,[]);
  }
});
test('close only requests the original review, never routes or accepts it',()=>{
  const p=page();p.read({action:'close',ot:'4400123',status:'INPRG'});
  assert.deepEqual(p.clicks,['prepare-close']);
});
test('print reuses the original control and unavailable controls are not invented',()=>{
  const p=page('CLOSE');p.read({action:'print',ot:'4400123',status:'CLOSE'});assert.deepEqual(p.clicks,['print']);
  p.elements.delete('maximo-desktop-print-part');assert.equal(p.read().actions.length,0);
});
const {handlePanelMessage,isMaximoWorkorderUrl}=require('../panel_worker.js');
function worker(){
  const calls=[];
  global.chrome={runtime:{id:'test',getURL:path=>'chrome-extension://test/'+path},
    tabs:{query:async()=>[{id:7,url:'https://eam.indraweb.net/maximo/ui/'}]},
    scripting:{executeScript:async spec=>{calls.push(spec);return [{result:{ot:'4400123',status:'INPRG'}}];}},
    sidePanel:{open:async spec=>calls.push(spec)}};
  return {calls,sender:{id:'test',url:'chrome-extension://test/sidepanel.html'}};
}
test('worker refuses another tab or untrusted panel before executing page code',async()=>{
  const p=worker();
  await assert.rejects(handlePanelMessage({type:'PANEL_ACTION',windowId:1,tabId:8,action:'close'},p.sender),/pestaña/);
  await assert.rejects(handlePanelMessage({type:'PANEL_CONTEXT',windowId:1},{id:'other',url:'https://example.com'}),/válida/);
  await assert.rejects(handlePanelMessage({type:'PANEL_ACTION',windowId:1,tabId:7,action:'unsafe'},p.sender),/desconocida/);
  assert.equal(p.calls.length,0);
});
test('panel context uses current window, and action forwards exact OT and status',async()=>{
  const p=worker();global.maximoPanelBridge=()=>{};
  const result=await handlePanelMessage({type:'PANEL_ACTION',windowId:1,tabId:7,action:'change',ot:'4400123',status:'INPRG'},p.sender);
  assert.equal(result.tabId,7);assert.deepEqual(p.calls[0].args,[{action:'change',ot:'4400123',status:'INPRG'}]);
  assert.equal(p.calls[0].world,'MAIN');
});
test('only the exact Maximo OT route can open the panel from the page',async()=>{
  const p=worker();
  for(const url of ['https://example.com/maximo/ui/','https://eam.indraweb.net/maximo/report','https://eam.indraweb.net.evil/maximo/ui/']) {
    assert.equal(isMaximoWorkorderUrl(url),false);
    await assert.rejects(handlePanelMessage({type:'OPEN_PANEL'},{tab:{id:7,url}}));
  }
  await handlePanelMessage({type:'OPEN_PANEL'},{tab:{id:7,url:'https://eam.indraweb.net/maximo/ui/'}});
  assert.deepEqual(p.calls,[{tabId:7}]);
});


test('injected exceptions keep their actual reason instead of a missing-result error',async()=>{
  const p=page();p.elements.get('maximo-desktop-close-ot').click=()=>{throw new Error('Concrete preparation failure');};
  assert.throws(()=>p.read({action:'close',ot:'4400123',status:'INPRG'}),/Concrete preparation failure/);
  const w=worker();global.maximoPanelBridge=()=>{};
  chrome.scripting.executeScript=async()=>[{result:{panelError:'Concrete preparation failure'}}];
  await assert.rejects(handlePanelMessage({type:'PANEL_CONTEXT',windowId:1},w.sender),/Concrete preparation failure/);
});


test('close progress survives reload without accepting another operation or another OT',()=>{
  const p=page();p.setProgress({ot:'4400123',text:'Verificando Registro guardado…',at:Date.now()});
  assert.ok(Array.from(p.read().progress).includes('Verificando Registro guardado…'));
  assert.throws(()=>p.read({action:'close',ot:'4400123',status:'INPRG'}));
  p.setProgress({ot:'OTHER',text:'Other operation',at:Date.now()});assert.equal(p.read().progress.length,0);
  p.setProgress({ot:'4400123',text:'Expired',at:Date.now()-11*60*1000});assert.equal(p.read().progress.length,0);
});
