// --- Tarama ------------------------------------------------------------------

function showScanProgress(scan) {
  const pct = scan.total ? Math.floor(scan.processed / scan.total * 100) : 0;
  $('scanBtn').textContent = scan.total ? t('scan.running_pct', { pct }) : t('scan.running');
  const box = $('notice');
  let progress = box.querySelector('progress');
  // İlerleme çubuğu bir kez kurulur; her yoklamada yalnız değeri değişir (ekran okuyucu her seferinde baştan okumasın).
  if (!progress) {
    box.classList.remove('error');
    box.replaceChildren(el('span', { class: 'notice-text', id: 'scanText' }),
      el('progress', { max: '1', value: '0', 'aria-label': t('scan.progress_label') }));
    progress = box.querySelector('progress');
  }
  progress.max = scan.total || 1;
  progress.value = scan.processed;
  let text = t('scan.listing');
  if (scan.total) {
    text = t('scan.progress', { processed: scan.processed, total: scan.total, pct });
    const elapsed = scan.started_at ? Date.now() / 1000 - scan.started_at : 0;
    if (scan.processed > 0 && elapsed > 5) {
      text += ' ' + t('scan.remaining', { time: formatDuration((scan.total - scan.processed) * elapsed / scan.processed) });
    }
    text += ' ' + t('scan.quota_note');
  }
  $('scanText').textContent = text;
}

// Tarama sunucuda arka planda sürer; bitene kadar durumu yokla.
// İptal düğmesi: tarama sürerken görünür. all=true → bütün hesapların taraması.
let cancelAll = false;

function showCancel(all) {
  cancelAll = all;
  $('cancelScanBtn').textContent = t('scan.cancel');
  $('cancelScanBtn').disabled = false;
  $('cancelScanBtn').hidden = false;
}

function hideCancel() {
  $('cancelScanBtn').hidden = true;
}

async function cancelScan() {
  $('cancelScanBtn').disabled = true;
  $('cancelScanBtn').textContent = t('scan.cancelling');
  try {
    await api(cancelAll ? '/api/scan/cancel/all' : '/api/scan/cancel', {});
  } catch (err) {
    notifyError(t('scan.failed'), err);
    $('cancelScanBtn').disabled = false;
    $('cancelScanBtn').textContent = t('scan.cancel');
  }
}

async function pollScan() {
  const account = state.account;
  setBusy(true);
  showCancel(false);
  try {
    while (state.account === account) {
      const scan = await api('/api/scan/status');
      if (!scan.running) {
        if (scan.error) throw new Error(scan.error);
        if (scan.cancelled) { notify(t('scan.cancelled')); return; }
        await load();
        refreshNotificationBadge();
        notify(t('scan.done', { mails: tn('unit.mail', state.data.toplam_mail_sayisi), senders: tn('unit.sender', state.data.gonderenler.length) }));
        return;
      }
      showScanProgress(scan);
      await new Promise(r => setTimeout(r, 1000));
    }
  } catch (err) {
    notifyError(t('scan.failed'), err);
  } finally {
    hideCancel();
    $('scanBtn').textContent = t('scan.start');
    setBusy(false);
  }
}

async function refreshNotificationBadge() {
  try {
    const { unread } = await api('/api/notifications/unread');
    $('notifCount').textContent = unread;
    $('notifCount').hidden = !unread;
  } catch (err) { /* rozet yenilenemezse sayfa yenilenince güncellenir */ }
}

// Bildirimler başka sekmede okunmuş olabilir; ana sayfaya dönünce rozet tazelensin.
document.addEventListener('visibilitychange', () => { if (!document.hidden && state.account) refreshNotificationBadge(); });

async function scanInbox(full = false) {
  try {
    showScanProgress(await api('/api/scan', { full }));
  } catch (err) {
    // 409: başka bir sekmede başlamış tarama; onu izlemeye devam et.
    if (!(err.status === 409 && err.body?.running)) {
      notifyError(t('scan.start_failed'), err);
      return;
    }
  }
  await pollScan();
}

