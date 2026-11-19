(() => {
  const dialog = document.querySelector('#session-board-dialog');
  if (!dialog) return;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const form = dialog.querySelector('form');
  const confirm = dialog.querySelector('[data-board-confirm]');
  const cancel = dialog.querySelector('[data-board-cancel]');
  const error = dialog.querySelector('[data-board-error]');
  const destination = dialog.querySelector('select');
  const reason = dialog.querySelector('textarea');
  const grid = document.querySelector('[data-session-board]');
  const player = document.querySelector('[data-player]');
  const labels = JSON.parse((grid || player).dataset.labels);
  const feedback = document.querySelector('[data-board-feedback]');
  let submitAction;

  function describe(title, description, button, {options, needsReason = false, dangerous = false} = {}, action) {
    dialog.querySelector('h2').textContent = title;
    dialog.querySelector('#session-dialog-copy').textContent = description;
    window.TestAizeSelect.replaceOptions(destination, (options || []).map(value => {
      const option = new Option(labels[value], value);
      option.dataset.tone = value;
      return option;
    }));
    destination.parentElement.hidden = !options;
    reason.parentElement.hidden = !needsReason;
    reason.required = needsReason;
    reason.value = '';
    error.hidden = true;
    confirm.textContent = button;
    confirm.classList.toggle('session-danger', dangerous);
    submitAction = action;
    if (!dialog.open) dialog.showModal();
    (needsReason ? reason : options ? destination : cancel).focus();
  }

  cancel.addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', event => { if (confirm.disabled) event.preventDefault(); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (confirm.disabled) return;
    error.hidden = true;
    cancel.disabled = confirm.disabled = true;
    try { await submitAction(); }
    catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally { cancel.disabled = confirm.disabled = false; }
  });

  async function request(url, body) {
    const response = await fetch(url, body === undefined ? {cache: 'no-store'} : {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const failure = new Error(payload.error || 'Não foi possível atualizar a execução.');
      failure.card = payload.card;
      throw failure;
    }
    return payload;
  }

  function sendForm(url, fields) {
    const post = document.createElement('form');
    post.method = 'POST';
    post.action = url;
    Object.entries({csrf_token: csrf, ...fields}).forEach(([key, value]) => {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = key;
      input.value = value;
      post.append(input);
    });
    document.body.append(post);
    post.submit();
  }

  function edit(target, name) {
    describe('Editar execução concluída?', name + '. Alterar os testes ou as evidências pode comprometer a integridade das evidências e a confiabilidade dos resultados.',
      'Liberar edição', {dangerous: true}, async () => {
        const {grant} = await request(target.dataset.editUrl, {confirmed: true});
        sendForm(target.dataset.playerUrl || location.href, {edit_grant: grant});
      });
  }

  function clone(target, name) {
    describe('Criar nova execução?', name + '. A cópia começa no Backlog com os mesmos casos e passos, sem resultados ou evidências.',
      'Criar no Backlog', {}, () => sendForm(target.dataset.cloneUrl, {}));
  }

  async function move(target, selected) {
    const getCard = () => request(target.dataset.boardUrl);
    const refresh = () => {
      if (target === player) location.assign(location.href);
      else { history.replaceState(null, '', '#' + target.id); location.reload(); }
    };
    const renderMove = async (card, to) => {
      if (!to) {
        if (!card.allowed.length) throw new Error('Esta execução não pode ser movida.');
        describe('Mover execução', card.source_name + ' · ' + labels[card.phase], 'Continuar',
          {options: card.allowed}, () => renderMove(card, destination.value));
        return;
      }
      if (!card.allowed.includes(to)) throw new Error('Esta movimentação não está mais disponível.');
      const save = async (body = {}) => {
        try {
          await request(target.dataset.boardUrl, {destination: to, version: card.version, ...body});
          refresh();
        } catch (failure) {
          if (failure.card?.allowed.includes(to)) {
            await renderMove(failure.card, to);
          }
          throw failure;
        }
      };
      if (to === 'blocked') {
        describe('Registrar impedimento', card.source_name + ' voltará para ' + labels[card.phase] + ' quando o impedimento for removido.',
          'Confirmar impedimento', {needsReason: true}, () => save({reason: reason.value}));
      } else if (to === 'done') {
        const pending = card.cases - card.counts.aprovado;
        const message = pending
          ? `Confira os resultados antes de concluir. ${card.counts.aprovado} de ${card.cases} casos estão aprovados.`
          : `Todos os ${card.cases} casos estão aprovados.`;
        describe('Concluir execução?', message + ' Após a conclusão, a execução abre somente para leitura. Alterações exigem liberar a edição.',
          'Concluir execução', {}, () => save({confirmed: true}));
      } else if (card.phase === 'blocked') {
        describe('Remover impedimento?', card.source_name + ' voltará para ' + labels[to] + '.', 'Remover impedimento', {}, () => save());
      } else {
        await save();
      }
    };
    try {
      const card = await getCard();
      await renderMove(card, selected || (card.phase === 'blocked' ? card.allowed[0] : ''));
    } catch (failure) {
      if (dialog.open) {
        error.textContent = failure.message;
        error.hidden = false;
      } else if (feedback) feedback.textContent = failure.message;
      else throw failure;
    }
  }

  window.TestAizeSessionBoard = {move};
  if (player) {
    const token = player.dataset.editGrant;
    let refreshingEdit = false;
    const end = () => fetch(player.dataset.endEditUrl, {
      method: 'POST', keepalive: true, headers: {'X-CSRF-Token': csrf, 'X-Session-Edit': token},
    });
    player.querySelector('[data-board-player-edit]')?.addEventListener('click', () => edit(player, player.dataset.sessionName));
    player.querySelector('[data-board-player-clone]')?.addEventListener('click', () => clone(player, player.dataset.sessionName));
    if (token) {
      window.TestAizeSessionBoard.endEdit = () =>
        sendForm(player.dataset.endEditUrl, {edit_grant: token, return_to_player: '1'});
      window.TestAizeSessionBoard.refreshPlayer = () => {
        refreshingEdit = true;
        sendForm(location.href, {edit_grant: token});
      };
      window.addEventListener('pagehide', () => { if (!refreshingEdit) end().catch(() => {}); }, {once: true});
      window.addEventListener('pageshow', event => { if (event.persisted) window.TestAizeSessionBoard.endEdit(); });
    }
  }
  if (!grid) return;
  window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });

  const search = document.querySelector('[data-board-search]');
  const filter = document.querySelector('[data-board-filter]');
  const lanes = [...grid.querySelectorAll('[data-board-lane]')];
  function applyFilters() {
    const query = search.value.trim().toLocaleLowerCase('pt-BR');
    lanes.forEach(lane => {
      lane.hidden = Boolean(filter.value && lane.dataset.boardLane !== filter.value);
      let count = 0;
      lane.querySelectorAll('[data-board-card]').forEach(element => {
        const card = JSON.parse(element.dataset.card);
        element.hidden = !`${card.source_name} #${card.id}`.toLocaleLowerCase('pt-BR').includes(query);
        if (!element.hidden) count++;
      });
      lane.querySelector('[data-board-count]').textContent = count;
      lane.querySelector('[data-board-empty]').hidden = count !== 0;
    });
  }
  search.addEventListener('input', applyFilters);
  filter.addEventListener('change', applyFilters);
  grid.addEventListener('click', event => {
    const button = event.target.closest('[data-board-action]');
    if (!button) return;
    const target = button.closest('[data-board-card]');
    const card = JSON.parse(target.dataset.card);
    feedback.textContent = '';
    if (button.dataset.boardAction === 'move') move(target);
    if (button.dataset.boardAction === 'edit') edit(target, card.source_name);
    if (button.dataset.boardAction === 'clone') clone(target, card.source_name);
    if (button.dataset.boardAction === 'delete') {
      describe('Excluir execução permanentemente?', card.source_name + '. Os resultados, o histórico, as evidências e os relatórios salvos desta execução serão apagados do disco.',
        'Excluir permanentemente', {dangerous: true}, () => sendForm(target.dataset.deleteUrl, {action: 'delete'}));
    }
  });

  let dragged;
  function clearDrag() {
    dragged = null;
    lanes.forEach(lane => lane.classList.remove('is-drop-target'));
  }
  grid.addEventListener('dragstart', event => {
    const origin = event.target.closest('[data-board-card]');
    if (!origin || !origin.draggable || event.target.closest('button, a')) { event.preventDefault(); return; }
    dragged = origin;
    event.dataTransfer.setData('text/plain', origin.id);
    event.dataTransfer.effectAllowed = 'move';
  });
  grid.addEventListener('dragend', clearDrag);
  grid.addEventListener('dragover', event => {
    const lane = event.target.closest('[data-board-lane]');
    if (!dragged || !lane) return;
    const allowed = JSON.parse(dragged.dataset.card).allowed.includes(lane.dataset.boardLane);
    lanes.forEach(item => item.classList.toggle('is-drop-target', allowed && item === lane));
    if (allowed) event.preventDefault();
  });
  grid.addEventListener('drop', event => {
    const lane = event.target.closest('[data-board-lane]');
    if (!lane || !dragged) return;
    event.preventDefault();
    const target = dragged;
    clearDrag();
    move(target, lane.dataset.boardLane);
  });

  const importer = document.querySelector('#board-import-dialog');
  const importButton = document.querySelector('[data-board-import]');
  importButton.addEventListener('click', () => importer.showModal());
  document.querySelector('[data-board-import-cancel]').addEventListener('click', () => importer.close());
  importButton.disabled = false;
  grid.querySelectorAll('[data-board-action]').forEach(button => { button.disabled = false; });
})();
