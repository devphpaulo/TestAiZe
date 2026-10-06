(() => {
  const button = document.querySelector('#automation-save');
  if (!button) return;
  const api = '/api/iniciativas/automacao/';
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const dialog = document.querySelector('#automation-save-dialog');
  const folderSelect = document.querySelector('#save-script-folder');
  const cycleSelect = document.querySelector('#save-script-cycle');
  let catalog = [];
  let savedId;
  let savedDestination;
  let exportedCode;
  async function request(path, body) {
    const response = await fetch(api + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body) } : {});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível salvar.');
    return result;
  }
  function options(select, entries, newLabel) {
    select.replaceChildren();
    for (const entry of entries) select.add(new Option(entry.name, entry.id));
    select.add(new Option(newLabel, '__new'));
  }
  function folderChanged() {
    const folder = catalog.find((item) => item.id === folderSelect.value);
    options(cycleSelect, folder?.cycles || [], 'Criar novo ciclo…');
    document.querySelector('#save-new-folder-label').hidden = folderSelect.value !== '__new';
    document.querySelector('#save-new-folder-name').required = folderSelect.value === '__new';
    cycleChanged();
  }
  function cycleChanged() {
    document.querySelector('#save-new-cycle-label').hidden = cycleSelect.value !== '__new';
    document.querySelector('#save-new-cycle-name').required = cycleSelect.value === '__new';
  }
  function exportCode() {
    const iframe = document.querySelector('.automation-frame-shell iframe');
    if (!iframe) return Promise.reject(new Error('Aguarde o recorder iniciar.'));
    const origin = new URL(iframe.src).origin;
    const requestId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => { cleanup(); reject(new Error('O recorder não respondeu. Tente novamente.')); }, 5000);
      function cleanup() { clearTimeout(timeout); window.removeEventListener('message', receive); }
      function receive(event) {
        if (event.source !== iframe.contentWindow || event.origin !== origin || event.data?.type !== 'testaize.export.code' || event.data.requestId !== requestId) return;
        cleanup(); resolve(event.data.code);
      }
      window.addEventListener('message', receive);
      iframe.contentWindow.postMessage({ type: 'testaize.export.request', requestId }, origin);
    });
  }
  button.addEventListener('click', async () => {
    try {
      exportedCode = await exportCode();
      if (!exportedCode?.trim()) throw new Error('Grave ou escreva um teste antes de salvar.');
      catalog = (await request('biblioteca')).folders;
      options(folderSelect, catalog, 'Criar nova pasta…');
      if (savedDestination) folderSelect.value = savedDestination.folder;
      folderChanged();
      if (savedDestination) { cycleSelect.value = savedDestination.cycle; cycleChanged(); }
      document.querySelector('#save-script-error').textContent = '';
      dialog.showModal();
    } catch (error) { document.querySelector('#automation-save-feedback').textContent = error.message; }
  });
  folderSelect.addEventListener('change', folderChanged);
  cycleSelect.addEventListener('change', cycleChanged);
  document.querySelector('#save-script-cancel').addEventListener('click', () => dialog.close());
  document.querySelector('#automation-save-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = event.currentTarget.querySelector('[type="submit"]'); submit.disabled = true;
    try {
      let folderId = folderSelect.value;
      if (folderId === '__new') {
        const folder = (await request('pastas', { name: document.querySelector('#save-new-folder-name').value })).item;
        folderId = folder.id; catalog.push({ ...folder, cycles: [] });
        options(folderSelect, catalog, 'Criar nova pasta…'); folderSelect.value = folderId; folderChanged();
      }
      let cycleId = cycleSelect.value;
      if (cycleId === '__new') {
        const cycle = (await request('ciclos', { folder_id: folderId, name: document.querySelector('#save-new-cycle-name').value })).item;
        cycleId = cycle.id; catalog.find((folder) => folder.id === folderId).cycles.push(cycle);
        options(cycleSelect, catalog.find((folder) => folder.id === folderId).cycles, 'Criar novo ciclo…'); cycleSelect.value = cycleId; cycleChanged();
      }
      const result = await request('scripts', { cycle_id: cycleId, name: document.querySelector('#save-script-name').value, code: exportedCode, script_id: savedId });
      savedId = result.item.id;
      savedDestination = { folder: folderId, cycle: cycleId };
      dialog.close();
      const feedback = document.querySelector('#automation-save-feedback'); feedback.replaceChildren(document.createTextNode('Script salvo. '));
      const link = document.createElement('a'); link.textContent = 'Abrir script na biblioteca'; link.href = '/iniciativas/automacao/scripts/' + savedId; feedback.append(link);
    } catch (error) { document.querySelector('#save-script-error').textContent = error.message; }
    finally { submit.disabled = false; }
  });
})();
