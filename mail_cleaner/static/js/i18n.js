// Çeviri: sunucu `window.I18N` (anahtar → metin) ve `window.LANG` değerlerini sayfaya yazar.
// t('anahtar', { ad: değer }) metindeki {ad} yer tutucularını doldurur; eksik anahtarda anahtarın kendisi görünür.
function t(key, params) {
  const text = window.I18N[key] ?? key;
  return params ? text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match)) : text;
}

// Çoğul: anahtar_one (count === 1) ya da anahtar_other; {count} otomatik doldurulur.
function tn(key, count, params) {
  return t(count === 1 ? `${key}_one` : `${key}_other`, { count, ...params });
}

// Dil seçici: seçimi çerezde saklar, sayfayı o dilde yeniden yükler.
function setLanguage(code) {
  document.cookie = `lang=${code}; path=/; max-age=${365 * 24 * 3600}; SameSite=Lax`;
  location.reload();
}

document.getElementById('languageSelect')?.addEventListener('change', e => setLanguage(e.target.value));
