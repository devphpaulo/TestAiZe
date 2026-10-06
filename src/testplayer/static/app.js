(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const themeButton = document.getElementById('theme-toggle');
  function updateThemeButton() {
    const light = document.documentElement.dataset.theme === 'light';
    const label = document.createElement('span');
    label.textContent = light ? 'Modo escuro' : 'Modo claro';
    themeButton.replaceChildren(TestaizeIcons.create(light ? 'moon' : 'sun'), label);
    themeButton.setAttribute('aria-label', light ? 'Ativar modo escuro' : 'Ativar modo claro');
  }
  if (themeButton) {
    updateThemeButton();
    themeButton.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('executor-theme', next); } catch (_) {}
      updateThemeButton();
    });
  }
  const accentPicker = document.getElementById('accent-picker');
  if (accentPicker) {
    const trigger = document.getElementById('accent-trigger');
    const options = document.getElementById('accent-options');
    const names = { neutro: 'Azul', roxo: 'Roxo', verde: 'Verde', vermelho: 'Vermelho', amarelo: 'Amarelo' };
    function updateAccent() {
      const selected = names[document.documentElement.dataset.accent] ? document.documentElement.dataset.accent : 'neutro';
      trigger.setAttribute('aria-label', `Escolher cor do aplicativo. Atual: ${names[selected]}`);
      accentPicker.querySelectorAll('[data-accent-choice]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.accentChoice === selected));
      });
    }
    function closeAccent() { options.hidden = true; trigger.setAttribute('aria-expanded', 'false'); }
    updateAccent();
    trigger.addEventListener('click', () => {
      options.hidden = !options.hidden;
      trigger.setAttribute('aria-expanded', String(!options.hidden));
    });
    accentPicker.querySelectorAll('[data-accent-choice]').forEach(button => button.addEventListener('click', () => {
      document.documentElement.dataset.accent = button.dataset.accentChoice;
      try { localStorage.setItem('testaize-accent', button.dataset.accentChoice); } catch (_) {}
      updateAccent();
      closeAccent();
      trigger.focus();
    }));
    document.addEventListener('click', event => { if (!accentPicker.contains(event.target)) closeAccent(); });
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || options.hidden) return;
      event.preventDefault();
      closeAccent();
      trigger.focus();
    });
  }
  const fileInput = document.getElementById('arquivo');
  if (fileInput) {
    const drop = document.querySelector('.dropzone');
    const name = document.querySelector('[data-file-name]');
    fileInput.addEventListener('change', () => { name.textContent = fileInput.files[0]?.name || 'Nenhum arquivo selecionado'; });
    ['dragenter', 'dragover'].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.add('dragging'); }));
    ['dragleave', 'drop'].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.remove('dragging'); }));
    drop.addEventListener('drop', event => {
      if (event.dataTransfer.files.length) { fileInput.files = event.dataTransfer.files; name.textContent = fileInput.files[0].name; }
    });
  }
  document.querySelectorAll('.flash').forEach(item => setTimeout(() => item.remove(), 9000));

  const folderCardModal = document.getElementById('folder-card-modal');
  if (folderCardModal) {
    const form = document.getElementById('folder-card-form');
    const urlInput = document.getElementById('folder-card-url');
    const error = document.getElementById('folder-card-error');
    const removeButton = document.getElementById('folder-card-remove');
    const saveButton = document.getElementById('folder-card-save');
    const closeButtons = [...folderCardModal.querySelectorAll('[data-folder-card-close]')];
    let selectedRow = null;
    let returnFocus = null;
    let busy = false;

    const cardUrlIsValid = value => {
      if (!value || value !== value.trim() || [...value].some(character => /\s/u.test(character) || character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) return false;
      try {
        const parsed = new URL(value);
        return ['http:', 'https:'].includes(parsed.protocol) && Boolean(parsed.hostname);
      } catch (_) { return false; }
    };
    const closeFolderCard = () => { if (!busy && folderCardModal.open) folderCardModal.close(); };
    const setFolderCardBusy = value => {
      busy = value;
      saveButton.disabled = value;
      removeButton.disabled = value;
      closeButtons.forEach(button => { button.disabled = value; });
    };
    const cardIcon = provider => provider === 'Jira' ? 'J' : provider === 'ClickUp' ? 'C' : '↗';
    function renderFolderCard(row, card) {
      const cell = row.querySelector('.folder-card-cell');
      cell.replaceChildren();
      if (card) {
        const link = document.createElement('a');
        link.className = 'folder-card-link';
        link.href = card.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.title = card.url;
        link.setAttribute('aria-label', `Abrir ${card.label} no ${card.provider} em nova aba`);
        const icon = document.createElement('span');
        icon.className = 'folder-card-provider';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = cardIcon(card.provider);
        const copy = document.createElement('span');
        const provider = document.createElement('small');
        provider.textContent = card.provider;
        const label = document.createElement('strong');
        label.textContent = `${card.label} ↗`;
        copy.append(provider, label);
        link.append(icon, copy);
        const edit = document.createElement('button');
        edit.className = 'folder-card-edit';
        edit.type = 'button';
        edit.dataset.folderCardEdit = '';
        edit.title = 'Editar vínculo';
        edit.setAttribute('aria-label', `Editar vínculo da pasta ${row.dataset.folderName}`);
        edit.append(TestaizeIcons.create('edit'));
        cell.append(link, edit);
      } else {
        const add = document.createElement('button');
        add.className = 'folder-card-add';
        add.type = 'button';
        add.dataset.folderCardEdit = '';
        const icon = document.createElement('span');
        icon.setAttribute('aria-hidden', 'true');
        icon.append(TestaizeIcons.create('plus'));
        add.append(icon, ' Vincular card');
        cell.append(add);
      }
    }
    function openFolderCard(trigger) {
      selectedRow = trigger.closest('[data-folder-card-row]');
      returnFocus = trigger;
      const existingUrl = selectedRow.dataset.cardUrl;
      document.getElementById('folder-card-folder').textContent = selectedRow.dataset.folderName;
      document.getElementById('folder-card-path').textContent = selectedRow.dataset.folderPath;
      document.getElementById('folder-card-modal-title').textContent = existingUrl ? 'Editar card vinculado' : 'Vincular card à pasta';
      urlInput.value = existingUrl;
      urlInput.removeAttribute('aria-invalid');
      error.textContent = '';
      removeButton.hidden = !existingUrl;
      folderCardModal.showModal();
      urlInput.focus();
    }
    document.addEventListener('click', event => {
      const trigger = event.target.closest('[data-folder-card-edit]');
      if (trigger) openFolderCard(trigger);
    });
    closeButtons.forEach(button => button.addEventListener('click', closeFolderCard));
    urlInput.addEventListener('input', () => { urlInput.removeAttribute('aria-invalid'); error.textContent = ''; });
    folderCardModal.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    folderCardModal.addEventListener('click', event => {
      if (event.target !== folderCardModal) return;
      const bounds = folderCardModal.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeFolderCard();
    });
    folderCardModal.addEventListener('close', () => { selectedRow = null; returnFocus?.focus(); returnFocus = null; });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy) return;
      const value = urlInput.value;
      if (!cardUrlIsValid(value)) {
        error.textContent = 'Informe um link completo iniciado por http:// ou https://.';
        urlInput.setAttribute('aria-invalid', 'true');
        urlInput.focus();
        return;
      }
      setFolderCardBusy(true);
      error.textContent = '';
      try {
        const response = await fetch(folderCardModal.dataset.endpoint, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify({folder_path: selectedRow.dataset.folderPath, card_url: value})});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Não foi possível salvar o vínculo.');
        selectedRow.dataset.cardUrl = result.card.url;
        selectedRow.dataset.cardProvider = result.card.provider;
        selectedRow.dataset.cardLabel = result.card.label;
        renderFolderCard(selectedRow, result.card);
        returnFocus = selectedRow.querySelector('[data-folder-card-edit]');
        folderCardModal.close();
      } catch (failure) {
        error.textContent = failure.message;
        urlInput.setAttribute('aria-invalid', 'true');
      } finally { setFolderCardBusy(false); }
    });
    removeButton.addEventListener('click', async () => {
      if (busy) return;
      setFolderCardBusy(true);
      error.textContent = '';
      try {
        const response = await fetch(folderCardModal.dataset.endpoint, {method: 'DELETE', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify({folder_path: selectedRow.dataset.folderPath})});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Não foi possível remover o vínculo.');
        selectedRow.dataset.cardUrl = '';
        selectedRow.dataset.cardProvider = '';
        selectedRow.dataset.cardLabel = '';
        renderFolderCard(selectedRow, null);
        returnFocus = selectedRow.querySelector('[data-folder-card-edit]');
        folderCardModal.close();
      } catch (failure) { error.textContent = failure.message; }
      finally { setFolderCardBusy(false); }
    });
  }

  const deleteModal = document.getElementById('delete-session-modal');
  if (deleteModal) {
    const form = document.getElementById('delete-session-form');
    const confirm = document.getElementById('confirm-session-delete');
    const updateDeleteChoice = () => {
      const permanent = form.querySelector('input[name="action"]:checked')?.value === 'delete';
      confirm.textContent = permanent ? 'Excluir sessão e arquivos' : 'Mover para Excluídas';
      confirm.classList.toggle('button-danger', permanent);
      confirm.classList.toggle('button-primary', !permanent);
    };
    document.querySelectorAll('[data-delete-session]').forEach(button => button.addEventListener('click', () => {
      form.action = button.dataset.deleteUrl;
      document.getElementById('delete-session-name').textContent = button.dataset.sessionName;
      form.querySelector('input[name="action"][value="move"]').checked = true;
      updateDeleteChoice();
      deleteModal.showModal();
    }));
    form.querySelectorAll('input[name="action"]').forEach(input => input.addEventListener('change', updateDeleteChoice));
    ['cancel-session-delete', 'cancel-session-delete-top'].forEach(id =>
      document.getElementById(id).addEventListener('click', () => deleteModal.close()));
    deleteModal.addEventListener('click', event => { if (event.target === deleteModal) deleteModal.close(); });
  }

  const player = document.querySelector('[data-player]');
  if (!player) return;
  const writable = player.dataset.writable === 'true';
  const views = [...document.querySelectorAll('[data-case-view]')];
  const caseButtons = [...document.querySelectorAll('[data-case-button]')];
  const cards = [...document.querySelectorAll('.step-card')];
  const saveState = document.getElementById('save-state');
  let selectedIndex = 0;
  const timers = new Map();
  const inFlight = new Map();
  const versions = new Map();
  const caseTimers = new Map();
  const caseInFlight = new Map();
  const caseVersions = new Map();
  const pendingUploads = new Set();
  const folderGroups = [...document.querySelectorAll('[data-folder-group]')];
  const search = document.getElementById('case-search');
  const viewIndexById = new Map(views.map((view, index) => [view.dataset.caseView, index]));
  const folderChoices = folderGroups.map(group => ({ name: group.dataset.folderGroup, label: group.dataset.folderLabel }));
  const cyclePicker = document.querySelector('[data-cycle-picker]');
  const cycleTrigger = document.getElementById('cycle-trigger');
  const cyclePopover = document.getElementById('cycle-popover');
  const cycleChecks = [...document.querySelectorAll('.cycle-check')];
  const cycleAll = document.getElementById('cycle-all');
  const labels = { nao_executado: 'Não executado', em_andamento: 'Em andamento', aprovado: 'Aprovado', reprovado: 'Reprovado', bloqueado: 'Bloqueado' };
  const caseViewChangeHandlers = new Set();
  function caseViewChanged() { caseViewChangeHandlers.forEach(handler => handler()); }

  function setSaveState(message, error = false) {
    saveState.textContent = message;
    saveState.classList.toggle('error', error);
    const pipDocument = window.documentPictureInPicture?.window?.document;
    const miniState = document.getElementById('mini-player-sync-state') || pipDocument?.getElementById('mini-player-sync-state');
    if (miniState) {
      miniState.lastChild.textContent = ` ${message}`;
      miniState.classList.toggle('error', error);
    }
  }
  function showCase(index) {
    if (index < 0 || index >= views.length) return;
    selectedIndex = index;
    views.forEach((view, i) => view.classList.toggle('is-hidden', i !== index));
    caseButtons.forEach(button => button.classList.toggle('active', button.dataset.caseButton === views[index].dataset.caseView));
    document.getElementById('breadcrumb-case').textContent = `Caso ${String(views[index].dataset.caseIndex).padStart(2, '0')}`;
    const visible = caseButtons.filter(button => !button.classList.contains('is-hidden')).map(button => viewIndexById.get(button.dataset.caseButton));
    const position = visible.indexOf(index);
    views[index].querySelector('[data-prev-case]').disabled = position <= 0;
    views[index].querySelector('[data-next-case]').disabled = position < 0 || position === visible.length - 1;
    const url = new URL(location.href);
    url.hash = `caso-${views[index].dataset.caseView}`;
    history.replaceState(null, '', url);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    caseViewChanged();
  }
  caseButtons.forEach(button => button.addEventListener('click', () => showCase(viewIndexById.get(button.dataset.caseButton))));
  function moveCase(direction) {
    const visible = caseButtons.filter(button => !button.classList.contains('is-hidden')).map(button => viewIndexById.get(button.dataset.caseButton));
    const next = visible[visible.indexOf(selectedIndex) + direction];
    if (next !== undefined) showCase(next);
  }
  document.querySelectorAll('[data-prev-case]').forEach(button => button.addEventListener('click', () => moveCase(-1)));
  document.querySelectorAll('[data-next-case]').forEach(button => button.addEventListener('click', () => moveCase(1)));
  function updateScopedSummary() {
    const visible = caseButtons.filter(button => !button.classList.contains('is-hidden'));
    const counts = { nao_executado: 0, em_andamento: 0, aprovado: 0, reprovado: 0, bloqueado: 0 };
    visible.forEach(button => { counts[button.dataset.status]++; });
    Object.entries(counts).forEach(([key, value]) => {
      const target = document.querySelector(`[data-count="${key}"]`);
      if (target) target.textContent = value;
    });
    const done = counts.aprovado + counts.reprovado + counts.bloqueado;
    const percent = visible.length ? Math.round(done / visible.length * 100) : 0;
    document.getElementById('progress-count').textContent = done;
    document.getElementById('progress-total').textContent = `de ${visible.length} casos com resultado`;
    for (const [status, count] of Object.entries(counts)) {
      const segment = document.querySelector(`[data-progress-status="${status}"]`);
      segment.style.width = `${visible.length ? count / visible.length * 100 : 0}%`;
      segment.title = `${labels[status]}: ${count}/${visible.length} (${visible.length ? Math.round(count / visible.length * 100) : 0}%)`;
    }
    document.getElementById('progress-percent').textContent = `${percent}%`;
    const chosen = cycleChecks.filter(check => check.checked);
    document.getElementById('summary-scope').textContent = chosen.length === cycleChecks.length ? 'Todas as pastas' : chosen.length === 1 ? chosen[0].dataset.label : `${chosen.length} ciclos selecionados`;
  }
  function filterCases(updateUrl = false) {
    const selectedFolders = new Set(cycleChecks.filter(check => check.checked).map(check => check.value));
    const all = selectedFolders.size === folderChoices.length;
    const caseTerm = search.value.trim().toLocaleLowerCase('pt-BR');
    caseButtons.forEach(button => {
      const folderMatch = all || selectedFolders.has(button.dataset.folder);
      button.classList.toggle('is-hidden', !folderMatch || (Boolean(caseTerm) && !button.dataset.search.includes(caseTerm)));
    });
    folderGroups.forEach(group => group.classList.toggle('is-hidden', !caseButtons.some(button => button.dataset.folder === group.dataset.folderGroup && !button.classList.contains('is-hidden'))));
    const visible = caseButtons.filter(button => !button.classList.contains('is-hidden'));
    document.getElementById('case-filter-empty').classList.toggle('is-hidden', visible.length > 0);
    if (!visible.length) views.forEach(view => view.classList.add('is-hidden'));
    if (visible.length && !visible.some(button => button.dataset.caseButton === views[selectedIndex].dataset.caseView)) showCase(viewIndexById.get(visible[0].dataset.caseButton));
    else if (visible.length && views[selectedIndex].classList.contains('is-hidden')) showCase(selectedIndex);
    if (updateUrl) {
      const url = new URL(location.href);
      url.searchParams.delete('pasta');
      if (!all) cycleChecks.filter(check => check.checked).forEach(check => url.searchParams.append('pasta', check.value));
      history.replaceState(null, '', url);
    }
    updateScopedSummary();
    caseViewChanged();
  }
  function updateCyclePicker() {
    const chosen = cycleChecks.filter(check => check.checked);
    cycleAll.checked = chosen.length === cycleChecks.length;
    cycleAll.indeterminate = chosen.length > 0 && chosen.length < cycleChecks.length;
    cycleTrigger.querySelector('span').textContent = chosen.length === cycleChecks.length ? 'Todas as pastas' : chosen.length === 1 ? chosen[0].dataset.label : chosen.length ? `${chosen.length} ciclos selecionados` : 'Nenhum ciclo selecionado';
    document.getElementById('cycle-count').textContent = `${chosen.length} de ${cycleChecks.length} selecionados`;
    filterCases(true);
  }
  cycleTrigger.addEventListener('click', () => {
    cyclePopover.hidden = !cyclePopover.hidden;
    cycleTrigger.setAttribute('aria-expanded', String(!cyclePopover.hidden));
    if (!cyclePopover.hidden) document.getElementById('cycle-search').focus();
  });
  cycleChecks.forEach(check => check.addEventListener('change', updateCyclePicker));
  cycleAll.addEventListener('change', () => { cycleChecks.forEach(check => { check.checked = cycleAll.checked; }); updateCyclePicker(); });
  document.getElementById('cycle-search').addEventListener('input', event => {
    const term = event.target.value.trim().toLocaleLowerCase('pt-BR');
    document.querySelectorAll('[data-cycle-option]').forEach(option => option.classList.toggle('is-hidden', Boolean(term) && !option.dataset.search.includes(term)));
  });
  document.getElementById('cycle-done').addEventListener('click', () => { cyclePopover.hidden = true; cycleTrigger.setAttribute('aria-expanded', 'false'); cycleTrigger.focus(); });
  document.addEventListener('click', event => { if (!cyclePicker.contains(event.target)) { cyclePopover.hidden = true; cycleTrigger.setAttribute('aria-expanded', 'false'); } });
  cyclePicker.addEventListener('keydown', event => { if (event.key === 'Escape') { cyclePopover.hidden = true; cycleTrigger.setAttribute('aria-expanded', 'false'); cycleTrigger.focus(); } });
  search?.addEventListener('input', () => filterCases());
  filterCases();
  updateCyclePicker();
  const initialHash = location.hash.match(/^#caso-(\d+)$/);
  if (initialHash) {
    const found = views.findIndex(view => view.dataset.caseView === initialHash[1]);
    if (found >= 0 && !caseButtons.find(button => button.dataset.caseButton === initialHash[1])?.classList.contains('is-hidden')) showCase(found);
  }
  if (!initialHash && caseButtons.some(button => !button.classList.contains('is-hidden'))) showCase(viewIndexById.get(caseButtons.find(button => !button.classList.contains('is-hidden')).dataset.caseButton));

  function setSidebar(side, collapsed) {
    player.dataset[side === 'left' ? 'leftCollapsed' : 'rightCollapsed'] = String(collapsed);
    const toggle = document.getElementById(`toggle-${side}`);
    toggle.setAttribute('aria-expanded', String(!collapsed));
    toggle.setAttribute('aria-label', `${collapsed ? 'Abrir' : 'Recolher'} ${side === 'left' ? 'lista de casos' : 'resumo'}`);
    try { localStorage.setItem(`executor-${side}-collapsed`, String(collapsed)); } catch (_) {}
  }
  for (const side of ['left', 'right']) {
    let collapsed = false;
    try { collapsed = localStorage.getItem(`executor-${side}-collapsed`) === 'true'; } catch (_) {}
    setSidebar(side, collapsed);
    document.getElementById(`toggle-${side}`).addEventListener('click', () => setSidebar(side, player.dataset[side === 'left' ? 'leftCollapsed' : 'rightCollapsed'] !== 'true'));
    let storedWidth = null;
    try { storedWidth = Number(localStorage.getItem(`executor-${side}-width`)); } catch (_) {}
    if (storedWidth && Number.isFinite(storedWidth)) player.style.setProperty(`--${side}-width`, `${Math.max(220, Math.min(side === 'left' ? 500 : 440, storedWidth))}px`);
  }
  if (window.innerWidth <= 850) { setSidebar('left', true); setSidebar('right', true); }
  document.querySelectorAll('[data-resize]').forEach(handle => {
    const side = handle.dataset.resize;
    const maximum = side === 'left' ? 500 : 440;
    function applyWidth(value) {
      const width = Math.max(220, Math.min(maximum, value, window.innerWidth - 350));
      player.style.setProperty(`--${side}-width`, `${width}px`);
      try { localStorage.setItem(`executor-${side}-width`, String(width)); } catch (_) {}
    }
    handle.addEventListener('pointerdown', event => {
      if (window.innerWidth < 900) return;
      handle.setPointerCapture(event.pointerId);
      const startX = event.clientX;
      const initial = (side === 'left' ? player.querySelector('.case-sidebar') : player.querySelector('.execution-sidebar')).getBoundingClientRect().width;
      function move(pointer) { applyWidth(initial + (pointer.clientX - startX) * (side === 'left' ? 1 : -1)); }
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', () => handle.removeEventListener('pointermove', move), { once: true });
      handle.addEventListener('pointercancel', () => handle.removeEventListener('pointermove', move), { once: true });
    });
    handle.addEventListener('keydown', event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const current = (side === 'left' ? player.querySelector('.case-sidebar') : player.querySelector('.execution-sidebar')).getBoundingClientRect().width;
      applyWidth(current + (event.key === 'ArrowRight' ? 20 : -20) * (side === 'left' ? 1 : -1));
    });
  });

  function aggregate(statuses) {
    if (statuses.every(s => s === 'nao_executado')) return 'nao_executado';
    if (statuses.includes('reprovado')) return 'reprovado';
    if (statuses.includes('bloqueado')) return 'bloqueado';
    if (statuses.every(s => s === 'aprovado')) return 'aprovado';
    return 'em_andamento';
  }
  function updateSummary() {
    views.forEach(view => {
      const caseId = view.dataset.caseView;
      const status = view.dataset.manualStatus || aggregate([...view.querySelectorAll('.step-card')].map(card => card.dataset.status));
      const tag = document.querySelector(`[data-case-status="${caseId}"]`);
      tag.textContent = labels[status];
      tag.className = `status-tag status-${status}`;
      const navTag = document.querySelector(`[data-case-tag="${caseId}"]`);
      navTag.textContent = labels[status];
      navTag.className = `status-tag case-nav-tag status-${status}`;
      const reportTag = document.querySelector(`[data-report-case-tag="${caseId}"]`);
      if (reportTag) { reportTag.textContent = labels[status]; reportTag.className = `status-tag status-${status}`; }
      caseButtons.find(button => button.dataset.caseButton === caseId).dataset.status = status;
      const failureActions = view.querySelector('[data-failure-actions]');
      if (failureActions) failureActions.classList.toggle('is-hidden', !(status === 'reprovado' && [...view.querySelectorAll('.step-card')].some(card => card.dataset.status === 'reprovado')));
    });
    updateScopedSummary();
  }
  cards.forEach(card => {
    card.dataset.status = card.querySelector('.step-status-buttons .selected')?.dataset.value || 'nao_executado';
  });
  views.forEach(view => { view.dataset.manualStatus = view.querySelector('.case-status-buttons .selected')?.dataset.value || ''; });
  updateSummary();

  const miniPlayer = document.getElementById('mini-player');
  const miniPlayerHome = document.getElementById('mini-player-home');
  const miniPlayerOpen = document.getElementById('mini-player-open');
  const miniPlayerFeedback = document.getElementById('mini-player-feedback');
  const activeMiniSteps = new Map(views.map(view => [view.dataset.caseView, view.querySelector('.step-card')]));
  let pipWindow = null;
  let focusMainAfterMiniClose = false;

  function activeMiniStep() {
    const view = views[selectedIndex];
    return activeMiniSteps.get(view?.dataset.caseView) || view?.querySelector('.step-card') || null;
  }
  function setActiveMiniStep(card, revealMain = false) {
    if (!card) return;
    activeMiniSteps.set(card.dataset.caseId, card);
    renderMiniPlayer();
    if (revealMain) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  function miniElement(tag, className, text = '') {
    const node = miniPlayer.ownerDocument.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
  }
  function setMiniPlayerFeedback(message, error = false) {
    miniPlayerFeedback.textContent = message;
    miniPlayerFeedback.classList.toggle('error', error);
  }
  function observedTextBlocks(editor) {
    const blocks = [];
    function collect(node) {
      if (node.nodeType === Node.TEXT_NODE) { blocks.push(node); return; }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.matches('.rich-image')) return;
      if (node.matches('p,div') && !node.querySelector('.rich-image')) { blocks.push(node); return; }
      node.childNodes.forEach(collect);
    }
    editor.childNodes.forEach(collect);
    return blocks;
  }
  function syncObservedText(editor, value) {
    const lines = value.replace(/\r/g, '').split('\n');
    const paragraphs = observedTextBlocks(editor);
    lines.forEach((line, index) => {
      if (!paragraphs[index]) {
        const paragraph = makeParagraph();
        editor.append(paragraph);
        paragraphs.push(paragraph);
      }
      paragraphs[index].textContent = line;
    });
    paragraphs.slice(lines.length).forEach(paragraph => paragraph.remove());
    updateSyncActions();
    queueEditor(editor);
  }
  function syncMiniObservedText(editor) {
    const card = editor.closest('.step-card');
    if (card !== activeMiniStep()) return;
    const input = miniPlayer.querySelector('.mini-player-step.active .mini-player-paste');
    if (input && !(input.ownerDocument.hasFocus() && input.ownerDocument.activeElement === input)) {
      input.value = plainText(serializeEditor(editor));
    }
  }
  function renderMiniPlayer() {
    const view = views[selectedIndex];
    if (!view || !miniPlayer) return;
    const focused = miniPlayer.ownerDocument.activeElement;
    const focusedStep = miniPlayer.contains(focused) ? focused.closest('.mini-player-step') : null;
    const focusTarget = focusedStep ? {
      stepId: focusedStep.dataset.stepId,
      control: focused.classList.contains('mini-player-status') ? 'status'
        : focused.classList.contains('mini-player-paste') ? 'paste' : 'summary',
      status: focused.dataset?.value || ''
    } : null;
    const stepCards = [...view.querySelectorAll('.step-card')];
    const active = activeMiniSteps.get(view.dataset.caseView) || stepCards[0];
    if (active) activeMiniSteps.set(view.dataset.caseView, active);
    const activeIndex = Math.max(0, stepCards.indexOf(active));
    miniPlayer.querySelector('#mini-player-case-label').textContent = view.querySelector('.case-kicker')?.textContent.trim() || '';
    miniPlayer.querySelector('#mini-player-case-title').textContent = view.querySelector('.case-heading h2')?.textContent.trim() || '';
    miniPlayer.querySelector('#mini-player-position').textContent = String(activeIndex + 1);
    miniPlayer.querySelector('#mini-player-total').textContent = String(stepCards.length);
    miniPlayer.querySelector('#mini-player-case-status').textContent = view.querySelector('[data-case-status]')?.textContent.trim() || '';
    const approved = stepCards.filter(card => card.dataset.status === 'aprovado').length;
    miniPlayer.querySelector('#mini-player-progress-bar').style.width = `${stepCards.length ? approved / stepCards.length * 100 : 0}%`;

    const list = miniPlayer.querySelector('#mini-player-steps');
    list.replaceChildren();
    stepCards.forEach((card, index) => {
      const item = miniElement('section', `mini-player-step${card === active ? ' active' : ''}`);
      item.dataset.stepId = card.dataset.stepId;
      item.dataset.status = card.dataset.status;
      const summary = miniElement('button', 'mini-player-step-summary');
      summary.type = 'button';
      summary.setAttribute('aria-expanded', String(card === active));
      const number = miniElement('span', 'mini-player-step-number', String(index + 1).padStart(2, '0'));
      const title = miniElement('span', 'mini-player-step-title', card.querySelector('.step-action h4')?.textContent.trim() || 'Passo sem descrição');
      const state = miniElement('span', 'mini-player-step-state');
      state.append(TestaizeIcons.status(card.dataset.status));
      state.setAttribute('aria-label', labels[card.dataset.status] || 'Não executado');
      summary.append(number, title, state);
      summary.addEventListener('click', () => setActiveMiniStep(card, true));
      item.append(summary);

      if (card === active) {
        const body = miniElement('div', 'mini-player-step-body');
        const statusLabel = miniElement('span', 'mini-player-field-label', 'Status do passo');
        const statusGroup = miniElement('div', 'mini-player-statuses');
        statusGroup.setAttribute('role', 'group');
        statusGroup.setAttribute('aria-label', `Status do passo ${index + 1}`);
        card.querySelectorAll('.step-status-buttons .status-icon-button').forEach(mainButton => {
          const button = miniElement('button', `mini-player-status status-choice-${mainButton.dataset.value}${mainButton.classList.contains('selected') ? ' selected' : ''}`);
          button.type = 'button';
          button.dataset.value = mainButton.dataset.value;
          button.dataset.tooltip = mainButton.getAttribute('aria-label');
          button.title = mainButton.getAttribute('aria-label');
          button.setAttribute('aria-label', mainButton.getAttribute('aria-label'));
          button.setAttribute('aria-pressed', String(mainButton.classList.contains('selected')));
          button.disabled = !writable;
          button.append(TestaizeIcons.status(mainButton.dataset.value));
          button.addEventListener('click', () => {
            mainButton?.click();
            queueMicrotask(renderMiniPlayer);
          });
          statusGroup.append(button);
        });

        const area = card.querySelector('.observed-area');
        const editor = area.querySelector('[data-rich-editor]');
        const observed = miniElement('div', 'mini-player-observed');
        const observedHead = miniElement('div', 'mini-player-observed-head');
        const paste = miniElement('textarea', 'mini-player-paste');
        paste.rows = 2;
        paste.disabled = !writable;
        paste.value = plainText(serializeEditor(editor));
        paste.placeholder = 'Descreva o resultado observado ou cole uma captura com Ctrl+V';
        paste.setAttribute('aria-label', 'Resultado observado');
        const images = [...area.querySelectorAll('.rich-image img')];
        const pasteHeading = miniElement('strong', 'mini-player-paste-title', 'Resultado observado');
        const pasteHint = miniElement('span', 'mini-player-paste-hint', writable ? 'Digite uma observação ou cole uma captura com Ctrl+V' : 'Sessão somente leitura');
        observedHead.append(pasteHeading, pasteHint);
        observed.append(observedHead, paste);
        if (images.length) {
          const evidence = miniElement('div', 'mini-player-evidence');
          images.forEach(source => {
            const image = miniPlayer.ownerDocument.createElement('img');
            image.src = source.src;
            image.alt = source.alt || 'Evidência do passo';
            evidence.append(image);
          });
          observed.append(evidence);
        }
        paste.addEventListener('input', () => {
          syncObservedText(editor, paste.value);
          setMiniPlayerFeedback('');
        });
        paste.addEventListener('paste', async event => {
          if (!writable) { setMiniPlayerFeedback('Esta execução está somente para leitura.', true); return; }
          const item = [...(event.clipboardData?.items || [])].find(entry => entry.type.startsWith('image/'));
          const file = item?.getAsFile() || [...(event.clipboardData?.files || [])].find(entry => entry.type.startsWith('image/'));
          if (!file) return;
          event.preventDefault();
          setMiniPlayerFeedback('Enviando evidência…');
          try {
            const anchor = editor?.querySelector('.rich-paragraph:last-of-type');
            await uploadImage(area, file, anchor, anchor?.textContent.length ?? null);
            await persist(card);
            setMiniPlayerFeedback('Evidência salva e sincronizada.');
            renderMiniPlayer();
          } catch (error) { setMiniPlayerFeedback(error.message, true); }
        });
        body.append(statusLabel, statusGroup, observed);
        item.append(body);
      }
      list.append(item);
    });
    if (focusTarget) {
      const step = [...list.querySelectorAll('.mini-player-step')].find(item => item.dataset.stepId === focusTarget.stepId);
      const target = focusTarget.control === 'status'
        ? [...(step?.querySelectorAll('.mini-player-status') || [])].find(button => button.dataset.value === focusTarget.status)
        : step?.querySelector(focusTarget.control === 'paste' ? '.mini-player-paste' : '.mini-player-step-summary');
      target?.focus();
    }
    const visible = caseButtons.filter(button => !button.classList.contains('is-hidden')).map(button => viewIndexById.get(button.dataset.caseButton));
    const position = visible.indexOf(selectedIndex);
    miniPlayer.querySelector('#mini-player-prev').disabled = position <= 0;
    miniPlayer.querySelector('#mini-player-next').disabled = position < 0 || position === visible.length - 1;
  }
  function syncMiniPlayerTheme() {
    if (!pipWindow) return;
    pipWindow.document.documentElement.dataset.theme = document.documentElement.dataset.theme;
    pipWindow.document.documentElement.dataset.accent = document.documentElement.dataset.accent;
  }
  function focusMainPlayer() {
    const target = activeMiniStep()?.querySelector('.step-status-buttons button, [data-rich-editor]');
    target?.focus();
    activeMiniStep()?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  function returnMiniPlayer() {
    pipWindow = null;
    miniPlayerHome.append(miniPlayer);
    miniPlayer.hidden = true;
    if (focusMainAfterMiniClose) focusMainPlayer();
    else miniPlayerOpen.focus();
    focusMainAfterMiniClose = false;
  }
  function showMiniPlayerFallback(message) {
    miniPlayerHome.append(miniPlayer);
    miniPlayer.dataset.surface = 'fallback';
    miniPlayer.querySelector('#mini-player-surface').textContent = message;
    miniPlayer.hidden = false;
    miniPlayer.querySelector('#mini-player-close').focus();
  }
  async function openMiniPlayer() {
    renderMiniPlayer();
    setMiniPlayerFeedback('');
    if (pipWindow && !pipWindow.closed) { pipWindow.focus(); return; }
    if ('documentPictureInPicture' in window) {
      try {
        pipWindow = await window.documentPictureInPicture.requestWindow({ width: 430, height: 720 });
        pipWindow.document.documentElement.lang = 'pt-BR';
        pipWindow.document.title = 'TestAíZé - Mini Player';
        document.querySelectorAll('link[rel="stylesheet"]').forEach(stylesheet => {
          const link = pipWindow.document.createElement('link');
          link.rel = 'stylesheet';
          link.href = stylesheet.href;
          pipWindow.document.head.append(link);
        });
        pipWindow.document.body.className = 'mini-player-window';
        miniPlayer.dataset.surface = 'pip';
        miniPlayer.querySelector('#mini-player-surface').textContent = 'Janela sempre visível sobre outros aplicativos.';
        miniPlayer.hidden = false;
        pipWindow.document.body.append(miniPlayer);
        syncMiniPlayerTheme();
        pipWindow.focus();
        miniPlayer.querySelector('#mini-player-close').focus();
        pipWindow.addEventListener('pagehide', returnMiniPlayer, { once: true });
        pipWindow.document.addEventListener('keydown', event => { if (event.key === 'Escape') pipWindow?.close(); });
        return;
      } catch (_) {
        pipWindow = null;
        showMiniPlayerFallback('O navegador não liberou a janela externa. Este painel flutua somente dentro do TestAíZé.');
        return;
      }
    }
    showMiniPlayerFallback('Picture-in-Picture não está disponível. Este painel flutua somente dentro do TestAíZé.');
  }
  function closeMiniPlayer(restoreMain = false) {
    focusMainAfterMiniClose = restoreMain;
    if (pipWindow && !pipWindow.closed) { pipWindow.close(); return; }
    miniPlayer.hidden = true;
    if (restoreMain) focusMainPlayer(); else miniPlayerOpen.focus();
    focusMainAfterMiniClose = false;
  }
  cards.forEach(card => {
    card.addEventListener('focusin', () => setActiveMiniStep(card));
    card.addEventListener('pointerdown', () => setActiveMiniStep(card));
    card.querySelectorAll('.step-status-buttons .status-icon-button').forEach(button =>
      button.addEventListener('click', () => queueMicrotask(renderMiniPlayer)));
  });
  caseViewChangeHandlers.add(renderMiniPlayer);
  new MutationObserver(syncMiniPlayerTheme).observe(document.documentElement, {
    attributes: true, attributeFilter: ['data-theme', 'data-accent']
  });
  miniPlayerOpen.addEventListener('click', openMiniPlayer);
  document.getElementById('mini-player-close').addEventListener('click', () => closeMiniPlayer());
  document.getElementById('mini-player-restore').addEventListener('click', () => closeMiniPlayer(true));
  document.getElementById('mini-player-prev').addEventListener('click', () => moveCase(-1));
  document.getElementById('mini-player-next').addEventListener('click', () => moveCase(1));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !miniPlayer.hidden && !pipWindow) closeMiniPlayer();
  });
  renderMiniPlayer();

  const pdfModal = document.getElementById('pdf-modal');
  if (pdfModal) {
    const reportForm = document.getElementById('pdf-form');
    const caseChecks = [...pdfModal.querySelectorAll('.pdf-case-check')];
    const allCheck = document.getElementById('pdf-all');
    const submit = document.getElementById('submit-pdf');
    function updatePdfSelection() {
      const selected = caseChecks.filter(check => check.checked).length;
      document.getElementById('pdf-selected-count').textContent = `${selected} de ${caseChecks.length} selecionados`;
      submit.disabled = selected === 0;
      document.getElementById('pdf-selection-error').textContent = selected ? '' : 'Selecione ao menos um caso.';
      allCheck.checked = selected === caseChecks.length;
      allCheck.indeterminate = selected > 0 && selected < caseChecks.length;
      pdfModal.querySelectorAll('.pdf-folder').forEach(folder => {
        const checks = [...folder.querySelectorAll('.pdf-case-check')];
        const checked = checks.filter(check => check.checked).length;
        const control = folder.querySelector('.pdf-folder-check');
        control.checked = checked === checks.length;
        control.indeterminate = checked > 0 && checked < checks.length;
      });
    }
    function updateReportFormat() {
      const format = reportForm.querySelector('input[name="report_format"]:checked')?.value || 'pdf';
      reportForm.action = format === 'html' ? reportForm.dataset.htmlUrl : reportForm.dataset.pdfUrl;
      submit.textContent = `Gerar ${format.toUpperCase()}`;
    }
    reportForm.querySelectorAll('input[name="report_format"]').forEach(input => input.addEventListener('change', updateReportFormat));
    document.getElementById('open-report-modal').addEventListener('click', () => {
      updateReportFormat();
      updatePdfSelection();
      pdfModal.showModal();
    });
    ['close-pdf-modal', 'cancel-pdf-modal'].forEach(id => document.getElementById(id).addEventListener('click', () => pdfModal.close()));
    pdfModal.addEventListener('click', event => {
      if (event.target !== pdfModal) return;
      const bounds = pdfModal.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom) pdfModal.close();
    });
    allCheck.addEventListener('change', () => { caseChecks.forEach(check => { check.checked = allCheck.checked; }); updatePdfSelection(); });
    pdfModal.querySelectorAll('.pdf-folder-check').forEach(check => check.addEventListener('change', () => {
      check.closest('.pdf-folder').querySelectorAll('.pdf-case-check').forEach(item => { item.checked = check.checked; });
      updatePdfSelection();
    }));
    caseChecks.forEach(check => check.addEventListener('change', updatePdfSelection));
    document.getElementById('pdf-form').addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      if (!caseChecks.some(check => check.checked)) { event.preventDefault(); updatePdfSelection(); }
      else {
        const button = document.getElementById('submit-pdf');
        button.disabled = true;
        try {
          if (writable) {
            setSaveState('Concluindo salvamentos…');
            await flushPendingMedia();
            for (const check of caseChecks.filter(item => item.checked)) {
              const view = viewIndexById.has(check.value) ? views[viewIndexById.get(check.value)] : null;
              if (!view) throw new Error('Caso selecionado não encontrado. Recarregue a página.');
              for (const card of view.querySelectorAll('.step-card')) await persist(card);
              await persistCase(view);
            }
          }
          pdfModal.close();
          form.submit();
        } catch (error) { setSaveState(error.message, true); }
        finally { button.disabled = false; }
      }
    });
    updatePdfSelection();
  }
  if (!writable) return;

  const syncModal = document.getElementById('sync-modal');
  let syncSource = null;
  let syncBusy = false;
  function syncCardEligible(card) {
    return Boolean(card?.querySelector('.step-action h4')?.textContent.trim()
      && card.dataset.statusSaved === 'true'
      && card.querySelector('.observed-area .rich-image'));
  }
  function syncCardIsCurrent(card) {
    if (!card) return false;
    const view = card.closest('[data-case-view]');
    const button = caseButtons.find(item => item.dataset.caseButton === view?.dataset.caseView);
    return view === views[selectedIndex] && !view.classList.contains('is-hidden')
      && Boolean(button && !button.classList.contains('is-hidden'));
  }
  function updateSyncActions() {
    cards.forEach(card => {
      const action = card.querySelector('[data-step-sync]');
      if (!action) return;
      const eligible = syncCardEligible(card);
      action.disabled = !eligible || syncBusy;
      action.title = eligible ? 'Sincronizar evidência deste passo'
        : 'Salve uma descrição, uma evidência e o status deste passo';
    });
  }
  function clearSyncSource() {
    syncSource?.classList.remove('sync-source-selected');
    syncSource = null;
    updateSyncActions();
  }
  function revalidateSyncSource() {
    if (syncSource && !syncCardIsCurrent(syncSource)) clearSyncSource();
    else updateSyncActions();
  }
  function selectSyncSource(card) {
    if (!syncCardIsCurrent(card)) { clearSyncSource(); return; }
    cards.forEach(item => item.classList.toggle('sync-source-selected', item === card));
    syncSource = card;
    updateSyncActions();
  }
  cards.forEach(card => {
    card.addEventListener('focusin', () => selectSyncSource(card));
    card.addEventListener('pointerdown', () => selectSyncSource(card));
    card.querySelector('[data-step-sync]')?.addEventListener('click', () => openSyncModal(card));
  });
  caseViewChangeHandlers.add(revalidateSyncSource);
  window.addEventListener('hashchange', clearSyncSource);

  function syncTargetChecks() { return [...syncModal.querySelectorAll('.sync-target-check')]; }
  function updateSyncSelection() {
    const checks = syncTargetChecks();
    const selected = checks.filter(check => check.checked).length;
    document.getElementById('sync-selected-count').textContent = `${selected} de ${checks.length} destinos selecionados`;
    syncModal.querySelectorAll('.sync-case-group').forEach(group => {
      const children = [...group.querySelectorAll('.sync-target-check')];
      const control = group.querySelector('.sync-case-check');
      const count = children.filter(check => check.checked).length;
      control.checked = count === children.length;
      control.indeterminate = count > 0 && count < children.length;
    });
    document.getElementById('confirm-sync').disabled = syncBusy || selected === 0;
    if (selected) document.getElementById('sync-feedback').textContent = '';
  }
  function renderSyncPreview(preview) {
    const origin = preview.origin;
    document.getElementById('sync-source-label').textContent =
      `Origem: ${origin.case_name} · Passo ${String(origin.step_position).padStart(2, '0')} · “${origin.description}”`;
    document.getElementById('sync-evidence-summary').textContent =
      `${origin.evidence_count} ${origin.evidence_count === 1 ? 'imagem' : 'imagens'} · ${labels[origin.status]}`;
    const evidenceList = document.getElementById('sync-evidence-list');
    evidenceList.replaceChildren(...origin.evidence.map(item => {
      const row = document.createElement('li');
      row.textContent = `${item.original_name} · ${(item.size / 1024).toFixed(1)} KB`;
      return row;
    }));
    const targetList = document.getElementById('sync-target-list');
    targetList.replaceChildren();
    let lastFolder = null;
    const cases = new Map();
    preview.targets.forEach(target => {
      const folder = target.folder || 'Sem pasta';
      if (folder !== lastFolder) {
        const heading = document.createElement('h3');
        heading.className = 'sync-folder-heading';
        heading.textContent = folder;
        targetList.append(heading);
        lastFolder = folder;
      }
      let group = cases.get(target.case_id);
      if (!group) {
        group = document.createElement('section');
        group.className = 'sync-case-group';
        const heading = document.createElement('label');
        heading.className = 'sync-case-heading';
        const caseCheck = document.createElement('input');
        caseCheck.type = 'checkbox'; caseCheck.className = 'sync-case-check'; caseCheck.checked = true;
        const name = document.createElement('strong'); name.textContent = target.case_name;
        heading.append(caseCheck, name); group.append(heading); targetList.append(group);
        caseCheck.addEventListener('change', () => {
          group.querySelectorAll('.sync-target-check').forEach(check => { check.checked = caseCheck.checked; });
          updateSyncSelection();
        });
        cases.set(target.case_id, group);
      }
      const row = document.createElement('label');
      row.className = 'sync-target-row';
      const check = document.createElement('input');
      check.type = 'checkbox'; check.className = 'sync-target-check'; check.value = target.step_id; check.checked = true;
      const copy = document.createElement('span'); copy.className = 'sync-target-copy';
      const title = document.createElement('strong'); title.textContent = `Passo ${String(target.step_position).padStart(2, '0')} · ${target.description}`;
      const detail = document.createElement('small');
      detail.textContent = `${labels[target.status]} · ${target.has_evidence ? 'Já possui evidência' : 'Sem evidência'}`;
      copy.append(title, detail); row.append(check, copy); group.append(row);
      check.addEventListener('change', updateSyncSelection);
    });
    document.getElementById('sync-empty').hidden = preview.targets.length > 0;
    document.getElementById('sync-select-all').disabled = preview.targets.length === 0;
    document.getElementById('sync-clear-all').disabled = preview.targets.length === 0;
    document.getElementById('sync-feedback').textContent = '';
    updateSyncSelection();
  }
  async function openSyncModal(card) {
    if (syncBusy || !syncCardIsCurrent(card) || !syncCardEligible(card)) return;
    selectSyncSource(card);
    document.getElementById('sync-target-list').replaceChildren();
    document.getElementById('sync-evidence-list').replaceChildren();
    document.getElementById('sync-empty').hidden = true;
    document.getElementById('sync-replicate-status').checked = false;
    document.getElementById('sync-feedback').className = 'sync-feedback';
    document.getElementById('sync-feedback').textContent = 'Carregando passos equivalentes…';
    document.getElementById('confirm-sync').disabled = true;
    syncModal.showModal();
    try {
      await flushView(card.closest('.case-view'));
      const response = await fetch(card.dataset.syncUrl);
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Não foi possível preparar a sincronização.');
      renderSyncPreview(result);
    } catch (error) {
      document.getElementById('sync-feedback').classList.add('error');
      document.getElementById('sync-feedback').textContent = error.message;
      setSaveState(error.message, true);
    }
  }
  function closeSyncModal() { if (!syncBusy) syncModal.close(); }
  ['close-sync-modal', 'cancel-sync-modal'].forEach(id => document.getElementById(id).addEventListener('click', closeSyncModal));
  syncModal.addEventListener('cancel', event => { if (syncBusy) event.preventDefault(); });
  syncModal.addEventListener('click', event => {
    if (event.target !== syncModal || syncBusy) return;
    const bounds = syncModal.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right
        || event.clientY < bounds.top || event.clientY > bounds.bottom) syncModal.close();
  });
  document.getElementById('sync-select-all').addEventListener('click', () => {
    syncTargetChecks().forEach(check => { check.checked = true; }); updateSyncSelection();
  });
  document.getElementById('sync-clear-all').addEventListener('click', () => {
    syncTargetChecks().forEach(check => { check.checked = false; }); updateSyncSelection();
  });
  document.getElementById('confirm-sync').addEventListener('click', async () => {
    if (syncBusy || !syncCardIsCurrent(syncSource) || !syncCardEligible(syncSource)) {
      revalidateSyncSource();
      return;
    }
    const selected = syncTargetChecks().filter(check => check.checked).map(check => Number(check.value));
    if (!selected.length) { updateSyncSelection(); return; }
    syncBusy = true;
    updateSyncActions();
    const confirm = document.getElementById('confirm-sync');
    const cancel = document.getElementById('cancel-sync-modal');
    confirm.disabled = true; cancel.disabled = true; confirm.textContent = 'Sincronizando…';
    document.getElementById('sync-feedback').textContent = 'Copiando evidências…';
    try {
      const response = await fetch(syncSource.dataset.syncUrl, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ target_step_ids: selected,
                               replicate_status: document.getElementById('sync-replicate-status').checked })
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Não foi possível sincronizar as evidências.');
      document.getElementById('sync-feedback').textContent =
        `Evidência sincronizada em ${result.synced} ${result.synced === 1 ? 'passo' : 'passos'}. Os destinos são independentes.`;
      document.getElementById('sync-feedback').className = 'sync-feedback success';
      confirm.textContent = 'Sincronizado';
      setSaveState('Evidência sincronizada');
      setTimeout(() => location.reload(), 900);
    } catch (error) {
      syncBusy = false;
      cancel.disabled = false; confirm.textContent = 'Sincronizar evidência';
      document.getElementById('sync-feedback').className = 'sync-feedback error';
      document.getElementById('sync-feedback').textContent = error.message;
      setSaveState(error.message, true);
      updateSyncActions(); updateSyncSelection();
    }
  });
  updateSyncActions();

  function serializeEditor(editor) {
    const blocks = [];
    function collectNode(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        if (node.textContent.length) blocks.push({ type: 'text', text: node.textContent });
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.matches('.rich-image')) {
        blocks.push({ type: 'image', id: node.dataset.evidenceId, width: Number(node.dataset.width) || 100 });
      } else if (node.matches('p,div')) {
        if (node.querySelector('.rich-image')) node.childNodes.forEach(collectNode);
        else blocks.push({ type: 'text', text: node.innerText.replace(/\r/g, '').replace(/\n$/, '') });
      } else if (node.matches('br')) {
        blocks.push({ type: 'text', text: '' });
      } else if (!node.matches('script,style')) {
        node.childNodes.forEach(collectNode);
      }
    }
    editor.childNodes.forEach(collectNode);
    return blocks.length ? blocks : [{ type: 'text', text: '' }];
  }
  function plainText(blocks) { return blocks.filter(block => block.type === 'text').map(block => block.text).join('\n'); }
  function collect(card) {
    const blocks = serializeEditor(card.querySelector('[data-rich-editor]'));
    return { status: card.dataset.status, actual: plainText(blocks), actual_doc: blocks,
             status_action: card.dataset.statusAction === 'true' };
  }
  async function persist(card) {
    const id = card.dataset.stepId;
    if (timers.has(id)) { clearTimeout(timers.get(id)); timers.delete(id); }
    if (inFlight.has(id)) { try { await inFlight.get(id); } catch (_) { /* Save the latest edit. */ } }
    const version = versions.get(id) || 0;
    const promise = (async () => {
      const response = await fetch(card.dataset.saveUrl, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify(collect(card))
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Falha ao salvar.');
      if (result.status_changed_at) {
        card.querySelector('[data-status-time]').textContent = `Status registrado em ${new Date(result.status_changed_at).toLocaleString('pt-BR')}`;
        card.dataset.statusSaved = 'true';
        updateSyncActions();
      }
      if ((versions.get(id) || 0) === version) card.dataset.statusAction = 'false';
      return version;
    })();
    inFlight.set(id, promise);
    try {
      await promise;
      if ((versions.get(id) || 0) > version) return persist(card);
      setSaveState('Tudo salvo');
    } catch (error) {
      if ((versions.get(id) || 0) > version) {
        if (inFlight.get(id) === promise) inFlight.delete(id);
        return persist(card);
      }
      setSaveState(error.message, true);
      throw error;
    }
    finally { if (inFlight.get(id) === promise) inFlight.delete(id); }
  }
  function queue(card) {
    const id = card.dataset.stepId;
    versions.set(id, (versions.get(id) || 0) + 1);
    setSaveState('Salvando…');
    if (timers.has(id)) clearTimeout(timers.get(id));
    timers.set(id, setTimeout(() => { persist(card).catch(() => {}); }, 550));
  }
  function selectIcon(row, selected) {
    row.querySelectorAll('.status-icon-button').forEach(button => {
      const active = button === selected;
      button.classList.toggle('selected', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }
  cards.forEach(card => {
    card.querySelectorAll('.step-status-buttons .status-icon-button').forEach(button => button.addEventListener('click', () => {
      card.dataset.status = button.dataset.value;
      card.dataset.statusAction = 'true';
      selectIcon(card.querySelector('.step-status-buttons'), button);
      updateSummary();
      queue(card);
    }));
  });
  async function persistCase(view) {
    const id = view.dataset.caseView;
    if (caseTimers.has(id)) { clearTimeout(caseTimers.get(id)); caseTimers.delete(id); }
    if (caseInFlight.has(id)) { try { await caseInFlight.get(id); } catch (_) { /* Save the latest edit. */ } }
    const version = caseVersions.get(id) || 0;
    const promise = (async () => {
      const response = await fetch(view.dataset.caseSaveUrl, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ status: view.dataset.manualStatus,
                               comment: plainText(serializeEditor(view.querySelector('.case-comment [data-rich-editor]'))),
                               comment_doc: serializeEditor(view.querySelector('.case-comment [data-rich-editor]')),
                               precondition_doc: serializeEditor(view.querySelector('.precondition [data-rich-editor]')) })
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Falha ao salvar o caso.');
      return version;
    })();
    caseInFlight.set(id, promise);
    try {
      await promise;
      if ((caseVersions.get(id) || 0) > version) return persistCase(view);
      setSaveState('Tudo salvo');
    } catch (error) {
      if ((caseVersions.get(id) || 0) > version) {
        if (caseInFlight.get(id) === promise) caseInFlight.delete(id);
        return persistCase(view);
      }
      setSaveState(error.message, true);
      throw error;
    }
    finally { if (caseInFlight.get(id) === promise) caseInFlight.delete(id); }
  }
  function queueCase(view) {
    const id = view.dataset.caseView;
    caseVersions.set(id, (caseVersions.get(id) || 0) + 1);
    setSaveState('Salvando…');
    if (caseTimers.has(id)) clearTimeout(caseTimers.get(id));
    caseTimers.set(id, setTimeout(() => { persistCase(view).catch(() => {}); }, 550));
  }
  views.forEach(view => {
    const row = view.querySelector('.case-status-buttons');
    const automatic = view.querySelector('.auto-status-button');
    row.querySelectorAll('.status-icon-button').forEach(button => button.addEventListener('click', () => {
      view.dataset.manualStatus = button.dataset.value;
      selectIcon(row, button);
      automatic.classList.remove('selected');
      automatic.setAttribute('aria-pressed', 'false');
      updateSummary();
      renderMiniPlayer();
      queueCase(view);
    }));
    automatic.addEventListener('click', () => {
      view.dataset.manualStatus = '';
      selectIcon(row, null);
      automatic.classList.add('selected');
      automatic.setAttribute('aria-pressed', 'true');
      updateSummary();
      renderMiniPlayer();
      queueCase(view);
    });
  });
  async function flushView(view) {
    await flushPendingMedia();
    for (const card of view.querySelectorAll('.step-card')) {
      const id = card.dataset.stepId;
      if (timers.has(id) || inFlight.has(id)) await persist(card);
    }
    const id = view.dataset.caseView;
    if (caseTimers.has(id) || caseInFlight.has(id)) await persistCase(view);
  }
  document.querySelectorAll('.failure-report-form').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try { await flushView(form.closest('.case-view')); form.submit(); }
    catch (error) { setSaveState(error.message, true); }
    finally { button.disabled = false; }
  }));
  document.querySelectorAll('.copy-bug-prompt').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    const original = button.textContent;
    try {
      const view = button.closest('.case-view');
      await flushView(view);
      const response = await fetch(button.closest('[data-failure-actions]').dataset.promptUrl);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Não foi possível carregar o prompt.');
      await navigator.clipboard.writeText(result.prompt);
      button.textContent = 'Prompt copiado';
      setTimeout(() => { button.textContent = original; }, 2500);
    } catch (error) { setSaveState(error.message, true); button.textContent = original; }
    finally { button.disabled = false; }
  }));
  document.getElementById('finish-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button');
    button.disabled = true;
    setSaveState('Concluindo salvamentos…');
    try {
      await flushPendingMedia();
      for (const card of cards) {
        const id = card.dataset.stepId;
        if (timers.has(id) || inFlight.has(id)) await persist(card);
      }
      for (const view of views) {
        const id = view.dataset.caseView;
        if (caseTimers.has(id) || caseInFlight.has(id)) await persistCase(view);
      }
      form.submit();
    } catch (error) {
      setSaveState(error.message, true);
      button.disabled = false;
    }
  });
  document.querySelectorAll('.retest-form').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const view = form.closest('.case-view');
    button.disabled = true;
    setSaveState('Guardando a execução atual…');
    try {
      await flushPendingMedia();
      for (const card of view.querySelectorAll('.step-card')) {
        const id = card.dataset.stepId;
        if (timers.has(id) || inFlight.has(id)) await persist(card);
      }
      const id = view.dataset.caseView;
      if (caseTimers.has(id) || caseInFlight.has(id)) await persistCase(view);
      form.submit();
    } catch (error) {
      setSaveState(error.message, true);
      button.disabled = false;
    }
  }));

  function queueEditor(editor) {
    const card = editor.closest('.step-card');
    if (card) queue(card);
    else queueCase(editor.closest('.case-view'));
  }
  function makeParagraph(value = '') {
    const paragraph = document.createElement('p');
    paragraph.className = 'rich-paragraph';
    paragraph.dataset.richText = '';
    paragraph.textContent = value;
    return paragraph;
  }
  function caretOffsetFromRange(paragraph, range) {
    if (!range || !paragraph.contains(range.startContainer)) return paragraph.textContent.length;
    const prefix = range.cloneRange();
    prefix.selectNodeContents(paragraph);
    prefix.setEnd(range.startContainer, range.startOffset);
    return prefix.toString().length;
  }
  function caretOffset(paragraph) {
    const selection = window.getSelection();
    return caretOffsetFromRange(paragraph, selection?.rangeCount ? selection.getRangeAt(0) : null);
  }
  function focusStart(paragraph) {
    paragraph.closest('[data-rich-editor]')?.focus();
    const range = document.createRange();
    range.selectNodeContents(paragraph);
    range.collapse(true);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  function focusEnd(node) {
    node.parentElement?.closest('[data-rich-editor]')?.focus();
    const range = document.createRange();
    range.selectNodeContents(node);
    range.collapse(false);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  function makeImageFigure(result, name) {
    const figure = document.createElement('figure');
    figure.className = 'rich-image';
    figure.contentEditable = 'false';
    figure.dataset.evidenceId = result.id;
    figure.dataset.width = '100';
    figure.style.width = '100%';
    const link = document.createElement('a');
    link.href = result.url; link.target = '_blank'; link.rel = 'noopener';
    link.title = 'Abrir imagem em tamanho original';
    const image = document.createElement('img'); image.src = result.url; image.alt = name;
    link.append(image);
    const caption = document.createElement('figcaption'); caption.textContent = name;
    const remove = document.createElement('button');
    remove.type = 'button'; remove.className = 'rich-image-remove'; remove.append(TestaizeIcons.create('x'));
    remove.setAttribute('aria-label', 'Excluir imagem'); remove.dataset.deleteUrl = result.delete_url;
    const handle = document.createElement('span');
    handle.className = 'rich-image-resize'; handle.append(TestaizeIcons.create('resize'));
    handle.tabIndex = 0; handle.setAttribute('role', 'slider');
    handle.setAttribute('aria-label', 'Largura da imagem');
    handle.setAttribute('aria-valuemin', '20'); handle.setAttribute('aria-valuemax', '100');
    handle.setAttribute('aria-valuenow', '100');
    handle.title = 'Arraste para ajustar a largura';
    figure.append(link, caption, remove, handle);
    return figure;
  }
  function insertFigure(editor, figure, paragraph, offset) {
    const anchor = paragraph?.isConnected ? paragraph : editor.querySelector('.rich-paragraph:last-of-type');
    editor._imageUrls.set(figure.dataset.evidenceId, figure.querySelector('.rich-image-remove').dataset.deleteUrl);
    if (!anchor) { editor.append(figure, makeParagraph()); focusStart(editor.lastElementChild); return; }
    const source = anchor.textContent;
    const position = Math.max(0, Math.min(source.length, offset ?? source.length));
    anchor.textContent = source.slice(0, position);
    const next = makeParagraph(source.slice(position));
    anchor.after(figure, next);
    focusStart(next);
  }
  function paragraphFromRange(editor, range) {
    const node = range?.startContainer;
    const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
    const paragraph = element?.closest('p,div');
    return paragraph && editor.contains(paragraph) && paragraph !== editor ? paragraph : null;
  }
  function selectedParagraph(editor) {
    const selection = window.getSelection();
    return paragraphFromRange(editor, selection?.rangeCount ? selection.getRangeAt(0) : null);
  }
  async function removeFigure(editor, figure) {
    const button = figure.querySelector('.rich-image-remove');
    const response = await fetch(button.dataset.deleteUrl, { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || 'Falha ao excluir imagem.');
    editor._imageUrls.delete(figure.dataset.evidenceId);
    figure.remove();
    if (!editor.children.length) editor.append(makeParagraph());
    updateSyncActions();
    queueEditor(editor);
    setSaveState('Imagem removida');
    renderMiniPlayer();
  }
  function syncRemovedImages(editor) {
    const current = new Set([...editor.querySelectorAll('.rich-image')].map(figure => figure.dataset.evidenceId));
    for (const [id, url] of editor._imageUrls) {
      if (current.has(id) || editor._pendingImageDeletes.has(id)) continue;
      editor._pendingImageDeletes.add(id);
      const task = (async () => {
        const response = await fetch(url, { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || 'Falha ao excluir imagem.');
      })();
      pendingUploads.add(task);
      task.then(() => editor._imageUrls.delete(id))
        .catch(error => setSaveState(`${error.message} Recarregue para tentar novamente.`, true))
        .finally(() => { editor._pendingImageDeletes.delete(id); pendingUploads.delete(task); });
    }
  }
  async function flushPendingMedia() {
    await Promise.all([...pendingUploads]);
    const editors = [...document.querySelectorAll('[data-rich-editor]')];
    editors.forEach(syncRemovedImages);
    await Promise.all([...pendingUploads]);
    if (editors.some(editor => [...editor._imageUrls.keys()].some(id =>
      !editor.querySelector(`.rich-image[data-evidence-id="${id}"]`)))) {
      throw new Error('Uma imagem ainda não foi removida. Tente novamente.');
    }
  }
  document.querySelectorAll('[data-rich-editor]').forEach(editor => {
    editor._imageUrls = new Map([...editor.querySelectorAll('.rich-image')].map(figure =>
      [figure.dataset.evidenceId, figure.querySelector('.rich-image-remove').dataset.deleteUrl]));
    editor._pendingImageDeletes = new Set();
    function rememberCaret() {
      editor._lastParagraph = selectedParagraph(editor);
      editor._lastOffset = editor._lastParagraph ? caretOffset(editor._lastParagraph) : null;
    }
    editor.addEventListener('mouseup', rememberCaret);
    editor.addEventListener('keyup', rememberCaret);
    editor.addEventListener('input', () => {
      syncRemovedImages(editor);
      updateSyncActions();
      queueEditor(editor);
      syncMiniObservedText(editor);
    });
    editor.addEventListener('keydown', event => {
      if (event.key !== 'Backspace' && event.key !== 'Delete') return;
      const selection = window.getSelection();
      if (!selection?.isCollapsed) return;
      const paragraph = selectedParagraph(editor);
      if (!paragraph) return;
      const atStart = caretOffset(paragraph) === 0;
      const atEnd = caretOffset(paragraph) === paragraph.textContent.length;
      let adjacent = event.key === 'Backspace' && atStart ? paragraph.previousSibling
        : event.key === 'Delete' && atEnd ? paragraph.nextSibling : null;
      while (adjacent?.nodeType === Node.TEXT_NODE && !adjacent.textContent.trim()) {
        adjacent = event.key === 'Backspace' ? adjacent.previousSibling : adjacent.nextSibling;
      }
      const figure = adjacent?.nodeType === Node.ELEMENT_NODE ? adjacent : null;
      if (figure?.matches('.rich-image')) {
        event.preventDefault();
        removeFigure(editor, figure).catch(error => setSaveState(error.message, true));
        return;
      }
      if (event.key !== 'Backspace' || !atStart) return;
      const previous = adjacent;
      if (!previous || (previous.nodeType === Node.ELEMENT_NODE && !previous.matches('p,div'))
          || (previous.nodeType !== Node.ELEMENT_NODE && previous.nodeType !== Node.TEXT_NODE)) return;
      event.preventDefault();
      if (previous.nodeType === Node.TEXT_NODE) {
        const boundary = previous.textContent.length;
        previous.textContent += paragraph.textContent;
        paragraph.remove();
        editor.focus();
        const range = document.createRange();
        range.setStart(previous, boundary);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
      } else {
        const boundary = previous.textContent.length;
        previous.append(...paragraph.childNodes);
        paragraph.remove();
        focusEnd(previous);
        const range = selection.getRangeAt(0);
        range.selectNodeContents(previous);
        range.setEnd(previous, previous.childNodes.length);
        if (boundary < previous.textContent.length) {
          let remaining = boundary;
          const walker = document.createTreeWalker(previous, NodeFilter.SHOW_TEXT);
          let textNode;
          while ((textNode = walker.nextNode())) {
            if (remaining <= textNode.textContent.length) {
              range.setStart(textNode, remaining);
              range.collapse(true);
              selection.removeAllRanges();
              selection.addRange(range);
              break;
            }
            remaining -= textNode.textContent.length;
          }
        }
      }
      queueEditor(editor);
    });
    editor.addEventListener('pointerdown', event => {
      const handle = event.target.closest('.rich-image-resize');
      if (!handle) return;
      event.preventDefault();
      const figure = handle.closest('.rich-image');
      const startX = event.clientX;
      const initial = Number(figure.dataset.width);
      handle.setPointerCapture(event.pointerId);
      function move(pointer) {
        const width = Math.max(20, Math.min(100, Math.round(initial + (pointer.clientX - startX) / editor.clientWidth * 100)));
        figure.dataset.width = String(width);
        figure.style.width = `${width}%`;
        handle.setAttribute('aria-valuenow', String(width));
        queueEditor(editor);
      }
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', () => handle.removeEventListener('pointermove', move), { once: true });
      handle.addEventListener('pointercancel', () => handle.removeEventListener('pointermove', move), { once: true });
    });
    editor.addEventListener('keydown', event => {
      const handle = event.target.closest('.rich-image-resize');
      if (!handle || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      const figure = handle.closest('.rich-image');
      const width = Math.max(20, Math.min(100, Number(figure.dataset.width) + (event.key === 'ArrowRight' ? 5 : -5)));
      figure.dataset.width = String(width); figure.style.width = `${width}%`;
      handle.setAttribute('aria-valuenow', String(width));
      queueEditor(editor);
    });
  });

  async function uploadImage(area, file, anchor = null, offset = null, selectionRange = null) {
    if (!file) return;
    const task = doUploadImage(area, file, anchor, offset, selectionRange);
    pendingUploads.add(task);
    try { await task; } finally { pendingUploads.delete(task); }
  }
  async function doUploadImage(area, file, anchor, offset, selectionRange) {
    const data = new FormData();
    data.append('imagem', file, file.name || 'Imagem colada.png');
    setSaveState('Enviando imagem…');
    try {
      const response = await fetch(area.dataset.uploadUrl, { method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: data });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Falha ao enviar imagem.');
      const editor = area.querySelector('[data-rich-editor]');
      if (editor) {
        if (selectionRange && !selectionRange.collapsed && editor.contains(selectionRange.commonAncestorContainer)) {
          selectionRange.deleteContents();
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(selectionRange);
          anchor = selectedParagraph(editor);
          offset = anchor ? caretOffset(anchor) : null;
          syncRemovedImages(editor);
        }
        insertFigure(editor, makeImageFigure(result, file.name || 'Imagem colada'), anchor, offset);
        selectSyncSource(area.closest('.step-card'));
        queueEditor(editor);
        setSaveState('Imagem inserida');
        renderMiniPlayer();
        return;
      }
      const node = document.createElement('div');
      node.className = 'evidence-item';
      node.dataset.evidenceId = result.id;
      const link = document.createElement('a');
      link.href = result.url; link.target = '_blank'; link.rel = 'noopener';
      const image = document.createElement('img'); image.src = result.url; image.alt = file.name || 'Imagem colada';
      const caption = document.createElement('span'); caption.textContent = file.name || 'Imagem colada';
      link.append(image, caption);
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'remove-evidence'; remove.append(TestaizeIcons.create('x'));
      remove.setAttribute('aria-label', 'Excluir imagem');
      remove.dataset.deleteUrl = result.delete_url;
      node.append(link, remove);
      area.querySelector('.evidence-list').append(node);
      updateEvidenceCount(area);
      setSaveState('Imagem salva');
    } catch (error) { setSaveState(error.message, true); throw error; }
  }
  function updateEvidenceCount(area) {
    area.querySelector('.evidence-heading span').textContent = `${area.querySelectorAll('.evidence-item').length} anexo(s)`;
  }
  document.querySelectorAll('.evidence-area').forEach(zone => {
    ['dragenter', 'dragover'].forEach(type => zone.addEventListener(type, event => { event.preventDefault(); zone.classList.add('dragging'); }));
    ['dragleave', 'drop'].forEach(type => zone.addEventListener(type, event => { event.preventDefault(); zone.classList.remove('dragging'); }));
    zone.addEventListener('drop', event => {
      const editor = zone.querySelector('[data-rich-editor]');
      uploadImage(zone, [...event.dataTransfer.files].find(file => file.type.startsWith('image/')),
                  editor && (selectedParagraph(editor) || editor.querySelector('.rich-paragraph:last-of-type'))).catch(() => {});
    });
  });
  document.querySelectorAll('.step-attachments').forEach(area => {
    const button = area.querySelector('.choose-step-attachment');
    const picker = area.querySelector('.step-attachment-input');
    const feedback = area.querySelector('.attachment-feedback');
    const showAttachmentError = message => { feedback.textContent = message; feedback.hidden = false; setSaveState(message, true); };
    if (!button || !picker) return;
    button.addEventListener('click', () => picker.click());
    picker.addEventListener('change', async () => {
      const files = [...picker.files];
      picker.value = '';
      if (!files.length) return;
      const existing = area.querySelectorAll('.step-attachment-item').length;
      const maxFiles = Number(area.dataset.maxFiles);
      const maxBytes = Number(area.dataset.maxBytes);
      if (existing + files.length > maxFiles) {
        showAttachmentError(`Cada passo aceita até ${maxFiles} arquivos. Remova um anexo antes de continuar.`);
        return;
      }
      const oversized = files.find(file => file.size > maxBytes);
      if (oversized) {
        showAttachmentError(`"${oversized.name}" excede o limite de 5 MB por arquivo.`);
        return;
      }
      feedback.hidden = true;
      for (const file of files) {
        const task = (async () => {
          const data = new FormData();
          data.append('arquivo', file, file.name);
          setSaveState(`Enviando ${file.name}…`);
          const response = await fetch(area.dataset.attachmentUploadUrl, {
            method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: data
          });
          const result = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(result.error || 'Falha ao anexar arquivo.');
          const row = document.createElement('div');
          row.className = 'step-attachment-item';
          row.dataset.attachmentId = result.id;
          const link = document.createElement('a');
          link.href = result.url;
          link.textContent = result.name;
          const size = document.createElement('small');
          size.textContent = `${(result.size / 1024).toFixed(1)} KB`;
          const remove = document.createElement('button');
          remove.type = 'button';
          remove.className = 'remove-step-attachment';
          remove.dataset.deleteUrl = result.delete_url;
          remove.textContent = 'Remover';
          remove.setAttribute('aria-label', `Remover ${result.name}`);
          row.append(link, size, remove);
          area.querySelector('.step-attachment-list').append(row);
          area.querySelector('[data-attachment-count]').textContent = `${area.querySelectorAll('.step-attachment-item').length} arquivo(s)`;
          setSaveState('Arquivo anexado');
        })();
        pendingUploads.add(task);
        try { await task; } catch (error) { showAttachmentError(error.message); break; }
        finally { pendingUploads.delete(task); }
      }
    });
    area.addEventListener('click', async event => {
      const remove = event.target.closest('.remove-step-attachment');
      if (!remove) return;
      remove.disabled = true;
      try {
        const response = await fetch(remove.dataset.deleteUrl, {
          method: 'POST', headers: { 'X-CSRF-Token': csrf }
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || 'Falha ao remover arquivo.');
        remove.closest('.step-attachment-item').remove();
        area.querySelector('[data-attachment-count]').textContent = `${area.querySelectorAll('.step-attachment-item').length} arquivo(s)`;
        feedback.hidden = true;
        setSaveState('Arquivo removido');
      } catch (error) { remove.disabled = false; showAttachmentError(error.message); }
    });
  });
  document.addEventListener('paste', event => {
    const zone = event.target.closest?.('.evidence-area');
    if (!zone) return;
    const file = [...(event.clipboardData?.files || [])].find(item => item.type.startsWith('image/'));
    if (file) {
      event.preventDefault();
      const editor = zone.querySelector('[data-rich-editor]');
      const paragraph = editor && selectedParagraph(editor);
      const range = editor && window.getSelection()?.rangeCount ? window.getSelection().getRangeAt(0).cloneRange() : null;
      uploadImage(zone, file, paragraph, paragraph ? caretOffset(paragraph) : null, range).catch(() => {});
    } else if (event.target.closest('[data-rich-editor]')) {
      event.preventDefault();
      const editor = event.target.closest('[data-rich-editor]');
      const selection = window.getSelection();
      if (!selection?.rangeCount || !editor.contains(selection.anchorNode)) return;
      const range = selection.getRangeAt(0);
      range.deleteContents();
      const pasted = document.createTextNode(event.clipboardData?.getData('text/plain') || '');
      range.insertNode(pasted);
      range.setStartAfter(pasted);
      range.collapse(true);
      selection.removeAllRanges();
      selection.addRange(range);
      syncRemovedImages(editor);
      queueEditor(editor);
    }
  });
  document.querySelectorAll('[data-rich-editor]').forEach(editor => editor.addEventListener('click', async event => {
    const button = event.target.closest('.rich-image-remove');
    if (!button) return;
    try {
      await removeFigure(editor, button.closest('.rich-image'));
    } catch (error) { setSaveState(error.message, true); }
  }));
  document.querySelectorAll('.evidence-list').forEach(list => list.addEventListener('click', async event => {
    const button = event.target.closest('.remove-evidence');
    if (!button) return;
    try {
      const response = await fetch(button.dataset.deleteUrl, { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Falha ao excluir imagem.');
      const area = button.closest('.evidence-area');
      button.closest('.evidence-item').remove();
      updateEvidenceCount(area);
      setSaveState('Imagem removida');
    } catch (error) { setSaveState(error.message, true); }
  }));
})();
