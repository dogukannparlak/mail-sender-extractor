from collections import Counter
import csv
import re
import time
from email.utils import parseaddr

from googleapiclient.errors import HttpError

import gmail_auth

# Gmail arama sözdizimine sızabilecek karakterler (boşluk, tırnak, parantez, ':') adreste olamaz.
EMAIL_RE = re.compile(r'^[^@\s"()<>,;:\\\[\]]+@[\w-]+(\.[\w-]+)+$')

CSV_HEADER = ['Adres', 'Ad', 'Mail Sayısı', 'Kategori', 'Abonelik']
LEGACY_CSV_HEADER = ['İsim/Adres', 'Mail Sayısı']


def sender_key(header):
    """From başlığını (adres, görünen ad) çiftine çevirir.

    Aynı adres farklı görünen adlarla gelebilir ("Ali (Classroom)" <no-reply@...>);
    sayım adrese göre yapılır. Adres geçerli değilse ham başlık anahtar olur.
    """
    name, addr = parseaddr(header)
    if EMAIL_RE.match(addr):
        return addr.lower(), name.strip()
    return header.strip(), ''


# Modelsiz kategori: Gmail'in kendi sekme etiketleri + List-Unsubscribe başlığı.
# Sıra önemli: sosyal ağ bildirimleri de çoğu zaman List-Unsubscribe taşır.
CATEGORIES = ('bulten', 'promosyon', 'bildirim', 'kisisel')


def message_category(label_ids, has_unsubscribe):
    labels = set(label_ids or [])
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

    def add_counted(self, key, name, count, kategori=None, abonelik=None):
        self._counts[key] += count
        if name:
            self._names.setdefault(key, Counter())[name] += count
        if kategori:
            self._categories.setdefault(key, Counter())[kategori] += count
        if abonelik is not None:
            self._unsubscribe[key] = self._unsubscribe.get(key, False) or abonelik

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


# Gmail, 50'den büyük batch'lerde hız sınırına takılabileceğini söylüyor.
BATCH_SIZE = 50
MAX_ATTEMPTS = 5


def _is_retryable(exc):
    if not isinstance(exc, HttpError):
        return False
    if exc.status_code == 429 or exc.status_code >= 500:
        return True
    return exc.status_code == 403 and 'rateLimitExceeded' in str(exc.content)


def list_inbox_ids(service):
    ids = []
    next_page_token = None
    while True:
        results = service.users().messages().list(
            userId='me', labelIds=['INBOX'], maxResults=500,
            pageToken=next_page_token
        ).execute()
        ids.extend(m['id'] for m in results.get('messages', []))
        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            return ids


def fetch_metadata(service, ids, headers, sleep=time.sleep):
    """Mailleri BATCH_SIZE'lık batch isteklerle getirir; hız sınırına takılanları bekleyip yeniden dener.

    Her başarılı yanıt için (id, yanıt) üretir.
    """
    pending = list(ids)
    attempt = 0
    while pending:
        done, retry = [], []

        def callback(request_id, response, exception):
            if exception is None:
                done.append((request_id, response))
            elif _is_retryable(exception):
                retry.append(request_id)
            else:
                raise exception

        for i in range(0, len(pending), BATCH_SIZE):
            batch = service.new_batch_http_request(callback=callback)
            for msg_id in pending[i:i + BATCH_SIZE]:
                batch.add(service.users().messages().get(
                    userId='me', id=msg_id, format='metadata', metadataHeaders=headers
                ), request_id=msg_id)
            batch.execute()
            yield from done
            done.clear()

        if retry:
            attempt += 1
            if attempt >= MAX_ATTEMPTS:
                raise RuntimeError(f'{len(retry)} mail Gmail hız sınırı yüzünden {MAX_ATTEMPTS} denemede alınamadı.')
            sleep(2 ** (attempt - 1))
        pending = retry


def extract_senders(service, progress=None, sleep=time.sleep):
    progress = progress or print_progress
    ids = list_inbox_ids(service)
    total = len(ids)
    progress(0, total)

    tally = SenderTally()
    fetched = fetch_metadata(service, ids, ['From', 'List-Unsubscribe'], sleep)
    for processed, (_, msg_data) in enumerate(fetched, start=1):
        headers = {h['name'].lower(): h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
        if 'from' in headers:
            key, name = sender_key(headers['from'])
            has_unsubscribe = bool(headers.get('list-unsubscribe'))
            tally.add_counted(key, name, 1,
                              kategori=message_category(msg_data.get('labelIds'), has_unsubscribe),
                              abonelik=has_unsubscribe)
        progress(processed, total)

    if progress is print_progress:
        print()
    return tally.result()


def print_progress(processed, total, bar_length=30):
    if total:
        ratio = min(processed / total, 1.0)
        filled = int(bar_length * ratio)
        bar = '#' * filled + '-' * (bar_length - filled)
        print(f'\r[{bar}] {processed}/{total} (%{ratio * 100:.1f})', end='', flush=True)
    else:
        print(f'\rTaranan mail sayısı: {processed}', end='', flush=True)


def save_to_csv(senders, filename='gonderenler.csv'):
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for address, info in sorted(senders.items(), key=lambda kv: -kv[1]['mail_sayisi']):
            abonelik = {True: '1', False: '0'}.get(info.get('abonelik'), '')
            writer.writerow([address, info['ad'], info['mail_sayisi'], info.get('kategori', ''), abonelik])
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
                kategori = row[3] if len(row) > 3 and row[3] in CATEGORIES else None
                abonelik = {'1': True, '0': False}.get(row[4]) if len(row) > 4 else None
                tally.add_counted(row[0], row[1], int(row[2]), kategori, abonelik)
    return tally.result()


if __name__ == '__main__':
    service = gmail_auth.get_service()
    senders = extract_senders(service)
    save_to_csv(senders)
