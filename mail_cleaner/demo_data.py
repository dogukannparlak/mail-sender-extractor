"""Demo modunun sahte verisi, dil başına bir takım: gönderenler, konular ve mail metni.

Gönderen satırı: (görünen ad, adres, mail sayısı, Gmail sekmesi, List-Unsubscribe var mı, one-click mi).
Bütün adresler `.example` alan adlarıdır; gerçek hiçbir kişiye ya da firmaya ait değildir.
"""

TR_SENDERS = [
    ('Örnek Market', 'kampanya@ornekmarket.example', 64, 'CATEGORY_PROMOTIONS', True, True),
    ('Örnek Market Sipariş', 'siparis@ornekmarket.example', 12, 'CATEGORY_UPDATES', False, False),
    ('Kitap Kulübü Bülteni', 'bulten@kitapkulubu.example', 41, 'CATEGORY_UPDATES', True, True),
    ('Teknoloji Haftası', 'haber@teknohafta.example', 37, 'CATEGORY_UPDATES', True, False),
    ('Seyahat Fırsatları', 'firsat@seyahat.example', 29, 'CATEGORY_PROMOTIONS', True, True),
    ('Sosyal Ağ', 'bildirim@sosyalag.example', 33, 'CATEGORY_SOCIAL', True, False),
    ('Kod Forumu', 'noreply@kodforumu.example', 18, 'CATEGORY_FORUMS', True, False),
    ('Örnek Banka', 'bilgi@ornekbanka.example', 15, 'CATEGORY_UPDATES', False, False),
    ('Örnek Banka Kart', 'kart@kart.ornekbanka.example', 9, 'CATEGORY_UPDATES', False, False),
    ('Kargo Takip', 'takip@kargo.example', 22, 'CATEGORY_UPDATES', False, False),
    ('Ali "Usta" Yılmaz', 'ali@ornek.example', 7, 'CATEGORY_PERSONAL', False, False),
    ('Ayşe Demir', 'ayse@ornek.example', 5, 'CATEGORY_PERSONAL', False, False),
    ('Ders Duyuruları (Prof. A)', 'no-reply@okul.example', 14, 'CATEGORY_UPDATES', False, False),
    ('Ders Duyuruları (Prof. B)', 'no-reply@okul.example', 11, 'CATEGORY_UPDATES', False, False),
    ('Müzik Servisi', 'merhaba@muzik.example', 19, 'CATEGORY_PROMOTIONS', True, False),
    ('Yemek Siparişi', 'indirim@yemek.example', 26, 'CATEGORY_PROMOTIONS', True, True),
]


TR_WORK_SENDERS = [
    ('Proje Yönetim Aracı', 'bildirim@proje.example', 45, 'CATEGORY_UPDATES', True, True),
    ('Kod Deposu', 'noreply@kod.example', 38, 'CATEGORY_UPDATES', True, False),
    ('Takvim', 'takvim@ofis.example', 21, 'CATEGORY_UPDATES', False, False),
    ('Etkinlik Duyuruları', 'etkinlik@konferans.example', 17, 'CATEGORY_PROMOTIONS', True, True),
    ('Ekip Lideri', 'lider@ofis.example', 9, 'CATEGORY_PERSONAL', False, False),
    ('Örnek Banka', 'bilgi@ornekbanka.example', 6, 'CATEGORY_UPDATES', False, False),
]


