const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const source = readFileSync(resolve(__dirname, '../src/testplayer/static/bugs.js'), 'utf8');

function editorContext(readonly = false) {
  const revoked = [];
  const context = {selectedImage: null, insertion: null, readonly, localFiles: new Map(), removed: new Set(),
    URL: {revokeObjectURL: url => revoked.push(url)},
    editor: {addEventListener(){}, focus(){}, contains(){return true;}}, document:{addEventListener(){}}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function selectImage('), source.indexOf('  const initial =')), context);
  function figure(id) {
    return {dataset:{evidenceId:id,width:'65'},style:{},classList:{add(){},remove(){}},focus(){},setAttribute(){},
      contains:()=>false, querySelector:()=>({src:`blob:${id}`}), remove(){this.deleted=true;}};
  }
  return {context, figure, revoked};
}

for (const key of ['Delete', 'Backspace']) test(`${key} removes only the selected image and records ownership cleanup`, () => {
  const {context, figure, revoked} = editorContext();
  const saved = figure('saved'); context.selectImage(saved);
  let prevented = false;
  context.imageKeydown({key,target:saved,preventDefault(){prevented=true;}});
  assert.equal(prevented,true); assert.equal(saved.deleted,true);
  assert.equal(context.removed.has('saved'),true); assert.equal(context.selectedImage,null);
  const local = figure('local'); context.localFiles.set('local',{}); context.selectImage(local);
  context.imageKeydown({key,target:local,preventDefault(){}});
  assert.equal(context.localFiles.has('local'),false); assert.deepEqual(revoked,['blob:local']);
  assert.equal(context.removed.has('local'),false);
});

test('image resize preserves proportions from horizontal, vertical and corner handles', () => {
  const {context,figure} = editorContext();
  for (const [edge,dx,dy] of [['e',80,0],['w',-80,0],['n',0,-40],['s',0,40],['se',0,40]]) {
    assert.equal(context.resizedWidth(400,200,800,edge,dx,dy),60);
  }
  const image = figure('image');
  context.setImageWidth(image,130); assert.equal(image.dataset.width,'100');
  context.setImageWidth(image,10); assert.equal(image.dataset.width,'20');
  context.selectImage(image); context.imageKeydown({key:'ArrowRight',target:image,preventDefault(){}});
  assert.equal(image.dataset.width,'25');
});

test('ordinary text deletion and finalized bug evidence remain untouched', () => {
  const {context,figure} = editorContext();
  context.imageKeydown({key:'Delete',preventDefault(){throw new Error('must preserve text editing');}});
  const image=figure('image'); context.selectImage(image);
  context.imageKeydown({key:'Escape',target:image,preventDefault(){}});
  context.imageKeydown({key:'Backspace',preventDefault(){throw new Error('not selected');}});
  assert.equal(image.deleted,undefined);
  const locked=editorContext(true); const finalImage=locked.figure('final'); locked.context.selectImage(finalImage);
  locked.context.imageKeydown({key:'Delete',preventDefault(){throw new Error('finalized');}});
  assert.equal(finalImage.deleted,undefined);
});


test('returning to text or tabbing away cannot delete a previously selected image', () => {
  const {context,figure} = editorContext(); const image=figure('saved');
  context.selectImage(image);
  context.imageKeydown({key:'Backspace',target:context.editor,preventDefault(){throw new Error('text deletion must remain native');}});
  assert.equal(context.selectedImage,null); assert.equal(image.deleted,undefined);
  context.selectImage(image);
  context.imageKeydown({key:'Tab',target:image});
  assert.equal(context.selectedImage,null); assert.equal(image.deleted,undefined);
});
