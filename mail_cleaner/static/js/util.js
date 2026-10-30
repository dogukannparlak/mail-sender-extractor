// --- Küçük yardımcılar -------------------------------------------------------

// Mail başlıklarından gelen metin sayfaya yalnız textContent ile girer (innerHTML yok):
// gönderen adı HTML ya da yeni bir attribute açamaz.
// el('button', { class: 'x', onclick: fn }, 'metin', çocukEleman)
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'class') node.className = value;
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

// Bütün sunucu çağrıları buradan geçer: JSON olmayan hata sayfası ya da kapalı sunucu
// da okunur bir mesaja dönüşür.
// Her istek seçili hesabı taşır; sunucu hangi hesabın dosyalarına ve Gmail'ine gideceğini buradan bilir.
const ACCOUNT_FREE_URLS = ['/api/accounts', '/api/accounts/add', '/api/scan/all', '/api/scan/status/all'];

async function api(url, payload) {
  const withAccount = state.account && !ACCOUNT_FREE_URLS.includes(url);
  if (withAccount && payload === undefined) {
    url += (url.includes('?') ? '&' : '?') + 'account=' + encodeURIComponent(state.account);
  }
  const options = payload === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(withAccount ? { ...payload, account: state.account } : payload),
  };
  let res;
  try {
    res = await fetch(url, options);
  } catch (err) {
    throw new ApiError('Sunucuya ulaşılamadı. Uygulama hâlâ çalışıyor mu?', 0, null);
  }
  let body = null;
  try { body = await res.json(); } catch (err) { /* JSON değil */ }
  if (!res.ok) throw new ApiError(body?.error || `Sunucu hatası (${res.status})`, res.status, body);
  return body;
}

function domainOf(address) {
  const at = address.lastIndexOf('@');
  return at === -1 ? address : address.slice(at + 1);
}

// Sunucudaki is_protected ile aynı kural: alan adı alt alan adlarını da kapsar.
function isProtected(address) {
  const email = address.toLowerCase();
  const domain = domainOf(email);
  return state.protectedList.adresler.includes(email) ||
    state.protectedList.alanlar.some(d => domain === d.slice(1) || domain.endsWith('.' + d.slice(1)));
}

function formatDate(ms) {
  if (!ms) return '';
  return new Date(Number(ms)).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatDuration(seconds) {
  if (seconds < 60) return 'bir dakikadan az';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `yaklaşık ${minutes} dk`;
  return `yaklaşık ${Math.floor(minutes / 60)} sa ${minutes % 60} dk`;
}

