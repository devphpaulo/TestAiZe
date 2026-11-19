(() => {
  const customizable = CSS.supports('appearance', 'base-select') && 'HTMLSelectedContentElement' in window;

  function decorate(option) {
    const {tone, icon} = option.dataset;
    if (!customizable || (!tone && !icon)) return;
    const marker = document.createElement('span');
    marker.className = 'app-select-marker';
    marker.setAttribute('aria-hidden', 'true');
    if (tone) marker.dataset.tone = tone;
    if (icon) marker.dataset.icon = icon;
    option.prepend(marker);
  }

  document.querySelectorAll('select:not([multiple]):not([size])').forEach(select => {
    select.classList.add('app-select');
    if (!customizable) return;
    Array.from(select.options).forEach(decorate);
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.append(document.createElement('selectedcontent'));
    select.prepend(trigger);
  });

  window.TestAizeSelect = {
    replaceOptions(select, options) {
      select.length = 0;
      for (const option of options) {
        decorate(option);
        select.add(option);
      }
    },
  };
})();
