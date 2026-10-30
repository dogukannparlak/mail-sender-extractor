"""Hesaplar: her Gmail hesabının token'ı ve verileri ayrı klasörde (ACCOUNTS_DIR/<adres>/)."""
import json
import os
import shutil
import threading

from . import auth
from .config import BASE_DIR, settings
from .gmail import EMAIL_RE
from .scanner import load_csv, save_to_csv

ACCOUNTS_DIR = settings.accounts_dir
# .env'deki ACCOUNT_n / EXTRA_ACCOUNTS: token dosyası başka bir yerde duran hesaplar (adres → token yolu).
# Verileri (liste, geri alma) yine ACCOUNTS_DIR/<adres>/ altında tutulur.
EXTRA_ACCOUNT_TOKENS = settings.extra_accounts
# Çoklu hesaptan önceki tek hesaplı düzen; ilk açılışta hesabın klasörüne taşınır.
LEGACY_TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')
LEGACY_DATA_FILES = ('gonderenler.csv', 'taranan_idler.json', 'son_islem.json')


class AccountPaths:
    """Bir hesabın dosyaları. Klasör adı hesabın adresidir (EMAIL_RE'den geçmiş, küçük harf)."""

    def __init__(self, account):
        self.account = account
        self.root = os.path.join(ACCOUNTS_DIR, account)
        self.external_token = account in EXTRA_ACCOUNT_TOKENS
        self.token = EXTRA_ACCOUNT_TOKENS.get(account) or os.path.join(self.root, 'token.json')
        # Bu hesabın kendi Google Cloud istemcisi (client_secret_….json); her hesap bağımsız bağlanır.
        self.client = os.path.join(self.root, 'credentials.json')
        self.csv = os.path.join(self.root, 'gonderenler.csv')
        self.undo = os.path.join(self.root, 'son_islem.json')
        # Taramada görülen mail id'leri (gönderen başına); silmede bu maillerin From'unu yeniden okumayız.
        self.scan_ids = os.path.join(self.root, 'taranan_idler.json')
        # Mail başına okunmuş başlıklar; sonraki taramalar yalnız yeni mailleri okur.
        self.scan_cache = os.path.join(self.root, 'tarama_onbellegi.json')


def _folder_names():
    if not os.path.isdir(ACCOUNTS_DIR):
        return set()
    return {name for name in os.listdir(ACCOUNTS_DIR) if EMAIL_RE.match(name)}


def list_accounts():
    """Bağlı hesaplar: token'ı olanlar."""
    names = _folder_names() | set(EXTRA_ACCOUNT_TOKENS)
    return sorted(name for name in names if os.path.exists(AccountPaths(name).token))


def list_pending():
    """Girişi bekleyen hesaplar: klasörüne istemci dosyası konmuş ama henüz token'ı olmayanlar."""
    return sorted(name for name in _folder_names()
                  if os.path.exists(AccountPaths(name).client) and not os.path.exists(AccountPaths(name).token))


def has_shared_client():
    """Proje klasöründe ortak bir credentials.json var mı (isteğe bağlı; her hesap kendi istemcisini de kullanabilir)."""
    return os.path.exists(auth.CREDENTIALS_PATH)


def resolve(account):
    """İstekteki hesabı doğrular. Tek hesap varsa account verilmese de o hesap kullanılır."""
    accounts = list_accounts()
    if not account:
        if len(accounts) == 1:
            return AccountPaths(accounts[0])
        raise ValueError('Önce bir Gmail hesabı ekle.' if not accounts else 'Hangi hesapta çalışılacağı belirtilmedi.')
    account = str(account).strip().lower()
    if account not in accounts:  # listede olmayan ad (ör. "../x") hiçbir klasöre ulaşamaz
        raise ValueError(f'Bilinmeyen hesap: {account!r}')
    return AccountPaths(account)


def get_service(account):
    paths = AccountPaths(account)
    os.makedirs(paths.root, mode=0o700, exist_ok=True)  # .env'deki hesabın veri klasörü henüz olmayabilir
    return auth.get_service(paths.token)


