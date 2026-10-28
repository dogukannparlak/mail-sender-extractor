import os
import re
import json
import socket
import ipaddress
import threading
import time
from email.utils import parseaddr
from functools import wraps
from urllib.parse import urlparse

from urllib3.util import parse_url
from urllib3.exceptions import LocationParseError

import requests
from flask import Flask, jsonify, request, render_template
from googleapiclient.errors import HttpError

from gmail_auth import get_service
from contextlib import contextmanager

from extract_senders import EMAIL_RE, extract_senders, load_csv, run_batched, save_to_csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, 'gonderenler.csv')
PROTECTED_PATH = os.path.join(BASE_DIR, 'korunanlar.json')
UNDO_PATH = os.path.join(BASE_DIR, 'son_islem.json')

app = Flask(__name__)

# DNS rebinding'e karşı: tarayıcı başka bir alan adıyla gelirse istekleri reddet.
ALLOWED_HOSTNAMES = {'localhost', '127.0.0.1', '[::1]'}


@app.before_request
def reject_foreign_host():
    hostname = re.sub(r':\d+$', '', request.host or '')
    if hostname not in ALLOWED_HOSTNAMES:
        return jsonify({'error': 'Bu uygulamaya yalnız localhost üzerinden erişilebilir.'}), 403
    # Host doğru olsa da başka bir site no-cors POST atabilir (ör. /api/scan).
    if request.method == 'POST':
        if request.headers.get('Sec-Fetch-Site', 'same-origin') not in ('same-origin', 'none'):
            return jsonify({'error': 'Başka sitelerden gelen istekler kabul edilmiyor.'}), 403
        origin = request.headers.get('Origin')
        if origin and urlparse(origin).hostname not in {h.strip('[]') for h in ALLOWED_HOSTNAMES}:
            return jsonify({'error': 'Başka sitelerden gelen istekler kabul edilmiyor.'}), 403


def _senders_payload(senders):
    """{adres: {'ad', 'mail_sayisi', ...}} sözlüğünden frontend'in beklediği düz listeyi üretir.

    `gonderen` alanı adrestir; API'ye geri gönderilen kimlik budur.
    """
    gonderenler = [
        {'gonderen': address, **info}
        for address, info in sorted(senders.items(), key=lambda kv: -kv[1]['mail_sayisi'])
    ]
    return {
        'toplam_mail_sayisi': sum(g['mail_sayisi'] for g in gonderenler),
        'gonderenler': gonderenler,
    }


def load_saved_senders():
    return load_csv(CSV_PATH) if os.path.exists(CSV_PATH) else {}


def read_senders_csv():
    return _senders_payload(load_saved_senders())


# CSV'yi oku-değiştir-yaz yapan işlemler (iki sekmeden silme, geri alma) birbirini ezmesin.
_csv_lock = threading.Lock()


def remove_senders_from_csv(senders):
    """Çöpe taşınan gönderenleri kayıtlı listeden çıkarır; sayfa yenilenince geri gelmesinler."""
    if not senders:
        return
    with _csv_lock:
        if not os.path.exists(CSV_PATH):
            return
        removed = set(senders)
        remaining = {k: v for k, v in load_saved_senders().items() if k not in removed}
        save_to_csv(remaining, filename=CSV_PATH)


class Busy(Exception):
    """Tarama ile silme/geri alma aynı anda çalışmasın (tarama sonucu silineni geri yazardı)."""


def _http_error_message(e):
    message = f'Gmail API hatası ({e.status_code}): {e.reason}'
    if e.status_code == 403:
        message += (' Yetki (scope) sorunu olabilir; token.json dosyasını silip '
                    'uygulamayı yeniden başlatarak tekrar giriş yapmayı deneyin.')
    return message


