import os
import re
import json
import shutil
import socket
import ipaddress
import threading
import time
from contextlib import contextmanager
from email.utils import parseaddr
from functools import wraps
from urllib.parse import urlparse

from urllib3.util import parse_url
from urllib3.exceptions import LocationParseError

import requests
from flask import Flask, jsonify, request, render_template
from googleapiclient.errors import HttpError

import gmail_auth
from google.auth.exceptions import RefreshError

from extract_senders import (EMAIL_RE, extract_senders, fetch_metadata, from_address, gmail_execute, load_csv,
                             message_headers, run_batched, save_to_csv)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Her Gmail hesabının token'ı ve verileri ayrı klasörde: hesaplar/<adres>/.
ACCOUNTS_DIR = os.path.join(BASE_DIR, 'hesaplar')
# Korunanlar bütün hesaplar için ortak: banka iki hesapta da korunsun.
PROTECTED_PATH = os.path.join(BASE_DIR, 'korunanlar.json')
# Çoklu hesaptan önceki tek hesaplı düzen; ilk açılışta hesabın klasörüne taşınır.
LEGACY_TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')
LEGACY_DATA_FILES = ('gonderenler.csv', 'taranan_idler.json', 'son_islem.json')
DEMO_MODE = False

app = Flask(__name__)

ALLOWED_HOSTNAMES = {'localhost', '127.0.0.1', '[::1]'}


@app.before_request
def reject_foreign_host():
    """Uygulama yalnız bu bilgisayardaki tarayıcıdan kullanılsın.

    - Host kontrolü: DNS rebinding ile başka bir alan adından gelen istekleri reddeder.
    - POST'ta Sec-Fetch-Site / Origin: başka bir sitenin arka planda attığı istekleri (CSRF) reddeder.
    """
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


# --- Hesaplar ----------------------------------------------------------------

class AccountPaths:
    """Bir hesabın dosyaları. Klasör adı hesabın adresidir (EMAIL_RE'den geçmiş, küçük harf)."""

    def __init__(self, account):
        self.account = account
        self.root = os.path.join(ACCOUNTS_DIR, account)
        self.token = os.path.join(self.root, 'token.json')
        self.csv = os.path.join(self.root, 'gonderenler.csv')
        self.undo = os.path.join(self.root, 'son_islem.json')
        # Taramada görülen mail id'leri (gönderen başına); silmede bu maillerin From'unu yeniden okumayız.
        self.scan_ids = os.path.join(self.root, 'taranan_idler.json')


def list_accounts():
    if not os.path.isdir(ACCOUNTS_DIR):
        return []
    return sorted(name for name in os.listdir(ACCOUNTS_DIR)
                  if EMAIL_RE.match(name) and os.path.exists(AccountPaths(name).token))


def get_service(account):
    return gmail_auth.get_service(AccountPaths(account).token)


def migrate_legacy_account():
    """Tek hesaplı sürümden kalan token.json ve veri dosyalarını hesabın klasörüne taşır.

    Hesabın adresi Gmail'den (getProfile) öğrenilir; ağ yoksa taşıma yapılmaz, sonra tekrar denenir.
    """
    if not os.path.exists(LEGACY_TOKEN_PATH):
        return None
    account = gmail_auth.account_email(gmail_auth.get_service(LEGACY_TOKEN_PATH))
    paths = AccountPaths(account)
    os.makedirs(paths.root, mode=0o700, exist_ok=True)
    for name in LEGACY_DATA_FILES:
        source = os.path.join(BASE_DIR, name)
        if os.path.exists(source) and not os.path.exists(os.path.join(paths.root, name)):
            shutil.move(source, os.path.join(paths.root, name))
    if os.path.exists(paths.token):
        os.remove(LEGACY_TOKEN_PATH)  # aynı hesap zaten eklenmiş; eski kopya gereksiz
    else:
        shutil.move(LEGACY_TOKEN_PATH, paths.token)
    return account


