/* Shared image interaction. Image undo is coordinated with native text history. */
(() => {
  function resizedWidth(width, height, contentWidth, edge, dx, dy) {
    const horizontal = edge.includes('w') ? -dx : dx;
    const vertical = (edge.includes('n') ? -dy : dy) * width / Math.max(height, 1);
    const delta = edge.length === 1 ? ('ns'.includes(edge) ? vertical : horizontal)
      : Math.abs(horizontal) > Math.abs(vertical) ? horizontal : vertical;
    return (width + delta) / Math.max(contentWidth, 1) * 100;
  }

  function createLedger(options = {}) {
    const aliases = new Map(), entries = new Set(), pending = new Set(), errors = new Map();
    function apply(entry, figure) {
      figure.dataset.evidenceId = entry.id;
      if (entry.url) figure.querySelector('img').src = entry.url;
      if (entry.delete_url) figure.dataset.deleteUrl = entry.delete_url;
    }
    function register(figure) {
      let entry = aliases.get(figure.dataset.evidenceId);
      if (!entry) {
        const image = figure.querySelector('img');
        entry = {key: figure.dataset.evidenceId, id: figure.dataset.evidenceId, url: image.src, name: image.alt || 'Imagem.png',
          delete_url: figure.dataset.deleteUrl, figure, desired: true, present: true};
        aliases.set(entry.id, entry); entries.add(entry);
      }
      entry.figure = figure;
      if (entry.present) apply(entry, figure);
      return entry;
    }
    function schedule(entry) {
      if (entry.task) return;
      errors.delete(entry);
      const task = (async () => {
        while (entry.desired !== entry.present) {
          if (entry.desired) {
            const result = await options.restore?.(entry);
            if (result) Object.assign(entry, result);
            aliases.set(entry.id, entry);
            entry.present = true;
            if (entry.desired) apply(entry, entry.figure);
          } else {
            await options.remove?.(entry);
            entry.present = false;
          }
        }
      })();
      entry.task = task; pending.add(task); options.pending?.(task);
      task.catch(error => { errors.set(entry, error); options.error?.(error); }).finally(() => {
        pending.delete(task); entry.task = null; options.change?.();
      });
    }
    function scan(figures) {
      const visible = new Set([...figures].map(register));
      for (const entry of entries) {
        const desired = visible.has(entry);
        if (entry.desired === desired) continue;
        entry.desired = desired; schedule(entry);
      }
    }
    async function flush() {
      while (pending.size) await Promise.all([...pending]);
      if (errors.size) throw [...errors.values()][0];
    }
    return {register, scan, flush};
  }

  function createHistory(signature, changed) {
    const undo = [], redo = [];
    function record(action, before) {
      const after = signature();
      if (before === after) return;
      undo.push({...action, before, after}); redo.length = 0;
    }
    function apply(from, to, method, expected) {
      const action = from.at(-1);
      if (!action || signature() !== action[expected]) return false;
      from.pop(); action[method](); to.push(action); changed(); return true;
    }
    return {record, undo: () => apply(undo, redo, 'undo', 'after'),
      redo: () => apply(redo, undo, 'redo', 'before'),
      input: type => { if (type !== 'historyUndo' && type !== 'historyRedo') redo.length = 0; }};
  }

  function create({id, url, name = 'Evidência', width = 100, delete_url}) {
    const figure = document.createElement('figure');
    figure.className = 'rich-image'; figure.contentEditable = 'false';
    figure.dataset.evidenceId = id; figure.dataset.width = String(width); figure.style.width = `${width}%`;
    if (delete_url) figure.dataset.deleteUrl = delete_url;
    const image = document.createElement('img'); image.src = url; image.alt = name; image.draggable = false;
    figure.append(image);
    return figure;
  }

  function mount(editor, options = {}) {
    let selected = null;
    const doc = editor.ownerDocument;
    const ledger = createLedger(options);
    const figures = () => [...editor.querySelectorAll('.rich-image')];
    function select(figure) {
      selected?.classList.remove('is-selected'); selected = figure;
      if (figure) { figure.classList.add('is-selected'); figure.focus({preventScroll:true}); }
    }
    function setWidth(figure, value) {
      const width = Math.max(20, Math.min(100, Math.round(value)));
      figure.dataset.width = String(width); figure.style.width = `${width}%`;
      figure.setAttribute('aria-label', `Imagem, largura ${width}%. Arraste as bordas ou use as setas. Delete exclui e Ctrl+Z desfaz.`);
      options.change?.();
    }
    function register(figure) {
      figure.contentEditable = 'false'; figure.tabIndex = 0;
      if (!figure.hasAttribute('data-image-interaction')) {
        figure.dataset.imageInteraction = ''; figure.tabIndex = 0; figure.setAttribute('role','group');
        figure.setAttribute('aria-label','Imagem. Selecione para redimensionar. Delete ou Backspace exclui; Ctrl+Z desfaz.');
        for (const edge of ['nw','n','ne','e','se','s','sw','w']) {
          const handle = doc.createElement('span'); handle.className = 'image-edge-handle';
          handle.dataset.edge = edge; handle.setAttribute('aria-hidden','true'); figure.append(handle);
        }
      }
      ledger.register(figure);
      return figure;
    }
    function changed() { figures().forEach(register); ledger.scan(figures()); options.change?.(); }
    function signature() {
      return JSON.stringify(TestaizeDocument.serialize(editor).map(block => block.type === 'image'
        ? {...block, id: ledger.register(figures().find(figure => figure.dataset.evidenceId === block.id)).key}
        : block));
    }
    const history = createHistory(signature, changed);
    function remove(figure) {
      register(figure);
      const before = signature(), parent = figure.parentNode, next = figure.nextSibling;
      const position = [...parent.childNodes].indexOf(figure);
      select(null); figure.remove(); editor.focus({preventScroll:true});
      history.record({
        undo: () => {
          const target = editor.contains(parent) ? parent : editor;
          const anchor = next?.parentNode === target ? next : target.childNodes[position] || null;
          target.insertBefore(figure, anchor); select(figure);
        },
        redo: () => { select(null); figure.remove(); editor.focus({preventScroll:true}); }
      }, before);
      changed();
    }
    editor.addEventListener('input', event => { history.input(event.inputType); changed(); });
    editor.addEventListener('focusin', event => { if (!event.target.closest('.rich-image')) select(null); });
    doc.addEventListener('pointerdown', event => { if (!editor.contains(event.target)) select(null); });
    editor.addEventListener('pointerdown', event => {
      const figure = event.target.closest('.rich-image');
      if (!figure || !editor.contains(figure)) { select(null); return; }
      event.preventDefault(); select(figure);
      const handle = event.target.closest('.image-edge-handle');
      if (!handle) return;
      const rect = figure.getBoundingClientRect(), style = getComputedStyle(editor);
      const width = editor.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const x = event.clientX, y = event.clientY, before = signature(), oldWidth = Number(figure.dataset.width);
      handle.setPointerCapture(event.pointerId);
      const move = pointer => setWidth(figure, resizedWidth(rect.width, rect.height, width, handle.dataset.edge,
                                                           pointer.clientX - x, pointer.clientY - y));
      const finish = () => {
        const newWidth = Number(figure.dataset.width);
        history.record({undo:()=>setWidth(figure, oldWidth), redo:()=>setWidth(figure, newWidth)}, before);
        handle.removeEventListener('pointermove',move); handle.removeEventListener('pointerup',finish);
        handle.removeEventListener('pointercancel',finish);
      };
      handle.addEventListener('pointermove',move); handle.addEventListener('pointerup',finish); handle.addEventListener('pointercancel',finish);
    });
    editor.addEventListener('keydown', event => {
      if (event.defaultPrevented) return;
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && (key === 'z' || key === 'y')) {
        const method = key === 'y' || event.shiftKey ? 'redo' : 'undo';
        if (history[method]()) { event.preventDefault(); return; }
        if (selected) { event.preventDefault(); select(null); editor.focus(); doc.execCommand(method, false); changed(); }
        return;
      }
      if (!selected) return;
      if (event.target !== selected && !selected.contains(event.target)) { select(null); return; }
      if (['Tab','ArrowUp','ArrowDown'].includes(event.key)) { select(null); return; }
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault(); event.stopPropagation(); remove(selected); return;
      }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        const figure = selected, before = signature(), oldWidth = Number(figure.dataset.width);
        setWidth(figure, oldWidth + (event.key === 'ArrowRight' ? 5 : -5));
        const newWidth = Number(figure.dataset.width);
        history.record({undo:()=>setWidth(figure,oldWidth),redo:()=>setWidth(figure,newWidth)},before);
      }
      if (event.key === 'Escape') { event.preventDefault(); select(null); editor.focus(); }
    });
    figures().forEach(register);
    return {register, remove, scan:changed, flush:ledger.flush};
  }
  globalThis.TestaizeImages = {create, mount, createLedger, createHistory, resizedWidth};
})();
