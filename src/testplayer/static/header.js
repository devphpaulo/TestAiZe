(() => {
  const picker = document.getElementById('appearance-picker');
  const trigger = document.getElementById('appearance-trigger');
  const panel = document.getElementById('appearance-panel');
  const boards = document.getElementById('board-select');
  boards?.addEventListener('change', () => {
    const option = boards.selectedOptions[0];
    if (option && !option.disabled) window.location.assign(option.value);
  });
  if (!picker || !trigger || !panel) return;
  const themeButtons = [...picker.querySelectorAll('[data-theme-choice]')];
  const accentButtons = [...picker.querySelectorAll('[data-accent-choice]')];
  function update() {
    themeButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === document.documentElement.dataset.theme)));
    accentButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.accentChoice === document.documentElement.dataset.accent)));
  }
  function close(restoreFocus = false) {
    panel.hidden = true; trigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus) trigger.focus();
  }
  trigger.addEventListener('click', () => {
    if (!panel.hidden) { close(); return; }
    panel.hidden = false; trigger.setAttribute('aria-expanded', 'true');
    (themeButtons.find(button => button.getAttribute('aria-pressed') === 'true') || themeButtons[0]).focus();
  });
  function choose(button, key, storageKey, value) {
    document.documentElement.dataset[key] = value;
    try { localStorage.setItem(storageKey, value); } catch (_) { /* Keep the choice for this page. */ }
    update(); button.focus();
  }
  themeButtons.forEach(button => button.addEventListener('click', () => choose(button, 'theme', 'executor-theme', button.dataset.themeChoice)));
  accentButtons.forEach(button => button.addEventListener('click', () => choose(button, 'accent', 'testaize-accent', button.dataset.accentChoice)));
  document.addEventListener('click', event => { if (!picker.contains(event.target)) close(); });
  document.addEventListener('focusin', event => { if (!picker.contains(event.target)) close(); });
  picker.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); event.stopPropagation(); close(true); }
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    const buttons = event.target.closest('.appearance-themes') ? themeButtons : accentButtons;
    const index = buttons.indexOf(event.target);
    if (index < 0) return;
    event.preventDefault();
    buttons[(index + (['ArrowLeft','ArrowUp'].includes(event.key) ? -1 : 1) + buttons.length) % buttons.length].focus();
  });
  update();
})();
