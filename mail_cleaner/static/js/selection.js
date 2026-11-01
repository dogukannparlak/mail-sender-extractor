// --- Seçim -------------------------------------------------------------------

function getSelected() {
  return state.data ? state.data.gonderenler.filter(g => state.selected.has(g.gonderen)) : [];
}

function visibleCheckboxes() {
  return [...document.querySelectorAll('.sender-checkbox:not(:disabled)')];
}

function updateSelection() {
  const picked = getSelected();
  const totalMail = picked.reduce((sum, g) => sum + g.mail_sayisi, 0);
  // Filtre değişince önceki seçimler gizli kalabilir; işleme girdiklerini açıkça göster.
  const hidden = picked.filter(g => !passesFilters(g)).length;
  // Birden fazla hesap varsa işlem çubuğu hangi hesapta olduğunu da söyler (başlık telefonda yukarıda kalır).
  $('selectedInfo').textContent =
    (state.accounts.length > 1 && state.account ? `${state.account} · ` : '') +
    (picked.length ? t('select.picked', { senders: tn('unit.sender', picked.length), mails: tn('unit.mail', totalMail) }) : t('select.none')) +
    (hidden ? ' · ' + t('select.hidden_by_filter', { count: hidden }) : '');
  $('deleteBtn').disabled = state.busy || picked.length === 0;
  const unsubscribable = picked.filter(canUnsubscribe);
  $('unsubBtn').disabled = state.busy || unsubscribable.length === 0;
  $('unsubBtn').title = picked.length && !unsubscribable.length ? t('select.no_links') : '';

  // Çıkılmış (otomatik ya da elle işaretli) gönderenler her zaman tek tuşla çöpe taşınabilir; yoksa pasif.
  const exited = exitedSenders();
  $('trashUnsubBtn').disabled = state.busy || exited.length === 0;
  $('trashUnsubBtn').textContent = t('unsub.trash_button', { count: exited.length });

  const boxes = visibleCheckboxes();
  const filtered = state.searchText || state.categoryFilters.length || state.linkFilter;
  $('selectAllLabel').textContent = `${filtered ? t('select.visible') : t('select.all')} (${boxes.length})`;
  $('selectAll').checked = boxes.length > 0 && boxes.every(b => b.checked);
  $('selectAll').indeterminate = boxes.some(b => b.checked || b.indeterminate) && !$('selectAll').checked;
  // Açık alan adı listelerindeki adres kutuları gruptaki/üstteki seçimle eşit kalsın.
  document.querySelectorAll('.member-checkbox').forEach(c => { c.checked = state.selected.has(c.dataset.address); });
}

function setBusy(busy) {
  state.busy = busy;
  $('undoBtn').disabled = busy;
  $('scanBtn').disabled = busy || !state.account;
  $('fullScanBtn').disabled = busy || !state.account;
  $('scanAllBtn').disabled = busy;
  // İşlem sürerken hesap değiştirilemez: sonuç yanlış hesabın ekranına yazılmasın.
  $('accountSelect').disabled = busy;
  $('addAccountBtn').disabled = busy;
  $('removeAccountBtn').disabled = busy;
  updateSelection();
}

