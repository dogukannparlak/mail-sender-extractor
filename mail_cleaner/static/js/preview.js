// --- Önizleme ve adres listesi -----------------------------------------------

async function togglePanel(rowData, panel, btn, forceOpen = false) {
  const open = forceOpen || !panel.classList.contains('open');
  panel.classList.toggle('open', open);
  btn.setAttribute('aria-expanded', String(open));
  btn.textContent = open ? t('row.hide') : (rowData.single ? t('row.preview') : t('row.addresses'));
  if (!open) {
    state.openPanels.delete(rowData.key);
    return;
  }
  state.openPanels.add(rowData.key);

  if (!rowData.single) {
    panel.replaceChildren(...rowData.members.slice().sort((a, b) => b.mail_sayisi - a.mail_sayisi)
      .map(m => createMemberItem(m, panel)));
    updateSelection();
    return;
  }

  await loadPreviewInto(panel, rowData.members[0].gonderen);
}

// Alan adı grubunun içindeki bir adres: tek adres satırındaki seçenekler (seç, önizle, kopyala, koru, abonelikten çık).
function createMemberItem(m, groupPanel) {
  const address = m.gonderen;
  const addressProtected = state.protectedList.adresler.includes(address.toLowerCase());
  const domainProtected = !addressProtected && isProtected(address);
  const locked = addressProtected || domainProtected;

  const preview = el('div', { class: 'member-preview' });
  const checkbox = el('input', {
    type: 'checkbox', class: 'member-checkbox', 'data-address': address,
    checked: state.selected.has(address),
    'aria-label': t('row.select_aria', { name: address }), disabled: locked,
    title: locked ? t('row.locked_title') : null,
    onchange: () => {
      checkbox.checked ? state.selected.add(address) : state.selected.delete(address);
      const groupBox = groupPanel.closest('.sender-item')?.querySelector('.sender-checkbox');
      if (groupBox) syncRowCheckbox(groupBox);
      updateSelection();
    },
  });

  const previewBtn = el('button', {
    type: 'button', class: 'small-btn', 'aria-expanded': 'false',
    'aria-label': t('row.preview_aria', { name: address }),
    onclick: () => {
      const open = !preview.classList.contains('open');
      preview.classList.toggle('open', open);
      previewBtn.setAttribute('aria-expanded', String(open));
      previewBtn.textContent = open ? t('row.hide') : t('row.preview');
      if (open) loadPreviewInto(preview, address);
    },
  }, t('row.preview'));
  const copyBtn = el('button', {
    type: 'button', class: 'small-btn copy-btn', 'aria-label': t('row.copy_aria', { text: address }),
    onclick: () => copyToClipboard(address, copyBtn),
  }, t('row.copy'));
  const lockBtn = el('button', {
    type: 'button', class: 'small-btn lock-btn', 'aria-pressed': String(locked),
    'aria-disabled': domainProtected ? 'true' : null,
    title: domainProtected ? t('row.domain_protected_title')
      : (locked ? t('row.protect_remove_title') : t('row.protect_title')),
    onclick: () => toggleProtected(address, !locked, lockBtn),
  }, el('span', { 'aria-hidden': 'true' }, locked ? '🔒 ' : '🔓 '), locked ? t('row.protected') : t('row.protect'));
  const unsubResult = el('span', { class: 'unsub-result', 'data-result-for': address });
  const unsubBtn = canUnsubscribe(m) && el('button', {
    type: 'button', class: 'small-btn danger unsub-btn', disabled: locked,
    'aria-label': t('row.unsubscribe_aria', { name: address }),
    onclick: () => unsubscribeRow(address, unsubResult, unsubBtn),
  }, t('row.unsubscribe'));

  const badge = CATEGORY_LABELS[m.kategori]
    ? el('span', { class: `badge badge-${m.kategori}` }, CATEGORY_LABELS[m.kategori]) : null;
  return el('div', { class: 'member-item' },
    el('div', { class: 'member-row' },
      checkbox,
      el('div', { class: 'member-info' },
        el('div', { class: 'member-title' }, `${address} · ${tn('unit.mail', m.mail_sayisi)}`, badge),
        m.ad ? el('div', { class: 'preview-snippet' }, m.ad) : null),
      el('div', { class: 'row-actions' }, previewBtn, copyBtn, lockBtn, unsubBtn, unsubResult)),
    preview);
}

async function loadPreviewInto(panel, sender) {
  const cacheKey = `${state.scope}|${sender}`;
  if (state.previewCache.has(cacheKey)) {
    renderPreviews(panel, state.previewCache.get(cacheKey));
    return;
  }
  panel.replaceChildren(el('div', { class: 'muted' }, t('common.loading')));
  try {
    const body = await api('/api/preview', { sender, scope: state.scope });
    state.previewCache.set(cacheKey, body.previews);
    renderPreviews(panel, body.previews);
  } catch (err) {
    panel.replaceChildren(el('div', { class: 'muted' }, t('preview.failed', { message: err.message })));
  }
}

function renderPreviews(panel, previews) {
  if (!previews.length) {
    panel.replaceChildren(el('div', { class: 'muted' }, t('preview.none')));
    return;
  }
  panel.replaceChildren(...previews.map(p => el('div', { class: 'preview-item' },
    el('div', { class: 'preview-subject' }, p.subject),
    el('div', { class: 'preview-snippet' }, formatDate(p.date), p.snippet ? ` — ${p.snippet}` : ''),
  )));
}

async function copyToClipboard(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = t('row.copied');
    notify(t('copy.done', { text }));
  } catch (err) {
    btn.textContent = t('row.copy_failed');
  } finally {
    setTimeout(() => { btn.textContent = t('row.copy'); }, 1500);
  }
}

