// --- Abonelikten çıkma -------------------------------------------------------

function describeUnsubResult(r) {
  if (r.status === 'done') return '✅ Otomatik olarak çıkıldı';
  if (r.status === 'manual_link') return '🔗 Çıkış sayfası var';
  if (r.status === 'manual_mailto') return '✉️ Çıkış maili adresi var';
  if (r.status === 'not_found') return 'Bu gönderenden mail bulunamadı';
  return 'Abonelik linki yok';
}

// Link, fetch'ten sonra window.open ile açılırsa popup engelleyicisine takılır;
// bunun yerine kullanıcının tıklayacağı bir bağlantı gösteriyoruz.
function showUnsubResult(resultEl, r) {
  const isLink = (r.status === 'manual_link' || r.status === 'manual_mailto') && /^(https?:|mailto:)/i.test(r.url || '');
  if (!isLink) {
    resultEl.textContent = describeUnsubResult(r);
    return;
  }
  resultEl.replaceChildren(el('a', { href: r.url, target: '_blank', rel: 'noopener noreferrer' },
    r.status === 'manual_link' ? '🔗 Çıkış sayfasını aç' : '✉️ Çıkış maili gönder'));
}

// Önce onaysız sorulur: sunucu hiçbir yere istek atmadan hangi gönderenlerde tek tıkla
// çıkış yapılabileceğini söyler. Kullanıcı onaylarsa yalnız onlar için tekrar istenir.
// Onay verilmezse o gönderenler için çıkış sayfası linki gösterilir.
async function unsubscribeWithConfirmation(senders) {
  const first = (await api('/api/unsubscribe', { senders, confirm_one_click: false })).results;
  const oneClick = first.filter(r => r.status === 'one_click_available');
  if (!oneClick.length) return first;

  const ok = await confirmDialog({
    title: 'Tek tıkla abonelikten çıkılsın mı?',
    lines: [`Hesap: ${state.account}`,
            `${oneClick.length} gönderenden otomatik olarak çıkılacak. Bu işlem geri alınamaz.`],
    items: oneClick.map(r => r.email),
    confirmLabel: 'Abonelikten çık',
  });
  if (!ok) return first.map(r => r.status === 'one_click_available' ? { ...r, status: 'manual_link' } : r);

  const confirmed = (await api('/api/unsubscribe',
    { senders: oneClick.map(r => r.sender), confirm_one_click: true })).results;
  const bySender = new Map(confirmed.map(r => [r.sender, r]));
  return first.map(r => bySender.get(r.sender) || r);
}

function showUnsubResultsInRows(results) {
  results.forEach(r => {
    const target = document.querySelector(`.unsub-result[data-result-for="${CSS.escape(r.sender)}"]`);
    if (target) showUnsubResult(target, r);
  });
}

async function unsubscribeRow(sender, resultEl, btn) {
  btn.disabled = true;
  btn.textContent = 'Bakılıyor…';
  try {
    const [result] = await unsubscribeWithConfirmation([sender]);
    showUnsubResult(resultEl, result);
  } catch (err) {
    resultEl.textContent = `Hata: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Abonelikten çık';
  }
}

async function unsubscribeSelected() {
  const picked = getSelected();
  const senders = picked.filter(canUnsubscribe).map(g => g.gonderen);
  const skipped = picked.length - senders.length;  // abonelik bağlantısı olmayanlar atlanır
  setBusy(true);
  $('unsubBtn').textContent = 'Bakılıyor…';
  notify(`${senders.length} gönderen için abonelik bilgisi kontrol ediliyor…` +
    (skipped ? ` (${skipped} gönderende abonelik bağlantısı yok, atlandı)` : ''));
  try {
    const results = await unsubscribeWithConfirmation(senders);
    showUnsubResultsInRows(results);
    const done = results.filter(r => r.status === 'done').length;
    const links = results.filter(r => r.status === 'manual_link' || r.status === 'manual_mailto').length;
    notify(`${done} gönderenden otomatik çıkıldı` +
      (links ? `; ${links} gönderenin çıkış linki kendi satırında.` : '.'),
      { details: results.map(r => `${r.email}: ${describeUnsubResult(r)}`) });
  } catch (err) {
    notifyError('Abonelik işlemi yapılamadı', err);
  } finally {
    $('unsubBtn').textContent = UNSUB_LABEL;
    setBusy(false);
  }
}

