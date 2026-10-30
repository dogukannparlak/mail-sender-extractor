# Geliştirme

## Testler

`pytest` testleri sahte bir Gmail servisine karşı çalışır; gerçek hesaba ya da ağa dokunmaz.
`tests/test_ui.py` sayfayı demo moduna karşı headless Chromium'da kullanır (Chromium kurulu
değilse atlanır).

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium   # tests/test_ui.py tarayıcı testleri ve scripts/make_screenshots.py için
python -m pytest tests/ -v
```

## Ekran görüntüleri

`python scripts/make_screenshots.py` sahte verili demo modunu başlatır ve dokümanlardaki ekran görüntülerini yazar:
`doc/screenshots/` (İngilizce arayüz) ve `doc-tr/screenshots/` (Türkçe arayüz). Yalnız bir takım için `en` ya da `tr` ver.
Chromium gerekir (yukarıya bak); gerçek hesap dosyalarına hiç dokunmaz.

## Dil ekleme

1. `mail_cleaner/locales/en.json` dosyasını `<kod>.json` olarak kopyala ve değerleri çevir (anahtarları ve `{yer tutucuları}`
   koru; çoğul için `_one` / `_other`).
2. Kodu `mail_cleaner/i18n.py` içindeki `LANGUAGES`'e ve `mail_cleaner/config.py` içinde kabul edilen değerlere (`LANGUAGE`) ekle.
3. İstersen `mail_cleaner/demo_data.py` içine (`DATASETS`) bir demo veri takımı ekle.
4. Testleri çalıştır: bir anahtar ya da yer tutucu eksikse, ya da sayfada başka bir dilin metni kalmışsa `tests/test_i18n.py` düşer.

## Notlar

- Token `gmail.modify` iznini (okuma + değiştirme) kullanır, çünkü web uygulaması mailleri
  Çöp Kutusu'na taşır. `extract_senders.py` yalnız okur ama aynı token'ı paylaşır.
- Bir hesabın girişi çalışmazsa (süresi dolmuş ya da izin geri alınmış) başlıktan hesabı çıkar ve yeniden ekle.

- Eski sürümler Türkçe dosya ve klasör adları kullanırdı (`hesaplar/`, `gonderenler.csv`, …). Uygulama açılışta bunları İngilizce adlara çevirir (üzerine yazmaz, silmez). `.env`'inde hâlâ `ACCOUNTS_DIR=hesaplar` yazıyorsa o klasör adı korunur.
