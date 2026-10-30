# Mimari

## Nasıl çalışır

```
tarayıcı (templates/*.html, static/css, static/js)
   │  fetch, yalnız aynı kaynaktan
   ▼
Flask mail_cleaner/web.py ── Host / Origin kontrolü ── Gmail API (google-api-python-client)
   │                                     ├─ messages.list  (tarama: -in:trash -in:sent -in:drafts, spam dahil;
   │                                     │                  silme/önizleme: from:"adres" in:inbox | -in:trash)
   │                                     ├─ batch messages.get (metadata)
   │                                     ├─ messages.batchModify (TRASH)
   │                                     └─ batch messages.untrash (geri al)
   └─ yerel dosyalar: accounts/<adres>/{token.json, credentials.json, senders.csv, scan_ids.json,
                     scan_cache.json, last_action.json, subscriptions.json, notifications.json,
                     activity_log.jsonl} · protected.json (ortak)
```

Gmail kotası kullanıcı başınadır; bu yüzden her hesabın kendi kota sınırlayıcısı vardır ve birkaç hesap aynı anda taranabilir. İlk
tarama her mailin başlıklarını okur; başlıklar `scan_cache.json` içinde saklanır, sonraki taramalar yalnız yeni mailleri okur.

## Proje yapısı

```
app.py                  web uygulaması giriş noktası (python app.py)
demo.py                 demo modu giriş noktası (python demo.py)
extract_senders.py      komut satırı aracı: bir hesabı CSV'ye tarar
scripts/                yardımcı betikler (make_screenshots.py)
doc/  doc-tr/           İngilizce / Türkçe dokümanlar (ekran görüntüleriyle)
tests/                  pytest testleri (sahte Gmail servisi) ve tarayıcı testleri (Playwright)
mail_cleaner/           uygulama paketi
  ├─ config.py          .env ayarları                     ├─ templates/  sayfalar (Jinja): base, index, subscriptions,
  ├─ auth.py            Google girişi, token'lar          │              notifications, activity_log + parçalar
  ├─ gmail.py           Gmail parçaları, kota sınırlayıcı ├─ static/css/ app.css (ana sayfa), pages.css (diğer sayfalar)
  ├─ scanner.py         mail başına önbellekli tarama     ├─ static/js/  özellik başına bir dosya, aşağıya bak
  ├─ accounts.py        hesap klasörleri ve dosyaları     └─ locales/    en.json, tr.json (bütün arayüz metinleri)
  ├─ mailbox.py         sayma, çöpe taşıma, geri alma, önizleme
  ├─ unsubscribe.py     List-Unsubscribe, tek tıkla çıkış ├─ i18n.py     dil seçimi ve t() / tn()
  ├─ subscriptions.py   abonelik listesi, bildirimler     ├─ migrate.py  eski sürümlerin dosyalarını yeniden adlandırır
  ├─ activity.py        hesap başına işlem günlüğü        ├─ demo.py, demo_data.py  sahte posta kutuları (en, tr)
  ├─ protected.py       korunan gönderenler (ortak)       ├─ storage.py  okunaklı JSON dosyaları
  ├─ state.py           tarama/taşıma durumu ve kilitler  └─ web.py      Flask uygulaması: sayfalar, JSON API, hata eşleme
```

### Ön yüz

Sayfalar sunucuda çizilen Jinja şablonlarıdır (`templates/base.html` ortak kalıp). Ana sayfanın davranışı `static/js/` altında,
**özellik başına bir dosyada**; bu sırayla, düz betik olarak yüklenir (derleme adımı yok; tek bir global alanı paylaşırlar):

| Dosya | İşi |
|---|---|
| `i18n.js` | `t()` / `tn()` çeviri yardımcıları ve dil seçici |
| `state.js` | sayfa durumu nesnesi ve sabitler |
| `util.js` | DOM yardımcısı `el()`, `api()` fetch sarmalayıcısı, tarih ve süre biçimleri |
| `ui.js` | bildirim alanı ve onay penceresi |
| `senders.js` | gönderen listesini süzme, sıralama, gruplama ve çizme |
| `preview.js` | gönderen önizlemesi, alan adı adres listesi, kopyalama |
| `selection.js` | seçim durumu, işlem çubuğu, meşgul durumu |
| `protection.js` | koru / korumayı kaldır |
| `unsubscribe.js` | onaylı abonelikten çıkma akışı |
| `delete.js` | Çöp Kutusu'na taşıma ve geri alma |
| `accounts.js` | hesap seçici, ekleme / çıkarma, giriş |
| `scan.js` | tarama, tüm hesapları tarama, ilerleme |
| `main.js` | olayların bağlanması ve açılış |
| `list.js` | tablo sayfalarında arama / filtre / sıralama |

### Arayüz metinleri

Bütün arayüz metinleri `mail_cleaner/locales/<dil>.json` dosyalarındadır (düz `anahtar → metin`, `{ad}` yer tutucuları, çoğul için
`_one` / `_other`). Python kodu ve şablonlar `t('anahtar')` çağırır; sayfa tarayıcıya yalnız JavaScript'in kullandığı anahtarları
gönderir. Bir test katalogları eşit tutar (her dilde aynı anahtarlar ve yer tutucular, eksik ya da kullanılmayan anahtar yok).

### Veri biçimi notları

Saklanan veride ve API'de bazı alan adları hâlâ Türkçedir (`gonderen`, `mail_sayisi`, `kategori`, `abonelik`, `tur`, `islem`, …);
kategori değerleri `bulten`, `promosyon`, `bildirim`, `kisisel`, `spam`. Bunlar kullanıcıya hiç gösterilmeyen iç kimliklerdir; mevcut
tarama önbellekleri, günlükler ve bildirimler çalışmaya devam etsin diye korundu. Dosya ve klasör adları İngilizcedir; eski sürümlerin
dosyaları açılışta `migrate.py` ile yeniden adlandırılır (üzerine yazılmaz, silinmez).

## Güvenlik notları

Uygulama maillerini değiştirebilen bir token tutar; bu yüzden yalnız kendi tarayıcından,
`localhost` üzerinden erişilecek şekilde kuruldu:

- `localhost` / `127.0.0.1` / `[::1]` dışındaki bir `Host` ile gelen istekler reddedilir
  (DNS rebinding); başka sitelerden gelen `POST`'lar `Sec-Fetch-Site` ve `Origin` ile reddedilir.
- Gönderen adresleri Gmail aramasına girmeden önce ayrıştırılıp doğrulanır; hazırlanmış bir
  `From` başlığı sorguyu genişletemez (ör. `x@y.com OR label:inbox`).
- Mail başlıklarından gelen her şey sayfaya girmeden önce HTML olarak kaçırılır.
- Tek tıkla çıkış yalnız genel IP'deki `https` adreslerine, yönlendirme izlenmeden ve yalnız
  sen onayladıktan sonra gönderilir.
- Abonelikler sayfasında gösterilen çıkış bağlantıları `http`, `https` ve `mailto:` ile sınırlıdır ve `rel="noopener noreferrer"` ile açılır; başka her şey (ör. `javascript:`) atılır.
- `credentials.json`, `accounts/` klasörü (token'lar, tarama önbelleği, bildirimler, işlem günlüğü) ve yerel veri dosyaları `.gitignore`'da. Önbellek ve günlük gönderen adresleri içerir, bilgisayarında kalır.

Uygulamayı bir ağa açma ya da ortak bir sunucuda çalıştırma.
