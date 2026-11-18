const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const context = {};
vm.createContext(context);
vm.runInContext(readFileSync(resolve(__dirname, '../src/testplayer/static/image-editor.js'), 'utf8'), context);

test('shared image resizing preserves proportions for every edge', () => {
  for (const [edge,dx,dy] of [['e',80,0],['w',-80,0],['s',0,40],['n',0,-40],['se',0,40]]) {
    assert.equal(context.TestaizeImages.resizedWidth(400,200,800,edge,dx,dy),60);
  }
});

test('image history yields to later native text edits and preserves redo ordering', () => {
  let document = 'text,image,text';
  const history = context.TestaizeImages.createHistory(() => document, () => {});
  const before = document;
  document = 'text,text';
  history.record({undo:()=>{document=before;},redo:()=>{document='text,text';}}, before);
  document += ' typed'; history.input('insertText');
  assert.equal(history.undo(), false); // The browser must undo text first.
  document = 'text,text'; history.input('historyUndo');
  assert.equal(history.undo(), true); assert.equal(document, before);
  assert.equal(history.redo(), true); assert.equal(document, 'text,text');
  history.undo(); history.input('insertText');
  assert.equal(history.redo(), false); // A fresh edit invalidates the redo branch.
});

test('multiple image deletions are restored in reverse order without losing neighboring text', () => {
  let document = ['before','image-a','between','image-b','after'];
  const history = context.TestaizeImages.createHistory(() => JSON.stringify(document), () => {});
  function remove(index) {
    const before = JSON.stringify(document), removed = document[index]; document.splice(index,1);
    history.record({undo:()=>document.splice(index,0,removed), redo:()=>document.splice(index,1)}, before);
  }
  remove(3); remove(1);
  assert.equal(history.undo(),true); assert.equal(history.undo(),true);
  assert.deepEqual(document,['before','image-a','between','image-b','after']);
  assert.equal(history.redo(),true); assert.equal(history.redo(),true);
  assert.deepEqual(document,['before','between','after']);
});
