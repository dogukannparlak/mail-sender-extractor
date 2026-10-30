// --- Hesaplar ----------------------------------------------------------------

const ACCOUNT_STORAGE_KEY = 'mail-temizleyici-hesap';

function rememberAccount(account) {
  try { localStorage.setItem(ACCOUNT_STORAGE_KEY, account); } catch (err) { /* gizli pencere: hatırlamasak da olur */ }
}

function rememberedAccount() {
  try { return localStorage.getItem(ACCOUNT_STORAGE_KEY); } catch (err) { return null; }
}

function renderAccounts() {
  const select = $('accountSelect');
  select.replaceChildren(...state.accounts.map(a => el('option', { value: a }, a)));
  select.value = state.account || '';
  select.hidden = state.accounts.length === 0;
  $('accountLabel').hidden = select.hidden;
  $('removeAccountBtn').hidden = state.accounts.length === 0;
  $('scanBtn').disabled = state.busy || !state.account;
  $('fullScanBtn').disabled = state.busy || !state.account;
  $('scanAllBtn').hidden = state.accounts.length < 2;
  $('scanAllBtn').disabled = state.busy;
  // Abonelikler, Bildirimler ve Günlük sayfaları seçili hesabın verisini gösterir.
  for (const link of document.querySelectorAll('.log-link[data-page]')) {
    link.href = `/${link.dataset.page}` + (state.account ? '?account=' + encodeURIComponent(state.account) : '');
  }
  if (state.account) refreshNotificationBadge();
}

async function loadAccounts(preferred = null) {
  const info = await api('/api/accounts');
  state.accounts = info.accounts;
  state.pending = info.pending || [];
  state.sharedClient = Boolean(info.shared_client);
  state.demo = Boolean(info.demo);
  if (info.migrated) notify(`Eski tek hesaplı kayıtlar ${info.migrated} hesabına taşındı.`);
  const wanted = [preferred, state.account, rememberedAccount()].find(a => a && state.accounts.includes(a));
  await switchAccount(wanted || state.accounts[0] || null);
}

// Hesap değişince her şey sıfırlanır: seçim, önizlemeler, açık paneller başka hesaba aittir.
async function switchAccount(account) {
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
      el('p', {}, 'Henüz bir Gmail hesabı eklenmedi.'),
      el('button', { type: 'button', onclick: addAccount }, 'Hesap ekle'),
    ));
    updateSelection();
    return;
  }
  rememberAccount(account);
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
    el('p', {}, el('strong', {}, 'Girişi bekleyen hesaplar'),
       ' (klasörüne istemci dosyası konmuş, henüz giriş yapılmamış):'),
    ...state.pending.map(account => el('p', {},
      el('button', { type: 'button', class: 'secondary-btn', onclick: () => {
        dialog.close();
        signIn({ pending: account }, account);
      } }, `${account} için giriş yap`))),
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
    throw new Error('Seçilen dosya JSON değil; Google Cloud\'dan indirdiğin client_secret_….json dosyasını seç.');
  }
}

// Giriş sunucuda arka planda bekler. Google sayfası tarayıcıda kendiliğinden açılmazsa
// aynı adres burada tıklanabilir link olarak durur.
function showSignInLink(url, expected) {
  notify(`Google giriş sayfası açılmadıysa linke tıkla, ${expected || 'eklemek istediğin hesabı'} seç ve izin ver. Bitince buraya dön.`, {
    action: { label: 'Google giriş sayfasını aç', onclick: () => window.open(url, '_blank', 'noopener') },
  });
}

async function signIn(payload, expected = null) {
  setBusy(true);
  notify('Google giriş sayfası hazırlanıyor…');
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
        notify(`${status.account} eklendi. "Gelen Kutusunu Tara" ile başla.`);
        setBusy(false);
        await loadAccounts(status.account);
        return;
      }
      if (status.state === 'error') throw new Error(status.error);
      await new Promise(r => setTimeout(r, 1000));
    }
  } catch (err) {
    notifyError('Hesap eklenemedi', err);
    setBusy(false);
  }
}

async function removeAccount() {
  const account = state.account;
  const ok = await confirmDialog({
    title: `${account} çıkarılsın mı?`,
    lines: [
      'Bu bilgisayardaki giriş anahtarı (token) silinir; maillerine dokunulmaz.',
      'Taranan liste ve son taşıma kaydı klasörde kalır; hesabı yeniden eklersen geri gelir.',
      "Uygulamanın Google'daki iznini tamamen kaldırmak için: myaccount.google.com/permissions",
    ],
    confirmLabel: 'Hesabı çıkar',
  });
  if (!ok) return;
  try {
    await api('/api/accounts/remove', {});
    notify(`${account} çıkarıldı.`);
    state.account = null;
    await loadAccounts();
  } catch (err) {
    notifyError('Hesap çıkarılamadı', err);
  }
}

