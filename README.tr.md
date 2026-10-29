# Mail Sender Extractor

*Other languages: [🇬🇧 English](README.md)*

Gmail gelen kutunu tarayan, mailleri gönderene göre gruplayan ve seçtiğin gönderenlerin
maillerini toplu olarak çöpe taşımanı ya da abonelikten çıkmanı sağlayan yerel bir web
uygulaması. Son silme geri alınabilir. Yalnız kendi bilgisayarında (`localhost`) çalışır;
Gmail'in kendi API'si dışında hiçbir yere veri gitmez.

![Demo modunda gönderen listesi](docs/screenshot.png)

## Özellikler

- **Arka planda tarama ve ilerleme çubuğu:** mail bilgileri arka planda Gmail batch
  istekleriyle alınır; sayfada ilerleme ve kalan süre görünür. Gmail kullanıcı başına dakikada
  yaklaşık 300 mail okumaya izin veriyor; uygulama hız sınırına çarpmak yerine bu kotaya göre
  ilerler (10.000 mail ≈ 35 dakika). Sonraki silmeler taramada görüleni yeniden kullanır.
- **Gönderen başına tek satır:** sayım gerçek adrese göre yapılır; aynı adres farklı adlarla
  gelse de tek satırdır. **Alan adı görünümü** ile `magaza.com`'u bütün olarak görebilirsin.
- **Modelsiz kategori:** her gönderen Gmail'in kendi sekmelerinden (`CATEGORY_*` etiketleri)
  ve `List-Unsubscribe` başlığından *bülten / promosyon / bildirim / kişisel* olarak etiketlenir.
- **Arama ve filtre:** ad ya da adresle ara; kategoriye ya da "abonelik linki olanlar"a göre
  süz. "Tümünü seç" yalnız ekranda görünen satırları seçer.
- **Korunan gönderenler:** bir adresi ya da alan adının tamamını kilitle (`@banka.com`, alt
  alan adları dahil). Kilitli gönderenler seçilemez; sunucu da onları silmeyi ve abonelikten
  çıkmayı reddeder.
- **Gerçek sayıyla silme:** *yalnız gelen kutusu* ya da *tüm mailler (arşiv dahil)* seç; onay
  penceresi Çöp Kutusu'na gerçekten kaç mail gideceğini gösterir.
- **Geri al:** son silme geri alınabilir. Mailler eski gelen kutusu/okunmadı durumlarıyla
  döner; arşivdeki mailler gelen kutusuna düşmez.
- **Onaylı abonelikten çıkma:** tek tıkla çıkış (RFC 8058) yalnız gönderen listesini onayladıktan
  sonra gönderilir; aksi halde kendin açacağın bir link ya da `mailto:` adresi verilir.
- **Birden fazla Gmail hesabı:** başlıktan hesap ekle ve hesaplar arasında geçiş yap. Her hesabın
  gönderen listesi, taraması ve geri alması ayrıdır; korunanlar listesi ortaktır. Onay pencereleri
  hesabı yazar, yanlış hesapta mail taşınmaz.
- **Önizleme ve kopyalama:** silmeden önce gönderenin son konularını gör; adresi kopyala.

## Gmail hesabı olmadan dene (demo modu)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
DEMO=1 python app.py
```

`http://localhost:5050` adresini aç. Demo modu bellekte iki sahte hesap kullanır (yaklaşık 500
mail); veri dosyaları geçici bir klasöre yazılır, abonelik istekleri bilgisayarından çıkmaz.

## Kendi Gmail'inle kullan

"Ana" bir hesap yok: **her Gmail hesabı kendi başına bağlanır**; kendi Google Cloud projesindeki
OAuth istemcisiyle. Başkasının projesine, onayına ya da test kullanıcı listesine gerek yoktur.
1–2. adımları bir kez, 3–4. adımları eklemek istediğin **her hesap için** yap.

### 1. Kur

```bash
git clone https://github.com/dogukannparlak/mail-sender-extractor.git
cd mail-sender-extractor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # isteğe bağlı: ayarlar, aşağıda "Ayarlar"
```

### 2. Çalıştır

```bash
source venv/bin/activate
python app.py
```

`http://localhost:5050` adresini aç. Uygulamayı kullanırken bu terminal açık kalsın; `Ctrl+C`
uygulamayı durdurur.

