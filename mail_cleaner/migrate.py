"""Eski (Türkçe adlı) sürümlerin yazdığı dosyaları yeni adlarına taşır.

Yalnız yeniden adlandırır: hiçbir şey silinmez, var olan bir dosyanın üzerine yazılmaz. Açılışta bir kez
çalışır (`web.main()` ve `extract_senders.py`); içe aktarmada çalışmaz, böylece testler gerçek verilere dokunmaz.
"""
import os

from . import accounts, protected
from .config import BASE_DIR, settings

LEGACY_ACCOUNT_FILES = {
    'gonderenler.csv': 'senders.csv',
    'son_islem.json': 'last_action.json',
    'taranan_idler.json': 'scan_ids.json',
    'tarama_onbellegi.json': 'scan_cache.json',
    'abonelikler.json': 'subscriptions.json',
    'bildirimler.json': 'notifications.json',
    'islem_gunlugu.jsonl': 'activity_log.jsonl',
}
LEGACY_ACCOUNTS_DIR = 'hesaplar'
LEGACY_PROTECTED_FILE = 'korunanlar.json'


def _rename(old, new, moved):
    if os.path.exists(old) and not os.path.exists(new):
        os.replace(old, new)
        moved.append((old, new))


def run(base_dir=None, accounts_dir=None, protected_path=None):
    """Taşınan (eski, yeni) yolların listesini döner."""
    base_dir = base_dir or BASE_DIR
    accounts_dir = accounts_dir or accounts.ACCOUNTS_DIR
    protected_path = protected_path or protected.PROTECTED_PATH
    moved = []
    # Varsayılan hesap klasörü hesaplar/ → accounts/ (.env'de ACCOUNTS_DIR açıkça yazılıysa o klasöre dokunulmaz).
    if accounts_dir == os.path.join(base_dir, 'accounts'):
        _rename(os.path.join(base_dir, LEGACY_ACCOUNTS_DIR), accounts_dir, moved)
    if os.path.isdir(accounts_dir):
        for name in sorted(os.listdir(accounts_dir)):
            folder = os.path.join(accounts_dir, name)
            if os.path.isdir(folder):
                for old, new in LEGACY_ACCOUNT_FILES.items():
                    _rename(os.path.join(folder, old), os.path.join(folder, new), moved)
    _rename(os.path.join(base_dir, LEGACY_PROTECTED_FILE), protected_path, moved)
    return moved
