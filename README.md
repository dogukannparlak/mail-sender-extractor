# Mail Sender Extractor

Gmail gelen kutusundaki mailleri gönderene göre sayan; seçtiğin gönderenlerden gelen mailleri
toplu olarak çöpe taşıyan veya (gönderen destekliyorsa) aboneliğini iptal eden bir web uygulaması.
Gönderenler tek, sıralanabilir bir liste olarak gösterilir. İstenirse yalnızca tarama/CSV çıktısı
için `extract_senders.py` bağımsız bir CLI script olarak da çalıştırılabilir.

## Özellikler

- **Tara:** Gelen kutusunu tarayıp gönderenleri mail sayısıyla listeler ve `gonderenler.csv`'ye yazar.
- **Sırala:** Mail sayısına (çoktan aza / azdan çoğa) veya isme (A‑Z / Z‑A) göre sıralama.
- **Toplu seçim:** "Tümünü seç" kutusu ile tüm gönderenleri tek tıkla işaretleme.
- **Adres kopyala:** Her gönderenin e-posta adresini panoya kopyalama.
- **Önizle:** Silmeden önce bir gönderenin son maillerinin konu ve tarihlerini görme.
- **Çöpe taşı:** Seçilen gönderenlerin tüm maillerini Gmail Çöp Kutusu'na taşıma (30 gün geri alınabilir).
- **Abonelikten çık:** `List-Unsubscribe` başlığını kullanarak otomatik (one-click) çıkış ya da
  manuel çıkış linki/adresi sunma.

## Kurulum

Sanal ortam zaten oluşturuldu (`venv/`). Kullanmak için:

```bash
source venv/bin/activate
```

Bağımlılıklar zaten kuruldu, ama tekrar kurman gerekirse:

```bash
pip install -r requirements.txt
```

## Google Cloud kimlik bilgileri (credentials.json)

Script'in çalışması için Gmail API erişimi olan bir OAuth client secret dosyasına ihtiyacın var:

1. [Google Cloud Console](https://console.cloud.google.com/) üzerinde bir proje oluştur (veya var olanı seç).
2. **APIs & Services > Library** kısmından **Gmail API**'yi etkinleştir.
3. **APIs & Services > Credentials** kısmından **Create Credentials > OAuth client ID** seç.
   - Application type: **Desktop app**
4. Oluşturulan client ID için JSON dosyasını indir ve bu klasöre `credentials.json` adıyla kaydet.

## Çalıştırma (web uygulaması, önerilen)

```bash
source venv/bin/activate
python app.py
```

Tarayıcıda `http://localhost:5050` adresini aç. İlk çalıştırmada (veya "Gelen Kutusunu Tara"
butonuna ilk basışta) bir tarayıcı penceresi açılıp Google hesabınla giriş yapmanı isteyecek.
Onayladıktan sonra `token.json` dosyası oluşturulur ve sonraki çalıştırmalarda tekrar giriş
yapmana gerek kalmaz.

"Gelen Kutusunu Tara" butonu gelen kutusunu tarar ve `gonderenler.csv` dosyasını güncel gönderen
listesiyle yeniden yazar. Arayüzdeki listeyi mail sayısına veya isme göre sıralayabilir, "Tümünü
seç" ile toplu seçim yapabilir, her gönderenin adresini kopyalayabilir ve "Önizle" ile silmeden
önce o gönderenin son maillerinin konularını görebilirsin. Seçtiğin gönderenlerin maillerini çöpe
taşıyabilir veya (gönderen destekliyorsa) abonelikten çıkabilirsin.

## Çalıştırma (yalnızca CSV, CLI)

Tarayıcı arayüzü olmadan sadece tarama/CSV çıktısı istiyorsan:

```bash
source venv/bin/activate
python extract_senders.py
```

Sonuç `gonderenler.csv` dosyasına yazılır: her satırda gönderen (isim/adres) ve o gönderenden gelen mail sayısı bulunur.

## Notlar

- `credentials.json` ve `token.json` gizli bilgiler içerir, `.gitignore` içinde hariç tutuldu.
- Depodaki `mail_kategorileri.json` şu an uygulama tarafından kullanılmıyor; ileride API key ile
  eklenecek AI destekli kategorilendirme için elle hazırlanmış örnek veri olarak saklanıyor.
  Tarama bu dosyaya dokunmaz.
- `app.py`'nin silme özelliği nedeniyle ortak `token.json`, `gmail.modify` (okuma + değiştirme)
  izniyle oluşturulur. `extract_senders.py`'nin kendisi Gmail'e yalnızca okuma amaçlı istekler
  gönderir, mail silmez veya değiştirmez — ama artık aynı token'ı web uygulamasıyla paylaştığı
  için token'ın izin kapsamı daha geniştir. Bu değişiklikten önce oluşturulmuş eski bir
  `token.json` varsa silip (`rm token.json`) yeniden giriş yapman gerekir.
