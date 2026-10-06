(() => {
  const page = document.querySelector('#automation-script');
  if (!page) return;
  const feedback = document.querySelector('#automation-library-feedback');
  document.querySelector('#automation-script-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const response = await fetch('/api/iniciativas/automacao/scripts/' + page.dataset.script, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content }, body: JSON.stringify({ name: document.querySelector('#script-name').value, cycle_id: document.querySelector('#script-cycle').value, code: document.querySelector('#script-code').value }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Não foi possível salvar.');
      page.dataset.cycle = result.item.cycle_id;
      page.querySelector('.automation-heading h1').textContent = result.item.name;
      document.title = result.item.name + ' · Automação';
      feedback.textContent = 'Script salvo no ciclo selecionado.';
    } catch (error) { feedback.textContent = error.message; }
  });
})();