def _current_paths(body=None):
    """İstekteki hesabın dosyaları. Tek hesap varsa account alanı verilmese de o hesap kullanılır."""
    account = request.args.get('account') or (body if body is not None else _json_body()).get('account')
    accounts = list_accounts()
    if not account:
        if len(accounts) == 1:
            return AccountPaths(accounts[0])
        raise ValueError('Önce bir Gmail hesabı ekle.' if not accounts else 'Hangi hesapta çalışılacağı belirtilmedi.')
    account = str(account).strip().lower()
    if account not in accounts:
        raise ValueError(f'Bilinmeyen hesap: {account!r}')
    return AccountPaths(account)


# --- Gönderen listesi (CSV) --------------------------------------------------

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


def load_saved_senders(paths):
    return load_csv(paths.csv) if os.path.exists(paths.csv) else {}


# CSV'yi oku-değiştir-yaz yapan işlemler (iki sekmeden silme, geri alma) birbirini ezmesin.
_csv_lock = threading.Lock()


def remove_senders_from_csv(paths, senders):
    """Çöpe taşınan gönderenleri kayıtlı listeden çıkarır; sayfa yenilenince geri gelmesinler."""
    if not senders:
        return
    with _csv_lock:
        if not os.path.exists(paths.csv):
            return
        removed = set(senders)
        remaining = {k: v for k, v in load_saved_senders(paths).items() if k not in removed}
        save_to_csv(remaining, filename=paths.csv)


# --- Hatalar ve istek gövdesi ------------------------------------------------

class Busy(Exception):
    """Tarama ile silme/geri alma aynı anda çalışmasın (tarama sonucu silineni geri yazardı)."""


def _http_error_message(e):
    message = f'Gmail API hatası ({e.status_code}): {e.reason}'
    if e.status_code == 403:
        message += ' Yetki (scope) sorunu olabilir; hesabı çıkarıp yeniden eklemeyi dene.'
    return message


# Google OAuth uygulaması "Testing" durumundaysa yenileme anahtarı birkaç günde sona erebilir.
LOGIN_EXPIRED_MESSAGE = ('Google oturumunun süresi dolmuş ya da izni geri alınmış. '
                         'Hesabı çıkarıp yeniden ekle.')


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
        except RefreshError:
            return jsonify({'error': LOGIN_EXPIRED_MESSAGE}), 401
        except Exception:
            app.logger.exception('Beklenmeyen hata')
            return jsonify({'error': 'Beklenmeyen bir hata oluştu; ayrıntı sunucu konsolunda.'}), 500
    return wrapper


def _json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


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
    scope = body.get('scope', 'inbox')
    if scope not in SCOPE_QUERIES:
        raise ValueError("'scope' yalnız 'inbox' ya da 'all' olabilir.")
    return scope


def _write_json(path, payload, compact=False):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        if compact:  # binlerce id içeren dosyalar (geri alma, tarama dizini)
            json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        else:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# --- Korunan gönderenler -----------------------------------------------------

# Korunan gönderenler (banka, okul...): seçilemez, silinemez, abonelikten çıkılamaz.
# Alan adı girdisi ("@garanti.com.tr") alt alan adlarını da kapsar.
DOMAIN_RE = re.compile(r'^@[\w-]+(\.[\w-]+)+$')


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


# --- Gmail sorguları ---------------------------------------------------------

def from_query(email, scope='all', unread_only=False):
    return f'from:"{email}"' + SCOPE_QUERIES[scope] + (' is:unread' if unread_only else '')


def find_message_ids(service, email, scope='all', unread_only=False):
    ids = []
    next_page_token = None
    while True:
        resp = gmail_execute(service.users().messages().list(
            userId='me', q=from_query(email, scope, unread_only), maxResults=500,
            pageToken=next_page_token
        ), 'list')
        ids.extend(m['id'] for m in resp.get('messages', []))
        next_page_token = resp.get('nextPageToken')
        if not next_page_token:
            break
    return ids


def load_scan_ids(paths):
    if not os.path.exists(paths.scan_ids):
        return {}
    with open(paths.scan_ids, encoding='utf-8') as f:
        return json.load(f)


# /api/count'un doğruladığı id'ler kısa süre saklanır; hemen ardından gelen silme
# aynı doğrulamayı (mail başına 20 kota birimi) ikinci kez yapmasın.
VERIFY_CACHE_SECONDS = 600
_verify_cache = {}
_verify_lock = threading.Lock()


