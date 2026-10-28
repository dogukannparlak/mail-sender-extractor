from collections import Counter
import csv
import os
import re
import threading
import time
from collections import deque
from email.utils import parseaddr

from googleapiclient.errors import HttpError

import gmail_auth

# Gmail arama sözdizimine sızabilecek karakterler (boşluk, tırnak, parantez, ':') adreste olamaz.
EMAIL_RE = re.compile(r'^[^@\s"()<>,;:\\\[\]]+@[\w-]+(\.[\w-]+)+$')

CSV_HEADER = ['Adres', 'Ad', 'Mail Sayısı', 'Kategori', 'Abonelik']
LEGACY_CSV_HEADER = ['İsim/Adres', 'Mail Sayısı']


def message_headers(msg):
    """Gmail metadata yanıtındaki başlıklar; ad büyük/küçük harfe duyarsız (List-Unsubscribe = list-unsubscribe)."""
    return {h['name'].lower(): h['value'] for h in (msg or {}).get('payload', {}).get('headers', [])}


def from_address(msg):
    """Mailin From adresi (küçük harf); başlık yoksa None."""
    headers = message_headers(msg)
    return sender_key(headers['from'])[0] if 'from' in headers else None


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


# Gmail, 50'den büyük batch'lerde hız sınırına takılabileceğini söylüyor.
BATCH_SIZE = 50
MAX_ATTEMPTS = 5


# Gmail kullanıcı kotası dakikada 6.000 birim; mail okuma (messages.get) 20 birim,
# yani dakikada en fazla ~300 mail okunabilir (developers.google.com/workspace/gmail/api/reference/quota,
# 2026-10-28). Kotaya çarpıp 429 yemek yerine harcamayı önceden sınırlıyoruz; biraz pay bırakıldı.
QUOTA_UNITS = {'get': 20, 'list': 5, 'batchModify': 50, 'untrash': 5}


class QuotaLimiter:
    """Son 60 saniyede harcanan birimi izler; sınır aşılacaksa bekler. units_per_minute=0 → sınırsız."""

    def __init__(self, units_per_minute=5400, clock=time.monotonic, sleep=time.sleep):
        self.units_per_minute = units_per_minute
        self._clock, self._sleep = clock, sleep
        self._spent = deque()  # (zaman, birim)
        self._lock = threading.Lock()  # tarama ve diğer istekler aynı kullanıcı kotasını paylaşır

    def spend(self, units):
        if not self.units_per_minute:
            return
        with self._lock:
            while True:
                now = self._clock()
                while self._spent and now - self._spent[0][0] >= 60:
                    self._spent.popleft()
                used = sum(u for _, u in self._spent)
                if not self._spent or used + units <= self.units_per_minute:
                    self._spent.append((now, units))
                    return
                self._sleep(max(60 - (now - self._spent[0][0]), 0.05))


quota = QuotaLimiter()


def gmail_execute(request, method):
    """Tekil Gmail çağrısı: kotayı say, 429/5xx'te googleapiclient'ın kendi geri çekilmesiyle yeniden dene."""
    quota.spend(QUOTA_UNITS[method])
    return request.execute(num_retries=3)


# 403 gövdesinde "rateLimitExceeded" ya da "userRateLimitExceeded" geçebilir.
RATE_LIMIT_REASONS = ('ratelimitexceeded', 'backenderror')


def _is_retryable(exc):
    if not isinstance(exc, HttpError):
        return False
    if exc.status_code == 429 or exc.status_code >= 500:
        return True
    body = str(exc.content).lower()
    return exc.status_code == 403 and any(reason in body for reason in RATE_LIMIT_REASONS)


def list_inbox_ids(service):
    ids = []
    next_page_token = None
    while True:
        results = gmail_execute(service.users().messages().list(
            userId='me', labelIds=['INBOX'], maxResults=500,
            pageToken=next_page_token
        ), 'list')
        ids.extend(m['id'] for m in results.get('messages', []))
        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            # Sayfalama sırasında yeni mail gelirse aynı id iki sayfada görünebilir.
            return list(dict.fromkeys(ids))


