/* Shared presentation helper. External URLs also work in Picture-in-Picture. */
(() => {
  const sprite = new URL('icons.svg', document.currentScript.src).href;
  const namespace = 'http://www.w3.org/2000/svg';
  const statusNames = { nao_executado: 'circle', em_andamento: 'clock', bloqueado: 'ban', reprovado: 'x', aprovado: 'check' };
  function create(name) {
    const svg = document.createElementNS(namespace, 'svg');
    svg.classList.add('ui-icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const use = document.createElementNS(namespace, 'use');
    use.setAttribute('href', `${sprite}#${name}`);
    svg.append(use);
    return svg;
  }
  window.TestaizeIcons = Object.freeze({ create, status: code => create(statusNames[code] || 'circle') });
})();
