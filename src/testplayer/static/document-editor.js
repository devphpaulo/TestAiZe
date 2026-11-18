(() => {
function serialize(editor) {
    const blocks = [];
    function collectNode(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        if (node.textContent.length) blocks.push({ type: 'text', text: node.textContent });
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.matches('.rich-image')) {
        blocks.push({ type: 'image', id: node.dataset.evidenceId, width: Number(node.dataset.width) || 100 });
      } else if (node.matches('p,div')) {
        if (node.querySelector('.rich-image')) node.childNodes.forEach(collectNode);
        else blocks.push({ type: 'text', text: node.innerText.replace(/\r/g, '').replace(/\n$/, '') });
      } else if (node.matches('br')) {
        blocks.push({ type: 'text', text: '' });
      } else if (!node.matches('script,style')) {
        node.childNodes.forEach(collectNode);
      }
    }
    editor.childNodes.forEach(collectNode);
    return blocks.length ? blocks : [{ type: 'text', text: '' }];
  }

  globalThis.TestaizeDocument = { serialize };
})();