def _clear_verify_cache(account=None):
    with _verify_lock:
        for key in [k for k in _verify_cache if account is None or k[0] == account]:
            del _verify_cache[key]


def verified_message_ids(service, paths, email, scope, scan_ids=None):
    """from: araması kelime bazlıdır; adı ya da benzer bir adresi eşleşen başka gönderenlerin
    mailleri de dönebilir (ör. korunan x@alan.com.tr). Yalnız From adresi birebir aynı olanları,
    korunan bir göndereni de kapsamıyorsa döndürür. İkinci değer: elenen mail sayısı.

    Taramada bu adresten geldiği görülen mailler yeniden okunmaz; yalnız yeni ya da
    arşivdeki mailler için From okunur.
    """
    wanted = email.lower()
    candidates = find_message_ids(service, email, scope)
    if not candidates:
        return [], 0
    cache_key = (paths.account, wanted, scope)
    with _verify_lock:
        cached = _verify_cache.get(cache_key)
    if cached and time.time() - cached['zaman'] < VERIFY_CACHE_SECONDS:
        known_good, known_bad = cached['kept'], cached['dropped']
    else:
        known_good = set((scan_ids if scan_ids is not None else load_scan_ids(paths)).get(wanted, []))
        known_bad = set()

    protected = load_protected()
    unknown = [i for i in candidates if i not in known_good and i not in known_bad]
    for msg_id, msg in fetch_metadata(service, unknown, ['From']):
        address = from_address(msg)
        if address == wanted and not is_protected(address, protected):
            known_good.add(msg_id)
        else:
            known_bad.add(msg_id)
    with _verify_lock:
        _verify_cache[cache_key] = {'zaman': time.time(), 'kept': known_good, 'dropped': known_bad}

    ids = [i for i in candidates if i in known_good]
    return ids, len(candidates) - len(ids)


# --- Abonelikten çıkma -------------------------------------------------------

# Bir gönderenin en yeni maili çoğu zaman işlemsel (sipariş/onay) olur ve
# List-Unsubscribe başlığı taşımaz; bülten mailleri birkaç mail geride olabilir.
# Bu yüzden tek mail yerine en yeni birkaç maile bakıyoruz.
UNSUBSCRIBE_SCAN_LIMIT = 15


def _first_unsubscribe_headers(service, email, ids):
    """En yeniden eskiye, From'u bu adres olan ve List-Unsubscribe taşıyan ilk mailin başlıkları."""
    fetched = dict(fetch_metadata(service, ids, ['From', 'List-Unsubscribe', 'List-Unsubscribe-Post']))
    for msg_id in ids:
        msg = fetched.get(msg_id)
        headers = message_headers(msg)
        # Başka bir gönderenin (adı bu adrese benzeyen) mailindeki link kullanılmasın.
        if headers.get('list-unsubscribe') and from_address(msg) == email.lower():
            return headers['list-unsubscribe'], headers.get('list-unsubscribe-post', '')
    return None, ''


def _resolve_host(hostname):
    return {info[4][0] for info in socket.getaddrinfo(hostname, 443)}


def is_safe_one_click_url(url, resolve=True):
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
    if not resolve:  # onaydan önce DNS sorgusu bile gönderene "çıkmaya çalıştı" bilgisini sızdırır
        return True
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
    resp = gmail_execute(service.users().messages().list(
        userId='me', q=from_query(email), maxResults=UNSUBSCRIBE_SCAN_LIMIT
    ), 'list')
    messages = resp.get('messages', [])
    if not messages:
        return {'status': 'not_found'}

    list_unsub, list_unsub_post = _first_unsubscribe_headers(service, email, [m['id'] for m in messages])
    if not list_unsub:
        return {'status': 'none'}

    urls = re.findall(r'<([^>]+)>', list_unsub)
    if not urls:  # bazı gönderenler <> kullanmadan düz adres yazar
        urls = [u.strip() for u in list_unsub.split(',') if u.strip()]
    http_url = next((u for u in urls if u.startswith('http')), None)
    mailto_url = next((u for u in urls if u.startswith('mailto:')), None)

    if http_url and 'one-click' in list_unsub_post.lower() and is_safe_one_click_url(http_url, resolve=False):
        if not confirm_one_click:
            return {'status': 'one_click_available', 'url': http_url}
        if not is_safe_one_click_url(http_url):
            return {'status': 'manual_link', 'url': http_url}
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


