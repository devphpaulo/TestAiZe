(() => {
  const page = document.querySelector('[data-bug-page]');
  if (!page) return;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const bug = JSON.parse(document.getElementById('bug-data').textContent);
  const editor = document.getElementById('bug-editor');
  const form = document.getElementById('bug-form');
  const localFiles = new Map();
  const removed = new Set();
  const pending = new Set();
  const readonly = bug?.status === 'finalizado';
  let insertion = null;
  const openingImages = new Set((bug?.evidence || []).filter(item => item.kind === 'abertura').map(item => item.id));
  const feedback = message => { document.getElementById('bug-feedback').textContent = message; };
  async function api(url, options = {}) {
    const response = await fetch(url, {...options, headers: {'X-CSRF-Token': csrf, ...options.headers}});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Não foi possível concluir a operação.');
    return result;
  }
  const post = (url, payload) => api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  const imageUrl = id => `/bugs/${bug.id}/evidencias/${id}`;
  function paragraph(text = '') {
    const node = document.createElement('p');
    node.textContent = text;
    if (!text) node.append(document.createElement('br'));
    return node;
  }
  function rememberSelection() {
    const selection = window.getSelection();
    if (selection.rangeCount && editor.contains(selection.anchorNode)) insertion = selection.getRangeAt(0).cloneRange();
  }
  editor.addEventListener('keyup', rememberSelection);
  editor.addEventListener('mouseup', rememberSelection);
  function insert(node) {
    if (insertion && editor.contains(insertion.commonAncestorContainer)) {
      const parent = insertion.startContainer.nodeType === Node.ELEMENT_NODE ? insertion.startContainer : insertion.startContainer.parentElement;
      const figure = parent.closest('.rich-image');
      if (figure) figure.after(node);
      else { insertion.deleteContents(); insertion.insertNode(node); }
    } else editor.append(node);
    const after = paragraph(); node.after(after);
    const range = document.createRange(); range.selectNodeContents(after); range.collapse(true);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    insertion = range.cloneRange();
  }
  const images = readonly ? null : TestaizeImages.mount(editor, {
    remove: entry => { if (!localFiles.has(entry.id)) removed.add(entry.id); insertion = null; },
    restore: entry => { removed.delete(entry.id); },
    error: error => feedback(error.message)
  });
  function imageNode(id, src, width = 100) {
    const figure = TestaizeImages.create({id, url: src, width, name: 'Evidência de abertura'});
    return images ? images.register(figure) : figure;
  }
  const initial = bug ? JSON.parse(bug.description_doc) : [{type: 'text', text: ''}];
  initial.forEach(block => editor.append(block.type === 'text' ? paragraph(block.text) : imageNode(block.id, imageUrl(block.id), block.width)));
  async function addFile(file) {
    if (readonly) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) throw new Error('Use PNG, JPEG ou WebP com até 10 MiB.');
    let id, src;
    if (bug) {
      const data = new FormData(); data.append('imagem', file); data.append('kind', 'abertura');
      const result = await api(`/api/bugs/${bug.id}/evidencias`, {method: 'POST', body: data});
      id = result.evidence.id; openingImages.add(id); src = imageUrl(id);
    } else {
      id = crypto.randomUUID(); localFiles.set(id, file); src = URL.createObjectURL(file);
    }
    insert(imageNode(id, src));
  }
  function upload(file) {
    const task = addFile(file).catch(error => { feedback(error.message); throw error; });
    pending.add(task); task.finally(() => pending.delete(task)).catch(() => {});
    return task;
  }
  document.getElementById('bug-image-choose')?.addEventListener('click', () => document.getElementById('bug-images').click());
  document.getElementById('bug-images')?.addEventListener('change', async event => {
    for (const file of event.target.files) { try { await upload(file); } catch (_) { break; } }
    event.target.value = '';
  });
  editor.addEventListener('paste', async event => {
    if (readonly) return;
    event.preventDefault(); rememberSelection();
    const files = [...event.clipboardData.items].filter(item => item.kind === 'file').map(item => item.getAsFile());
    if (files.length) {
      for (const file of files) { try { await upload(file); } catch (_) { break; } }
      return;
    }
    const text = event.clipboardData.getData('text/plain');
    const selection = window.getSelection();
    if (selection.rangeCount && editor.contains(selection.anchorNode)) {
      const range = selection.getRangeAt(0); range.deleteContents();
      const node = document.createTextNode(text); range.insertNode(node); range.setStartAfter(node); range.collapse(true);
      selection.removeAllRanges(); selection.addRange(range); insertion = range.cloneRange();
    }
  });
  editor.addEventListener('drop', event => { event.preventDefault(); });
  editor.addEventListener('keydown', event => {
    if (event.key === 'Enter' && window.getSelection()?.anchorNode?.parentElement?.closest('.rich-image')) {
      event.preventDefault(); insert(paragraph());
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]'); button.disabled = true;
    try {
      await Promise.all([...pending]);
      if (images) await images.flush();
      const fields = Object.fromEntries(new FormData(form)); fields.blocks = TestaizeDocument.serialize(editor);
      const usedImages = new Set(fields.blocks.filter(block => block.type === 'image').map(block => block.id));
      for (const id of openingImages) { if (!usedImages.has(id)) removed.add(id); else removed.delete(id); }
      let result;
      if (bug) {
        result = await post(`/api/bugs/${bug.id}`, fields);
        for (const id of removed) await api(`/api/bugs/${bug.id}/evidencias/${id}`, {method: 'DELETE'});
      } else {
        const data = new FormData(); data.append('document', JSON.stringify(fields));
        for (const [id, file] of localFiles) { if (usedImages.has(id)) data.append(id, file); }
        const origin = page.dataset.originCase ? `?precondition_case=${encodeURIComponent(page.dataset.originCase)}` : '';
        result = await api(`/api/sessao/${page.dataset.sessionId}/bugs${origin}`, {method: 'POST', body: data});
      }
      window.location.href = `/bugs/${result.bug.id}?session_id=${encodeURIComponent(page.dataset.sessionId)}`;
    } catch (error) { feedback(error.message); }
    finally { button.disabled = false; }
  });
  document.querySelectorAll('[data-transition]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await post(`/api/bugs/${bug.id}/estado`, {target: button.dataset.transition, expected_state: bug.status, token: bug.current_retest_token});
      window.location.reload();
    } catch (error) { feedback(error.message); button.disabled = false; }
  }));
  document.getElementById('bug-proof')?.addEventListener('submit', async event => {
    event.preventDefault(); const proof = event.currentTarget; const button = proof.querySelector('button'); button.disabled = true;
    try {
      const data = new FormData(proof); data.append('kind', 'reteste'); data.append('token', bug.current_retest_token);
      if (!data.get('imagem')?.size) data.delete('imagem');
      await api(`/api/bugs/${bug.id}/evidencias`, {method: 'POST', body: data}); window.location.reload();
    } catch (error) { feedback(error.message); button.disabled = false; }
  });
  document.querySelectorAll('[data-unlink-session]').forEach(button => button.addEventListener('click', async () => {
    try { await api(`/api/bugs/${bug.id}/sessao/${button.dataset.unlinkSession}/vinculos/${button.dataset.unlinkCase}`, {method: 'DELETE'}); window.location.reload(); }
    catch (error) { feedback(error.message); }
  }));
  const dialog = document.getElementById('bug-link-dialog');
  dialog?.addEventListener('close', () => document.getElementById('bug-link-open')?.focus());
  const statusLabels = {nao_executado: 'Não executado', em_andamento: 'Em andamento', aprovado: 'Aprovado', reprovado: 'Reprovado', bloqueado: 'Bloqueado'};
  let linkBusy = false;
  const allCheck = document.getElementById('bug-link-all');
  const search = document.getElementById('bug-link-search');
  const normalizeSearch = text => text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  function caseChecks() { return [...dialog.querySelectorAll('[data-case-id]:not(:disabled)')]; }
  function updateSelection() {
    if (!dialog) return;
    const checks = caseChecks();
    const selected = checks.filter(input => input.checked).length;
    const visible = checks.filter(input => !input.closest('.bug-link-case').hidden);
    allCheck.checked = visible.length > 0 && visible.every(input => input.checked);
    allCheck.indeterminate = visible.some(input => input.checked) && !allCheck.checked;
    allCheck.disabled = visible.length === 0;
    document.getElementById('bug-link-count').textContent = `${selected} de ${checks.length} selecionados`;
    document.getElementById('bug-link-confirm').disabled = !selected || linkBusy;
    dialog.querySelectorAll('.bug-link-folder').forEach(group => {
      const groupChecks = [...group.querySelectorAll('[data-case-id]:not(:disabled)')].filter(input => !input.closest('.bug-link-case').hidden);
      const checkbox = group.querySelector('[data-folder-check]');
      checkbox.checked = groupChecks.length > 0 && groupChecks.every(input => input.checked);
      checkbox.indeterminate = groupChecks.some(input => input.checked) && !checkbox.checked;
      checkbox.disabled = groupChecks.length === 0;
    });
  }
  function filterCases() {
    const term = normalizeSearch(search.value.trim());
    dialog.querySelectorAll('.bug-link-case').forEach(row => { row.hidden = !row.dataset.search.includes(term); });
    dialog.querySelectorAll('.bug-link-folder').forEach(group => { group.hidden = [...group.querySelectorAll('.bug-link-case')].every(row => row.hidden); });
    document.getElementById('bug-link-empty').hidden = [...dialog.querySelectorAll('.bug-link-case')].some(row => !row.hidden);
    updateSelection();
  }
  function renderLinkCases(cases) {
    const container = document.getElementById('bug-link-cases'); container.replaceChildren();
    const folders = new Map();
    for (const item of cases.filter(item => item.status !== 'aprovado')) {
      if (!folders.has(item.folder)) {
        const group = document.createElement('section'); group.className = 'bug-link-folder';
        const heading = document.createElement('label'); heading.className = 'bug-link-folder-heading';
        const all = document.createElement('input'); all.type = 'checkbox'; all.dataset.folderCheck = '';
        const folderName = item.folder.replace(/\\/g, '/').split('/').filter(Boolean).pop() || 'Sem pasta';
        all.setAttribute('aria-label', `Selecionar pasta ${folderName}`);
        all.addEventListener('change', () => { group.querySelectorAll('[data-case-id]:not(:disabled)').forEach(input => { if (!input.closest('.bug-link-case').hidden) input.checked = all.checked; }); updateSelection(); });
        const text = document.createElement('span'); const name = document.createElement('strong'); name.textContent = folderName; name.title = item.folder;
        const count = document.createElement('small'); count.dataset.folderCount = ''; text.append(name, count); heading.append(all, text); group.append(heading);
        folders.set(item.folder, group); container.append(group);
      }
      const group = folders.get(item.folder);
      const label = document.createElement('label'); label.className = 'bug-link-case'; label.dataset.search = normalizeSearch(`${item.name} ${item.folder}`);
      const input = document.createElement('input'); input.type = 'checkbox'; input.dataset.caseId = item.id; input.disabled = item.result !== 'elegivel';
      input.setAttribute('aria-label', item.name); input.addEventListener('change', updateSelection);
      const name = document.createElement('span'); name.className = 'bug-link-case-name'; name.textContent = item.name;
      if (item.result === 'ja_vinculado') { const hint = document.createElement('small'); hint.textContent = 'Já vinculado'; name.append(hint); }
      const badge = document.createElement('span'); badge.className = `bug-badge bug-case-${item.status}`; badge.textContent = statusLabels[item.status];
      label.append(input, name, badge); group.append(label);
    }
    for (const group of folders.values()) {
      const count = group.querySelectorAll('[data-case-id]').length;
      group.querySelector('[data-folder-count]').textContent = `${count} ${count === 1 ? 'caso' : 'casos'}`;
    }
    filterCases();
  }
  document.getElementById('bug-link-open')?.addEventListener('click', async event => {
    const trigger = event.currentTarget; trigger.disabled = true;
    try {
      const result = await api(`/api/bugs/${bug.id}/sessao/${page.dataset.sessionId}/vinculos`);
      search.value = ''; renderLinkCases(result.cases);
      document.getElementById('bug-link-feedback').textContent = '';
      document.getElementById('bug-link-close').textContent = 'Cancelar';
      dialog.showModal(); search.focus();
    } catch (error) { feedback(error.message); }
    finally { trigger.disabled = false; }
  });
  search?.addEventListener('input', filterCases);
  allCheck?.addEventListener('change', () => { caseChecks().forEach(input => { if (!input.closest('.bug-link-case').hidden) input.checked = allCheck.checked; }); updateSelection(); });
  for (const id of ['bug-link-close', 'bug-link-x']) document.getElementById(id)?.addEventListener('click', () => dialog.close());
  document.getElementById('bug-link-confirm')?.addEventListener('click', async () => {
    if (linkBusy) return;
    linkBusy = true; updateSelection();
    try {
      const ids = caseChecks().filter(input => input.checked).map(input => Number(input.dataset.caseId));
      const result = await post(`/api/bugs/${bug.id}/sessao/${page.dataset.sessionId}/vinculos`, {case_ids: ids});
      dialog.addEventListener('close', () => window.location.reload(), {once: true});
      const refreshed = await api(`/api/bugs/${bug.id}/sessao/${page.dataset.sessionId}/vinculos`);
      renderLinkCases(refreshed.cases);
      const linked = result.results.filter(item => item.result === 'vinculado').length;
      const existing = result.results.filter(item => item.result === 'ja_vinculado').length;
      const refused = result.results.filter(item => item.result === 'recusado');
      document.getElementById('bug-link-feedback').textContent = [
        linked ? `${linked} ${linked === 1 ? 'caso vinculado' : 'casos vinculados'}.` : '',
        existing ? `${existing} já vinculados.` : '',
        ...refused.map(item => `${item.name}: ${item.reason}.`)
      ].filter(Boolean).join(' ');
      document.getElementById('bug-link-close').textContent = 'Concluir';
    } catch (error) { document.getElementById('bug-link-feedback').textContent = `Erro: ${error.message}`; }
    finally { linkBusy = false; updateSelection(); }
  });
})();
