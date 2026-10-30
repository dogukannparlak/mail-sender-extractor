// --- Abonelikten çıkma -------------------------------------------------------

function describeUnsubResult(r) {
  if (r.status === 'done') return t('unsub.result_done');
  if (r.status === 'manual_link') return t('unsub.result_link');
  if (r.status === 'manual_mailto') return t('unsub.result_mailto');
  if (r.status === 'not_found') return t('unsub.result_not_found');
  return t('unsub.result_none');
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
    r.status === 'manual_link' ? t('unsub.open_page') : t('unsub.send_mail')));
}

// Önce onaysız sorulur: sunucu hiçbir yere istek atmadan hangi gönderenlerde tek tıkla
// çıkış yapılabileceğini söyler. Kullanıcı onaylarsa yalnız onlar için tekrar istenir.
// Onay verilmezse o gönderenler için çıkış sayfası linki gösterilir.
async function unsubscribeWithConfirmation(senders) {
  const first = (await api('/api/unsubscribe', { senders, confirm_one_click: false })).results;
  const oneClick = first.filter(r => r.status === 'one_click_available');
  if (!oneClick.length) return first;

  const ok = await confirmDialog({
    title: t('unsub.confirm_title'),
    lines: [t('dialog.account', { account: state.account }),
            t('unsub.confirm_body', { senders: tn('unit.sender', oneClick.length) })],
    items: oneClick.map(r => r.email),
    confirmLabel: t('row.unsubscribe'),
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
  btn.textContent = t('unsub.checking');
  try {
    const [result] = await unsubscribeWithConfirmation([sender]);
    showUnsubResult(resultEl, result);
  } catch (err) {
    resultEl.textContent = t('common.error_prefix', { message: err.message });
  } finally {
    btn.disabled = false;
    btn.textContent = t('row.unsubscribe');
  }
}

async function unsubscribeSelected() {
  const picked = getSelected();
  const senders = picked.filter(canUnsubscribe).map(g => g.gonderen);
  const skipped = picked.length - senders.length;  // abonelik bağlantısı olmayanlar atlanır
  setBusy(true);
  $('unsubBtn').textContent = t('unsub.checking');
  notify(t('unsub.checking_senders', { senders: tn('unit.sender', senders.length) }) +
    (skipped ? ' ' + t('unsub.skipped_no_link', { senders: tn('unit.sender', skipped) }) : ''));
  try {
    const results = await unsubscribeWithConfirmation(senders);
    showUnsubResultsInRows(results);
    const done = results.filter(r => r.status === 'done').length;
    const links = results.filter(r => r.status === 'manual_link' || r.status === 'manual_mailto').length;
    notify(t('unsub.summary_done', { senders: tn('unit.sender', done) }) +
      (links ? t('unsub.summary_links', { senders: tn('unit.sender', links) }) : '.'),
      { details: results.map(r => `${r.email}: ${describeUnsubResult(r)}`) });
  } catch (err) {
    notifyError(t('unsub.failed'), err);
  } finally {
    $('unsubBtn').textContent = UNSUB_LABEL;
    setBusy(false);
  }
}

