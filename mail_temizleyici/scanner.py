"""Gelen kutusu, spam ve arşiv taraması: gönderen başına sayım, ad, modelsiz kategori; CSV okuma/yazma."""
from collections import Counter
import csv
import os
import time

from .gmail import fetch_metadata, gmail_execute, message_headers, sender_key

CSV_HEADER = ['Adres', 'Ad', 'Mail Sayısı', 'Kategori', 'Abonelik']
LEGACY_CSV_HEADER = ['İsim/Adres', 'Mail Sayısı']



# Modelsiz kategori: Gmail'in kendi sekme etiketleri + List-Unsubscribe başlığı.
# Sıra önemli: sosyal ağ bildirimleri de çoğu zaman List-Unsubscribe taşır.
CATEGORIES = ('bulten', 'promosyon', 'bildirim', 'kisisel', 'spam')


def message_category(label_ids, has_unsubscribe):
    labels = set(label_ids or [])
    if 'SPAM' in labels:
        return 'spam'
    if 'CATEGORY_PROMOTIONS' in labels:
        return 'promosyon'
    if labels & {'CATEGORY_SOCIAL', 'CATEGORY_FORUMS'}:
        return 'bildirim'
    if has_unsubscribe:
        return 'bulten'
    if 'CATEGORY_UPDATES' in labels:
        return 'bildirim'
    return 'kisisel'


class SenderTally:
    """Gönderen başına mail sayısını, en sık görülen adı ve kategoriyi toplar."""

    def __init__(self):
        self._counts = Counter()
        self._names = {}
        self._categories = {}
        self._unsubscribe = {}

    def add_counted(self, key, name, count, category=None, has_unsubscribe=None):
        self._counts[key] += count
        if name:
            self._names.setdefault(key, Counter())[name] += count
        if category:
            self._categories.setdefault(key, Counter())[category] += count
        if has_unsubscribe is not None:
            self._unsubscribe[key] = self._unsubscribe.get(key, False) or has_unsubscribe

    def result(self):
        senders = {}
        for key, count in self._counts.most_common():
            info = {
                'ad': self._names[key].most_common(1)[0][0] if key in self._names else '',
                'mail_sayisi': count,
            }
            if key in self._categories:
                info['kategori'] = self._categories[key].most_common(1)[0][0]
            if key in self._unsubscribe:
                info['abonelik'] = self._unsubscribe[key]
            senders[key] = info
        return senders


# Taranan yerler: gelen kutusu, spam ve arşiv. Çöp, gönderilenler ve taslaklar hariç
# (gönderilenlerde From kullanıcının kendisi olurdu).
SCAN_QUERY = '-in:trash -in:sent -in:drafts'


def list_scan_ids(service):
    ids = []
    next_page_token = None
    while True:
        results = gmail_execute(service.users().messages().list(
            userId='me', q=SCAN_QUERY, includeSpamTrash=True, maxResults=500,
            pageToken=next_page_token
        ), 'list')
        ids.extend(m['id'] for m in results.get('messages', []))
        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            # Sayfalama sırasında yeni mail gelirse aynı id iki sayfada görünebilir.
            return list(dict.fromkeys(ids))



def extract_senders(service, progress=lambda processed, total: None, sleep=time.sleep, id_index=None, cache=None):
    """Gelen kutusu, spam ve arşivi tarar; {adres: {'ad', 'mail_sayisi', 'kategori', 'abonelik'}} döner.

    id_index verilirse {adres: [mail id]} ile doldurulur; silme sırasında bu mailler için
    From adresini yeniden okumak (her biri 20 kota birimi) gerekmez.

    cache verilirse {mail id: [adres, ad, kategori, abonelik] ya da None (From yok)} tutar: bir mailin
    başlıkları değişmez, o yüzden önceki taramalarda okunanlar yeniden çekilmez, yalnız yeni mailler
    okunur. Taranan yerlerden çıkanlar (ör. çöpe gidenler) cache'ten silinir. Kategori etiketi sonradan değişirse (ör. mail
    başka sekmeye taşınırsa) cache temizlenip tam tarama yapılana kadar eski kalır.
    """
    ids = list_scan_ids(service)
    total = len(ids)
    progress(0, total)

    cache = {} if cache is None else cache
    for stale in set(cache) - set(ids):
        del cache[stale]
    new_ids = [i for i in ids if i not in cache]
    processed = total - len(new_ids)
    progress(processed, total)

    for msg_id, msg_data in fetch_metadata(service, new_ids, ['From', 'List-Unsubscribe'], sleep):
        processed += 1
        if msg_data is None:  # tarama sırasında silinmiş
            progress(processed, total)
            continue
        headers = message_headers(msg_data)
        if 'from' in headers:
            key, name = sender_key(headers['from'])
            has_unsubscribe = bool(headers.get('list-unsubscribe'))
            cache[msg_id] = [key, name, message_category(msg_data.get('labelIds'), has_unsubscribe),
                             has_unsubscribe]
        else:
            cache[msg_id] = None
        progress(processed, total)

    tally = SenderTally()
    for msg_id in ids:
        entry = cache.get(msg_id)
        if entry:
            key, name, category, has_unsubscribe = entry
            tally.add_counted(key, name, 1, category=category, has_unsubscribe=has_unsubscribe)
            if id_index is not None:
                id_index.setdefault(key, []).append(msg_id)
    return tally.result()


def print_progress(processed, total, bar_length=30):
    if total:
        ratio = min(processed / total, 1.0)
        filled = int(bar_length * ratio)
        bar = '#' * filled + '-' * (bar_length - filled)
        print(f'\r[{bar}] {processed}/{total} (%{ratio * 100:.1f})', end='', flush=True)
    else:
        print(f'\rTaranan mail sayısı: {processed}', end='', flush=True)


# Görünen adı gönderen yazar; "=HYPERLINK(...)" gibi bir ad CSV Excel'de açılınca formül olur.
FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _csv_safe(value):
    return "'" + value if value.startswith(FORMULA_PREFIXES) else value


def _csv_unsafe(value):
    return value[1:] if value.startswith("'") and value[1:].startswith(FORMULA_PREFIXES) else value


def save_to_csv(senders, filename='gonderenler.csv'):
    # Önce geçici dosyaya yaz: okuyan biri yarım dosya görmesin.
    tmp = filename + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for address, info in sorted(senders.items(), key=lambda kv: -kv[1]['mail_sayisi']):
            abonelik = {True: '1', False: '0'}.get(info.get('abonelik'), '')
            writer.writerow([_csv_safe(address), _csv_safe(info['ad']), info['mail_sayisi'],
                             info.get('kategori', ''), abonelik])
    os.replace(tmp, filename)
    print(f"{len(senders)} benzersiz gönderen '{filename}' dosyasına yazıldı.")


def load_csv(filename):
    """save_to_csv'nin yazdığı dosyayı okur; eski (ham From başlığı, sayı) biçimini adrese göre birleştirir."""
    tally = SenderTally()
    with open(filename, encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        legacy = header is not None and header[:1] != CSV_HEADER[:1]
        for row in reader:
            if legacy:
                if len(row) >= 2 and row[1].strip().isdigit():
                    key, name = sender_key(row[0])
                    tally.add_counted(key, name, int(row[1]))
            elif len(row) >= 3 and row[2].strip().isdigit():
                category = row[3] if len(row) > 3 and row[3] in CATEGORIES else None
                has_unsubscribe = {'1': True, '0': False}.get(row[4]) if len(row) > 4 else None
                tally.add_counted(_csv_unsafe(row[0]), _csv_unsafe(row[1]), int(row[2]), category, has_unsubscribe)
    return tally.result()
