# tokenlar/

Elinde hazır token dosyası olan hesaplar için. Bu klasördeki dosyalar git'e girmez (bu README hariç).

1. Token dosyasını buraya kopyala, adını değiştir: ör. `ikinci.json`.
2. `.env`'de ilgili satırın başındaki `#`'i kaldır ve adresi yaz:
   `ACCOUNT_2=ikinci@gmail.com=tokenlar/ikinci.json`
3. Uygulamayı yeniden başlat; hesap üstteki "Taranan hesap" seçicisinde görünür.

Token dosyan yoksa buraya bir şey koymana gerek yok: uygulamada "+ Hesap ekle" ile giriş yap,
token `hesaplar/<adres>/token.json` olarak kendiliğinden yazılır.
