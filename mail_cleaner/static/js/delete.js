// --- Çöp Kutusu'na taşıma ve geri alma ---------------------------------------

async function deleteSelected() {
  const picked = getSelected();
  const senders = picked.map(g => g.gonderen);
  const hidden = picked.filter(g => !passesFilters(g)).length;
  setBusy(true);
  try {
    // Taramadaki sayı gelen kutusu, arşiv ve spam'i sayar; onayda seçilen kapsamın gerçek sayısı görünsün.
    $('deleteBtn').textContent = 'Sayılıyor…';
    const count = await api('/api/count', { senders, scope: state.scope });
    const skipped = count.details.reduce((sum, d) => sum + (d.skipped || 0), 0);
    const scopeText = state.scope === 'all' ? 'tüm maillerde (arşiv ve spam dahil)' : 'gelen kutusunda';

    const ok = await confirmDialog({
      title: `${count.total} mail Çöp Kutusu'na taşınsın mı?`,
      lines: [
        `Hesap: ${state.account}`,
        `${picked.length} gönderenden ${scopeText} bulunan ${count.total} mail taşınacak. 30 gün içinde geri alabilirsin.`,
        skipped ? `${skipped} mail atlandı: gönderen adresi tam eşleşmiyor ya da gönderen korunuyor.` : null,
      ].filter(Boolean),
      items: count.details.map(d => `${d.email} · ${d.count} mail`),
      warning: hidden ? `${hidden} seçili gönderen şu an filtre yüzünden görünmüyor; onlar da taşınacak.` : '',
      confirmLabel: "Çöp Kutusu'na taşı",
    });
    if (!ok) return;

    $('deleteBtn').textContent = 'Taşınıyor…';
    notify('Taşınıyor; bu sekmeyi kapatma…');
    const result = await api('/api/delete', { senders, scope: state.scope });

    const removed = new Set(result.details.map(d => d.sender));
    const remaining = state.data.gonderenler.filter(g => !removed.has(g.gonderen));
    setData({ toplam_mail_sayisi: remaining.reduce((sum, g) => sum + g.mail_sayisi, 0), gonderenler: remaining });
    await refreshUndo();
    notify(`${result.total_deleted} mail Çöp Kutusu'na taşındı (${result.account}).`, {
      details: result.details.map(d => `${d.email}: ${d.deleted} mail`),
      action: result.total_deleted ? { label: 'Geri al', onclick: undoLastDelete } : null,
    });
  } catch (err) {
    notifyError('Taşınamadı', err);
    // İşlem yarıda kesildiyse bir kısmı taşınmış olabilir: listeyi ve geri alma durumunu tazele.
    load();
    refreshUndo();
  } finally {
    $('deleteBtn').textContent = DELETE_LABEL;
    setBusy(false);
  }
}

async function refreshUndo() {
  const btn = $('undoBtn');
  try {
    const info = await api('/api/undo');
    btn.hidden = !info.available;
    if (info.available) {
      btn.textContent = `Son taşımayı geri al (${info.count} mail)`;
      btn.title = 'Gönderenler: ' + info.senders.join(', ');
    }
  } catch (err) {
    btn.hidden = true;  // geri alma bilgisi alınamazsa butonu göstermemek yeterli
  }
}

async function undoLastDelete() {
  setBusy(true);
  notify('Son taşıma geri alınıyor…');
  try {
    const result = await api('/api/undo', {});
    await load();
    notify(`${result.restored} mail Çöp Kutusu'ndan geri alındı.` +
      (result.missing ? ` ${result.missing} mail artık Çöp Kutusu'nda değildi (kalıcı silinmiş olabilir).` : ''),
      { details: result.senders });
  } catch (err) {
    notifyError('Geri alınamadı', err);
  } finally {
    setBusy(false);
    refreshUndo();
  }
}

