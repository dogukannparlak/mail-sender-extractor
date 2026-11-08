// Uygulama gibi davranış: dış bağlantılar varsayılan tarayıcıda açılır, sayfalar aynı pencerede gezilir, ⌘, ayarları açar.
// Pencere (data-app) ya da tarayıcı fark etmez; dış bağlantı kuralı ikisinde de çalışır.
(function () {
  const inApp = document.documentElement.dataset.app === '1';
  const isExternal = a => /^https?:/i.test(a.getAttribute('href') || '') && a.host !== location.host;

  function openExternal(url) {
    fetch('/api/open-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) })
      .catch(() => window.open(url, '_blank', 'noopener'));
  }

  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a || e.defaultPrevented) return;
    if (isExternal(a)) { e.preventDefault(); openExternal(a.href); return; }
    if (inApp && a.target === '_blank') a.removeAttribute('target');  // sayfalar yeni pencere değil, aynı pencerede açılır
  });

  if (inApp) {
    const realOpen = window.open;
    window.open = function (url, ...rest) {
      if (url && /^https?:/i.test(url) && new URL(url, location.href).host !== location.host) { openExternal(url); return null; }
      if (url) { location.href = url; return null; }
      return realOpen.call(window, url, ...rest);
    };
  }

  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === ',') { e.preventDefault(); appGo('/settings'); }
  });

  // Menüden ve sayfalardan: seçili hesabı koruyarak başka sayfaya geç.
  window.appGo = function (path) {
    location.href = path;  // etkin hesap sunucuda; adreste hesap taşımaya gerek yok
  };

  // --- Etkin hesap: her sayfada ve sekmede aynı ---------------------------------
  async function activeAccount() {
    const res = await fetch('/api/active-account');
    return (await res.json()).active;
  }

  // Alt sayfalardaki hesap seçici: önce sunucuya yaz, sonra sayfayı yeni hesapla yenile.
  window.setActiveAccount = async function (account) {
    await fetch('/api/active-account', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account }) });
    location.href = location.pathname;  // ?account= kalmasın: sunucudaki etkin hesap geçerli
  };

  async function syncAccount() {
    if (document.hidden) return;
    const current = typeof window.currentAccount === 'function' ? window.currentAccount() : document.documentElement.dataset.account;
    if (!current) return;
    try {
      const active = await activeAccount();
      if (!active || active === current) return;
      if (typeof window.onActiveAccountChanged === 'function') window.onActiveAccountChanged(active);
      else location.href = location.pathname;
    } catch (err) { /* sunucuya ulaşılamıyorsa bir sonraki yoklamada tekrar denenir */ }
  }
  setInterval(syncAccount, 3000);
  window.addEventListener('focus', syncAccount);
  document.addEventListener('visibilitychange', syncAccount);

  // Uygulama penceresindeki sayfayı varsayılan tarayıcıda da aç (isteğe bağlı).
  window.openInBrowser = function () { openExternal(location.href); };

  // Küçük geçici bildirim (menüden tetiklenen işlemlerin sonucu için)
  window.appToast = function (text, error) {
    let box = document.getElementById('appToast');
    if (!box) {
      box = document.createElement('div');
      box.id = 'appToast';
      box.style.cssText = 'position:fixed;left:50%;bottom:20px;transform:translateX(-50%);max-width:80vw;padding:10px 16px;border-radius:10px;'
        + 'background:var(--card,#fff);color:var(--text,#000);border:1px solid var(--border,#ccc);box-shadow:0 4px 18px rgba(0,0,0,.2);z-index:9999;font:13px -apple-system,system-ui,sans-serif';
      document.body.append(box);
    }
    box.textContent = text;
    box.style.borderColor = error ? 'var(--err,#b33434)' : 'var(--border,#ccc)';
    clearTimeout(box._t);
    box._t = setTimeout(() => box.remove(), 6000);
  };

  // Menüden: bir işlem uç noktasını çağır, sonucu bildir (CSV, yedek, veri klasörü).
  window.appPost = async function (url) {
    const account = (window.currentAccount && window.currentAccount()) || document.documentElement.dataset.account || '';
    try {
      const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ account }) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) window.appToast(data.error || t('err.unexpected'), true);
      else if (url !== '/api/data/open' && data.path) window.appToast(data.path);
    } catch (err) {
      window.appToast(t('api.unreachable'), true);
    }
  };
})();
