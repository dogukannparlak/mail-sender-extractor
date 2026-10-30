// --- Olaylar -----------------------------------------------------------------

$('scanBtn').addEventListener('click', () => scanInbox());
$('fullScanBtn').addEventListener('click', () => scanInbox(true));
$('scanAllBtn').addEventListener('click', scanAllAccounts);
$('deleteBtn').addEventListener('click', deleteSelected);
$('unsubBtn').addEventListener('click', unsubscribeSelected);
$('undoBtn').addEventListener('click', undoLastDelete);

$('searchInput').addEventListener('input', e => {
  state.searchText = e.target.value.trim().toLocaleLowerCase('tr');
  if (state.data) render();
});
$('linkFilter').addEventListener('change', e => {
  state.linkFilter = e.target.value;
  if (state.data) render();
});
$('categorySelect').addEventListener('change', e => {
  state.categoryFilter = e.target.value;
  if (state.data) render();
});
$('viewSelect').addEventListener('change', e => {
  state.viewMode = e.target.value;
  // "Adres sayısı" sıralaması yalnız alan adı görünümünde anlamlı: alan adı başına kaç adres var.
  const domainView = state.viewMode === 'domain';
  document.querySelectorAll('#sortSelect [data-domain-only]').forEach(o => { o.hidden = !domainView; o.disabled = !domainView; });
  if (!domainView && state.sortMode.startsWith('members_')) {
    state.sortMode = 'count_desc';
    $('sortSelect').value = 'count_desc';
  }
  state.openPanels.clear();
  if (state.data) render();
});
$('sortSelect').addEventListener('change', e => {
  state.sortMode = e.target.value;
  if (state.data) render();
});
// Kapsam değişince önizlemeler yeni kapsamla yeniden yüklensin; açık paneller açık kalır.
$('scopeSelect').addEventListener('change', e => {
  state.scope = e.target.value;
  state.previewCache.clear();
  if (state.data) render();
});

// Yalnız ekranda görünen (ve korunmayan) satırları seçer ya da bırakır.
$('selectAll').addEventListener('change', e => {
  const checked = e.target.checked;
  visibleCheckboxes().forEach(cb => {
    cb.rowMembers.forEach(m => checked ? state.selected.add(m.gonderen) : state.selected.delete(m.gonderen));
    syncRowCheckbox(cb);
  });
  updateSelection();
});

$('accountSelect').addEventListener('change', e => switchAccount(e.target.value));
$('addAccountBtn').addEventListener('click', addAccount);
$('clientFileInput').addEventListener('change', async e => {
  const file = e.target.files[0];
  if (!file) return;
  $('addAccountDialog').close();
  try {
    await signIn({ client: await readClientFile(file) });
  } catch (err) {
    notifyError('Hesap eklenemedi', err);
  }
});
$('useSharedClientBtn').addEventListener('click', () => {
  $('addAccountDialog').close();
  signIn({});
});
$('removeAccountBtn').addEventListener('click', removeAccount);

loadAccounts().catch(err => notifyError('Hesaplar yüklenemedi', err));
