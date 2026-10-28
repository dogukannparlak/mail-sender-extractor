"""Flask uygulaması: sayfa ve JSON API. İş mantığı diğer modüllerde; burada istek doğrulama ve hata eşleme var."""
import re
import threading
import time
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, jsonify, request, render_template
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from . import accounts, mailbox, protected, state
from .config import settings
from .gmail import quota
from .mailbox import extract_email
from .scanner import extract_senders
from .storage import write_json
from .unsubscribe import find_unsubscribe_info
from . import auth

auth.CREDENTIALS_PATH = settings.credentials_path
quota.units_per_minute = settings.quota_per_minute
DEFAULT_SCOPE = settings.default_scope
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
    return jsonify({'accounts': accounts.list_accounts(), 'migrated': migrated, 'demo': DEMO_MODE})


@app.route('/api/accounts/add', methods=['POST'])
@handle_errors
def api_accounts_add():
    if DEMO_MODE:
        raise ValueError('Demo modunda hesap eklenmez; gerçek hesap için uygulamayı DEMO olmadan başlat.')
    # Tarayıcıda Google giriş penceresi açılır; kullanıcı girişi bitirene kadar istek bekler.
    account = accounts.add_account()
    return jsonify({'account': account, 'accounts': accounts.list_accounts()})


@app.route('/api/accounts/remove', methods=['POST'])
@handle_errors
def api_accounts_remove():
    """Hesabın token'ını siler; taranan liste ve geri alma kaydı klasörde kalır (yeniden eklenince döner)."""
    paths = _current_paths()
    with state.mutation(paths.account):
        accounts.remove_token(paths)
    mailbox.clear_verify_cache(paths.account)
    return jsonify({'removed': paths.account, 'accounts': accounts.list_accounts()})


@app.route('/api/senders')
@handle_errors
def api_senders():
    return jsonify(_senders_payload(accounts.load_saved_senders(_current_paths())))


# --- Tarama ------------------------------------------------------------------

def _run_scan(service, paths):
    account = paths.account
    try:
        scan_ids = {}
        senders = extract_senders(
            service, progress=lambda done, total: state.update_scan(account, processed=done, total=total),
            id_index=scan_ids)
        accounts.save_senders(paths, senders)
        write_json(paths.scan_ids, scan_ids, compact=True)
        mailbox.clear_verify_cache(account)
        state.update_scan(account, error=None)
    except HttpError as e:
        state.update_scan(account, error=_http_error_message(e))
    except RefreshError:
        state.update_scan(account, error=LOGIN_EXPIRED_MESSAGE)
    except Exception:
        app.logger.exception('Tarama hatası')
        state.update_scan(account, error='Tarama sırasında beklenmeyen bir hata oluştu; ayrıntı sunucu konsolunda.')
    finally:
        state.update_scan(account, running=False, finished_at=time.time())


@app.route('/api/scan', methods=['POST'])
@handle_errors
def api_scan():
    paths = _current_paths()
    error, scan = state.start_scan(paths.account, time.time())
    if error:
        return jsonify({'error': error, **scan}), 409
    try:
        service = accounts.get_service(paths.account)  # giriş/kimlik hataları isteğin kendisinde dönsün
    except Exception:
        state.update_scan(paths.account, running=False)
        raise
    threading.Thread(target=_run_scan, args=(service, paths), daemon=True).start()
    return jsonify(state.snapshot(paths.account)), 202


@app.route('/api/scan/status')
@handle_errors
def api_scan_status():
    return jsonify(state.snapshot(_current_paths().account))


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
        return jsonify(mailbox.delete_senders(paths, senders, emails, scope))


@app.route('/api/undo')
@handle_errors
def api_undo_info():
    return jsonify(mailbox.undo_info(_current_paths()))


@app.route('/api/undo', methods=['POST'])
@handle_errors
def api_undo():
    paths = _current_paths()
    with state.mutation(paths.account):
        return jsonify(mailbox.undo_last(paths))


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
    return jsonify({'results': results})


def main():
    if settings.demo:
        from . import demo
        demo.enable()
    app.run(debug=settings.flask_debug, port=settings.port, threaded=True)