def handle_errors(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Busy as e:
            return jsonify({'error': str(e)}), 409
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except FileNotFoundError as e:
            return jsonify({'error': str(e)}), 500
        except HttpError as e:
            return jsonify({'error': _http_error_message(e)}), 502
        except Exception:
            app.logger.exception('Beklenmeyen hata')
            return jsonify({'error': 'Beklenmeyen bir hata oluştu; ayrıntı sunucu konsolunda.'}), 500
    return wrapper


def _validated_senders(body):
    senders = (body or {}).get('senders')
    if not isinstance(senders, list):
        raise ValueError("İstek gövdesinde 'senders' adında bir liste bekleniyor.")
    return senders


def extract_email(sender):
    # From başlığını gönderen yazar; adres doğrulanmadan Gmail sorgusuna girerse
    # "x@y.com OR label:inbox" gibi bir değer bütün gelen kutusunu eşleştirir.
    _, email = parseaddr(sender)
    if not EMAIL_RE.match(email):
        raise ValueError(f'Geçersiz gönderen adresi: {sender!r}')
    return email


# Tarama yalnız gelen kutusunu sayar; "all" arşivdeki mailleri de kapsar.
# Gmail'in from: araması çöp ve spam kutusunu zaten dışarıda bırakır.
SCOPE_QUERIES = {'inbox': ' in:inbox', 'all': ''}


def _validated_scope(body):
    scope = (body or {}).get('scope', 'inbox')
    if scope not in SCOPE_QUERIES:
        raise ValueError("'scope' yalnız 'inbox' ya da 'all' olabilir.")
    return scope


# Korunan gönderenler (banka, okul...): seçilemez, silinemez, abonelikten çıkılamaz.
# Alan adı girdisi ("@garanti.com.tr") alt alan adlarını da kapsar.
DOMAIN_RE = re.compile(r'^@[\w-]+(\.[\w-]+)+$')


def _write_json(path, payload):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_protected():
    if not os.path.exists(PROTECTED_PATH):
        return {'adresler': [], 'alanlar': []}
    with open(PROTECTED_PATH, encoding='utf-8') as f:
        stored = json.load(f)
    return {'adresler': sorted(stored.get('adresler', [])), 'alanlar': sorted(stored.get('alanlar', []))}


def is_protected(email, protected):
    email = email.lower()
    domain = email.rsplit('@', 1)[-1]
    if email in protected['adresler']:
        return True
    return any(domain == d[1:] or domain.endswith('.' + d[1:]) for d in protected['alanlar'])


def reject_protected(emails):
    protected = load_protected()
    blocked = [email for email in emails if is_protected(email, protected)]
    if blocked:
        raise ValueError('Korunan gönderenlere işlem yapılamaz: ' + ', '.join(blocked))


def from_query(email, scope='all', extra=''):
    return f'from:"{email}"' + SCOPE_QUERIES[scope] + extra


def find_message_ids(service, email, scope='all', extra=''):
    ids = []
    next_page_token = None
    while True:
        resp = service.users().messages().list(
            userId='me', q=from_query(email, scope, extra), maxResults=500,
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
    # urlparse ile requests (urllib3) URL'yi farklı ayrıştırabilir:
    # "https://127.0.0.1\\@x.com/" urlparse'a göre x.com, requests'e göre 127.0.0.1.
    # Kimlik bilgisi/ters eğik çizgi içeren URL'leri reddedip iki ayrıştırıcının
    # aynı host'u görmesini şart koşuyoruz.
    if '\\' in url:
        return False
    parsed = urlparse(url)
    try:
        u3 = parse_url(url)
    except LocationParseError:
        return False
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or u3.auth:
        return False
    if (u3.host or '').strip('[]').lower() != parsed.hostname.lower():
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


def find_unsubscribe_info(service, email, confirm_one_click=False):
    """confirm_one_click=False iken hiçbir isteği göndermez; one-click mümkünse bunu bildirir.

    Tek tıkla çıkış geri alınamaz, bu yüzden POST yalnız kullanıcı onayından sonra gider.
    """
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
        if not confirm_one_click:
            return {'status': 'one_click_available', 'url': http_url}
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


# Tarama binlerce mailde dakikalar sürer; arka planda çalışır, arayüz durumu sorar.
_scan_lock = threading.Lock()
_scan_state = {'running': False, 'processed': 0, 'total': 0, 'error': None, 'finished_at': None}
_active_mutations = 0


@contextmanager
def _mutation():
    global _active_mutations
    with _scan_lock:
        if _scan_state['running']:
            raise Busy('Tarama sürerken silme ya da geri alma yapılamaz; tarama bitince tekrar dene.')
        _active_mutations += 1
    try:
        yield
    finally:
        with _scan_lock:
            _active_mutations -= 1


def _update_scan(**changes):
    with _scan_lock:
        _scan_state.update(changes)


def _run_scan(service):
    try:
        senders = extract_senders(service, progress=lambda done, total: _update_scan(processed=done, total=total))
        with _csv_lock:
            save_to_csv(senders, filename=CSV_PATH)
        _update_scan(error=None)
    except HttpError as e:
        _update_scan(error=_http_error_message(e))
    except Exception:
        app.logger.exception('Tarama hatası')
        _update_scan(error='Tarama sırasında beklenmeyen bir hata oluştu; ayrıntı sunucu konsolunda.')
    finally:
        _update_scan(running=False, finished_at=time.time())


@app.route('/api/scan', methods=['POST'])
@handle_errors
def api_scan():
    with _scan_lock:
        if _scan_state['running']:
            return jsonify({'error': 'Tarama zaten sürüyor.', **_scan_state}), 409
        if _active_mutations:
            return jsonify({'error': 'Silme ya da geri alma sürüyor; bitince tekrar dene.', **_scan_state}), 409
        _scan_state.update(running=True, processed=0, total=0, error=None, finished_at=None)
    try:
        service = get_service()  # giriş/kimlik hataları isteğin kendisinde dönsün
    except Exception:
        _update_scan(running=False)
        raise
    threading.Thread(target=_run_scan, args=(service,), daemon=True).start()
    return jsonify(api_scan_status().get_json()), 202


@app.route('/api/scan/status')
def api_scan_status():
    with _scan_lock:
        return jsonify(dict(_scan_state))


@app.route('/api/protected')
@handle_errors
def api_protected():
    return jsonify(load_protected())


@app.route('/api/protected', methods=['POST'])
@handle_errors
def api_protected_update():
    body = request.get_json(silent=True) or {}
    value = body.get('value')
    if not isinstance(value, str):
        raise ValueError("İstek gövdesinde 'value' adında bir metin bekleniyor.")
    value = value.strip().lower()
    if DOMAIN_RE.match(value):
        field = 'alanlar'
    elif EMAIL_RE.match(value):
        field = 'adresler'
    else:
        raise ValueError(f'Geçersiz adres ya da alan adı: {value!r} (alan adı için "@ornek.com" yaz).')

    protected = load_protected()
    entries = set(protected[field])
    if body.get('protected', True):
        entries.add(value)
    else:
        entries.discard(value)
    protected[field] = sorted(entries)
    _write_json(PROTECTED_PATH, protected)
    return jsonify(protected)


@app.route('/api/count', methods=['POST'])
@handle_errors
def api_count():
    """Silme onayında gösterilecek gerçek eşleşme sayısı (taramadaki sayı yalnız gelen kutusu)."""
    body = request.get_json(silent=True)
    senders = _validated_senders(body)
    scope = _validated_scope(body)
    emails = [extract_email(sender) for sender in senders]
    service = get_service()

    details = [
        {'sender': sender, 'email': email, 'count': len(find_message_ids(service, email, scope))}
        for sender, email in zip(senders, emails)
    ]
    return jsonify({'scope': scope, 'total': sum(d['count'] for d in details), 'details': details})


def _batch_modify(service, ids, add=(), remove=()):
    for i in range(0, len(ids), 1000):
        service.users().messages().batchModify(
            userId='me',
            body={'ids': ids[i:i + 1000], 'addLabelIds': list(add), 'removeLabelIds': list(remove)}
        ).execute()


@app.route('/api/delete', methods=['POST'])
@handle_errors
def api_delete():
    body = request.get_json(silent=True)
    senders = _validated_senders(body)
    scope = _validated_scope(body)
    # Hepsini önce doğrula: geçersiz bir adres yüzünden işlem yarıda kalmasın.
    emails = [extract_email(sender) for sender in senders]
    reject_protected(emails)
    with _mutation():
        return _delete(senders, emails, scope)


def _delete(senders, emails, scope):
    service = get_service()
    saved = load_saved_senders()
    # Geri alma için her mailin çöpe gitmeden önceki INBOX/UNREAD durumu saklanır;
    # "tüm mailler"de arşivdeki mailler geri alınınca gelen kutusuna düşmemeli.
    undo = {'zaman': time.time(), 'scope': scope, 'ids': [], 'inbox': [], 'unread': [], 'gonderenler': {}}
    results = []
    total = 0
    finished = []
    try:
        for sender, email in zip(senders, emails):
            message_ids = find_message_ids(service, email, scope)
            if message_ids:
                in_scope = set(message_ids)
                inbox_ids = message_ids if scope == 'inbox' else [
                    i for i in find_message_ids(service, email, 'inbox') if i in in_scope]
                unread_ids = [i for i in find_message_ids(service, email, scope, ' is:unread') if i in in_scope]
                undo['ids'] += message_ids
                undo['inbox'] += inbox_ids
                undo['unread'] += unread_ids
                undo['gonderenler'][email.lower()] = saved.get(email.lower())
                # Çöpe taşımadan önce yaz: işlem yarıda kesilirse taşınanlar yine geri alınabilsin.
                _write_json(UNDO_PATH, undo)
                _batch_modify(service, message_ids, add=['TRASH'], remove=['INBOX', 'UNREAD'])

            finished.append(email.lower())
            results.append({'sender': sender, 'email': email, 'deleted': len(message_ids)})
            total += len(message_ids)
    finally:
        remove_senders_from_csv(finished)
    return jsonify({'scope': scope, 'total_deleted': total, 'details': results})


def load_undo():
    if not os.path.exists(UNDO_PATH):
        return None
    with open(UNDO_PATH, encoding='utf-8') as f:
        return json.load(f)


@app.route('/api/undo')
@handle_errors
def api_undo_info():
    undo = load_undo()
    if not undo:
        return jsonify({'available': False})
    return jsonify({'available': True, 'zaman': undo['zaman'], 'count': len(undo['ids']),
                    'senders': sorted(undo['gonderenler'])})


@app.route('/api/undo', methods=['POST'])
@handle_errors
def api_undo():
    """Son silme işlemini geri alır: çöpten çıkarır, INBOX/UNREAD etiketlerini eski haline getirir."""
    with _mutation():
        return _undo()


def _undo():
    undo = load_undo()
    if not undo:
        raise ValueError('Geri alınacak bir silme işlemi yok.')
    service = get_service()
    # Resmi yol messages.untrash; çöp boşaltılmışsa ya da 30 gün geçmişse mail 404 döner, atlanır.
    messages = service.users().messages()
    restored = {msg_id for msg_id, resp in run_batched(
        service, undo['ids'], lambda msg_id: messages.untrash(userId='me', id=msg_id)) if resp is not None}
    _batch_modify(service, [i for i in undo['inbox'] if i in restored], add=['INBOX'])
    _batch_modify(service, [i for i in undo['unread'] if i in restored], add=['UNREAD'])

    with _csv_lock:
        if os.path.exists(CSV_PATH):
            senders = load_saved_senders()
            for address, info in undo['gonderenler'].items():
                if info and address not in senders:
                    senders[address] = info
            save_to_csv(senders, filename=CSV_PATH)
    os.remove(UNDO_PATH)
    return jsonify({'restored': len(restored), 'missing': len(set(undo['ids']) - restored),
                    'senders': sorted(undo['gonderenler'])})


@app.route('/api/preview', methods=['POST'])
@handle_errors
def api_preview():
    body = request.get_json(silent=True) or {}
    sender = body.get('sender')
    if not isinstance(sender, str) or not sender.strip():
        raise ValueError("İstek gövdesinde 'sender' adında bir metin bekleniyor.")

    scope = _validated_scope(body)
    email = extract_email(sender)
    service = get_service()
    resp = service.users().messages().list(
        userId='me', q=from_query(email, scope), maxResults=5
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
    body = request.get_json(silent=True)
    senders = _validated_senders(body)
    confirm_one_click = (body or {}).get('confirm_one_click') is True
    emails = [extract_email(sender) for sender in senders]
    reject_protected(emails)
    service = get_service()

    results = []
    for sender, email in zip(senders, emails):
        info = find_unsubscribe_info(service, email, confirm_one_click)
        results.append({'sender': sender, 'email': email, **info})

    return jsonify({'results': results})


if __name__ == '__main__':
    if os.environ.get('DEMO') == '1':
        import sys
        import demo
        demo.enable(sys.modules[__name__])
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1', port=5050, threaded=True)
