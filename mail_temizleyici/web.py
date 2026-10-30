"""Flask uygulaması: sayfa ve JSON API. İş mantığı diğer modüllerde; burada istek doğrulama ve hata eşleme var."""
import os
import re
import threading
import time
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, jsonify, request, render_template
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from . import accounts, activity, mailbox, protected, state, subscriptions
from .config import settings
from .gmail import quota
from .mailbox import extract_email
from .scanner import extract_senders
from .storage import read_json, write_json
from .unsubscribe import find_unsubscribe_info
from . import auth, storage

auth.CREDENTIALS_PATH = settings.credentials_path
storage.COMPACT = settings.compact_files
quota.units_per_minute = settings.quota_per_minute
DEFAULT_SCOPE = settings.default_scope
DEMO_MODE = False

app = Flask(__name__)
# İstekler küçük JSON'lar; en büyüğü yüklenen istemci dosyası (~1 KB).
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024


def _page_paths():
    """Sayfaların hesabı: ?account=; yoksa ya da bilinmiyorsa ilk hesap. Hesap yoksa None."""
    names = accounts.list_accounts()
    wanted = (request.args.get('account') or '').strip().lower()
    name = wanted if wanted in names else (names[0] if names else None)
    return accounts.AccountPaths(name) if name else None


@app.context_processor
def inject_page_account():
    """Menüde gösterilen hesap, hesap listesi ve o hesabın okunmamış bildirim sayısı."""
    if request.endpoint not in ('subscriptions_page', 'notifications_page', 'log_page'):
        return {}
    paths = _page_paths()
    return {'page_account': paths.account if paths else None, 'account_list': accounts.list_accounts(),
            'unread_notifications': subscriptions.unread_count(paths) if paths else 0}


@app.template_filter('link_label')
def link_label(url):
    """Uzun çıkış adresi yerine kısa etiket: https için alan adı, mailto için "e-posta · alan adı"."""
    if url.lower().startswith('mailto:'):
        address = url[7:].split('?')[0]
        return 'E-posta ile çık · ' + (address.rsplit('@', 1)[-1] if '@' in address else address)
    return urlparse(url).hostname or url


@app.template_filter('datetimeformat')
def datetimeformat(timestamp):
    return time.strftime('%d.%m.%Y %H:%M:%S', time.localtime(timestamp))


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


# --- Hata eşleme ve istek doğrulama ------------------------------------------

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
        except state.Busy as e:
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


def _current_paths(body=None):
    """İstekteki hesap: GET'te ?account=, POST'ta gövdedeki account alanı."""
    body = body if body is not None else _json_body()
    return accounts.resolve(request.args.get('account') or body.get('account'))


def _validated_senders(body):
    senders = (body or {}).get('senders')
    if not isinstance(senders, list):
        raise ValueError("İstek gövdesinde 'senders' adında bir liste bekleniyor.")
    return senders


def _validated_scope(body):
    scope = body.get('scope', 'inbox')
    if scope not in mailbox.SCOPE_QUERIES:
        raise ValueError("'scope' yalnız 'inbox' ya da 'all' olabilir.")
    return scope


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


# --- Sayfa ve hesaplar -------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html', demo=DEMO_MODE, default_scope=DEFAULT_SCOPE)


@app.route('/api/accounts')
@handle_errors
def api_accounts():
    migrated = accounts.migrate_legacy_account()
    return jsonify({'accounts': accounts.list_accounts(), 'pending': accounts.list_pending(),
                    'shared_client': accounts.has_shared_client(), 'migrated': migrated, 'demo': DEMO_MODE})


# Google girişi tarayıcıda yapılır ve dakikalar sürebilir; arka planda bekler, arayüz durumu sorar.
_signin_lock = threading.Lock()
_signin = {'state': 'idle', 'url': None, 'account': None, 'expected': None, 'error': None}


def _signin_snapshot():
    with _signin_lock:
        return dict(_signin)