EN_SENDERS = [
    ('Example Market', 'deals@examplemarket.example', 64, 'CATEGORY_PROMOTIONS', True, True),
    ('Example Market Orders', 'orders@examplemarket.example', 12, 'CATEGORY_UPDATES', False, False),
    ('Book Club Newsletter', 'news@bookclub.example', 41, 'CATEGORY_UPDATES', True, True),
    ('Tech Weekly', 'digest@techweekly.example', 37, 'CATEGORY_UPDATES', True, False),
    ('Travel Deals', 'offers@traveldeals.example', 29, 'CATEGORY_PROMOTIONS', True, True),
    ('Social Network', 'notify@socialnet.example', 33, 'CATEGORY_SOCIAL', True, False),
    ('Code Forum', 'noreply@codeforum.example', 18, 'CATEGORY_FORUMS', True, False),
    ('Example Bank', 'info@examplebank.example', 15, 'CATEGORY_UPDATES', False, False),
    ('Example Bank Card', 'card@cards.examplebank.example', 9, 'CATEGORY_UPDATES', False, False),
    ('Parcel Tracking', 'track@parcels.example', 22, 'CATEGORY_UPDATES', False, False),
    ('Alex "Ace" Morgan', 'alex@friends.example', 7, 'CATEGORY_PERSONAL', False, False),
    ('Sam Taylor', 'sam@friends.example', 5, 'CATEGORY_PERSONAL', False, False),
    ('Course Announcements (Prof. A)', 'no-reply@university.example', 14, 'CATEGORY_UPDATES', False, False),
    ('Course Announcements (Prof. B)', 'no-reply@university.example', 11, 'CATEGORY_UPDATES', False, False),
    ('Music Service', 'hello@music.example', 19, 'CATEGORY_PROMOTIONS', True, False),
    ('Food Delivery', 'offers@fooddelivery.example', 26, 'CATEGORY_PROMOTIONS', True, True),
]

EN_WORK_SENDERS = [
    ('Project Tracker', 'notify@projects.example', 45, 'CATEGORY_UPDATES', True, True),
    ('Code Hosting', 'noreply@codehost.example', 38, 'CATEGORY_UPDATES', True, False),
    ('Calendar', 'calendar@office.example', 21, 'CATEGORY_UPDATES', False, False),
    ('Event Announcements', 'events@conference.example', 17, 'CATEGORY_PROMOTIONS', True, True),
    ('Team Lead', 'lead@office.example', 9, 'CATEGORY_PERSONAL', False, False),
    ('Example Bank', 'info@examplebank.example', 6, 'CATEGORY_UPDATES', False, False),
]

TR_SUBJECTS = {
    'CATEGORY_PROMOTIONS': ['%50 indirim bugün bitiyor', 'Sana özel kampanya', 'Sepetinde ürün kaldı'],
    'CATEGORY_UPDATES': ['Haftalık özet', 'Hesap hareketin', 'Yeni duyuru yayınlandı'],
    'CATEGORY_SOCIAL': ['Bir arkadaşın seni etiketledi', '3 yeni bildirimin var'],
    'CATEGORY_FORUMS': ['Konuna yeni yanıt', 'Haftanın popüler başlıkları'],
    'CATEGORY_PERSONAL': ['Hafta sonu planı', 'Notları gönderiyorum'],
}



EN_SUBJECTS = {
    'CATEGORY_PROMOTIONS': ['50% off ends today', 'A special offer for you', 'You left something in your cart'],
    'CATEGORY_UPDATES': ['Your weekly digest', 'Account activity', 'New announcement posted'],
    'CATEGORY_SOCIAL': ['A friend tagged you', 'You have 3 new notifications'],
    'CATEGORY_FORUMS': ['New reply to your topic', 'Popular threads this week'],
    'CATEGORY_PERSONAL': ['Weekend plans', 'Sending the notes'],
}

DATASETS = {
    'tr': {
        'accounts': {'demo@ornek.example': (TR_SENDERS, 7), 'is@ornek.example': (TR_WORK_SENDERS, 11)},
        'subjects': TR_SUBJECTS,
        'snippet': 'Bu bir demo mailidir; gerçek bir hesaptan gelmiyor.',
        'unsubscribe_path': 'abonelik/cik',
        'unsubscribe_mailbox': 'cik',
    },
    'en': {
        'accounts': {'demo@mail.example': (EN_SENDERS, 7), 'work@mail.example': (EN_WORK_SENDERS, 11)},
        'subjects': EN_SUBJECTS,
        'snippet': 'This is a demo message; it does not come from a real account.',
        'unsubscribe_path': 'unsubscribe',
        'unsubscribe_mailbox': 'unsubscribe',
    },
}
