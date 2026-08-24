from collections import Counter
import csv

import gmail_auth


def extract_senders(service):
    senders = Counter()
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
                if h['name'] == 'From':
                    senders[h['value']] += 1

            processed += 1
            print_progress(processed, total_estimate)

        next_page_token = results.get('nextPageToken')
        if not next_page_token:
            break

    print()
    return senders


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
        writer.writerow(['İsim/Adres', 'Mail Sayısı'])
        for sender, count in senders.most_common():
            writer.writerow([sender, count])
    print(f"{len(senders)} benzersiz gönderen '{filename}' dosyasına yazıldı.")

if __name__ == '__main__':
    service = gmail_auth.get_service()
    senders = extract_senders(service)
    save_to_csv(senders)
