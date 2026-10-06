const parameters = new URLSearchParams(location.search);
const embedded = parameters.get('embedded') === '1';
document.documentElement.dataset.embedded = String(embedded);
function appearance(theme, accent) {
  document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.accent = ['roxo', 'verde', 'vermelho', 'amarelo'].includes(accent) ? accent : 'neutro';
}
appearance(parameters.get('theme'), parameters.get('accent'));
const parentOrigin = document.referrer ? new URL(document.referrer).origin : null;
window.addEventListener('message', (event) => {
  if (event.source === parent && event.origin === parentOrigin && event.data?.type === 'testaize.appearance') appearance(event.data.theme, event.data.accent);
  if (event.source === parent && event.origin === parentOrigin && event.data?.type === 'testaize.export.request') {
    parent.postMessage({ type: 'testaize.export.code', requestId: event.data.requestId, code: document.querySelector('#code').value }, parentOrigin);
  }
});
const tabs = [document.querySelector('#code-tab'), document.querySelector('#steps-tab')];
function selectTab(selected) {
  for (const tab of tabs) {
    const active = tab === selected;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
  }
}
for (const tab of tabs) {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs[1] : tabs.find((item) => item !== tab);
    selectTab(next); next.focus();
  });
}
if (embedded && parentOrigin) {
  new ResizeObserver(() => parent.postMessage({ type: 'testaize.recorder.resize', height: Math.ceil(document.querySelector('.recorder-app').getBoundingClientRect().height) }, parentOrigin)).observe(document.querySelector('.recorder-app'));
}
