const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const context = {}; vm.createContext(context);
vm.runInContext(readFileSync(resolve(__dirname, '../src/testplayer/static/image-editor.js'), 'utf8'), context);
function figure(id='image', width='65') {
  const image={src:`/images/${id}`,alt:'evidence.png'};
  return {dataset:{evidenceId:id,width,deleteUrl:`/delete/${id}`},querySelector:()=>image};
}
test('bug undo restores ownership and keeps the original image and width available', async () => {
  const removed=new Set(), localFiles=new Map([['local','original file']]);
  const ledger=context.TestaizeImages.createLedger({remove:entry=>removed.add(entry.id),restore:entry=>removed.delete(entry.id)});
  const node=figure('local'); ledger.register(node);
  ledger.scan([]); await ledger.flush();
  assert.equal(removed.has('local'),true); assert.equal(localFiles.get('local'),'original file');
  ledger.scan([node]); await ledger.flush();
  assert.equal(removed.has('local'),false); assert.equal(node.dataset.width,'65');
  ledger.scan([]); await ledger.flush();
  assert.equal(removed.has('local'),true);
});
test('Player undo after deletion and autosave reuploads bytes and replaces obsolete IDs', async () => {
  let uploads=0; const files=new Map([['image','bytes']]);
  const ledger=context.TestaizeImages.createLedger({
    remove:entry=>{ entry.blob=files.get(entry.id); files.delete(entry.id); },
    restore:entry=>{ const id=`restored-${++uploads}`; files.set(id,entry.blob); return {id,url:`/images/${id}`,delete_url:`/delete/${id}`}; }
  });
  const node=figure(); ledger.register(node); ledger.scan([]); await ledger.flush();
  assert.equal(files.size,0);
  ledger.scan([node]); await ledger.flush();
  assert.equal(node.dataset.evidenceId,'restored-1'); assert.equal(node.dataset.width,'65');
  assert.equal(files.get('restored-1'),'bytes'); assert.equal(node.dataset.deleteUrl,'/delete/restored-1');
  ledger.scan([]); await ledger.flush();
  const nativeUndoNode=figure('image'); ledger.scan([nativeUndoNode]); await ledger.flush();
  assert.equal(nativeUndoNode.dataset.evidenceId,'restored-2'); assert.equal(files.size,1);
});
test('undo racing with an in-flight delete waits and restores once', async () => {
  let release; const gate=new Promise(resolve=>{release=resolve;}); const actions=[];
  const ledger=context.TestaizeImages.createLedger({remove:async()=>{actions.push('delete');await gate;},restore:()=>{actions.push('restore');}});
  const node=figure(); ledger.register(node); ledger.scan([]); ledger.scan([node]);
  release(); await ledger.flush();
  assert.deepEqual(actions,['delete','restore']);
});
test('restore failure blocks saving until the invalid undo is redone', async () => {
  const ledger=context.TestaizeImages.createLedger({remove:()=>{},restore:()=>{throw new Error('upload failed');}});
  const node=figure(); ledger.register(node); ledger.scan([]); await ledger.flush();
  ledger.scan([node]); await assert.rejects(ledger.flush(),/upload failed/);
  await new Promise(resolve=>setImmediate(resolve));
  ledger.scan([]); await ledger.flush();
});
