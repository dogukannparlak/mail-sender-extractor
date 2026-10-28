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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')
CREDENTIALS_PATH = os.path.join(BASE_DIR, 'credentials.json')


# Aynı anda gelen iki istek iki ayrı giriş penceresi açmasın, token.json'a yarışarak yazmasın.
_auth_lock = threading.Lock()


def get_service():
    with _auth_lock:
        return build('gmail', 'v1', credentials=_load_credentials())


def _load_credentials():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
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
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"credentials.json bulunamadı ({CREDENTIALS_PATH}). "
                    "README.md'deki kurulum adımlarına bakın."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # Token Gmail'e yazma yetkisi taşır; yalnız dosya sahibi okuyabilsin.
        fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as token:
            token.write(creds.to_json())
        os.chmod(TOKEN_PATH, 0o600)
    return creds
