"""Mail Temizleyici: Gmail gönderenlerini tarayan, toplu taşıyan ve abonelikten çıkaran yerel uygulama.

Modüller:
- config      .env ayarları
- auth        Google girişi, hesap başına token
- gmail       Gmail API ortak parçaları (adres ayrıştırma, kota, batch)
- scanner     gelen kutusu taraması ve CSV
- accounts    hesap klasörleri, hesap listesi, eski düzenden taşıma
- protected   korunan gönderenler
- state       tarama/taşıma durumları ve kilitler
- mailbox     sayma, Çöp Kutusu'na taşıma, geri alma, önizleme
- unsubscribe List-Unsubscribe ve tek tıkla çıkış
- web         Flask uygulaması ve API
- demo        sahte posta kutuları
"""
