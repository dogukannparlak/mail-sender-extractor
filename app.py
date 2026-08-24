import os
import re
import csv
from functools import wraps

import requests
from flask import Flask, jsonify, request, render_template
from googleapiclient.errors import HttpError

from gmail_auth import get_service
from extract_senders import extract_senders, save_to_csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, 'gonderenler.csv')

app = Flask(__name__)


def _senders_payload(counts):
    """Counter veya (gonderen, sayi) çiftlerinden frontend'in beklediği düz listeyi üretir."""
    items = counts.most_common() if hasattr(counts, 'most_common') else list(counts)
    gonderenler = [{'gonderen': sender, 'mail_sayisi': count} for sender, count in items]
    return {
        'toplam_mail_sayisi': sum(g['mail_sayisi'] for g in gonderenler),
        'gonderenler': gonderenler,
    }


def read_senders_csv():
    if not os.path.exists(CSV_PATH):
        return {'toplam_mail_sayisi': 0, 'gonderenler': []}
    rows = []
    with open(CSV_PATH, encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # başlık satırı
        for row in reader:
            if len(row) >= 2 and str(row[1]).strip().isdigit():
                rows.append((row[0], int(row[1])))
    return _senders_payload(rows)


def handle_errors(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except FileNotFoundError as e:
            return jsonify({'error': str(e)}), 500
        except HttpError as e:
            message = f'Gmail API hatası ({e.status_code}): {e.reason}'
            if e.status_code == 403:
                message += (' Yetki (scope) sorunu olabilir; token.json dosyasını silip '
                             'uygulamayı yeniden başlatarak tekrar giriş yapmayı deneyin.')
            return jsonify({'error': message}), 502
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return wrapper


def _validated_senders(body):
    senders = (body or {}).get('senders')
    if not isinstance(senders, list):
        raise ValueError("İstek gövdesinde 'senders' adında bir liste bekleniyor.")
    return senders


def extract_email(sender):
    match = re.search(r'<(.+?)>', sender)
    return match.group(1) if match else sender.strip()


def find_message_ids(service, email):
    ids = []
    next_page_token = None
    while True:
        resp = service.users().messages().list(
            userId='me', q=f'from:{email}', maxResults=500,
            pageToken=next_page_token
        ).execute()
        ids.extend(m['id'] for m in resp.get('messages', []))
        next_page_token = resp.get('nextPageToken')
        if not next_page_token:
            break
    return ids


# Bir gönderenin en yeni maili çoğu zaman işlemsel (sipariş/onay) olur ve
# List-Unsubscribe başlığı taşımaz; bülten mailleri birkaç mail geride olabilir.
# Bu yüzden tek mail yerine en yeni birkaç maile bakıyoruz.
UNSUBSCRIBE_SCAN_LIMIT = 15


def _read_unsubscribe_headers(service, msg_id):
    msg = service.users().messages().get(
        userId='me', id=msg_id, format='metadata',
        metadataHeaders=['List-Unsubscribe', 'List-Unsubscribe-Post']
    ).execute()
    # Başlık adı büyük/küçük harf duyarlı olmamalı (List-Unsubscribe vs list-unsubscribe).
    headers = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}
    return headers.get('list-unsubscribe'), headers.get('list-unsubscribe-post', '')


def find_unsubscribe_info(service, email):
    resp = service.users().messages().list(
        userId='me', q=f'from:{email}', maxResults=UNSUBSCRIBE_SCAN_LIMIT
    ).execute()
    messages = resp.get('messages', [])
    if not messages:
        return {'status': 'not_found'}

    list_unsub = None
    list_unsub_post = ''
    for m in messages:
        candidate, candidate_post = _read_unsubscribe_headers(service, m['id'])
        if candidate:
            list_unsub, list_unsub_post = candidate, candidate_post
            break

    if not list_unsub:
        return {'status': 'none'}

    urls = re.findall(r'<([^>]+)>', list_unsub)
    if not urls:  # bazı gönderenler <> kullanmadan düz adres yazar
        urls = [u.strip() for u in list_unsub.split(',') if u.strip()]
    http_url = next((u for u in urls if u.startswith('http')), None)
    mailto_url = next((u for u in urls if u.startswith('mailto:')), None)

    if http_url and 'one-click' in list_unsub_post.lower():
        try:
            r = requests.post(http_url, data={'List-Unsubscribe': 'One-Click'}, timeout=10)
            if r.ok:
                return {'status': 'done', 'url': http_url}
            return {'status': 'manual_link', 'url': http_url}
        except requests.RequestException:
            return {'status': 'manual_link', 'url': http_url}

    if http_url:
        return {'status': 'manual_link', 'url': http_url}
    if mailto_url:
        return {'status': 'manual_mailto', 'url': mailto_url}
    return {'status': 'none'}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/senders')
@handle_errors
def api_senders():
    return jsonify(read_senders_csv())


@app.route('/api/scan', methods=['POST'])
@handle_errors
def api_scan():
    service = get_service()
    counts = extract_senders(service)
    save_to_csv(counts, filename=CSV_PATH)
    return jsonify(_senders_payload(counts))


@app.route('/api/delete', methods=['POST'])
@handle_errors
def api_delete():
    senders = _validated_senders(request.get_json(silent=True))
    service = get_service()

    results = []
    total = 0
    for sender in senders:
        email = extract_email(sender)
        message_ids = find_message_ids(service, email)

        for i in range(0, len(message_ids), 1000):
            chunk = message_ids[i:i + 1000]
            service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': chunk,
                    'addLabelIds': ['TRASH'],
                    'removeLabelIds': ['INBOX', 'UNREAD'],
                }
            ).execute()

        results.append({'sender': sender, 'email': email, 'deleted': len(message_ids)})
        total += len(message_ids)

    return jsonify({'total_deleted': total, 'details': results})


@app.route('/api/preview', methods=['POST'])
@handle_errors
def api_preview():
    body = request.get_json(silent=True) or {}
    sender = body.get('sender')
    if not isinstance(sender, str) or not sender.strip():
        raise ValueError("İstek gövdesinde 'sender' adında bir metin bekleniyor.")

    email = extract_email(sender)
    service = get_service()
    resp = service.users().messages().list(
        userId='me', q=f'from:{email}', maxResults=5
    ).execute()

    previews = []
    for m in resp.get('messages', []):
        msg = service.users().messages().get(
            userId='me', id=m['id'], format='metadata',
            metadataHeaders=['Subject']
        ).execute()
        headers = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}
        internal = msg.get('internalDate')
        previews.append({
            'subject': headers.get('subject', '(konu yok)'),
            'date': int(internal) if internal else None,
            'snippet': msg.get('snippet', ''),
        })

    return jsonify({'sender': sender, 'email': email, 'previews': previews})


@app.route('/api/unsubscribe', methods=['POST'])
@handle_errors
def api_unsubscribe():
    senders = _validated_senders(request.get_json(silent=True))
    service = get_service()

    results = []
    for sender in senders:
        email = extract_email(sender)
        info = find_unsubscribe_info(service, email)
        results.append({'sender': sender, 'email': email, **info})

    return jsonify({'results': results})


if __name__ == '__main__':
    app.run(debug=True, port=5050, threaded=True)
