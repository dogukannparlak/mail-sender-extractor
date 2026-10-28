from collections import Counter
import csv
import re
from email.utils import parseaddr

import gmail_auth

# Gmail arama sözdizimine sızabilecek karakterler (boşluk, tırnak, parantez, ':') adreste olamaz.
EMAIL_RE = re.compile(r'^[^@\s"()<>,;:\\\[\]]+@[\w-]+(\.[\w-]+)+$')

CSV_HEADER = ['Adres', 'Ad', 'Mail Sayısı']
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


class SenderTally:
    """Gönderen başına mail sayısını ve en sık görülen adı toplar."""

    def __init__(self):
        self._counts = Counter()
        self._names = {}

    def add(self, header):
        key, name = sender_key(header)
        self.add_counted(key, name, 1)

    def add_counted(self, key, name, count):
        self._counts[key] += count
        if name:
            self._names.setdefault(key, Counter())[name] += count

    def result(self):
        return {
            key: {
                'ad': self._names[key].most_common(1)[0][0] if key in self._names else '',
                'mail_sayisi': count,
            }
            for key, count in self._counts.most_common()
        }


def extract_senders(service):
    tally = SenderTally()
    next_page_token = None
    processed = 0

    label = service.users().labels().get(userId='me', id='INBOX').execute()
    total_estimate = label.get('messagesTotal', 0)

    while True:
        results = service.users().messages().list(
            userId='me', labelIds=['INBOX'], maxResults=500,
            pageToken=next_page_token
        ).execute()

        messages = results.get('messages', [])
        for msg in messages:
            msg_data = service.users().messages().get(
                userId='me', id=msg['id'],
                format='metadata', metadataHeaders=['From']
            ).execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            for h in headers:
                if h['name'].lower() == 'from':
                    tally.add(h['value'])

            processed += 1
            print_progress(processed, total_estimate)

        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            break

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
            writer.writerow([address, info['ad'], info['mail_sayisi']])
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
                tally.add_counted(row[0], row[1], int(row[2]))
    return tally.result()


if __name__ == '__main__':
    service = gmail_auth.get_service()
    senders = extract_senders(service)
    save_to_csv(senders)
