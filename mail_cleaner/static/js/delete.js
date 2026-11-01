// --- Çöp Kutusu'na taşıma ve geri alma ---------------------------------------

async function deleteSelected() {
  await deleteSenders(getSelected());
}

function exitedSenders() {
  return state.data ? state.data.gonderenler.filter(g => g.cikildi && !isProtected(g.gonderen)) : [];
}

async function deleteSenders(picked) {
  const senders = picked.map(g => g.gonderen);
  const hidden = picked.filter(g => !passesFilters(g)).length;
  setBusy(true);
  try {
    // Taramadaki sayı gelen kutusu, arşiv ve spam'i sayar; onayda seçilen kapsamın gerçek sayısı görünsün.
    $('deleteBtn').textContent = t('delete.counting');
    const count = await api('/api/count', { senders, scope: state.scope });
    const skipped = count.details.reduce((sum, d) => sum + (d.skipped || 0), 0);
    const scopeKey = state.scope === 'all' ? 'delete.scope_all' : 'delete.scope_inbox';

    const ok = await confirmDialog({
      title: t('delete.confirm_title', { mails: tn('unit.mail', count.total) }),
      lines: [
        t('dialog.account', { account: state.account }),
        t('delete.confirm_body', { senders: tn('unit.sender', picked.length), scope: t(scopeKey), mails: tn('unit.mail', count.total) }),
        skipped ? t('delete.skipped', { mails: tn('unit.mail', skipped) }) : null,
      ].filter(Boolean),
      items: count.details.map(d => `${d.email} · ${tn('unit.mail', d.count)}`),
      warning: hidden ? tn('delete.hidden_warning', hidden) : '',
      confirmLabel: t('delete.confirm_label'),
    });
    if (!ok) return;

    $('deleteBtn').textContent = t('delete.moving');
    notify(t('delete.moving_notice'));
    const result = await api('/api/delete', { senders, scope: state.scope });

    const removed = new Set(result.details.map(d => d.sender));
    const remaining = state.data.gonderenler.filter(g => !removed.has(g.gonderen));
    setData({ toplam_mail_sayisi: remaining.reduce((sum, g) => sum + g.mail_sayisi, 0), gonderenler: remaining });
    await refreshUndo();
    notify(t('delete.done', { mails: tn('unit.mail', result.total_deleted), account: result.account }), {
      details: result.details.map(d => `${d.email}: ${tn('unit.mail', d.deleted)}`),
      action: result.total_deleted ? { label: t('undo.label'), onclick: undoLastDelete } : null,
    });
  } catch (err) {
    notifyError(t('delete.failed'), err);
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
      btn.textContent = t('undo.button_count', { mails: tn('unit.mail', info.count) });
      btn.title = t('undo.senders', { senders: info.senders.join(', ') });
    }
  } catch (err) {
    btn.hidden = true;  // geri alma bilgisi alınamazsa butonu göstermemek yeterli
  }
}

async function undoLastDelete() {
  setBusy(true);
  notify(t('undo.running'));
  try {
    const result = await api('/api/undo', {});
    await load();
    notify(t('undo.done', { mails: tn('unit.mail', result.restored) }) +
      (result.missing ? ' ' + t('undo.missing', { mails: tn('unit.mail', result.missing) }) : ''),
      { details: result.senders });
  } catch (err) {
    notifyError(t('undo.failed'), err);
  } finally {
    setBusy(false);
    refreshUndo();
  }
}

