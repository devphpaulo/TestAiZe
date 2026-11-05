const assert=require('node:assert/strict');
const {test}=require('node:test');
const vm=require('node:vm');
const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const source=readFileSync(resolve(__dirname,'../src/testplayer/static/header.js'),'utf8');
function setup(blockStorage=false) {
  let focused; const stored={}, navigations=[];
  function element(dataset={}) {return {dataset,attrs:{},events:{},addEventListener(type,fn){this.events[type]=fn;},setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];},focus(){focused=this;}};}
  const themes=['light','dark'].map(themeChoice=>element({themeChoice}));
  const colors=['neutro','roxo','verde','vermelho','amarelo'].map(accentChoice=>element({accentChoice}));
  const picker=element(),trigger=element(),panel=element(),boards=element(); panel.hidden=true;
  picker.contains=target=>[picker,trigger,panel,...themes,...colors].includes(target);
  picker.querySelectorAll=selector=>selector.includes('theme')?themes:colors;
  for(const item of themes) item.closest=()=>true;
  for(const item of colors) item.closest=()=>null;
  const elements={'appearance-picker':picker,'appearance-trigger':trigger,'appearance-panel':panel,'board-select':boards};
  const doc={documentElement:{dataset:{theme:'dark',accent:'verde'}},events:{},getElementById:id=>elements[id],addEventListener(type,fn){this.events[type]=fn;}};
  const sandbox={document:doc,localStorage:{setItem(k,v){if(blockStorage)throw Error('disabled');stored[k]=v;}},window:{location:{assign:url=>navigations.push(url)}}};
  vm.createContext(sandbox);vm.runInContext(source,sandbox);
  return {picker,trigger,panel,boards,themes,colors,doc,stored,navigations,get focused(){return focused;}};
}
test('combined panel keeps saved choices, updates both preferences and closes accessibly',()=>{
  const s=setup(); assert.equal(s.themes[1].attrs['aria-pressed'],'true');assert.equal(s.colors[2].attrs['aria-pressed'],'true');
  s.trigger.events.click(); assert.equal(s.panel.hidden,false);assert.equal(s.focused,s.themes[1]);
  s.themes[0].events.click();s.colors[1].events.click();
  assert.equal(s.doc.documentElement.dataset.theme,'light');assert.equal(s.stored['executor-theme'],'light');assert.equal(s.stored['testaize-accent'],'roxo');
  assert.equal(s.panel.hidden,false);
  s.picker.events.keydown({key:'Escape',preventDefault(){},stopPropagation(){}});
  assert.equal(s.panel.hidden,true);assert.equal(s.focused,s.trigger);
});
test('outside click, tabbing away and unavailable storage behave safely',()=>{
  const s=setup(true);s.trigger.events.click();s.themes[0].events.click();assert.equal(s.doc.documentElement.dataset.theme,'light');
  s.doc.events.click({target:{}});assert.equal(s.panel.hidden,true);
  s.trigger.events.click();s.doc.events.focusin({target:{}});assert.equal(s.panel.hidden,true);
});
test('board selection navigates to its option and ignores disabled boards',()=>{
  const s=setup();s.boards.selectedOptions=[{value:'/bugs',disabled:false}];s.boards.events.change();
  s.boards.selectedOptions=[{value:'/iniciativas/automacao',disabled:true}];s.boards.events.change();assert.deepEqual(s.navigations,['/bugs']);
});
