(() => {
  const root = document.documentElement;
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  let preference;
  try { preference = localStorage.getItem('executor-theme'); } catch (_) { /* Use the system theme. */ }
  if (preference !== 'light' && preference !== 'dark') preference = null;
  let trigger;
  function render() {
    const theme = preference ?? (systemTheme.matches ? 'dark' : 'light');
    root.dataset.theme = theme;
    trigger?.setAttribute('aria-pressed', String(theme === 'dark'));
  }
  render();
  systemTheme.addEventListener('change', render);
  document.addEventListener('DOMContentLoaded', () => {
    trigger = document.getElementById('appearance-trigger');
    trigger?.addEventListener('click', () => {
      preference = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('executor-theme', preference); } catch (_) { /* Keep the choice for this page. */ }
      render();
    });
    render();
  });
})();