// Bütün hesapların taramasını izler; hesap başına bir ilerleme çubuğu. seen: izlenecek hesaplar.
function showAllScanProgress(list) {
  const box = $('notice');
  box.classList.remove('error');
  let wrap = box.querySelector('.all-scan');
  if (!wrap) {
    wrap = el('div', { class: 'all-scan' });
    box.replaceChildren(wrap);
  }
  for (const s of list) {
    let row = [...wrap.children].find(r => r.dataset.account === s.account);
    if (!row) {
      row = el('div', { class: 'all-scan-row', 'data-account': s.account },
        el('span', { class: 'all-scan-text' }),
        el('progress', { max: '1', value: '0', 'aria-label': t('scan.account_progress_label', { account: s.account }) }));
      wrap.append(row);
    }
    const pct = s.total ? Math.floor(s.processed / s.total * 100) : 0;
    const progress = row.querySelector('progress');
    progress.max = s.total || 1;
    progress.value = s.processed;
    row.querySelector('.all-scan-text').textContent = s.error ? t('scan.account_error', { account: s.account }) :
      s.running ? t('scan.account_progress', { account: s.account, processed: s.processed, total: s.total || '…', pct }) :
      t('scan.account_done', { account: s.account });
  }
}

async function pollAllScans(seen) {
  setBusy(true);
  showCancel(true);
  $('scanAllBtn').textContent = t('scan.running');
  try {
    for (;;) {
      const { accounts } = await api('/api/scan/status/all');
      for (const a of accounts) if (a.running) seen.add(a.account);
      const mine = accounts.filter(a => seen.has(a.account));
      showAllScanProgress(mine);
      if (!mine.some(a => a.running)) {
        const failed = mine.filter(a => a.error);
        const cancelled = mine.filter(a => a.cancelled);
        await load();
        refreshNotificationBadge();
        if (cancelled.length) {
          notify(t('scan.all_cancelled'), { details: cancelled.map(a => a.account) });
        } else if (failed.length) {
          notify(tn('scan.all_failed', failed.length), {
            error: true, details: failed.map(a => `${a.account}: ${a.error}`) });
        } else {
          notify(tn('scan.all_done', mine.length));
        }
        return;
      }
      await new Promise(r => setTimeout(r, 1000));
    }
  } catch (err) {
    notifyError(t('scan.failed'), err);
  } finally {
    hideCancel();
    $('scanAllBtn').textContent = t('scan.all');
    setBusy(false);
  }
}

async function scanAllAccounts(full = false) {
  try {
    const { accounts } = await api('/api/scan/all', { full });
    const errors = accounts.filter(a => !a.started && !a.already_running);
    if (errors.length === accounts.length) {
      notify(t('scan.none_started'), { error: true, details: errors.map(a => `${a.account}: ${a.error}`) });
      return;
    }
    await pollAllScans(new Set(accounts.filter(a => a.started).map(a => a.account)));
  } catch (err) {
    notifyError(t('scan.all_start_failed'), err);
  }
}

async function resumeScanIfRunning() {
  try {
    const { accounts } = await api('/api/scan/status/all');
    if (accounts.some(a => a.running)) pollAllScans(new Set());
  } catch (err) { /* durum alınamazsa sayfa normal açılır */ }
}


// "Yeni bir şey var mı?": bütün hesaplarda yalnız id listesine bakar; hiçbir şey okunmaz ya da yazılmaz.
async function checkForNew() {
  setBusy(true);
  $('checkNewBtn').textContent = t('scan.checking');
  try {
    const { accounts } = await api('/api/scan/check', {});
    const failed = accounts.filter(a => a.error);
    const found = accounts.filter(a => !a.error && !a.running && (a.new > 0 || !a.scanned));
    const details = [
      ...found.map(a => a.scanned ? t('scan.check_account_new', { account: a.account, count: tn('unit.mail', a.new) })
                                  : t('scan.check_account_never', { account: a.account })),
      ...failed.map(a => `${a.account}: ${a.error}`),
    ];
    if (found.length) {
      notify(tn('scan.check_found', found.length), {
        error: failed.length > 0, details,
        action: { label: t('scan.check_scan_now'), onclick: () => scanAllAccounts() },
      });
    } else if (failed.length) {
      notify(t('scan.check_failed'), { error: true, details });
    } else {
      notify(t('scan.check_none'));
    }
  } catch (err) {
    notifyError(t('scan.check_failed'), err);
  } finally {
    $('checkNewBtn').textContent = t('scan.check');
    setBusy(false);
  }
}
