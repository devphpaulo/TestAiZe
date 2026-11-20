const assert = require('node:assert/strict');
const { test } = require('node:test');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');

function setup({ blocked = false, saved = null, dark = true } = {}) {
  function eventTarget() {
    return {
      events: {},
      addEventListener(type, listener) { this.events[type] = listener; },
    };
  }
  const media = { ...eventTarget(), matches: dark };
  const trigger = { ...eventTarget(), setAttribute(name, value) { this[name] = value; } };
  const boards = eventTarget();
  const document = {
    ...eventTarget(),
    documentElement: { dataset: {} },
    getElementById(id) { return { 'appearance-trigger': trigger, 'board-select': boards }[id]; },
  };
  const navigations = [];
  const sandbox = vm.createContext({
    document,
    localStorage: {
      getItem() { if (blocked) throw Error('disabled'); return saved; },
      setItem(_key, value) { if (blocked) throw Error('disabled'); saved = value; },
    },
    window: { matchMedia() { return media; }, location: { assign(url) { navigations.push(url); } } },
  });
  for (const file of ['theme.js', 'header.js']) {
    vm.runInContext(readFileSync(resolve(__dirname, '../src/testplayer/static', file), 'utf8'), sandbox);
  }
  document.events.DOMContentLoaded();
  return { root: document.documentElement, trigger, boards, media, navigations, get saved() { return saved; } };
}

test('the theme button toggles directly and keeps the saved choice', () => {
  const ui = setup({ saved: 'light' });
  assert.equal(ui.root.dataset.theme, 'light');
  assert.equal(ui.trigger['aria-pressed'], 'false');
  ui.trigger.events.click();
  assert.equal(ui.root.dataset.theme, 'dark');
  assert.equal(ui.trigger['aria-pressed'], 'true');
  assert.equal(ui.saved, 'dark');
});

test('the system theme applies until the user makes a choice, even without storage', () => {
  const ui = setup({ blocked: true });
  assert.equal(ui.root.dataset.theme, 'dark');
  ui.media.matches = false;
  ui.media.events.change();
  assert.equal(ui.root.dataset.theme, 'light');
  ui.trigger.events.click();
  ui.media.events.change();
  assert.equal(ui.root.dataset.theme, 'dark');
});

test('board selection navigates to its option and ignores disabled boards', () => {
  const ui = setup();
  ui.boards.selectedOptions = [{ value: '/bugs', disabled: false }];
  ui.boards.events.change();
  ui.boards.selectedOptions = [{ value: '/iniciativas/automacao', disabled: true }];
  ui.boards.events.change();
  assert.deepEqual(ui.navigations, ['/bugs']);
});
