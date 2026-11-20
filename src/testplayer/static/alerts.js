(() => {
  const paths = {
    error: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6m0-6 6 6"/>',
    success: '<circle cx="12" cy="12" r="10"/><path d="m8 12 3 3 5-6"/>',
    warning: '<path d="M10.3 3.9 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4m0 4h.01"/>',
  };
  const storageKey = 'testaize-next-alert';

  function show(message, tone = 'error', owner = document) {
    if (!String(message ?? '').trim()) return;
    const container = [...owner.querySelectorAll('dialog[open]')].at(-1) || owner.body;
    const stack = owner.getElementById('app-alerts') || owner.createElement('div');
    stack.id = 'app-alerts';
    stack.className = 'app-alerts';
    if (stack.parentElement !== container) container.append(stack);
    if (typeof stack.showPopover === 'function') {
      stack.setAttribute('popover', 'manual');
      if (!stack.matches(':popover-open')) stack.showPopover();
    }
    tone = Object.hasOwn(paths, tone) ? tone : 'warning';
    if ([...stack.children].some(row => row.dataset.tone === tone && row.textContent === message)) return;
    const row = owner.createElement('div');
    row.className = 'app-alert';
    row.dataset.tone = tone;
    row.setAttribute('role', tone === 'error' ? 'alert' : 'status');
    const icon = owner.createElementNS('http://www.w3.org/2000/svg', 'svg');
    icon.setAttribute('viewBox', '0 0 24 24');
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = paths[tone];
    const text = owner.createElement('span');
    text.textContent = message;
    row.append(icon, text);
    stack.append(row);
    setTimeout(() => {
      row.remove();
      if (!stack.childElementCount && typeof stack.hidePopover === 'function' && stack.matches(':popover-open')) {
        stack.hidePopover();
      }
    }, 6000);
  }

  function next(message, tone) {
    try { sessionStorage.setItem(storageKey, JSON.stringify({message, tone})); }
    catch (_) { show(message, tone); }
  }

  window.TestaizeAlerts = {show, next};
  document.querySelectorAll('[data-server-alert]').forEach(item =>
    show(item.textContent, item.dataset.serverAlert));
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    sessionStorage.removeItem(storageKey);
    if (saved) show(saved.message, saved.tone);
  } catch (_) { /* Storage can be unavailable in private sessions. */ }

  let invalidField;
  document.addEventListener('invalid', event => {
    const field = event.target;
    if (!field.validationMessage) return;
    event.preventDefault();
    if (invalidField) return;
    invalidField = field;
    setTimeout(() => {
      const label = invalidField.labels?.[0]?.firstChild?.textContent.trim();
      show(label ? `${label}: ${invalidField.validationMessage}` : invalidField.validationMessage, 'warning');
      invalidField.focus();
      invalidField = null;
    }, 0);
  }, true);
})();
