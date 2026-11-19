import {test} from 'node:test';
import assert from 'node:assert/strict';
import {detectOts,linksFor} from '../public/core.mjs';
test('notification reads visible OT and ignores internal ID',()=>{
 assert.deepEqual(detectOts("La orden de trabajo: '4448382 ' con descripcion: 'Equipo'\nhttps://eam.indraweb.net/maximo/ui/?event=loadapp&value=wo_tr&workorderid=4483953"),['4448382']);
});
test('internal identifiers alone never become an OT',()=>{
 assert.deepEqual(detectOts('https://eam.indraweb.net/maximo/ui/?uniqueid=4483953&workorderid=4483953'),[]);
 assert.deepEqual(detectOts('Incidencia 36316972; equipo 1815-UI73'),[]);
});
test('several contextual OTs are deduplicated, not silently selected',()=>{
 assert.deepEqual(detectOts('OT 4448382\nOT: 4448382\nOrden de trabajo: 4446909'),['4448382','4446909']);
});
test('read only URL is rebuilt from trusted domain and fixed plant',()=>{
 const links=linksFor('4448382');const url=new URL(links.web);
 assert.equal(url.origin,'https://eam.indraweb.net');
 assert.equal(url.searchParams.get('additionaleventvalue'),"wonum='4448382' and siteid='LAB-BAD'");
 assert.equal(links.md,'maximodesk://ot/4448382');
 assert.equal(linksFor('4448382',true).md,'maximodesk-dev://ot/4448382');
});
test('bad IDs cannot introduce SQL or other navigation',()=>{
 for(const value of ['',null,"4448382' or 1=1",'https://evil.test', '4'.repeat(21),'<script>']) assert.throws(()=>linksFor(value));
});
test('filtered links can supply OT; foreign hosts cannot',()=>{
 assert.deepEqual(detectOts('',[linksFor('4448382').web]),['4448382']);
 assert.deepEqual(detectOts('',[linksFor('4448382').web.replace('eam.indraweb.net','evil.test')]),[]);
});

test('MD modes preserve web target and default backward compatibility',()=>{
 const normal=linksFor('4448382');
 for(const action of ['open_filter','filter']) {
  const links=linksFor('4448382',true,action);
  assert.equal(links.web,normal.web);
  assert.equal(links.md,`maximodesk-dev://ot/4448382?action=${action}`);
 }
 assert.throws(()=>linksFor('4448382',false,'close'));
});
