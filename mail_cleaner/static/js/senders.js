// --- Veri ve liste -----------------------------------------------------------

function passesFilters(g) {
  if (state.categoryFilter && g.kategori !== state.categoryFilter) return false;
  if (state.linkFilter === 'with' && !g.baglanti) return false;
  if (state.linkFilter === 'without' && g.baglanti) return false;
  if (state.searchText) {
    const haystack = `${g.ad} ${g.gonderen}`.toLocaleLowerCase(window.LANG);
    if (!haystack.includes(state.searchText)) return false;
  }
  return true;
}

// Ekrandaki satırlar: adres görünümünde gönderen başına, alan adı görünümünde alan adı başına bir satır.
function buildRows() {
  const visible = state.data.gonderenler.filter(passesFilters);
  if (state.viewMode === 'address') {
    return visible.map(g => ({
      key: g.gonderen, label: g.ad || g.gonderen, sub: g.ad ? g.gonderen : '',
      count: g.mail_sayisi, members: [g], single: true,
    }));
  }
  const groups = new Map();
  visible.forEach(g => {
    const domain = domainOf(g.gonderen);
    if (!groups.has(domain)) groups.set(domain, []);
    groups.get(domain).push(g);
  });
  return [...groups].map(([domain, members]) => ({
    key: '@' + domain, label: domain, sub: tn('unit.address', members.length),
    count: members.reduce((sum, g) => sum + g.mail_sayisi, 0), members, single: false,
  }));
}

function sortedRows() {
  const rows = buildRows();
  rows.sort((a, b) => {
    if (state.sortMode === 'name_asc') return a.label.localeCompare(b.label, window.LANG);
    if (state.sortMode === 'name_desc') return b.label.localeCompare(a.label, window.LANG);
    if (state.sortMode === 'members_desc' || state.sortMode === 'members_asc') {
      const byMembers = a.members.length - b.members.length || a.count - b.count;
      return state.sortMode === 'members_asc' ? byMembers : -byMembers;
    }
    const diff = a.count - b.count;
    return state.sortMode === 'count_asc' ? diff : -diff;
  });
  return rows;
}

function setData(body) {
  state.data = body;
  const known = new Set(state.data.gonderenler.map(g => g.gonderen));
  [...state.selected].forEach(key => {
    if (!known.has(key) || isProtected(key)) state.selected.delete(key);
  });
  render();
}

async function load() {
  try {
    const [senders, protectedList] = await Promise.all([api('/api/senders'), api('/api/protected')]);
    state.protectedList = protectedList;
    setData(senders);
  } catch (err) {
    $('senders').replaceChildren(el('div', { class: 'empty-state' },
      el('p', {}, t('list.load_failed', { message: err.message })),
      el('button', { type: 'button', class: 'secondary-btn', onclick: load }, t('common.retry')),
    ));
  }
}

// Liste yeniden çizilince odak kaybolmasın: aynı satırın aynı butonuna geri ver.
function rememberFocus() {
  const active = document.activeElement;
  const row = active?.closest?.('.sender-row');
  return row ? { key: row.dataset.key, role: active.dataset.role } : null;
}

function restoreFocus(focus) {
  if (!focus) return;
  const row = [...document.querySelectorAll('.sender-row')].find(r => r.dataset.key === focus.key);
  row?.querySelector(`[data-role="${focus.role}"]`)?.focus();
}

function render() {
  const focus = rememberFocus();
  const data = state.data;
  $('grandTotal').textContent = t('list.total', { mails: tn('unit.mail', data.toplam_mail_sayisi), senders: tn('unit.sender', data.gonderenler.length) });
  // Kategori ve abonelik bilgisi yalnız yeni taramada toplanır; eski kayıtta filtreleri gösterme.
  $('categoryFilterWrap').hidden = !data.gonderenler.some(g => g.kategori);
  $('unsubFilterWrap').hidden = !data.gonderenler.some(g => 'baglanti' in g);

  const container = $('senders');
  if (!data.gonderenler.length) {
    container.replaceChildren(el('p', { class: 'empty-state' },
      t('list.empty')));
    updateSelection();
    return;
  }

  const rows = sortedRows();
  if (!rows.length) {
    container.replaceChildren(el('div', { class: 'empty-state' },
      el('p', {}, t('list.no_match')),
      el('button', { type: 'button', class: 'secondary-btn', onclick: clearFilters }, t('list.clear_filters')),
    ));
    updateSelection();
    return;
  }

  container.replaceChildren(el('div', { class: 'sender-list' }, rows.map(createRow)));
  updateSelection();
  restoreFocus(focus);
}

