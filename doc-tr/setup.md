# Kurulum

Uygulamayı çalıştırma: Gmail'siz hızlı demo, sonra gerçek hesaplar için tam kurulum (Google Cloud istemcisi, hesap ekleme, birden fazla hesap).
Ayarlar [configuration.md](configuration.md) içinde.

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
cp .env.example .env        # isteğe bağlı: ayarlar, bkz. configuration.md
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

Uygulama o hesabın istemci dosyasını ve giriş anahtarını `accounts/<adres>/` klasörüne koyar (git
bu klasörü yok sayar). Silinen mailler doğrudan kalıcı olarak silinmez, Gmail'in **Çöp Kutusu**'na
taşınır; Gmail Çöp Kutusu'nu 30 gün sonra boşaltır.

**Hesap eklemenin diğer yolları:**

| Elinde olan | Yapılacak |
|---|---|
| Hesabın `client_secret_….json` dosyası, klasörleri elle hazırlamak istiyorsun | `accounts/<adres>/` klasörünü oluştur, dosyayı oraya `credentials.json` adıyla koy. Hesap **+ Hesap ekle** penceresinde "girişi bekleyen" olarak çıkar; ona bas. Başka bir Google hesabıyla giriş reddedilir. |
| O hesabın istemcisiyle oluşturulmuş hazır bir `token.json` | `tokens/` klasörüne koy, `.env`'e `ACCOUNT_2=<adres>=tokens/<dosya>.json` satırını ekle (bkz. [configuration.md](configuration.md)). |
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
| Google Cloud istemcisi, giriş anahtarı, gönderen listesi, tarama dizini ve önbelleği, son taşıma kaydı, abonelikler, bildirimler, işlem günlüğü | Hesap başına: `accounts/<adres>/`                                                                                                |
| Korunan gönderenler (`protected.json`)                              | Ortak: kilitlediğin banka her hesapta korunur                                                                                       |
| Gmail kotası (dakikada ~300 mail okuma)                                | Gmail hesap başına sayar, uygulama da öyle: her hesabın kendi bütçesi var, bu yüzden birkaç hesap aynı anda taranabilir (*Tüm hesapları tara*) |

**Tek hesaplı sürümden geçiş:** ilk açılışta mevcut `token.json` ve veri dosyaları (`senders.csv`,
`scan_ids.json`, `last_action.json`) ait oldukları hesabın klasörüne taşınır; o token onunla oluşturulduysa `credentials.json` da taşınır. Sayfa hangi hesaba
taşındığını yazar.
