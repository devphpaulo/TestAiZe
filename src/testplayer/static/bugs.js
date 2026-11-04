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
  function imageNode(id, src, width = 100) {
    const figure = document.createElement('figure');
    figure.className = 'rich-image'; figure.contentEditable = 'false';
    figure.dataset.evidenceId = id; figure.dataset.width = String(width); figure.style.width = `${width}%`;
    const image = document.createElement('img'); image.src = src; image.alt = 'Evidência de abertura'; figure.append(image);
    if (!readonly) {
      const controls = document.createElement('span'); controls.className = 'bug-image-controls';
      const label = document.createElement('label'); label.textContent = 'Largura ';
      const slider = document.createElement('input'); slider.type = 'range'; slider.min = '20'; slider.max = '100'; slider.value = width;
      slider.setAttribute('aria-label', 'Largura da imagem');
      slider.addEventListener('input', () => { figure.dataset.width = slider.value; figure.style.width = `${slider.value}%`; });
      label.append(slider); controls.append(label);
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remover imagem';
      remove.addEventListener('click', () => {
        if (localFiles.has(id)) { URL.revokeObjectURL(src); localFiles.delete(id); }
        else removed.add(id);
        figure.remove(); insertion = null;
      }); controls.append(remove); figure.append(controls);
    }
    return figure;
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
      id = result.evidence.id; src = imageUrl(id);
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
      const fields = Object.fromEntries(new FormData(form)); fields.blocks = TestaizeDocument.serialize(editor);
      let result;
      if (bug) {
        result = await post(`/api/bugs/${bug.id}`, fields);
        for (const id of removed) await api(`/api/bugs/${bug.id}/evidencias/${id}`, {method: 'DELETE'});
      } else {
        const data = new FormData(); data.append('document', JSON.stringify(fields));
        for (const [id, file] of localFiles) data.append(id, file);
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
  document.getElementById('bug-link-open')?.addEventListener('click', async () => {
    try {
      const result = await api(`/api/bugs/${bug.id}/sessao/${page.dataset.sessionId}/vinculos`);
      const container = document.getElementById('bug-link-cases'); container.replaceChildren();
      const folders = new Map();
      result.cases.forEach(item => {
        if (!folders.has(item.folder)) {
          const group = document.createElement('fieldset'); const legend = document.createElement('legend');
          const all = document.createElement('input'); all.type = 'checkbox'; all.setAttribute('aria-label', `Selecionar pasta ${item.folder || 'Sem pasta'}`);
          all.addEventListener('change', () => group.querySelectorAll('[data-case-id]:not(:disabled)').forEach(input => { input.checked = all.checked; }));
          legend.append(all, document.createTextNode(` ${item.folder || 'Sem pasta'}`)); group.append(legend);
          folders.set(item.folder, group); container.append(group);
        }
        const label = document.createElement('label'); const input = document.createElement('input'); input.type = 'checkbox'; input.dataset.caseId = item.id;
        input.disabled = item.result !== 'elegivel';
        label.append(input, document.createTextNode(` ${item.name} · ${item.status}${item.reason ? ' · ' + item.reason : ''}${item.result === 'ja_vinculado' ? ' · Já vinculado' : ''}`));
        folders.get(item.folder).append(label);
      });
      document.getElementById('bug-link-feedback').textContent = ''; dialog.showModal();
    } catch (error) { feedback(error.message); }
  });
  document.getElementById('bug-link-close')?.addEventListener('click', () => dialog.close());
  document.getElementById('bug-link-confirm')?.addEventListener('click', async event => {
    const button = event.currentTarget; button.disabled = true;
    try {
      const ids = [...dialog.querySelectorAll('[data-case-id]:checked')].map(input => Number(input.dataset.caseId));
      const result = await post(`/api/bugs/${bug.id}/sessao/${page.dataset.sessionId}/vinculos`, {case_ids: ids});
      document.getElementById('bug-link-feedback').textContent = result.results.map(item => `${item.name}: ${item.result}${item.reason ? ' — ' + item.reason : ''}`).join('; ');
      // Keep the per-case outcome visible until the user closes the modal.
      dialog.addEventListener('close', () => window.location.reload(), {once: true});
    } catch (error) { document.getElementById('bug-link-feedback').textContent = `Erro: ${error.message}`; }
    finally { button.disabled = false; }
  });
})();
