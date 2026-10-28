"""Google OAuth girişi ve hesap başına token dosyaları."""
import json
import os
import threading

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# app.py'nin silme özelliği 'modify' izni gerektirir; extract_senders.py salt
# okunur çağrılar yapsa da aynı token.json paylaşıldığından ortak scope kullanılır.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # proje klasörü
TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')
CREDENTIALS_PATH = os.path.join(BASE_DIR, 'credentials.json')


# Aynı anda gelen iki istek iki ayrı giriş penceresi açmasın, token.json'a yarışarak yazmasın.
_auth_lock = threading.Lock()


def get_service(token_path=None):
    """token_path'teki hesap için Gmail servisi; token yoksa ya da geçersizse giriş penceresi açar."""
    with _auth_lock:
        return build('gmail', 'v1', credentials=_load_credentials(token_path or TOKEN_PATH))


def account_email(service):
    return service.users().getProfile(userId='me').execute()['emailAddress'].lower()


class WrongAccount(ValueError):
    pass


# Giriş sayfası tarayıcıda kendiliğinden açılmayabilir (varsayılan tarayıcı yok, sunucu arka planda);
# adres arayüzde tıklanabilir link olarak da gösterilsin diye yakalanır.
SIGN_IN_TIMEOUT_SECONDS = 300


class _ReportingFlow(InstalledAppFlow):
    on_url = None

    def authorization_url(self, **kwargs):
        url, state = super().authorization_url(**kwargs)
        if self.on_url:
            self.on_url(url)
        return url, state


def validate_client_config(config):
    """Google Cloud'dan indirilen istemci dosyası (client_secret_….json) Masaüstü uygulaması türünde olmalı."""
    if not isinstance(config, dict):
        raise ValueError('İstemci dosyası okunamadı: JSON nesnesi bekleniyor.')
    if 'web' in config and 'installed' not in config:
        raise ValueError('Bu istemci "Web application" türünde; Google Cloud\'da "Desktop app" türünde bir istemci oluştur.')
    installed = config.get('installed')
    if not isinstance(installed, dict) or not installed.get('client_id') or not installed.get('client_secret'):
        raise ValueError('Bu bir Google OAuth istemci dosyası değil (client_secret_….json bekleniyor).')
    return {'installed': installed}


def add_account(accounts_dir, client_config, expected_email=None, on_url=None):
    """Verilen istemciyle Google'a giriş yapar; istemciyi ve token'ı <accounts_dir>/<adres>/ altına yazar, adresi döner.

    Her hesap kendi Google Cloud istemcisiyle bağlanır; ortak bir "ana" hesap yoktur.
    prompt=select_account: tarayıcıda açık olan hesap sessizce seçilmesin, kullanıcı hangisi olduğunu seçsin.
    expected_email verilirse (klasörü önceden hazırlanmış hesap) başka bir hesapla giriş reddedilir.
    """
    client_config = validate_client_config(client_config)
    with _auth_lock:
        flow = _ReportingFlow.from_client_config(client_config, SCOPES)
        flow.on_url = on_url
        try:
            creds = flow.run_local_server(port=0, prompt='select_account', timeout_seconds=SIGN_IN_TIMEOUT_SECONDS)
        except AttributeError:
            # Süre içinde Google'dan dönüş olmadı (sayfa açılmadı ya da kapatıldı).
            raise ValueError('Google girişi 5 dakika içinde tamamlanmadı; tekrar dene.') from None
        email = account_email(build('gmail', 'v1', credentials=creds))
        if expected_email and email != expected_email.lower():
            raise WrongAccount(f'Google\'da {email} ile giriş yapıldı ama bu klasör {expected_email} için. '
                               f'Giriş penceresinde {expected_email} hesabını seç.')
        folder = os.path.join(accounts_dir, email)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        _write_private(os.path.join(folder, 'credentials.json'), json.dumps(client_config, indent=2) + '\n')
        _save_token(creds, os.path.join(folder, 'token.json'))
    return email


def load_client_config(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _write_private(path, text):
    """İstemci sırrı ve token yalnız dosya sahibince okunabilsin (0600)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(text)
    os.chmod(path, 0o600)


def _sign_in(**kwargs):
    """Tek hesaplı eski düzen için: kökteki credentials.json ile giriş."""
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"credentials.json bulunamadı ({CREDENTIALS_PATH}). "
            "README.md'deki kurulum adımlarına bakın."
        )
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    return flow.run_local_server(port=0, **kwargs)


def _save_token(creds, token_path):
    # Token Gmail'e yazma yetkisi taşır; yalnız dosya sahibi okuyabilsin. Okunaklı yazılır; içerik aynı.
    _write_private(token_path, json.dumps(json.loads(creds.to_json()), indent=2) + '\n')


def _load_credentials(token_path):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError:
                # Yenileme anahtarı geçersiz (süresi doldu ya da izin geri alındı): yeniden giriş gerekir.
                creds = None
        if not refreshed:
            creds = _sign_in()
        _save_token(creds, token_path)
    return creds
