// Onay kutulu çoklu seçim menüsü: <details class="multi"> içinde <summary> + .multi-menu > label > input[type=checkbox].
// root.values() seçili değerleri verir (boş = hepsi); seçim değişince root üzerinde 'change' olayı tetiklenir.
function setupMultiSelect(root) {
  const boxes = [...root.querySelectorAll('input[type=checkbox]')];
  const summary = root.querySelector('summary');
  const update = () => {
    const picked = boxes.filter(b => b.checked);
    summary.textContent = !picked.length ? t('filter.all')
      : picked.length <= 2 ? picked.map(b => b.parentElement.textContent.trim()).join(', ')
      : t('filter.n_selected', { count: picked.length });
  };
  root.values = () => boxes.filter(b => b.checked).map(b => b.value);
  root.clear = () => { boxes.forEach(b => { b.checked = false; }); update(); };
  boxes.forEach(b => b.addEventListener('change', () => { update(); root.dispatchEvent(new Event('change')); }));
  document.addEventListener('click', e => { if (!root.contains(e.target)) root.open = false; });
  root.addEventListener('keydown', e => { if (e.key === 'Escape') { root.open = false; summary.focus(); } });
  update();
}
