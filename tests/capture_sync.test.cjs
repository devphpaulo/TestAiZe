const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(resolve(__dirname, '../src/testplayer/static/app.js'), 'utf8');
// Exercise the production event handlers with an editor double; no browser runtime.
const handlers = source.slice(source.indexOf('  function applyCaptureResult('), source.indexOf('  async function pollCapture('));
function player({ revision = 2, generation = 'current', dirty = false, conflict = false } = {}) {
  const editor = { _imageUrls: new Map(), contains: () => false, querySelector: () => null };
  const view = { dataset: { executionGeneration: generation } };
  const card = {
    dataset: { stepId: '10', resultRevision: String(revision), revisionConflict: String(conflict) },
    querySelector: () => editor, closest: () => view,
  };
  const writes = [];
  const sandbox = {
    player: { dataset: { sessionId: 'session' } }, captureClientId: 'browser', captureSilent: false,
    document: { activeElement: null, querySelector: () => card },
    timers: new Map(dirty ? [['10', 1]] : []), inFlight: new Map(),
    setSaveState: () => {}, renderMiniPlayer: () => {},
    syncObservedText: (_editor, text) => writes.push(text),
    makeImageFigure: (image) => image, insertFigure: () => writes.push('image'),
  };
  vm.createContext(sandbox);
  vm.runInContext(handlers, sandbox);
  return { sandbox, card, writes };
}
const event = { session_id: 'session', case_id: 1, step_id: 10, revision: 3,
  execution_generation: 'current', actual: 'Texto remoto', evidence_id: 'image' };

test('reloading does not replay older text or evidence from the event queue', () => {
  const { sandbox, writes, card } = player();
  sandbox.applyCaptureResult({ ...event, revision: 1 });
  sandbox.applyCaptureEvidence({ ...event, revision: 1 });
  assert.deepEqual(writes, []);
  assert.equal(card.dataset.resultRevision, '2');
});
test('events from a previous execution cannot change the retest editor', () => {
  const { sandbox, writes } = player({ revision: 0, generation: 'new-run' });
  sandbox.applyCaptureResult(event);
  sandbox.applyCaptureEvidence(event);
  assert.deepEqual(writes, []);
});
test('a queued local edit is preserved even after its field loses focus', () => {
  const { sandbox, writes, card } = player({ dirty: true });
  sandbox.applyCaptureResult(event);
  assert.deepEqual(writes, []);
  assert.equal(card.dataset.revisionConflict, 'true');
  assert.equal(card.dataset.resultRevision, '2');
});
test('an evidence event cannot clear an existing text conflict', () => {
  const { sandbox, card } = player({ conflict: true });
  sandbox.applyCaptureEvidence(event);
  assert.equal(card.dataset.revisionConflict, 'true');
  assert.equal(card.dataset.resultRevision, '2');
});
test('a current contiguous result is reconciled when the editor is clean', () => {
  const { sandbox, writes, card } = player();
  sandbox.applyCaptureResult(event);
  assert.deepEqual(writes, ['Texto remoto']);
  assert.equal(card.dataset.resultRevision, '3');
});