def _run_sign_in(client_config, expected):
    def on_url(url):
        with _signin_lock:
            _signin['url'] = url
    try:
        account = accounts.add_account(client_config, expected, on_url)
        activity.record(accounts.AccountPaths(account), 'hesap_eklendi')
        with _signin_lock:
            _signin.update(state='done', account=account)
    except ValueError as e:
        with _signin_lock:
            _signin.update(state='error', error=str(e))
    except HttpError as e:
        # Sık görülen: projede Gmail API açılmamış (403 accessNotConfigured).
        message = _http_error_message(e)
        if 'accessNotConfigured' in str(e.content) or 'has not been used' in str(e.content):
            message = ('Bu hesabın Google Cloud projesinde Gmail API açık değil: APIs & Services › Library › '
                       'Gmail API › Enable, birkaç dakika bekle ve tekrar dene.')
        with _signin_lock:
            _signin.update(state='error', error=message)
    except Exception:
        app.logger.exception('Google girişi hatası')
        with _signin_lock:
            _signin.update(state='error', error='Google girişi tamamlanamadı; ayrıntı sunucu konsolunda.')


@app.route('/api/accounts/add', methods=['POST'])
@handle_errors
def api_accounts_add():
    if DEMO_MODE:
        raise ValueError('Demo modunda hesap eklenmez; gerçek hesap için uygulamayı DEMO olmadan başlat.')
    body = _json_body()
    client = body.get('client')
    if client is not None and not isinstance(client, dict):
        raise ValueError("'client' istemci dosyasının (client_secret_….json) içeriği olmalı.")
    client_config, expected = accounts.sign_in_plan(client_config=client, pending=body.get('pending'))
    with _signin_lock:
        if _signin['state'] == 'waiting':
            raise state.Busy('Başka bir Google girişi bekleniyor; önce onu bitir ya da 5 dakika bekle.')
        _signin.update(state='waiting', url=None, account=None, expected=expected, error=None)
    threading.Thread(target=_run_sign_in, args=(client_config, expected), daemon=True).start()
    return jsonify(_signin_snapshot()), 202


@app.route('/api/accounts/add/status')
@handle_errors
def api_accounts_add_status():
    return jsonify(_signin_snapshot())


@app.route('/api/accounts/remove', methods=['POST'])
@handle_errors
def api_accounts_remove():
    """Hesabın token'ını siler; taranan liste ve geri alma kaydı klasörde kalır (yeniden eklenince döner)."""
    paths = _current_paths()
    with state.mutation(paths.account):
        accounts.remove_token(paths)
    activity.record(paths, 'hesap_cikarildi')
    mailbox.clear_verify_cache(paths.account)
    return jsonify({'removed': paths.account, 'accounts': accounts.list_accounts()})


@app.route('/api/senders')
@handle_errors
def api_senders():
    paths = _current_paths()
    payload = _senders_payload(accounts.load_saved_senders(paths))
    # Çıkış bağlantısı okunabilen göndericiler: arayüz "Abonelikten çık"ı yalnız onlarda sunar.
    linked = {r['adres'] for r in subscriptions.rows(paths, read_json(paths.scan_cache, {}), only_links=True)}
    for sender in payload['gonderenler']:
        sender['baglanti'] = sender['gonderen'] in linked
    return jsonify(payload)


# --- Tarama ------------------------------------------------------------------

def _run_scan(service, paths, full=False):
    account = paths.account
    try:
        scan_ids = {}
        cache = {} if full else read_json(paths.scan_cache, {})
        known = set(cache)
        started = time.time()
        senders = extract_senders(
            service, progress=lambda done, total: state.update_scan(account, processed=done, total=total),
            id_index=scan_ids, cache=cache)
        accounts.save_senders(paths, senders)
        write_json(paths.scan_ids, scan_ids)
        write_json(paths.scan_cache, cache, compact=True)
        mailbox.clear_verify_cache(account)
        state.update_scan(account, error=None)
        try:
            subscriptions.after_scan(paths, cache)
        except Exception:  # bildirim üretilemese de tarama sonucu kaydedilmiş kalsın
            app.logger.exception('Tarama sonrası abonelik kontrolü hatası')
        activity.record(paths, 'tarama', tam=full, mail=sum(len(v) for v in scan_ids.values()),
                        yeni_okunan=len(set(cache) - known), gonderen=len(senders),
                        sure_sn=round(time.time() - started))
    except HttpError as e:
        state.update_scan(account, error=_http_error_message(e))
        activity.record(paths, 'tarama', tam=full, hata=_http_error_message(e))
    except RefreshError:
        state.update_scan(account, error=LOGIN_EXPIRED_MESSAGE)
        activity.record(paths, 'tarama', tam=full, hata=LOGIN_EXPIRED_MESSAGE)
    except Exception:
        app.logger.exception('Tarama hatası')
        state.update_scan(account, error='Tarama sırasında beklenmeyen bir hata oluştu; ayrıntı sunucu konsolunda.')
        activity.record(paths, 'tarama', tam=full, hata='beklenmeyen hata')
    finally:
        state.update_scan(account, running=False, finished_at=time.time())


