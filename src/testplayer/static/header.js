(() => {
  const boards = document.getElementById('board-select');
  boards?.addEventListener('change', () => {
    const option = boards.selectedOptions[0];
    if (option && !option.disabled) window.location.assign(option.value);
  });
})();
