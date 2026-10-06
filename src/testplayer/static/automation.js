(() => {
  const workspace = document.querySelector('#automation-workspace');
  if (!workspace) return;
  const api = '/api/iniciativas/automacao/recorder/';
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const owner = crypto.randomUUID();
  const status = document.querySelector('#automation-status');
  const shell = document.querySelector('#automation-frame-shell');
  const placeholder = document.querySelector('#automation-placeholder');
  const retry = document.querySelector('#automation-retry');
  const exit = document.querySelector('#automation-exit');
  let url;
  let starting = false;
  let leaving = false;
  let heartbeat;

  function showStatus(message, error = false) {
    status.textContent = message;
    status.parentElement.dataset.error = String(error);
    retry.hidden = !error;
  }

  async function request(action, options = {}) {
    const response = await fetch(api + action, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify({ owner }), signal: AbortSignal.timeout(22000), ...options,
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'Não foi possível iniciar o recorder.');
    return result;
  }

  function embed() {
    const iframe = document.createElement('iframe');
    const destination = new URL(url);
    destination.searchParams.set('theme', document.documentElement.dataset.theme || 'light');
    destination.searchParams.set('accent', document.documentElement.dataset.accent || 'neutro');
    iframe.src = destination.href;
    iframe.title = 'Gravação de testes Playwright: navegador e código';
    iframe.allow = 'clipboard-read; clipboard-write';
    shell.querySelector('iframe')?.remove();
    shell.append(iframe);
    placeholder.hidden = true;
    shell.setAttribute('aria-busy', 'false');
  }

  async function start() {
    if (starting || leaving) return;
    starting = true;
    clearInterval(heartbeat);
    showStatus('Iniciando gravador…');
    shell.setAttribute('aria-busy', 'true');
    try {
      const result = await request('start');
      if (leaving) { await request('stop'); return; }
      url = result.url;
      embed();
      showStatus('Gravador pronto. Informe uma URL para começar.');
      heartbeat = setInterval(checkStatus, 20000);
    } catch (error) {
      showStatus(error.message || 'Conexão interrompida. Tente novamente.', true);
      shell.setAttribute('aria-busy', 'false');
    } finally { starting = false; }
  }

  async function checkStatus() {
    try {
      const response = await fetch(api + 'status?owner=' + encodeURIComponent(owner), { signal: AbortSignal.timeout(5000) });
      if (!response.ok) return;
      const result = await response.json();
      if (result.state !== 'ready') {
        clearInterval(heartbeat);
        shell.querySelector('iframe')?.remove();
        placeholder.hidden = false;
        showStatus(result.state === 'replaced' ? 'Gravação aberta em outra aba. Retome aqui para continuar.' : 'Gravador encerrado. Inicie novamente quando quiser.', true);
      }
    } catch { /* The manager's finite lease handles a missing host. */ }
  }

  function unload() {
    leaving = true;
    clearInterval(heartbeat);
    fetch(api + 'stop', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify({ owner }), keepalive: true }).catch(() => {
      navigator.sendBeacon(api + 'stop', new URLSearchParams({ csrf_token: csrf, owner }));
    });
  }

  retry.addEventListener('click', start);
  exit.addEventListener('click', async () => {
    exit.disabled = true;
    leaving = true;
    try { await request('stop'); window.location.assign(workspace.dataset.home); }
    catch (error) { leaving = false; exit.disabled = false; showStatus('Não foi possível encerrar. Tente novamente.', true); }
  });
  window.addEventListener('pagehide', unload);
  window.addEventListener('pageshow', (event) => { if (event.persisted) { leaving = false; start(); } });
  new MutationObserver(() => {
    // Parent-to-worker presentation message only; recorder protocol remains private.
    const iframe = shell.querySelector('iframe');
    if (iframe && url) iframe.contentWindow.postMessage({ type: 'testaize.appearance',
      theme: document.documentElement.dataset.theme, accent: document.documentElement.dataset.accent }, new URL(url).origin);
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'data-accent'] });
  window.addEventListener('message', (event) => {
    const iframe = shell.querySelector('iframe');
    if (!iframe || !url || event.source !== iframe.contentWindow || event.origin !== new URL(url).origin) return;
    if (event.data?.type === 'testaize.recorder.resize' && Number.isFinite(event.data.height)) {
      iframe.style.height = Math.max(500, Math.min(4000, event.data.height)) + 'px';
    }
  });
  start();
})();
