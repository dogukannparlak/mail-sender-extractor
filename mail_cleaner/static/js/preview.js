// --- Önizleme ve adres listesi -----------------------------------------------

async function togglePanel(rowData, panel, btn, forceOpen = false) {
  const open = forceOpen || !panel.classList.contains('open');
  panel.classList.toggle('open', open);
  btn.setAttribute('aria-expanded', String(open));
  btn.textContent = open ? 'Gizle' : (rowData.single ? 'Önizle' : 'Adresler');
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
    'aria-label': `${address} seç`, disabled: locked,
    title: locked ? 'Korunan gönderen: seçilemez' : null,
    onchange: () => {
      checkbox.checked ? state.selected.add(address) : state.selected.delete(address);
      const groupBox = groupPanel.closest('.sender-item')?.querySelector('.sender-checkbox');
      if (groupBox) syncRowCheckbox(groupBox);
      updateSelection();
    },
  });

  const previewBtn = el('button', {
    type: 'button', class: 'small-btn', 'aria-expanded': 'false',
    'aria-label': `${address}: son mailleri önizle`,
    onclick: () => {
      const open = !preview.classList.contains('open');
      preview.classList.toggle('open', open);
      previewBtn.setAttribute('aria-expanded', String(open));
      previewBtn.textContent = open ? 'Gizle' : 'Önizle';
      if (open) loadPreviewInto(preview, address);
    },
  }, 'Önizle');
  const copyBtn = el('button', {
    type: 'button', class: 'small-btn copy-btn', 'aria-label': `${address} kopyala`,
    onclick: () => copyToClipboard(address, copyBtn),
  }, 'Kopyala');
  const lockBtn = el('button', {
    type: 'button', class: 'small-btn lock-btn', 'aria-pressed': String(locked),
    'aria-disabled': domainProtected ? 'true' : null,
    title: domainProtected ? 'Alan adı korunuyor; korumayı üstteki alan adı satırından kaldır'
      : (locked ? 'Korumayı kaldır' : 'Koru: seçilemez, taşınamaz, abonelikten çıkılamaz'),
    onclick: () => toggleProtected(address, !locked, lockBtn),
  }, el('span', { 'aria-hidden': 'true' }, locked ? '🔒 ' : '🔓 '), locked ? 'Korunuyor' : 'Koru');
  const unsubResult = el('span', { class: 'unsub-result', 'data-result-for': address });
  const unsubBtn = canUnsubscribe(m) && el('button', {
    type: 'button', class: 'small-btn danger unsub-btn', disabled: locked,
    'aria-label': `${address} aboneliğinden çık`,
    onclick: () => unsubscribeRow(address, unsubResult, unsubBtn),
  }, 'Abonelikten çık');

  const badge = CATEGORY_LABELS[m.kategori]
    ? el('span', { class: `badge badge-${m.kategori}` }, CATEGORY_LABELS[m.kategori]) : null;
  return el('div', { class: 'member-item' },
    el('div', { class: 'member-row' },
      checkbox,
      el('div', { class: 'member-info' },
        el('div', { class: 'member-title' }, `${address} · ${m.mail_sayisi} mail`, badge),
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
  panel.replaceChildren(el('div', { class: 'muted' }, 'Yükleniyor…'));
  try {
    const body = await api('/api/preview', { sender, scope: state.scope });
    state.previewCache.set(cacheKey, body.previews);
    renderPreviews(panel, body.previews);
  } catch (err) {
    panel.replaceChildren(el('div', { class: 'muted' }, `Önizleme yüklenemedi: ${err.message}`));
  }
}

function renderPreviews(panel, previews) {
  if (!previews.length) {
    panel.replaceChildren(el('div', { class: 'muted' }, 'Bu kapsamda bu gönderenden mail bulunamadı.'));
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
    btn.textContent = 'Kopyalandı';
    notify(`${text} panoya kopyalandı.`);
  } catch (err) {
    btn.textContent = 'Kopyalanamadı';
  } finally {
    setTimeout(() => { btn.textContent = 'Kopyala'; }, 1500);
  }
}

