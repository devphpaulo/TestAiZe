(() => {
  const page = document.querySelector('#automation-library, #automation-script');
  if (!page) return;
  const api = '/api/iniciativas/automacao/';
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const feedback = document.querySelector('#automation-library-feedback');
  const dialog = document.querySelector('#automation-entity-dialog');
  let editing;
  let activeRun;
  let timer;
  async function request(path, method = 'GET', body) {
    const response = await fetch(api + path, { method, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, ...(body ? { body: JSON.stringify(body) } : {}) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível concluir a operação.');
    return result;
  }
  document.querySelector('#automation-cycle-filter')?.addEventListener('change', (event) => event.currentTarget.form.submit());
  for (const button of document.querySelectorAll('[data-entity-kind]')) button.addEventListener('click', () => {
    editing = button.dataset;
    document.querySelector('#automation-entity-title').textContent = (editing.entityId ? 'Renomear ' : 'Criar ') + (editing.entityKind === 'pastas' ? 'pasta' : 'ciclo');
    document.querySelector('#automation-entity-name').value = editing.entityName || '';
    document.querySelector('#automation-entity-error').textContent = '';
    dialog.showModal();
  });
  document.querySelector('#automation-entity-cancel')?.addEventListener('click', () => dialog.close());
  document.querySelector('#automation-entity-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const result = await request(editing.entityKind + (editing.entityId ? '/' + editing.entityId : ''), editing.entityId ? 'PUT' : 'POST', { name: document.querySelector('#automation-entity-name').value, folder_id: editing.folderId || page.dataset.folder });
      if (!editing.entityId && editing.entityKind === 'pastas') window.location.assign('/iniciativas/automacao/pastas/' + result.item.id);
      else window.location.reload();
    } catch (error) { document.querySelector('#automation-entity-error').textContent = error.message; }
  });
  for (const button of document.querySelectorAll('[data-delete-kind]')) button.addEventListener('click', async () => {
    if (!confirm(`Excluir ${button.dataset.deleteName}? Os scripts deste item serão removidos; o histórico de execuções será preservado.`)) return;
    try { await request(button.dataset.deleteKind + '/' + button.dataset.deleteId, 'DELETE'); window.location.assign(window.location.pathname); }
    catch (error) { feedback.textContent = error.message; }
  });
  function renderRun(run) {
    activeRun = run.id;
    document.querySelector('#suite-progress').hidden = false;
    for (const metric of ['total', 'passed', 'failed', 'skipped']) document.querySelector('#suite-' + metric).textContent = run[metric] || 0;
    const running = run.state === 'running';
    const completed = run.passed + run.failed + run.skipped;
    const stateNames = { completed: 'Execução concluída', cancelled: 'Execução cancelada', interrupted: 'Execução interrompida', error: 'Falha na execução' };
    document.querySelector('#suite-state').textContent = running ? `${completed}/${run.total} testes concluídos. ${run.current || 'Preparando suíte…'}` : stateNames[run.state] || run.state;
    const bar = document.querySelector('#suite-bar'); bar.max = run.total || 1; bar.value = completed;
    document.querySelector('#suite-cancel').hidden = !running;
    document.querySelector('#suite-run').disabled = running || page.dataset.hasScripts === 'false';
    const errors = document.querySelector('#suite-errors'); errors.replaceChildren();
    for (const message of run.errors || []) { const item = document.createElement('pre'); item.textContent = message; errors.append(item); }
    const results = document.querySelector('#suite-results'); results.replaceChildren();
    for (const result of run.results || []) {
      const row = document.createElement('li'); row.dataset.status = result.status;
      const title = document.createElement('strong'); title.textContent = `${result.script_name} · ${result.title}`;
      const status = document.createElement('span'); status.textContent = `${{ passed: 'Aprovado', failed: 'Reprovado', skipped: 'Ignorado' }[result.status]} · ${(result.duration / 1000).toFixed(2)}s`;
      row.append(title, status);
      if (result.error) { const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Motivo da falha'; const reason = document.createElement('pre'); reason.textContent = result.error; details.append(summary, reason); row.append(details); }
      results.append(row);
    }
    clearTimeout(timer);
    if (running) timer = setTimeout(() => loadRun(run.id), 1000);
  }
  async function loadRun(id) {
    try { renderRun((await request('execucoes/' + id)).run); }
    catch (error) { feedback.textContent = error.message; }
  }
  document.querySelector('#suite-run')?.addEventListener('click', async () => {
    try { renderRun((await request('execucoes', 'POST', { folder_id: page.dataset.folder, cycle_id: page.dataset.cycle || null })).run); }
    catch (error) { feedback.textContent = error.message; }
  });
  document.querySelector('#suite-cancel')?.addEventListener('click', async () => {
    try { await request('execucoes/' + activeRun + '/cancelar', 'POST', {}); loadRun(activeRun); }
    catch (error) { feedback.textContent = error.message; }
  });
  for (const button of document.querySelectorAll('[data-view-run]')) button.addEventListener('click', () => loadRun(button.dataset.viewRun));
  if (page.dataset.latestRun) loadRun(page.dataset.latestRun);
  window.addEventListener('pagehide', () => clearTimeout(timer));
})();
