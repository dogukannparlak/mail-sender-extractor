# Yapılandırma

## Ayarlar (`.env`)

Ayarlar proje klasöründeki `.env` dosyasında durur (git'e girmez). Örnekten başla:

```bash
cp .env.example .env
```

| Ayar                             | Varsayılan          | Ne yapar                                                                                                    |
| -------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------- |
| `PORT`                         | `5050`             | `http://localhost:<PORT>` portu                                                                           |
| `LANGUAGE` | boş | Arayüz dili: `en` ya da `tr`. Boşsa tarayıcının dili izlenir (ikisi de değilse İngilizce) |
| `DEMO`                         | `0`                | `1` = sahte hesaplarla demo modu, Gmail'e bağlanmaz                                                      |
| `FLASK_DEBUG`                  | `0`                | Flask hata ayıklama modu (yalnız geliştirirken)                                                          |
| `COMPACT_FILES`                | `0`                | `0` = uygulamanın yazdığı JSON dosyaları girintili ve okunaklı, `1` = sıkışık tek satır      |
| `CREDENTIALS_PATH` | `credentials.json` | İsteğe bağlı ortak OAuth istemcisi; normalde her hesap kendi dosyasını getirir |
| `ACCOUNTS_DIR`                 | `accounts`         | Her hesap için bir alt klasör içeren klasör                                                             |
| `ACCOUNT_1`, `ACCOUNT_2`, … | boş                 | Token dosyası elinde olan her hesap için bir satır: `adres=token_yolu` (ör. `tokens/ikinci.json`) |
| `EXTRA_ACCOUNTS`               | boş                 | Aynısı tek satırda: `adres=token_yolu, adres=token_yolu`                                               |
| `GMAIL_QUOTA_PER_MINUTE`       | `5400`             | Uygulamanın kendine izin verdiği dakikalık kota birimi (Gmail sınırı 6.000)                           |
| `DEFAULT_SCOPE`                | `inbox`            | Taşıma/önizlemenin varsayılan kapsamı: `inbox` ya da `all`                                         |

Komut satırında verilen değer `.env`'nin önüne geçer (`DEMO=1 python app.py`). Göreli yollar proje
klasörüne göredir; `~` açılır. Hatalı bir değer uygulamayı açılışta, hangi ayar olduğunu yazarak
durdurur. `ACCOUNT_n` / `EXTRA_ACCOUNTS` hesapları sayfadan çıkarılamaz (token dosyası senin); satırı sil.

## Dil

Arayüz **English** ve **Türkçe** olarak kullanılabilir. Sayfa başlığındaki (ve Abonelikler, Bildirimler, İşlem günlüğü
sayfalarındaki) dil seçiciyi kullan; seçim çerezde hatırlanır.

Dil şu sırayla seçilir: adreste `?lang=tr` › çerez › `.env`'deki `LANGUAGE` ayarı › tarayıcının `Accept-Language` başlığı ›
İngilizce. Sunucu mesajları (hatalar, `.env` sorunları) aynı kurala uyar; arka plan taramasının mesajları taramayı başlatan
tarayıcı sekmesinin dilinde yazılır.

Demo modu aynı dilde sahte veri kullanır (`LANGUAGE`, boşsa İngilizce). Yeni dil eklemek için bkz.
[development.md](development.md#dil-ekleme).

## Yalnız CSV (CLI)

```bash
python extract_senders.py                   # tek hesap varsa onu
python extract_senders.py biri@gmail.com    # belirli bir hesap
```

O hesabın `accounts/<adres>/senders.csv` dosyasını yazar: adres başına bir satır, görünen ad,
sayı, kategori ve abonelik linki görülüp görülmediği. Eski CSV dosyaları (ham `From` başlığı +
sayı) hâlâ okunur ve adrese göre birleştirilir.
