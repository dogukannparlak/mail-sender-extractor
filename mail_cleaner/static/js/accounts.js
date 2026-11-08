// --- Hesaplar ----------------------------------------------------------------

// Etkin hesap sunucuda tutulur: ana sayfa, alt sayfalar ve açık bütün sekmeler aynı hesabı gösterir (bkz. app.js).
window.currentAccount = () => state.account;
window.onActiveAccountChanged = account => { if (!state.busy) switchAccount(account, false); };

function renderAccounts() {
  const select = $('accountSelect');
  select.replaceChildren(...state.accounts.map(a => el('option', { value: a }, a)));
  select.value = state.account || '';
  select.hidden = state.accounts.length === 0;
  $('accountLabel').hidden = select.hidden;
  $('removeAccountBtn').hidden = state.accounts.length === 0;
  $('reauthBtn').hidden = !state.account;
  $('scanBtn').disabled = state.busy || !state.account;
  $('fullScanBtn').disabled = state.busy || !state.account;
  $('scanAllBtn').hidden = state.accounts.length < 2;
  $('scanAllBtn').disabled = state.busy;
  $('fullScanAllBtn').hidden = state.accounts.length < 2;
  $('fullScanAllBtn').disabled = state.busy;
  $('checkNewBtn').disabled = state.busy || !state.account;
  // Abonelikler, Bildirimler ve Günlük sayfaları seçili hesabın verisini gösterir.
  for (const link of document.querySelectorAll('.log-link[data-page]')) {
    link.href = `/${link.dataset.page}`;
  }
  if (state.account) refreshNotificationBadge();
}

async function loadAccounts(preferred = null) {
  const info = await api('/api/accounts');
  state.accounts = info.accounts;
  state.pending = info.pending || [];
  state.sharedClient = Boolean(info.shared_client);
  state.demo = Boolean(info.demo);
  if (info.migrated) notify(t('account.migrated', { account: info.migrated }));
  const wanted = [preferred, state.account, info.active].find(a => a && state.accounts.includes(a));
  await switchAccount(wanted || state.accounts[0] || null);
}

// Hesap değişince her şey sıfırlanır: seçim, önizlemeler, açık paneller başka hesaba aittir.
async function switchAccount(account, publish = true) {
  state.account = account;
  state.data = null;
  state.selected.clear();
  state.previewCache.clear();
  state.openPanels.clear();
  clearNotice();  // önceki hesabın bildirimi (ör. "Tarama tamamlandı") yeni hesaba ait değil
  renderAccounts();
  if (!account) {
    $('grandTotal').textContent = '';
    $('undoBtn').hidden = true;
    $('senders').replaceChildren(el('div', { class: 'empty-state' },
      el('p', {}, t('account.none')),
      el('button', { type: 'button', onclick: addAccount }, t('account.add_short')),
    ));
    updateSelection();
    return;
  }
  if (publish) api('/api/active-account', { account }).catch(() => { /* kaydedilemese de bu pencere çalışır */ });
  await load();
  await refreshUndo();
  await resumeScanIfRunning();
}

// Hesap ekleme penceresi: istemci dosyası seç, girişi bekleyen bir klasörü bağla ya da (varsa) ortak istemciyi kullan.
function addAccount() {
  if (state.demo) return signIn({});  // sunucu demo'da hesap eklemeyi reddeder ve nedenini söyler
  const dialog = $('addAccountDialog');
  $('clientFileInput').value = '';
  $('pendingAccounts').replaceChildren(...(state.pending.length ? [
    el('p', {}, el('strong', {}, t('account.pending_title')), ' ' + t('account.pending_hint')),
    ...state.pending.map(account => el('p', {},
      el('button', { type: 'button', class: 'secondary-btn', onclick: () => {
        dialog.close();
        signIn({ pending: account }, account);
      } }, t('account.sign_in_for', { account })))),
  ] : []));
  $('sharedClientOption').hidden = !state.sharedClient;
  dialog.showModal();
  $('addAccountCancel').focus();
}

async function readClientFile(file) {
  const text = await file.text();
  try {
    return JSON.parse(text);
  } catch (err) {
    throw new Error(t('account.not_json'));
  }
}

// Giriş sunucuda arka planda bekler. Google sayfası tarayıcıda kendiliğinden açılmazsa
// aynı adres burada tıklanabilir link olarak durur.
function showSignInLink(url, expected) {
  notify(t('account.signin_link_hint', { account: expected || t('account.signin_any_account') }), {
    action: { label: t('account.signin_open'), onclick: () => window.open(url, '_blank', 'noopener') },
  });
}

async function signIn(payload, expected = null) {
  setBusy(true);
  notify(t('account.signin_preparing'));
  try {
    await api('/api/accounts/add', payload);
    let shownUrl = null;
    while (true) {
      const status = await api('/api/accounts/add/status');
      if (status.url && status.url !== shownUrl) {
        shownUrl = status.url;
        showSignInLink(status.url, expected || status.expected);
      }
      if (status.state === 'done') {
        notify(t('account.added', { account: status.account }));
        setBusy(false);
        await loadAccounts(status.account);
        return;
      }
      if (status.state === 'error') throw new Error(status.error);
      await new Promise(r => setTimeout(r, 1000));
    }
  } catch (err) {
    notifyError(t('account.add_failed'), err);
    setBusy(false);
  }
}

async function removeAccount() {
  const account = state.account;
  const ok = await confirmDialog({
    title: t('account.remove_title', { account }),
    lines: [t('account.remove_line1'), t('account.remove_line2'), t('account.remove_line3')],
    confirmLabel: t('account.remove'),
  });
  if (!ok) return;
  try {
    await api('/api/accounts/remove', {});
    notify(t('account.removed', { account }));
    state.account = null;
    await loadAccounts();
  } catch (err) {
    notifyError(t('account.remove_failed'), err);
  }
}

