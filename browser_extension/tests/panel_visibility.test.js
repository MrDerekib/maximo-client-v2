const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../panel_visibility.js'),'utf8');
function harness(session=new Map()) {
  const notices=[],listeners={};
  const tabs=[{id:7,windowId:1},{id:8,windowId:1},{id:9,windowId:2}];
  const scope=vm.createContext({console,chrome:{
    storage:{session:{get:async key=>({[key]:session.get(key)}),set:async values=>{for(const [key,value]of Object.entries(values))session.set(key,value);}}},
    tabs:{query:async filter=>tabs.filter(tab=>tab.windowId===filter.windowId),sendMessage:async(id,message)=>notices.push({id,...message})},
    sidePanel:{onOpened:{addListener:fn=>listeners.open=fn},onClosed:{addListener:fn=>listeners.close=fn}}
  }});
  vm.runInContext(source,scope);
  return {scope,session,notices,listeners,open:(info,value)=>scope.setPanelVisibility(info,value),read:tab=>scope.panelIsOpen(tab)};
}
test('native open hides launcher only in matching tab/window; close restores it',async()=>{
  const h=harness();h.listeners.open({windowId:1,tabId:7,path:'sidepanel.html'});
  assert.equal(await h.read({id:7,windowId:1}),true);
  assert.equal(await h.read({id:8,windowId:1}),false);
  assert.equal(await h.read({id:7,windowId:2}),false);
  assert.equal(h.notices.find(row=>row.id===7).open,true);
  h.listeners.close({windowId:1,tabId:7,path:'sidepanel.html'});
  assert.equal(await h.read({id:7,windowId:1}),false);
  assert.equal(h.notices.at(-2).open,false);
});
test('global panel hides launchers in its window and survives worker restart/readback',async()=>{
  const h=harness();await h.open({windowId:1,path:'sidepanel.html'},true);
  const restarted=harness(h.session);
  assert.equal(await restarted.read({id:8,windowId:1}),true);
  assert.equal(await restarted.read({id:9,windowId:2}),false);
  await restarted.open({windowId:1},false);
  assert.equal(await restarted.read({id:8,windowId:1}),false);
});
test('rapid open-close updates are serialized and unrelated panels are ignored',async()=>{
  const h=harness();
  await Promise.all([h.open({windowId:1,tabId:7},true),h.open({windowId:1,tabId:7},false)]);
  assert.equal(await h.read({id:7,windowId:1}),false);
  await h.open({windowId:1,path:'other.html'},true);
  assert.equal(await h.read({id:7,windowId:1}),false);
});
test('launcher hides, reappears and stays hidden after body replacement',async()=>{
  const elements=new Map();let listener,tick;
  const body={appendChild:node=>elements.set(node.id,node)};
  const scope=vm.createContext({MaximoPartLogic:{pageKind:()=>"workorder"},location:{href:'https://eam.indraweb.net/maximo/ui/'},
    document:{documentElement:{dataset:{}},body,getElementById:id=>elements.get(id),
      createElement:()=>({addEventListener(){}})},setInterval:fn=>tick=fn,
    chrome:{runtime:{onMessage:{addListener:fn=>listener=fn},sendMessage:async()=>({ok:true,value:{open:false}})}}});
  vm.runInContext(fs.readFileSync(require.resolve('../panel_content.js'),'utf8'),scope);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements.get('maximo-desktop-panel-launcher').hidden,false);
  listener({type:'PANEL_VISIBILITY',open:true});
  assert.equal(elements.get('maximo-desktop-panel-launcher').hidden,true);
  elements.clear();scope.chrome.runtime.sendMessage=async()=>({ok:true,value:{open:true}});tick();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements.get('maximo-desktop-panel-launcher').hidden,true);
  listener({type:'PANEL_VISIBILITY',open:false});
  assert.equal(elements.get('maximo-desktop-panel-launcher').hidden,false);
});