# --- Sayfa ve hesap API'si ---------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html', demo=DEMO_MODE)


@app.route('/api/accounts')
@handle_errors
def api_accounts():
    migrated = migrate_legacy_account()
    return jsonify({'accounts': list_accounts(), 'migrated': migrated, 'demo': DEMO_MODE})


@app.route('/api/accounts/add', methods=['POST'])
@handle_errors
def api_accounts_add():
    if DEMO_MODE:
        raise ValueError('Demo modunda hesap eklenmez; gerçek hesap için uygulamayı DEMO olmadan başlat.')
    # Tarayıcıda Google giriş penceresi açılır; kullanıcı girişi bitirene kadar istek bekler.
    account = gmail_auth.add_account(ACCOUNTS_DIR)
    return jsonify({'account': account, 'accounts': list_accounts()})


@app.route('/api/accounts/remove', methods=['POST'])
@handle_errors
def api_accounts_remove():
    """Hesabın token'ını siler; taranan liste ve geri alma kaydı klasörde kalır (yeniden eklenince döner)."""
    paths = _current_paths()
    with _mutation(paths.account):
        os.remove(paths.token)
    _clear_verify_cache(paths.account)
    return jsonify({'removed': paths.account, 'accounts': list_accounts()})


@app.route('/api/senders')
@handle_errors
def api_senders():
    return jsonify(_senders_payload(load_saved_senders(_current_paths())))


# --- Tarama ------------------------------------------------------------------

# Tarama binlerce mailde dakikalar sürer; arka planda çalışır, arayüz durumu sorar.
# Durum hesap başına tutulur: iki hesap ayrı ayrı taranabilir.
_scan_lock = threading.Lock()
_scans = {}
_mutations = {}


def _scan_state(account):
    """Kilit altında çağrılmalı."""
    return _scans.setdefault(account, {'running': False, 'processed': 0, 'total': 0, 'error': None,
                                       'started_at': None, 'finished_at': None})


@contextmanager
def _mutation(account):
    with _scan_lock:
        if _scan_state(account)['running']:
            raise Busy('Tarama sürerken silme ya da geri alma yapılamaz; tarama bitince tekrar dene.')
        if _mutations.get(account):  # iki sekme ya da çift tıklama: ikinci işlem birincinin geri alma kaydını ezerdi
            raise Busy('Başka bir silme ya da geri alma sürüyor; bitince tekrar dene.')
        _mutations[account] = 1
    try:
        yield
    finally:
        with _scan_lock:
            _mutations[account] = 0


def _update_scan(account, **changes):
    with _scan_lock:
        _scan_state(account).update(changes)


def _run_scan(service, paths):
    account = paths.account
    try:
        scan_ids = {}
        senders = extract_senders(
            service, progress=lambda done, total: _update_scan(account, processed=done, total=total),
            id_index=scan_ids)
        with _csv_lock:
            save_to_csv(senders, filename=paths.csv)
        _write_json(paths.scan_ids, scan_ids, compact=True)
        _clear_verify_cache(account)
        _update_scan(account, error=None)
    except HttpError as e:
        _update_scan(account, error=_http_error_message(e))
    except RefreshError:
        _update_scan(account, error=LOGIN_EXPIRED_MESSAGE)
    except Exception:
        app.logger.exception('Tarama hatası')
        _update_scan(account, error='Tarama sırasında beklenmeyen bir hata oluştu; ayrıntı sunucu konsolunda.')
    finally:
        _update_scan(account, running=False, finished_at=time.time())