### 3. Google Cloud kurulumu (her hesap için bir kez, ~10 dakika)

[Google Cloud Console](https://console.cloud.google.com/)'a **eklemek üzere olduğun Gmail hesabıyla**
gir. Google menü adlarını zaman zaman değiştiriyor; ad farklıysa en yakın olanı seç.

1. **Proje oluştur.** Üstteki proje seçici › **New project** › bir ad ver (ör. `mail-temizleyici`)
   › **Create**. Üstte yeni projenin seçili olduğundan emin ol.
2. **Gmail API'yi aç.**
   [APIs & Services › Library › Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   sayfasında **Enable**'a bas.
3. **Giriş ekranını kur.** [Google Auth Platform](https://console.cloud.google.com/auth/overview)
   › **Get started**:
   - **App information:** herhangi bir uygulama adı (ör. `Mail Temizleyici`), destek e-postası
     olarak kendi adresin.
   - **Audience:** **External**.
   - **Contact information:** kendi adresin. Politikayı kabul et › **Create**.
4. **Kendini test kullanıcısı yap** (proje senin olsa da gerekli). **Audience** › **Test users** ›
   **Add users** › bu hesabın Gmail adresini yazıp sonuna virgül koy; adres yuvarlak bir etikete
   dönüşsün › **Save**. Listede "1 user (1 test)" yazdığını kontrol et. Bunu yapmazsan giriş
   `Hata 403: access_denied` verir.
5. **Gmail iznini ekle** (önerilir). **Data access** › **Add or remove scopes** ›
   `https://www.googleapis.com/auth/gmail.modify` iznini bul (ya da "Manually add scopes" kutusuna
   yapıştır) › **Update** › **Save**.
6. **İstemciyi oluştur.** **Clients** › **Create client** › Application type **Desktop app** ›
   herhangi bir ad › **Create** › **Download JSON**. `client_secret_1234….json` gibi bir dosya
   iner. Kimseyle paylaşma: projeni tanıtır.

### 4. Hesabı uygulamaya ekle

1. Sayfanın üstündeki **+ Hesap ekle**'ye bas.
2. 3.6'da indirdiğin `client_secret_….json` dosyasını seç.
3. Google penceresi açılır. **Aynı hesabı** seç, sonra:
   - "Google bu uygulamayı doğrulamadı" uyarısı çıkar; proje test modunda ve yalnız sen
     kullanıyorsun. **Devam**'a bas.
   - Gmail erişimine izin ver (okuma ve değiştirme: uygulama mailleri Çöp Kutusu'na taşıyabilsin).
4. Uygulamaya döndüğünde "<adres> eklendi" yazar. **Gelen Kutusunu Tara**'ya bas.

Uygulama o hesabın istemci dosyasını ve giriş anahtarını `hesaplar/<adres>/` klasörüne koyar (git
bu klasörü yok sayar). Silinen mailler doğrudan kalıcı olarak silinmez, Gmail'in **Çöp Kutusu**'na
taşınır; Gmail Çöp Kutusu'nu 30 gün sonra boşaltır.

**Hesap eklemenin diğer yolları:**

| Elinde olan | Yapılacak |
|---|---|
| Hesabın `client_secret_….json` dosyası, klasörleri elle hazırlamak istiyorsun | `hesaplar/<adres>/` klasörünü oluştur, dosyayı oraya `credentials.json` adıyla koy. Hesap **+ Hesap ekle** penceresinde "girişi bekleyen" olarak çıkar; ona bas. Başka bir Google hesabıyla giriş reddedilir. |
| O hesabın istemcisiyle oluşturulmuş hazır bir `token.json` | `tokenlar/` klasörüne koy, `.env`'e `ACCOUNT_2=<adres>=tokenlar/<dosya>.json` satırını ekle (bkz. "Ayarlar"). |
| Proje klasöründe tek, ortak bir `credentials.json` | Hâlâ çalışır: **+ Hesap ekle** bunu da önerir. O zaman her hesap o tek projenin test kullanıcısı olmalı. |

**Test modu notu:** Google test modundaki uygulamaların girişini yaklaşık 7 gün sonra düşürebilir.
Öyle olunca uygulama oturumun süresinin dolduğunu söyler: **Hesabı çıkar**, sonra aynı dosyayla
yeniden ekle. (Google Auth Platform › Audience'ta uygulamayı yayınlamak bunu önler, karşılığında
"doğrulanmamış uygulama" uyarısı çıkar; Google'ın bu konudaki güncel kurallarını doğrulamadım.)

### 5. Birden fazla hesap

Birden çok Gmail hesabını (kişisel, okul, iş) aynı sayfadan yönetebilirsin.

1. **Ekle:** her hesap için yukarıdaki 3–4. adımları uygula. Google hesap seçme ekranını gösterir;
   tarayıcıda o an açık olan hesap sessizce seçilmez.
2. **Geçiş yap:** üstteki hesap seçiciden hesabı seç. Liste, seçim, önizlemeler ve "Geri al" o
   hesaba aittir; geçişte seçim diğer hesaba taşınmaz.
3. **Çalış:** tarama, taşıma, geri alma ve abonelikten çıkma her zaman yalnız seçili hesapta yapılır.
   Onay penceresi ve alttaki çubuk hesabın adını yazar; yanlış hesapta mail taşımazsın.
4. **Çıkar:** **Hesabı çıkar** yalnız o hesabın bu bilgisayardaki giriş anahtarını (token) siler.
   Maillerine dokunulmaz; kayıtlı gönderen listesi de kalır, hesabı yeniden eklersen geri gelir.
   Uygulamanın Google'daki iznini de kaldırmak için:
   [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

| Ne                                                                      | Hesap başına mı, ortak mı?                                                                                                       |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Google Cloud istemcisi, giriş anahtarı, gönderen listesi, tarama dizini, son taşıma kaydı | Hesap başına: `hesaplar/<adres>/`                                                                                                |
| Korunan gönderenler (`korunanlar.json`)                              | Ortak: kilitlediğin banka her hesapta korunur                                                                                       |
| Gmail kotası (dakikada ~300 mail okuma)                                | Gmail hesap başına sayar; uygulama bütün hesapları birlikte yavaşlatır, iki tarama aynı anda yaklaşık yarı hızda ilerler |

**Tek hesaplı sürümden geçiş:** ilk açılışta mevcut `token.json` ve veri dosyaları (`gonderenler.csv`,
`taranan_idler.json`, `son_islem.json`) ait oldukları hesabın klasörüne taşınır; o token onunla oluşturulduysa `credentials.json` da taşınır. Sayfa hangi hesaba
taşındığını yazar.

### 6. Ayarlar (`.env`)

Ayarlar proje klasöründeki `.env` dosyasında durur (git'e girmez). Örnekten başla:

```bash
cp .env.example .env
```

| Ayar                             | Varsayılan          | Ne yapar                                                                                                    |
| -------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------- |
| `PORT`                         | `5050`             | `http://localhost:<PORT>` portu                                                                           |
| `DEMO`                         | `0`                | `1` = sahte hesaplarla demo modu, Gmail'e bağlanmaz                                                      |
| `FLASK_DEBUG`                  | `0`                | Flask hata ayıklama modu (yalnız geliştirirken)                                                          |
| `COMPACT_FILES`                | `0`                | `0` = uygulamanın yazdığı JSON dosyaları girintili ve okunaklı, `1` = sıkışık tek satır      |
| `CREDENTIALS_PATH` | `credentials.json` | İsteğe bağlı ortak OAuth istemcisi; normalde her hesap kendi dosyasını getirir |
| `ACCOUNTS_DIR`                 | `hesaplar`         | Her hesap için bir alt klasör içeren klasör                                                             |
| `ACCOUNT_1`, `ACCOUNT_2`, … | boş                 | Token dosyası elinde olan her hesap için bir satır: `adres=token_yolu` (ör. `tokenlar/ikinci.json`) |
| `EXTRA_ACCOUNTS`               | boş                 | Aynısı tek satırda: `adres=token_yolu, adres=token_yolu`                                               |
| `GMAIL_QUOTA_PER_MINUTE`       | `5400`             | Uygulamanın kendine izin verdiği dakikalık kota birimi (Gmail sınırı 6.000)                           |
| `DEFAULT_SCOPE`                | `inbox`            | Taşıma/önizlemenin varsayılan kapsamı: `inbox` ya da `all`                                         |

Komut satırında verilen değer `.env`'nin önüne geçer (`DEMO=1 python app.py`). Göreli yollar proje
klasörüne göredir; `~` açılır. Hatalı bir değer uygulamayı açılışta, hangi ayar olduğunu yazarak
durdurur. `ACCOUNT_n` / `EXTRA_ACCOUNTS` hesapları sayfadan çıkarılamaz (token dosyası senin); satırı sil.

### Yalnız CSV (CLI)

```bash
python extract_senders.py                   # tek hesap varsa onu
python extract_senders.py biri@gmail.com    # belirli bir hesap
```

O hesabın `hesaplar/<adres>/gonderenler.csv` dosyasını yazar: adres başına bir satır, görünen ad,
sayı, kategori ve abonelik linki görülüp görülmediği. Eski CSV dosyaları (ham `From` başlığı +
sayı) hâlâ okunur ve adrese göre birleştirilir.

## Nasıl çalışır

```
tarayıcı (templates/index.html)
   │  fetch, yalnız aynı kaynaktan
   ▼
Flask app.py ── Host / Origin kontrolü ── Gmail API (google-api-python-client)
   │                                       ├─ messages.list  (from:"adres" in:inbox)
   │                                       ├─ batch messages.get (metadata)
   │                                       ├─ messages.batchModify (TRASH)
   │                                       └─ batch messages.untrash (geri al)
   └─ yerel dosyalar: hesaplar/<adres>/{token.json, gonderenler.csv, taranan_idler.json,
                     son_islem.json} · korunanlar.json (ortak)
```

Proje klasöründeki giriş dosyaları: `app.py` (web uygulaması), `demo.py` (demo modu),
`extract_senders.py` (CLI). Kod `mail_temizleyici/` paketinde, her iş için bir modül:

| Modül                   | Ne yapar                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------- |
| `config.py`            | `.env`'i okur, değerleri denetler                                                           |
| `auth.py`              | Google girişi, hesap başına bir token (`0600`)                                            |
| `gmail.py`             | Gmail API ortak parçaları: adres ayrıştırma, kota sınırlayıcı, yeniden denemeli batch |
| `scanner.py`           | Gelen kutusu taraması: adres başına sayım, görünen ad, kategori; CSV okuma/yazma         |
| `accounts.py`          | Hesap klasörleri, hesap listesi, eski tek hesaplı dosyaların taşınması                   |
| `protected.py`         | Korunan gönderenler (bütün hesaplarda ortak)                                                |
| `state.py`             | Hesap başına tarama/taşıma durumu ve kilitler                                              |
| `mailbox.py`           | Sayma, Çöp Kutusu'na taşıma, geri alma, önizleme (gönderen birebir kontrolüyle)         |
| `unsubscribe.py`       | List-Unsubscribe ve SSRF korumalı tek tıkla çıkış                                        |
| `web.py`               | Flask uygulaması: sayfa, JSON API, istek denetimi, hata eşleme                               |
| `demo.py`              | Demo modu için sahte posta kutuları                                                          |
| `templates/index.html` | Sayfa (düz JS, derleme adımı yok)                                                           |

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
- `credentials.json`, `hesaplar/` klasörü (token'lar) ve yerel veri dosyaları `.gitignore`'da.

Uygulamayı bir ağa açma ya da ortak bir sunucuda çalıştırma.

## Testler

`pytest` testleri sahte bir Gmail servisine karşı çalışır; gerçek hesaba ya da ağa dokunmaz.
`tests/test_ui.py` sayfayı demo moduna karşı headless Chromium'da kullanır (Chromium kurulu
değilse atlanır).

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium   # yalnız tests/test_ui.py tarayıcı testleri için
python -m pytest tests/ -v
```

## Notlar

- Token `gmail.modify` iznini (okuma + değiştirme) kullanır, çünkü web uygulaması mailleri
  Çöp Kutusu'na taşır. `extract_senders.py` yalnız okur ama aynı token'ı paylaşır.
- Bir hesabın girişi çalışmazsa (süresi dolmuş ya da izin geri alınmış) başlıktan hesabı çıkar ve yeniden ekle.