function createRow(rowData) {
  const { single, members } = rowData;
  const g = members[0];
  // Alan adı satırında korunan adresler seçime girmez; satır yalnız hepsi korunuyorsa kapanır.
  const selectable = members.filter(m => !isProtected(m.gonderen));
  const allLocked = selectable.length === 0;
  // Alan adı satırının kilidi alan adını, adres satırınınki yalnız adresi korur.
  const lockValue = single ? g.gonderen : rowData.key;
  const locked = single ? isProtected(g.gonderen) : state.protectedList.alanlar.includes(rowData.key);

  const checkbox = el('input', {
    type: 'checkbox', class: 'sender-checkbox', 'data-role': 'select',
    'aria-label': t('row.select_aria', { name: rowData.label }), disabled: allLocked,
    title: allLocked ? t('row.locked_title') : null,
    onchange: () => {
      selectable.forEach(m => checkbox.checked ? state.selected.add(m.gonderen) : state.selected.delete(m.gonderen));
      updateSelection();  // açık adres listesindeki kutuları da eşitler
    },
  });
  checkbox.rowMembers = selectable;

  const panel = el('div', { class: 'sender-preview', id: `panel-${rowData.key.replace(/[^a-zA-Z0-9_-]/g, '_')}` });
  const previewBtn = el('button', {
    type: 'button', class: 'small-btn', 'data-role': 'preview',
    'aria-expanded': 'false', 'aria-controls': panel.id,
    'aria-label': t(single ? 'row.preview_aria' : 'row.show_addresses_aria', { name: rowData.label }),
    onclick: () => togglePanel(rowData, panel, previewBtn),
  }, single ? t('row.preview') : t('row.addresses'));

  const copyText = single ? g.gonderen : domainOf(g.gonderen);
  const copyBtn = el('button', {
    type: 'button', class: 'small-btn copy-btn', 'data-role': 'copy',
    'aria-label': t('row.copy_aria', { text: copyText }), onclick: () => copyToClipboard(copyText, copyBtn),
  }, t('row.copy'));

  const lockBtn = el('button', {
    type: 'button', class: 'small-btn lock-btn', 'data-role': 'lock', 'aria-pressed': String(locked),
    title: locked ? t('row.protect_remove_title') : t('row.protect_title'),
    onclick: () => toggleProtected(lockValue, !locked, lockBtn),
  }, el('span', { 'aria-hidden': 'true' }, locked ? '🔒 ' : '🔓 '), locked ? t('row.protected') : t('row.protect'));

  const unsubResult = el('span', { class: 'unsub-result', 'data-result-for': single ? g.gonderen : null });
  const unsubBtn = single && canUnsubscribe(g) && el('button', {
    type: 'button', class: 'small-btn danger unsub-btn', 'data-role': 'unsub', disabled: allLocked,
    'aria-label': t('row.unsubscribe_aria', { name: rowData.label }),
    onclick: () => unsubscribeRow(g.gonderen, unsubResult, unsubBtn),
  }, t('row.unsubscribe'));

  const badge = single && CATEGORY_LABELS[g.kategori]
    ? el('span', { class: `badge badge-${g.kategori}` }, CATEGORY_LABELS[g.kategori]) : null;
  const protectedCount = members.length - selectable.length;
  const protectedBadge = protectedCount
    ? el('span', { class: 'badge badge-protected' }, single ? t('row.protected') : t('row.protected_count', { count: protectedCount })) : null;

  const row = el('div', { class: 'sender-row' + (allLocked ? ' protected' : ''), 'data-key': rowData.key },
    checkbox,
    el('div', { class: 'sender-info', title: single && g.ad ? `${g.ad} <${g.gonderen}>` : rowData.key },
      el('span', { class: 'sender-name' }, rowData.label, badge, protectedBadge),
      rowData.sub ? el('span', { class: 'sender-email' }, rowData.sub) : null,
    ),
    el('span', { class: 'sender-count', 'aria-label': tn('unit.mail', rowData.count) }, rowData.count),
    el('div', { class: 'row-actions' }, previewBtn, copyBtn, lockBtn, unsubBtn, unsubResult),
  );
  syncRowCheckbox(checkbox);

  if (state.openPanels.has(rowData.key)) togglePanel(rowData, panel, previewBtn, true);
  return el('div', { class: 'sender-item' }, row, panel);
}

function syncRowCheckbox(checkbox) {
  const picked = checkbox.rowMembers.filter(m => state.selected.has(m.gonderen)).length;
  checkbox.checked = picked > 0 && picked === checkbox.rowMembers.length;
  checkbox.indeterminate = picked > 0 && !checkbox.checked;
}

function clearFilters() {
  state.searchText = '';
  state.categoryFilter = '';
  state.linkFilter = '';
  $('searchInput').value = '';
  $('categorySelect').value = '';
  $('linkFilter').value = '';
  render();
}