@app.route('/api/scan', methods=['POST'])
@handle_errors
def api_scan():
    paths = _current_paths()
    account = paths.account
    with _scan_lock:
        state = _scan_state(account)
        if state['running']:
            return jsonify({'error': 'Tarama zaten sürüyor.', **state}), 409
        if _mutations.get(account):
            return jsonify({'error': 'Silme ya da geri alma sürüyor; bitince tekrar dene.', **state}), 409
        state.update(running=True, processed=0, total=0, error=None, started_at=time.time(), finished_at=None)
    try:
        service = get_service(account)  # giriş/kimlik hataları isteğin kendisinde dönsün
    except Exception:
        _update_scan(account, running=False)
        raise
    threading.Thread(target=_run_scan, args=(service, paths), daemon=True).start()
    return jsonify(_scan_snapshot(account)), 202


def _scan_snapshot(account):
    with _scan_lock:
        return dict(_scan_state(account))


@app.route('/api/scan/status')
@handle_errors
def api_scan_status():
    return jsonify(_scan_snapshot(_current_paths().account))


# --- Korunanlar API'si -------------------------------------------------------

@app.route('/api/protected')
@handle_errors
def api_protected():
    return jsonify(load_protected())


@app.route('/api/protected', methods=['POST'])
@handle_errors
def api_protected_update():
    body = _json_body()
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
    _clear_verify_cache()
    return jsonify(protected)


# --- Sayma, taşıma, geri alma ------------------------------------------------

@app.route('/api/count', methods=['POST'])
@handle_errors
def api_count():
    """Silme onayında gösterilecek gerçek eşleşme sayısı (taramadaki sayı yalnız gelen kutusu)."""
    body = _json_body()
    paths = _current_paths(body)
    senders = _validated_senders(body)
    scope = _validated_scope(body)
    emails = [extract_email(sender) for sender in senders]
    service = get_service(paths.account)

    details = []
    for sender, email in zip(senders, emails):
        ids, skipped = verified_message_ids(service, paths, email, scope)
        details.append({'sender': sender, 'email': email, 'count': len(ids), 'skipped': skipped})
    return jsonify({'account': paths.account, 'scope': scope,
                    'total': sum(d['count'] for d in details), 'details': details})


def _batch_modify(service, ids, add=(), remove=()):
    for i in range(0, len(ids), 1000):
        gmail_execute(service.users().messages().batchModify(
            userId='me',
            body={'ids': ids[i:i + 1000], 'addLabelIds': list(add), 'removeLabelIds': list(remove)}
        ), 'batchModify')


@app.route('/api/delete', methods=['POST'])
@handle_errors
def api_delete():
    body = _json_body()
    paths = _current_paths(body)
    senders = _validated_senders(body)
    scope = _validated_scope(body)
    # Hepsini önce doğrula: geçersiz bir adres yüzünden işlem yarıda kalmasın.
    emails = [extract_email(sender) for sender in senders]
    reject_protected(emails)
    with _mutation(paths.account):
        return _delete(paths, senders, emails, scope)


def _trash_sender(service, paths, email, scope, undo, scan_ids):
    """Bir göndericinin maillerini çöpe taşır; önce geri alma kaydına ekler. (taşınan, elenen) döner."""
    message_ids, skipped = verified_message_ids(service, paths, email, scope, scan_ids)
    if not message_ids:
        return 0, skipped
    # Geri alma için her mailin çöpe gitmeden önceki INBOX/UNREAD durumu saklanır;
    # "tüm mailler"de arşivdeki mailler geri alınınca gelen kutusuna düşmemeli.
    in_scope = set(message_ids)
    inbox_ids = message_ids if scope == 'inbox' else [
        i for i in find_message_ids(service, email, 'inbox') if i in in_scope]
    unread_ids = [i for i in find_message_ids(service, email, scope, unread_only=True) if i in in_scope]
    undo['ids'] += message_ids
    undo['inbox'] += inbox_ids
    undo['unread'] += unread_ids
    # Çöpe taşımadan önce yaz: işlem yarıda kesilirse taşınanlar yine geri alınabilsin.
    _write_json(paths.undo, undo, compact=True)
    _batch_modify(service, message_ids, add=['TRASH'], remove=['INBOX', 'UNREAD'])
    return len(message_ids), skipped