def _start_scan(paths, full):
    """Hesabın taramasını arka planda başlatır; başlatılamazsa (hata metni, durum) döner, başlarsa (None, durum)."""
    error, scan = state.start_scan(paths.account, time.time())
    if error:
        return error, scan
    try:
        service = accounts.get_service(paths.account)  # giriş/kimlik hataları isteğin kendisinde dönsün
    except Exception:
        state.update_scan(paths.account, running=False)
        raise
    threading.Thread(target=_run_scan, args=(service, paths, full), daemon=True).start()
    return None, state.snapshot(paths.account)


@app.route('/api/scan', methods=['POST'])
@handle_errors
def api_scan():
    paths = _current_paths()
    full = _json_body().get('full') is True  # true: önbelleği yok say, bütün mailleri yeniden oku
    error, scan = _start_scan(paths, full)
    if error:
        return jsonify({'error': error, **scan}), 409
    return jsonify(scan), 202


@app.route('/api/scan/all', methods=['POST'])
@handle_errors
def api_scan_all():
    """Bütün hesapları aynı anda tarar. Gmail kotası hesap başına olduğundan toplam süre en yavaş hesabınki kadardır."""
    full = _json_body().get('full') is True
    results = []
    for name in accounts.list_accounts():
        try:
            error, scan = _start_scan(accounts.AccountPaths(name), full)
        except Exception as e:  # bir hesabın girişi bozuksa diğerleri yine taransın
            error, scan = (LOGIN_EXPIRED_MESSAGE if isinstance(e, RefreshError) else str(e) or type(e).__name__), {}
        results.append({'account': name, 'started': error is None, 'error': error})
    return jsonify({'accounts': results}), 202


@app.route('/api/scan/status/all')
@handle_errors
def api_scan_status_all():
    return jsonify({'accounts': [{'account': name, **state.snapshot(name)} for name in accounts.list_accounts()]})


@app.route('/api/scan/status')
@handle_errors
def api_scan_status():
    return jsonify(state.snapshot(_current_paths().account))


# --- İşlem günlüğü -----------------------------------------------------------

@app.route('/gunluk')
def log_page():
    paths = _page_paths()
    return render_template('gunluk.html', events=activity.recent(paths) if paths else [])


# --- Abonelikler ve bildirimler ----------------------------------------------

@app.route('/abonelikler')
def subscriptions_page():
    paths = _page_paths()
    cache = read_json(paths.scan_cache, {}) if paths else {}
    rows = subscriptions.rows(paths, cache, only_links=True) if paths else []
    without_links = len(subscriptions.rows(paths, cache)) - len(rows) if paths else 0
    return render_template('abonelikler.html', rows=rows, without_links=without_links,
                           scanned=bool(paths and os.path.exists(paths.scan_cache)))


@app.route('/bildirimler')
def notifications_page():
    paths = _page_paths()
    return render_template('bildirimler.html', notifications=subscriptions.all_notifications(paths) if paths else [])


@app.route('/api/notifications/unread')
@handle_errors
def api_notifications_unread():
    return jsonify({'unread': subscriptions.unread_count(_current_paths())})


@app.route('/api/notifications/read', methods=['POST'])
@handle_errors
def api_notifications_read():
    subscriptions.mark_all_read(_current_paths())
    return jsonify({'unread': 0})