def sign_in_plan(client_config=None, pending=None):
    """Hangi istemciyle, hangi hesap için giriş yapılacağı. Öncelik: girişi bekleyen klasör >
    yüklenen istemci dosyası > (varsa) ortak credentials.json. (istemci, beklenen adres) döner."""
    if pending:
        pending = str(pending).strip().lower()
        if pending not in list_pending():
            raise ValueError(f'Girişi bekleyen böyle bir hesap yok: {pending!r}')
        return auth.validate_client_config(auth.load_client_config(AccountPaths(pending).client)), pending
    if client_config is not None:
        return auth.validate_client_config(client_config), None
    if has_shared_client():
        return auth.validate_client_config(auth.load_client_config(auth.CREDENTIALS_PATH)), None
    raise ValueError('Bu hesabın Google Cloud istemci dosyasını (client_secret_….json) seç. '
                     'Nasıl oluşturulacağı README\'de adım adım yazıyor.')


def add_account(client_config, expected_email=None, on_url=None):
    return auth.add_account(ACCOUNTS_DIR, client_config, expected_email, on_url)


def remove_token(paths):
    if paths.external_token:
        raise ValueError(f'{paths.account} .env dosyasında (ACCOUNT_n / EXTRA_ACCOUNTS) tanımlı; çıkarmak için oradaki satırı sil.')
    os.remove(paths.token)


def migrate_legacy_account():
    """Tek hesaplı sürümden kalan token.json ve veri dosyalarını hesabın klasörüne taşır.

    Hesabın adresi Gmail'den (getProfile) öğrenilir; ağ yoksa taşıma yapılmaz, sonra tekrar denenir.
    """
    if not os.path.exists(LEGACY_TOKEN_PATH):
        return None
    account = auth.account_email(auth.get_service(LEGACY_TOKEN_PATH))
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
    adopt_shared_client(paths)
    return account


def _client_id(path, kind):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return (data.get('installed') or {}).get('client_id') if kind == 'client' else data.get('client_id')


def adopt_shared_client(paths):
    """Ortak credentials.json bu hesabın token'ını üreten istemciyse onu hesabın klasörüne taşır.

    Böylece "ana" bir hesap kalmaz: istemci, ait olduğu hesabın yanında durur.
    """
    shared = auth.CREDENTIALS_PATH
    if not os.path.exists(shared) or os.path.exists(paths.client):
        return False
    if _client_id(shared, 'client') != _client_id(paths.token, 'token'):
        return False
    shutil.move(shared, paths.client)
    os.chmod(paths.client, 0o600)
    return True


# --- Hesabın gönderen listesi (CSV) ------------------------------------------

def load_saved_senders(paths):
    return load_csv(paths.csv) if os.path.exists(paths.csv) else {}


# CSV'yi oku-değiştir-yaz yapan işlemler (iki sekmeden silme, geri alma) birbirini ezmesin.
csv_lock = threading.Lock()


def save_senders(paths, senders):
    with csv_lock:
        save_to_csv(senders, filename=paths.csv)


def remove_senders(paths, senders):
    """Çöpe taşınan gönderenleri kayıtlı listeden çıkarır; sayfa yenilenince geri gelmesinler."""
    if not senders:
        return
    with csv_lock:
        if not os.path.exists(paths.csv):
            return
        removed = set(senders)
        remaining = {k: v for k, v in load_saved_senders(paths).items() if k not in removed}
        save_to_csv(remaining, filename=paths.csv)


def restore_senders(paths, rows):
    """Geri alınan gönderenlerin satırlarını listeye geri koyar (varsa dokunmaz)."""
    with csv_lock:
        if not os.path.exists(paths.csv):
            return
        senders = load_saved_senders(paths)
        for address, info in rows.items():
            if info and address not in senders:
                senders[address] = info
        save_to_csv(senders, filename=paths.csv)
