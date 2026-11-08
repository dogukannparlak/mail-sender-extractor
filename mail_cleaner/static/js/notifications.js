// Bildirimler sayfası: arama/filtre/sıralama, satır seçimi, okundu/okunmadı işaretleme.
const $ = id => document.getElementById(id);

if ($('sort')) {
  const table = $('notifTable');
  const account = table.dataset.account;
  const rows = [...document.querySelectorAll('tbody tr')];
  const boxes = () => [...document.querySelectorAll('tbody tr:not([hidden]) .rowSel')];
  const selectedRows = () => rows.filter(r => r.querySelector('.rowSel').checked);

  setupList({
    rows, search: $('q'), sort: $('sort'), count: $('count'), noMatch: $('noMatch'),
    selects: [{ el: $('fType'), attr: 'type' }], checks: [{ el: $('fUnread'), attr: 'unread' }],
  });

  function updateSelection() {
    const picked = selectedRows().length;
    $('markRead').disabled = !picked;
    $('markUnread').disabled = !picked;
    $('selCount').textContent = picked ? t('notif.selected', { count: picked }) : '';
    const visible = boxes();
    $('selectAll').checked = visible.length > 0 && visible.every(cb => cb.checked);
    $('selectAll').indeterminate = !$('selectAll').checked && visible.some(cb => cb.checked);
  }

  // Satırların, sayacın ve menü rozetinin görünümünü sunucudaki durumla eşitler (sayfayı yenilemeden).
  function showUnread(unread) {
    $('unreadChip').textContent = t('notif.chip_unread', { count: unread });
    $('unreadChip').hidden = unread === 0;
    $('readAll').disabled = unread === 0;
    document.querySelectorAll('.count-badge').forEach(badge => { badge.hidden = unread === 0; badge.textContent = unread; });
  }

  async function mark(targets, read, ids) {
    try {
      const res = await fetch('/api/notifications/read', {
        method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account, ids, read }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || res.status);
      targets.forEach(row => { row.classList.toggle('unread', !read); row.dataset.unread = read ? '0' : '1'; });
      showUnread(data.unread);
      return true;
    } catch (err) {
      $('count').textContent = err.message;
      return false;
    }
  }

  $('readAll').addEventListener('click', async () => {
    $('readAll').disabled = true;
    if (!await mark(rows, true, null)) $('readAll').disabled = false;
  });
  for (const [button, read] of [[$('markRead'), true], [$('markUnread'), false]]) {
    button.addEventListener('click', async () => {
      const picked = selectedRows();
      if (await mark(picked, read, picked.map(r => r.dataset.id))) {
        picked.forEach(r => { r.querySelector('.rowSel').checked = false; });
        updateSelection();
        // "Yalnız okunmamış" süzgeci açıksa görünümü yeni duruma göre tazele
        $('fUnread').dispatchEvent(new Event('change'));
      }
    });
  }

  $('selectAll').addEventListener('change', e => { boxes().forEach(cb => { cb.checked = e.target.checked; }); updateSelection(); });
  document.querySelector('tbody').addEventListener('change', e => { if (e.target.classList.contains('rowSel')) updateSelection(); });
  // Mail gibi: bildirime basınca okundu olur (seçim kutusu ve düğmeler hariç).
  document.querySelector('tbody').addEventListener('click', e => {
    if (e.target.closest('input, button')) return;
    const row = e.target.closest('tr');
    if (row && row.dataset.unread === '1') mark([row], true, [row.dataset.id]);
  });
  // Süzgeç/arama değişince görünmeyen satırlar seçili kalmasın.
  const dropHidden = () => {
    rows.filter(r => r.hidden).forEach(r => { r.querySelector('.rowSel').checked = false; });
    updateSelection();
  };
  $('q').addEventListener('input', dropHidden);
  [$('fType'), $('fUnread')].forEach(c => c.addEventListener('change', dropHidden));
}