@app.route('/api/subscriptions/mark', methods=['POST'])
@handle_errors
def api_subscriptions_mark():
    body = _json_body()
    paths = _current_paths(body)
    address = extract_email(str(body.get('sender', '')))
    subscriptions.mark(paths, address.lower(), body.get('unsubscribed') is True)
    return jsonify({'sender': address.lower(), 'unsubscribed': body.get('unsubscribed') is True})


# --- Korunanlar --------------------------------------------------------------

@app.route('/api/protected')
@handle_errors
def api_protected():
    return jsonify(protected.load_protected())


@app.route('/api/protected', methods=['POST'])
@handle_errors
def api_protected_update():
    body = _json_body()
    result = protected.set_protected(body.get('value'), body.get('protected', True))
    mailbox.clear_verify_cache()
    return jsonify(result)


# --- Sayma, taşıma, geri alma, önizleme, abonelik ----------------------------

def _senders_request():
    """Gönderen listesi alan isteklerin ortak doğrulaması: hesap, gönderenler, adresler."""
    body = _json_body()
    paths = _current_paths(body)
    senders = _validated_senders(body)
    # Hepsini önce doğrula: geçersiz bir adres yüzünden işlem yarıda kalmasın.
    emails = [extract_email(sender) for sender in senders]
    return body, paths, senders, emails


@app.route('/api/count', methods=['POST'])
@handle_errors
def api_count():
    body, paths, senders, emails = _senders_request()
    return jsonify(mailbox.count(paths, senders, emails, _validated_scope(body)))


@app.route('/api/delete', methods=['POST'])
@handle_errors
def api_delete():
    body, paths, senders, emails = _senders_request()
    scope = _validated_scope(body)
    protected.reject_protected(emails)
    with state.mutation(paths.account):
        try:
            result = mailbox.delete_senders(paths, senders, emails, scope)
        except Exception as e:
            activity.record(paths, 'silme', kapsam=scope, gonderenler=emails, hata=str(e) or type(e).__name__)
            raise
        activity.record(paths, 'silme', kapsam=scope, toplam=result['total_deleted'],
                        gonderenler={d['email']: d['deleted'] for d in result['details']})
        return jsonify(result)


@app.route('/api/undo')
@handle_errors
def api_undo_info():
    return jsonify(mailbox.undo_info(_current_paths()))


@app.route('/api/undo', methods=['POST'])
@handle_errors
def api_undo():
    paths = _current_paths()
    with state.mutation(paths.account):
        result = mailbox.undo_last(paths)
        activity.record(paths, 'geri_alma', geri_alinan=result['restored'], bulunamayan=result['missing'],
                        gonderenler=result['senders'])
        return jsonify(result)


@app.route('/api/preview', methods=['POST'])
@handle_errors
def api_preview():
    body = _json_body()
    paths = _current_paths(body)
    sender = body.get('sender')
    if not isinstance(sender, str) or not sender.strip():
        raise ValueError("İstek gövdesinde 'sender' adında bir metin bekleniyor.")
    scope = _validated_scope(body)
    return jsonify(mailbox.preview(paths, sender, extract_email(sender), scope))


@app.route('/api/unsubscribe', methods=['POST'])
@handle_errors
def api_unsubscribe():
    body, paths, senders, emails = _senders_request()
    confirm_one_click = body.get('confirm_one_click') is True
    protected.reject_protected(emails)
    service = accounts.get_service(paths.account)
    results = [{'sender': sender, 'email': email, **find_unsubscribe_info(service, email, confirm_one_click)}
               for sender, email in zip(senders, emails)]
    if confirm_one_click:
        for r in results:
            if r['status'] == 'done':
                subscriptions.mark(paths, r['email'], True, how='otomatik')
    activity.record(paths, 'abonelik', onayli=confirm_one_click,
                    sonuclar={r['email']: r['status'] for r in results})
    return jsonify({'results': results})


def main():
    if settings.demo:
        from . import demo
        demo.enable()
    app.run(debug=settings.flask_debug, port=settings.port, threaded=True)
