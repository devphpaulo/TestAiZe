const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const source = readFileSync(resolve(__dirname, '../src/testplayer/static/app.js'), 'utf8');

test('late status responses cannot overwrite a newer revision or execution', () => {
  const buttons = [{dataset:{value:'bloqueado'}}, {dataset:{value:'reprovado'}}];
  const row = {querySelectorAll: () => buttons};
  const automatic = {classList:{toggle(){}}, setAttribute(){}};
  const view = {dataset:{executionGeneration:'current',statusRevision:'4',manualStatus:'bloqueado'},
    querySelector: selector => selector === '.case-status-buttons' ? row : automatic};
  let renders = 0;
  const sandbox = {selectIcon(){}, updateSummary(){}, renderMiniPlayer(){renders++;}, setSaveState(){}};
  vm.createContext(sandbox);
  vm.runInContext(source.slice(source.indexOf('  function applyCaseState('), source.indexOf('  function persistStatus(')), sandbox);
  sandbox.applyCaseState(view, {status_revision:3,execution_generation:'current',manual_status:''});
  sandbox.applyCaseState(view, {status_revision:7,execution_generation:'old',manual_status:''});
  assert.equal(view.dataset.manualStatus, 'bloqueado');
  assert.equal(renders, 0);
  sandbox.applyCaseState(view, {status_revision:5,execution_generation:'current',manual_status:'reprovado'});
  assert.equal(view.dataset.manualStatus, 'reprovado');
  assert.equal(view.dataset.statusRevision, '5');
  assert.equal(renders, 1);
});

test('dependent actions wait for pending status and propagate failure', async () => {
  let resolveStatus;
  const status = new Promise(resolve => {resolveStatus = resolve;});
  const sandbox = {statusInFlight:new Map([['1',status]]), caseTimers:new Map(), caseInFlight:new Map(),
    flushPendingMedia:async()=>{}, timers:new Map(), inFlight:new Map(), persist:async()=>{}, persistCase:async()=>{}};
  vm.createContext(sandbox);
  vm.runInContext(source.slice(source.indexOf('  async function flushView('), source.indexOf("  document.querySelectorAll('.failure-report-form')")), sandbox);
  const view = {dataset:{caseView:'1'},querySelectorAll:()=>[]};
  let finished = false;
  const flush = sandbox.flushView(view).then(()=>{finished=true;});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(finished, false);
  resolveStatus(); await flush;
  assert.equal(finished, true);
  sandbox.statusInFlight.set('1',Promise.reject(new Error('status failed')));
  await assert.rejects(sandbox.flushView(view), /status failed/);
});
