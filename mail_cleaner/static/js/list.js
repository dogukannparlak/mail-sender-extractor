// Tablo satırlarını arama, filtre ve sıralamayla yönetir. Satırlar sunucuda çizilir; burada yalnız gizlenir/yeniden dizilir.
// Satır öznitelikleri: data-<filtre adı> (filtre), data-sort-<anahtar> (sıralama; sayı ya da metin).
function setupList({ rows, search, selects = [], checks = [], sort, count, noMatch }) {
  if (!rows.length) return;
  const tbody = rows[0].parentElement;
  const sortValue = (row, key) => row.dataset['sort' + key[0].toUpperCase() + key.slice(1)] ?? '';
  const apply = () => {
    const query = search ? search.value.trim().toLocaleLowerCase('tr') : '';
    let shown = 0;
    for (const row of rows) {
      let ok = !query || row.textContent.toLocaleLowerCase('tr').includes(query);
      for (const { el, attr } of selects) if (ok && el.value && row.dataset[attr] !== el.value) ok = false;
      for (const { el, attr } of checks) if (ok && el.checked && row.dataset[attr] !== '1') ok = false;
      row.hidden = !ok;
      if (ok) shown++;
    }
    count.textContent = t('list.showing', { shown, total: rows.length });
    noMatch.hidden = shown > 0;
  };
  const reorder = () => {
    const [key, dir] = sort.value.split(':');
    const sign = dir === 'asc' ? 1 : -1;
    rows.sort((a, b) => {
      const x = sortValue(a, key), y = sortValue(b, key);
      const numeric = x !== '' && y !== '' && !isNaN(x) && !isNaN(y);
      return sign * (numeric ? Number(x) - Number(y) : x.localeCompare(y, 'tr'));
    });
    rows.forEach(r => tbody.append(r));
  };
  search?.addEventListener('input', apply);
  [...selects, ...checks].forEach(({ el }) => el.addEventListener('change', apply));
  sort.addEventListener('change', reorder);
  reorder();
  apply();
}
