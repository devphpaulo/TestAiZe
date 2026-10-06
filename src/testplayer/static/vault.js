(() => {
  const open = document.querySelector('#vault-open');
  if (!open) return;
  const dialog = document.querySelector('#vault-dialog');
  const list = document.querySelector('#vault-entries');
  const feedback = document.querySelector('#vault-feedback');
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const endpoint = '/api/iniciativas/automacao/cofre';

  async function update(payload) {
    const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível atualizar o Cofre.');
    render(result.entries, payload.key, payload.value);
    feedback.textContent = 'Cofre atualizado. Os valores serão usados ao rodar as etapas.';
  }

  function render(entries, changedKey, submittedValue) {
    if (!changedKey) list.replaceChildren();
    const previousRows = new Map([...list.querySelectorAll('.vault-entry')].map((row) => [row.dataset.key, row]));
    const keys = new Set(entries.map((entry) => entry.key));
    for (const [key, row] of previousRows) if (!keys.has(key)) row.remove();
    for (const entry of entries) {
      if (changedKey && entry.key !== changedKey && previousRows.has(entry.key)) continue;
      const row = document.createElement('form');
      row.className = 'vault-entry';
      row.dataset.key = entry.key;
      const key = document.createElement('code');
      key.textContent = entry.key;
      const reference = document.createElement('small');
      reference.textContent = `process.env.${entry.key}`;
      const title = document.createElement('div');
      title.append(key, reference);
      const value = document.createElement('input');
      value.type = entry.secret ? 'password' : 'text';
      value.autocomplete = 'off';
      value.setAttribute('aria-label', `Valor de ${entry.key}`);
      const knownValue = entry.key === changedKey && typeof submittedValue === 'string' ? submittedValue : previousRows.get(entry.key)?.querySelector('input:not([type="checkbox"])')?.value;
      value.value = entry.secret && entry.has_value ? knownValue || '' : entry.value || '';
      value.placeholder = entry.secret && entry.has_value ? '••••••••' : 'Informe um valor';
      const savedState = document.createElement('small'); savedState.className = 'vault-saved-state';
      savedState.textContent = entry.has_value ? '✓ Valor salvo nesta execução' : 'Nenhum valor cadastrado';
      title.append(savedState);
      let changed = false;
      value.addEventListener('input', () => { changed = true; savedState.textContent = 'Alterado · salve para aplicar'; });
      const secretLabel = document.createElement('label');
      secretLabel.className = 'vault-secret';
      const secret = document.createElement('input');
      secret.type = 'checkbox'; secret.checked = entry.secret;
      secretLabel.append(secret, document.createTextNode('Valor secreto'));
      secret.addEventListener('change', () => { value.type = secret.checked ? 'password' : 'text'; });
      const save = document.createElement('button');
      save.type = 'submit'; save.className = 'button button-secondary'; save.textContent = 'Salvar';
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'button button-ghost'; remove.textContent = 'Limpar';
      remove.setAttribute('aria-label', `Limpar ${entry.key}`);
      remove.addEventListener('click', () => update({ action: 'remove', key: entry.key }).catch((error) => { feedback.textContent = error.message; }));
      row.append(title, value, secretLabel, save, remove);
      row.addEventListener('submit', (event) => {
        event.preventDefault();
        update({ key: entry.key, secret: secret.checked, ...(changed || !entry.has_value ? { value: value.value } : {}) }).catch((error) => { feedback.textContent = error.message; });
      });
      if (previousRows.has(entry.key)) previousRows.get(entry.key).replaceWith(row);
      else list.append(row);
    }
  }

  open.addEventListener('click', async () => {
    feedback.textContent = '';
    dialog.showModal();
    try {
      const response = await fetch(endpoint, { cache: 'no-store' });
      if (!response.ok) throw new Error('Não foi possível abrir o Cofre.');
      render((await response.json()).entries);
    } catch (error) { feedback.textContent = error.message; }
  });
  document.querySelector('#vault-close').addEventListener('click', () => dialog.close());
  document.querySelector('#vault-add').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await update({ key: form.elements.key.value.trim(), value: form.elements.value.value, secret: form.elements.secret.checked });
      form.reset();
    } catch (error) { feedback.textContent = error.message; }
  });
  document.querySelector('#vault-add').elements.secret.addEventListener('change', (event) => {
    document.querySelector('#vault-add').elements.value.type = event.target.checked ? 'password' : 'text';
  });
  dialog.addEventListener('close', () => { list.replaceChildren(); document.querySelector('#vault-add').reset(); });
})();
