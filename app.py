import os
import re
import csv
import socket
from collections import Counter
import ipaddress
from email.utils import parseaddr
from functools import wraps
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, request, render_template
from googleapiclient.errors import HttpError

from gmail_auth import get_service
from extract_senders import extract_senders, save_to_csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, 'gonderenler.csv')

app = Flask(__name__)

# DNS rebinding'e karşı: tarayıcı başka bir alan adıyla gelirse istekleri reddet.
ALLOWED_HOSTNAMES = {'localhost', '127.0.0.1', '[::1]'}


@app.before_request
def reject_foreign_host():
    hostname = re.sub(r':\d+$', '', request.host or '')
    if hostname not in ALLOWED_HOSTNAMES:
        return jsonify({'error': 'Bu uygulamaya yalnız localhost üzerinden erişilebilir.'}), 403


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


def remove_senders_from_csv(senders):
    """Çöpe taşınan gönderenleri kayıtlı listeden çıkarır; sayfa yenilenince geri gelmesinler."""
    if not os.path.exists(CSV_PATH):
        return
    removed = set(senders)
    remaining = Counter({
        g['gonderen']: g['mail_sayisi']
        for g in read_senders_csv()['gonderenler']
        if g['gonderen'] not in removed
    })
    save_to_csv(remaining, filename=CSV_PATH)


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
        except Exception:
            app.logger.exception('Beklenmeyen hata')
            return jsonify({'error': 'Beklenmeyen bir hata oluştu; ayrıntı sunucu konsolunda.'}), 500
    return wrapper


def _validated_senders(body):
    senders = (body or {}).get('senders')
    if not isinstance(senders, list):
        raise ValueError("İstek gövdesinde 'senders' adında bir liste bekleniyor.")
    return senders


# Gmail arama sözdizimine sızabilecek karakterler (boşluk, tırnak, parantez, ':') adreste olamaz.
EMAIL_RE = re.compile(r'^[^@\s"()<>,;:\\\[\]]+@[\w-]+(\.[\w-]+)+$')


def extract_email(sender):
    # From başlığını gönderen yazar; adres doğrulanmadan Gmail sorgusuna girerse
    # "x@y.com OR label:inbox" gibi bir değer bütün gelen kutusunu eşleştirir.
    _, email = parseaddr(sender)
    if not EMAIL_RE.match(email):
        raise ValueError(f'Geçersiz gönderen adresi: {sender!r}')
    return email


def from_query(email):
    return f'from:"{email}"'


def find_message_ids(service, email):
    ids = []
    next_page_token = None
    while True:
        resp = service.users().messages().list(
            userId='me', q=from_query(email), maxResults=500,
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


def _resolve_host(hostname):
    return {info[4][0] for info in socket.getaddrinfo(hostname, 443)}


def is_safe_one_click_url(url):
    """One-click isteği sunucudan gider; yerel ağa/loopback'e istek atılmasını engeller."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        return False
    try:
        addresses = _resolve_host(parsed.hostname)
    except (socket.gaierror, UnicodeError):
        return False
    for addr in addresses:
        ip = ipaddress.ip_address(addr.split('%')[0])
        if not ip.is_global:
            return False
    return bool(addresses)


def find_unsubscribe_info(service, email):
    resp = service.users().messages().list(
        userId='me', q=from_query(email), maxResults=UNSUBSCRIBE_SCAN_LIMIT
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

    if http_url and 'one-click' in list_unsub_post.lower() and is_safe_one_click_url(http_url):
        try:
            r = requests.post(http_url, data={'List-Unsubscribe': 'One-Click'},
                              timeout=10, allow_redirects=False)
            if r.ok and not r.is_redirect:
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
    # Hepsini önce doğrula: geçersiz bir adres yüzünden işlem yarıda kalmasın.
    emails = [extract_email(sender) for sender in senders]
    service = get_service()

    results = []
    total = 0
    for sender, email in zip(senders, emails):
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

    remove_senders_from_csv(senders)
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
        userId='me', q=from_query(email), maxResults=5
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
    emails = [extract_email(sender) for sender in senders]
    service = get_service()

    results = []
    for sender, email in zip(senders, emails):
        info = find_unsubscribe_info(service, email)
        results.append({'sender': sender, 'email': email, **info})

    return jsonify({'results': results})


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1', port=5050, threaded=True)
