// Ayarlar sayfası: formu kaydeder; veri klasörü, yedek ve CSV düğmeleri.
const noticeBox = document.getElementById('notice');

function show(text, error = false) {
  noticeBox.textContent = text;
  noticeBox.style.color = error ? 'var(--err)' : 'var(--ok)';
}

async function post(url, payload = {}) {
  let res;
  try {
    res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  } catch (err) {
    throw new Error(t('api.unreachable'));
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || t('err.unexpected'));
  return data;
}

async function run(action) {
  try { await action(); } catch (err) { show(err.message, true); }
}

document.getElementById('settingsForm').addEventListener('submit', e => {
  e.preventDefault();
  const form = e.target;
  const language = form.LANGUAGE.value;
  run(async () => {
    await post('/api/settings', {
      LANGUAGE: language, DEFAULT_SCOPE: form.DEFAULT_SCOPE.value,
      GMAIL_QUOTA_PER_MINUTE: form.GMAIL_QUOTA_PER_MINUTE.value, COMPACT_FILES: form.COMPACT_FILES.checked ? '1' : '0',
    });
    if (language) { document.cookie = `lang=${language}; path=/; max-age=${365 * 24 * 3600}; SameSite=Lax`; location.reload(); return; }
    show(t('settings.saved'));
  });
});

document.getElementById('openData').addEventListener('click', () => run(async () => { await post('/api/data/open'); }));
document.getElementById('backupData').addEventListener('click', () => run(async () => {
  const r = await post('/api/data/backup');
  show(t('settings.backup_done', { path: r.path }));
}));
document.getElementById('exportCsv')?.addEventListener('click', () => run(async () => {
  const r = await post('/api/export/csv', { account: document.getElementById('csvAccount').value });
  show(t('settings.csv_done', { path: r.path }));
}));