# Tarama sürerken silinen bir mail 404 döner; bu, bütün taramayı düşürmemeli.
SKIPPABLE_STATUSES = {400, 404}


def run_batched(service, ids, make_request, sleep=time.sleep, method='get'):
    """make_request(id) isteklerini BATCH_SIZE'lık batch'lerle çalıştırır.

    Her id için bir kez (id, yanıt) üretir; yanıt None ise mail artık yok (404/400).
    Hız sınırına takılanlar (tek istek ya da batch'in tamamı) bekleyip yeniden denenir;
    ilerleme olan turlarda deneme sayacı sıfırlanır.
    """
    pending = list(dict.fromkeys(ids))  # aynı request_id iki kez eklenirse batch KeyError verir
    attempt = 0
    while pending:
        retry = []
        progressed = False
        for i in range(0, len(pending), BATCH_SIZE):
            chunk = pending[i:i + BATCH_SIZE]
            finished, failed = [], []

            def callback(request_id, response, exception):
                if exception is None:
                    finished.append((request_id, response))
                elif isinstance(exception, HttpError) and exception.status_code in SKIPPABLE_STATUSES:
                    finished.append((request_id, None))
                elif _is_retryable(exception):
                    failed.append(request_id)
                else:
                    raise exception

            quota.spend(QUOTA_UNITS[method] * len(chunk))  # batch kotayı azaltmaz: her çağrı ayrı sayılır
            batch = service.new_batch_http_request(callback=callback)
            for msg_id in chunk:
                batch.add(make_request(msg_id), request_id=msg_id)
            try:
                batch.execute()
            except HttpError as e:
                if not _is_retryable(e):
                    raise
                done_ids = {request_id for request_id, _ in finished}
                failed = [msg_id for msg_id in chunk if msg_id not in done_ids]

            if finished:
                progressed = True
                yield from finished
            if failed:
                retry.extend(failed)
                if i + BATCH_SIZE < len(pending):
                    sleep(1)  # kota dolmuş; sıradaki batch'i hemen göndermeyelim

        if retry:
            attempt = 1 if progressed else attempt + 1
            if attempt >= MAX_ATTEMPTS:
                raise RuntimeError(f'{len(retry)} mail Gmail hız sınırı yüzünden {MAX_ATTEMPTS} denemede alınamadı.')
            sleep(2 ** (attempt - 1))
        pending = list(dict.fromkeys(retry))


def fetch_metadata(service, ids, headers, sleep=time.sleep):
    messages = service.users().messages()
    return run_batched(service, ids, lambda msg_id: messages.get(
        userId='me', id=msg_id, format='metadata', metadataHeaders=headers
    ), sleep)



def extract_senders(service, progress=lambda processed, total: None, sleep=time.sleep, id_index=None):
    """Gelen kutusunu tarar; {adres: {'ad', 'mail_sayisi', 'kategori', 'abonelik'}} döner.

    id_index verilirse {adres: [mail id]} ile doldurulur; silme sırasında bu mailler için
    From adresini yeniden okumak (her biri 20 kota birimi) gerekmez.
    """
    ids = list_inbox_ids(service)
    total = len(ids)
    progress(0, total)

    tally = SenderTally()
    fetched = fetch_metadata(service, ids, ['From', 'List-Unsubscribe'], sleep)
    for processed, (msg_id, msg_data) in enumerate(fetched, start=1):
        if msg_data is None:  # tarama sırasında silinmiş
            progress(processed, total)
            continue
        headers = message_headers(msg_data)
        if 'from' in headers:
            key, name = sender_key(headers['from'])
            has_unsubscribe = bool(headers.get('list-unsubscribe'))
            tally.add_counted(key, name, 1,
                              category=message_category(msg_data.get('labelIds'), has_unsubscribe),
                              has_unsubscribe=has_unsubscribe)
            if id_index is not None:
                id_index.setdefault(key, []).append(msg_id)
        progress(processed, total)

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


if __name__ == '__main__':
    service = gmail_auth.get_service()
    senders = extract_senders(service, progress=print_progress)
    print()
    save_to_csv(senders)
