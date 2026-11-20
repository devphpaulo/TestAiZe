(() => {
  const page = document.querySelector('[data-bug-page]');
  if (!page) return;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const bug = JSON.parse(document.getElementById('bug-data').textContent);
  const editor = document.getElementById('bug-editor');
  const form = document.getElementById('bug-form');
  const localFiles = new Map();
  const readonly = bug?.status === 'finalizado';
  const imageExtensions = new Set(['.png', '.jpeg', '.jpg', '.webp']);
  const input = document.getElementById('bug-files');
  const acceptedExtensions = new Set(input?.accept.split(',') || []);
  const maxFileBytes = Number(page.dataset.maxFileBytes);
  const maxEvidence = Number(page.dataset.maxEvidence);
  const attachmentList = document.getElementById('bug-attachment-list');
  const attachmentSection = document.getElementById('bug-attachments');
  const imageMimes = new Set(['image/png', 'image/jpeg', 'image/webp']);
  let insertion = null;
  const feedback = message => TestaizeAlerts.show(message);
  async function api(url, options = {}) {
    const response = await fetch(url, {...options, headers: {'X-CSRF-Token': csrf, ...options.headers}});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Não foi possível concluir a operação.');
    return result;
  }
  const post = (url, payload) => api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  const imageUrl = id => `/bugs/${bug.id}/evidencias/${id}`;
  const attachments = new Map((bug?.evidence || [])
    .filter(item => item.kind === 'abertura' && !imageMimes.has(item.mime))
    .map(item => [item.id, {name: item.original_name, url: imageUrl(item.id)}]));
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
    remove: () => { insertion = null; },
    error: error => feedback(error.message)
  });
  function imageNode(id, src, width = 100) {
    const figure = TestaizeImages.create({id, url: src, width, name: 'Evidência de abertura'});
    return images ? images.register(figure) : figure;
  }
  const initial = bug ? JSON.parse(bug.description_doc) : [{type: 'text', text: ''}];
  initial.forEach(block => editor.append(block.type === 'text' ? paragraph(block.text) : imageNode(block.id, imageUrl(block.id), block.width)));
  function renderAttachments() {
    attachmentList.replaceChildren();
    attachmentSection.hidden = !attachments.size;
    for (const [id, item] of attachments) {
      const row = document.createElement('li');
      const link = document.createElement('a');
      link.href = item.url; link.download = item.name; link.textContent = item.name;
      row.append(link);
      if (!readonly) {
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'bug-button bug-button-outline';
        remove.textContent = 'Remover'; remove.setAttribute('aria-label', `Remover ${item.name}`);
        remove.addEventListener('click', () => {
          if (localFiles.delete(id)) URL.revokeObjectURL(item.url);
          attachments.delete(id);
          renderAttachments();
          document.getElementById('bug-file-choose').focus();
        });
        row.append(remove);
      }
      attachmentList.append(row);
    }
  }
  renderAttachments();
  function addFiles(files) {
    for (const file of files) {
      try {
        const extension = file.name.toLowerCase().match(/\.[^.]+$/)?.[0];
        if (!acceptedExtensions.has(extension)) throw new Error(`Formato não aceito: ${file.name}.`);
        if (!file.size || file.size > maxFileBytes) throw new Error(`${file.name}: o arquivo deve ter conteúdo e até 10 MB.`);
        if (attachments.size + editor.querySelectorAll('.rich-image').length >= maxEvidence) throw new Error(`Limite de ${maxEvidence} evidências de abertura.`);
        const id = crypto.randomUUID();
        const url = URL.createObjectURL(file);
        localFiles.set(id, file);
        if (imageExtensions.has(extension)) insert(imageNode(id, url));
        else {
          attachments.set(id, {name: file.name, url});
          renderAttachments();
        }
      } catch (error) { feedback(error.message); }
    }
  }
  document.getElementById('bug-file-choose')?.addEventListener('click', () => input.click());
  input?.addEventListener('change', () => {
    addFiles(input.files);
    input.value = '';
  });
  editor.addEventListener('paste', async event => {
    if (readonly) return;
    event.preventDefault(); rememberSelection();
    const files = [...event.clipboardData.items].filter(item => item.kind === 'file').map(item => item.getAsFile()).filter(Boolean);
    if (files.length) {
      addFiles(files);
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
    const button = form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    button.disabled = true;
    try {
      if (images) await images.flush();
      const fields = Object.fromEntries(new FormData(form)); fields.blocks = TestaizeDocument.serialize(editor);
      fields.attachment_ids = [...attachments.keys()];
      const used = new Set([...fields.attachment_ids, ...fields.blocks.filter(block => block.type === 'image').map(block => block.id)]);
      const data = new FormData(); data.append('document', JSON.stringify(fields));
      for (const id of used) { if (localFiles.has(id)) data.append(id, localFiles.get(id)); }
      const result = await api(bug ? `/api/bugs/${bug.id}` : `/api/sessao/${page.dataset.sessionId}/bugs`, {method: 'POST', body: data});
      TestaizeAlerts.next(bug ? 'Alterações salvas.' : 'Bug reportado.', 'success');
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
  document.getElementById('bug-pdf-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch(form.action, {method: 'POST', headers: {'X-CSRF-Token': csrf}});
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.error || 'Não foi possível exportar o PDF.');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `bug-${bug.id.slice(0, 8)}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { feedback(error.message); }
    finally { button.disabled = false; }
  });
  document.getElementById('bug-proof')?.addEventListener('submit', async event => {
    event.preventDefault(); const proof = event.currentTarget; const button = proof.querySelector('button'); button.disabled = true;
    try {
      const data = new FormData(proof); data.append('kind', 'reteste'); data.append('token', bug.current_retest_token);
      if (!data.get('arquivo')?.size) data.delete('arquivo');
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
    } catch (error) { feedback(error.message); }
    finally { linkBusy = false; updateSelection(); }
  });
})();
