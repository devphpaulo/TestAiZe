/* Presentation for the existing confirmation flows; native dialog handles keyboard focus. */
(() => {
  let dialog;
  let pending = false;
  function build() {
    dialog = document.createElement('dialog');
    dialog.className = 'confirmation-dialog';
    dialog.setAttribute('aria-labelledby', 'confirmation-title');
    dialog.setAttribute('aria-describedby', 'confirmation-message');
    const form = document.createElement('form');
    form.method = 'dialog';
    const body = document.createElement('div');
    body.className = 'confirmation-body';
    const title = document.createElement('h2');
    title.id = 'confirmation-title';
    const message = document.createElement('p');
    message.id = 'confirmation-message';
    body.append(title, message);
    const actions = document.createElement('div');
    actions.className = 'confirmation-actions';
    for (const [value, label] of [['cancel', 'Cancelar'], ['confirm', 'Confirmar']]) {
      const button = document.createElement('button');
      button.type = 'submit'; button.value = value; button.textContent = label;
      button.className = `button button-${value === 'cancel' ? 'secondary' : 'primary'}`;
      actions.append(button);
    }
    form.append(body, actions);
    dialog.append(form);
    document.body.append(dialog);
  }
  function ask({ title, message, confirmLabel = 'Confirmar', danger = false }) {
    if (pending) return Promise.resolve(false);
    if (!dialog) build();
    pending = true;
    const previousFocus = document.activeElement;
    dialog.querySelector('#confirmation-title').textContent = title;
    dialog.querySelector('#confirmation-message').textContent = message;
    const confirm = dialog.querySelector('[value="confirm"]');
    confirm.textContent = confirmLabel;
    confirm.className = `button button-${danger ? 'danger' : 'primary'}`;
    dialog.returnValue = 'cancel';
    return new Promise(resolve => {
      dialog.addEventListener('close', () => {
        pending = false;
        if (previousFocus?.isConnected) previousFocus.focus();
        resolve(dialog.returnValue === 'confirm');
      }, { once: true });
      dialog.showModal();
      dialog.querySelector(danger ? '[value="cancel"]' : '[value="confirm"]').focus();
    });
  }
  window.TestaizeConfirm = Object.freeze({ ask });
})();
