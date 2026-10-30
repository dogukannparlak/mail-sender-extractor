// --- Tarama ------------------------------------------------------------------

function showScanProgress(scan) {
  const pct = scan.total ? Math.floor(scan.processed / scan.total * 100) : 0;
  $('scanBtn').textContent = scan.total ? `Taranıyor %${pct}` : 'Taranıyor…';
  const box = $('notice');
  let progress = box.querySelector('progress');
  // İlerleme çubuğu bir kez kurulur; her yoklamada yalnız değeri değişir (ekran okuyucu her seferinde baştan okumasın).
  if (!progress) {
    box.classList.remove('error');
    box.replaceChildren(el('span', { class: 'notice-text', id: 'scanText' }),
      el('progress', { max: '1', value: '0', 'aria-label': 'Tarama ilerlemesi' }));
    progress = box.querySelector('progress');
  }
  progress.max = scan.total || 1;
  progress.value = scan.processed;
  let text = 'Gelen kutusu, spam ve arşivdeki mailler listeleniyor…';
  if (scan.total) {
    text = `${scan.processed} / ${scan.total} mail tarandı (%${pct}).`;
    const elapsed = scan.started_at ? Date.now() / 1000 - scan.started_at : 0;
    if (scan.processed > 0 && elapsed > 5) {
      text += ` Kalan süre ${formatDuration((scan.total - scan.processed) * elapsed / scan.processed)}.`;
    }
    text += ' Gmail dakikada en fazla ~300 mail okumaya izin veriyor.';
  }
  $('scanText').textContent = text;
}

// Tarama sunucuda arka planda sürer; bitene kadar durumu yokla.
async function pollScan() {
  const account = state.account;
  setBusy(true);
  try {
    while (state.account === account) {
      const scan = await api('/api/scan/status');
      if (!scan.running) {
        if (scan.error) throw new Error(scan.error);
        await load();
        refreshNotificationBadge();
        notify(`Tarama tamamlandı: ${state.data.toplam_mail_sayisi} mail, ${state.data.gonderenler.length} gönderen.`);
        return;
      }
      showScanProgress(scan);
      await new Promise(r => setTimeout(r, 1000));
    }
  } catch (err) {
    notifyError('Tarama sırasında hata oluştu', err);
  } finally {
    $('scanBtn').textContent = 'Gelen Kutusunu Tara';
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

async function scanInbox(full = false) {
  try {
    showScanProgress(await api('/api/scan', { full }));
  } catch (err) {
    // 409: başka bir sekmede başlamış tarama; onu izlemeye devam et.
    if (!(err.status === 409 && err.body?.running)) {
      notifyError('Tarama başlatılamadı', err);
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
        el('progress', { max: '1', value: '0', 'aria-label': `${s.account} tarama ilerlemesi` }));
      wrap.append(row);
    }
    const pct = s.total ? Math.floor(s.processed / s.total * 100) : 0;
    const progress = row.querySelector('progress');
    progress.max = s.total || 1;
    progress.value = s.processed;
    row.querySelector('.all-scan-text').textContent = s.error ? `${s.account}: hata` :
      s.running ? `${s.account}: ${s.processed} / ${s.total || '…'} (%${pct})` : `${s.account}: tamamlandı`;
  }
}

async function pollAllScans(seen) {
  setBusy(true);
  $('scanAllBtn').textContent = 'Taranıyor…';
  try {
    for (;;) {
      const { accounts } = await api('/api/scan/status/all');
      for (const a of accounts) if (a.running) seen.add(a.account);
      const mine = accounts.filter(a => seen.has(a.account));
      showAllScanProgress(mine);
      if (!mine.some(a => a.running)) {
        const failed = mine.filter(a => a.error);
        await load();
        refreshNotificationBadge();
        if (failed.length) {
          notify(`Tarama bitti, ${failed.length} hesapta hata var.`, {
            error: true, details: failed.map(a => `${a.account}: ${a.error}`) });
        } else {
          notify(`${mine.length} hesabın taraması tamamlandı.`);
        }
        return;
      }
      await new Promise(r => setTimeout(r, 1000));
    }
  } catch (err) {
    notifyError('Tarama sırasında hata oluştu', err);
  } finally {
    $('scanAllBtn').textContent = 'Tüm hesapları tara';
    setBusy(false);
  }
}

async function scanAllAccounts() {
  try {
    const { accounts } = await api('/api/scan/all', {});
    const errors = accounts.filter(a => !a.started && !/zaten sürüyor/.test(a.error || ''));
    if (errors.length === accounts.length) {
      notify('Hiçbir hesabın taraması başlatılamadı.', { error: true, details: errors.map(a => `${a.account}: ${a.error}`) });
      return;
    }
    await pollAllScans(new Set(accounts.filter(a => a.started).map(a => a.account)));
  } catch (err) {
    notifyError('Taramalar başlatılamadı', err);
  }
}

async function resumeScanIfRunning() {
  try {
    const { accounts } = await api('/api/scan/status/all');
    if (accounts.some(a => a.running)) pollAllScans(new Set());
  } catch (err) { /* durum alınamazsa sayfa normal açılır */ }
}