def _delete(paths, senders, emails, scope):
    service = get_service(paths.account)
    saved = load_saved_senders(paths)
    scan_ids = load_scan_ids(paths)
    undo = {'zaman': time.time(), 'scope': scope, 'ids': [], 'inbox': [], 'unread': [], 'gonderenler': {}}
    results = []
    finished = []
    try:
        for sender, email in zip(senders, emails):
            undo['gonderenler'][email.lower()] = saved.get(email.lower())
            deleted, skipped = _trash_sender(service, paths, email, scope, undo, scan_ids)
            if not deleted:
                undo['gonderenler'].pop(email.lower())
            finished.append(email.lower())
            results.append({'sender': sender, 'email': email, 'deleted': deleted, 'skipped': skipped})
    finally:
        remove_senders_from_csv(paths, finished)
        _clear_verify_cache(paths.account)
    return jsonify({'account': paths.account, 'scope': scope,
                    'total_deleted': sum(r['deleted'] for r in results), 'details': results})


def load_undo(paths):
    if not os.path.exists(paths.undo):
        return None
    with open(paths.undo, encoding='utf-8') as f:
        return json.load(f)


@app.route('/api/undo')
@handle_errors
def api_undo_info():
    undo = load_undo(_current_paths())
    if not undo:
        return jsonify({'available': False})
    return jsonify({'available': True, 'zaman': undo['zaman'], 'count': len(undo['ids']),
                    'senders': sorted(undo['gonderenler'])})


@app.route('/api/undo', methods=['POST'])
@handle_errors
def api_undo():
    """Son silme işlemini geri alır: çöpten çıkarır, INBOX/UNREAD etiketlerini eski haline getirir."""
    paths = _current_paths()
    with _mutation(paths.account):
        return _undo(paths)


def _restore_senders_to_csv(paths, undo):
    with _csv_lock:
        if not os.path.exists(paths.csv):
            return
        senders = load_saved_senders(paths)
        for address, info in undo['gonderenler'].items():
            if info and address not in senders:
                senders[address] = info
        save_to_csv(senders, filename=paths.csv)


def _undo(paths):
    undo = load_undo(paths)
    if not undo:
        raise ValueError('Geri alınacak bir silme işlemi yok.')
    service = get_service(paths.account)
    # Resmi yol messages.untrash; çöp boşaltılmışsa ya da 30 gün geçmişse mail 404 döner, atlanır.
    messages = service.users().messages()
    restored = {msg_id for msg_id, resp in run_batched(
        service, undo['ids'], lambda msg_id: messages.untrash(userId='me', id=msg_id), method='untrash')
        if resp is not None}
    _batch_modify(service, [i for i in undo['inbox'] if i in restored], add=['INBOX'])
    _batch_modify(service, [i for i in undo['unread'] if i in restored], add=['UNREAD'])

    _restore_senders_to_csv(paths, undo)
    os.remove(paths.undo)
    _clear_verify_cache(paths.account)
    return jsonify({'restored': len(restored), 'missing': len(set(undo['ids']) - restored),
                    'senders': sorted(undo['gonderenler'])})


# --- Önizleme ve abonelik API'si ---------------------------------------------

PREVIEW_LIMIT = 5


@app.route('/api/preview', methods=['POST'])
@handle_errors
def api_preview():
    body = _json_body()
    paths = _current_paths(body)
    sender = body.get('sender')
    if not isinstance(sender, str) or not sender.strip():
        raise ValueError("İstek gövdesinde 'sender' adında bir metin bekleniyor.")

    scope = _validated_scope(body)
    email = extract_email(sender)
    service = get_service(paths.account)
    resp = gmail_execute(service.users().messages().list(
        userId='me', q=from_query(email, scope), maxResults=PREVIEW_LIMIT
    ), 'list')
    ids = [m['id'] for m in resp.get('messages', [])]
    fetched = dict(fetch_metadata(service, ids, ['From', 'Subject']))

    previews = []
    for msg_id in ids:
        msg = fetched.get(msg_id)
        # Silmeyle aynı kural: yalnız From adresi birebir bu gönderen olan mailler.
        if from_address(msg) != email.lower():
            continue
        headers = message_headers(msg)
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
    body = _json_body()
    paths = _current_paths(body)
    senders = _validated_senders(body)
    confirm_one_click = body.get('confirm_one_click') is True
    emails = [extract_email(sender) for sender in senders]
    reject_protected(emails)
    service = get_service(paths.account)

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
