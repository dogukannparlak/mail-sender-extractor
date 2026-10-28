"""Google OAuth girişi ve hesap başına token dosyaları."""
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


def add_account(accounts_dir):
    """Yeni bir Google hesabıyla giriş yapar; token'ı <accounts_dir>/<adres>/token.json'a yazar, adresi döner.

    prompt=select_account: tarayıcıda açık olan hesap sessizce seçilmesin, kullanıcı hangisi olduğunu seçsin.
    """
    with _auth_lock:
        creds = _sign_in(prompt='select_account')
        email = account_email(build('gmail', 'v1', credentials=creds))
        folder = os.path.join(accounts_dir, email)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        _save_token(creds, os.path.join(folder, 'token.json'))
    return email


def _sign_in(**kwargs):
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"credentials.json bulunamadı ({CREDENTIALS_PATH}). "
            "README.md'deki kurulum adımlarına bakın."
        )
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    return flow.run_local_server(port=0, **kwargs)


def _save_token(creds, token_path):
    # Token Gmail'e yazma yetkisi taşır; yalnız dosya sahibi okuyabilsin.
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as token:
        token.write(creds.to_json())
    os.chmod(token_path, 0o600)


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
