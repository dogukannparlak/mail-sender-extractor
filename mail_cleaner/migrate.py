"""Eski (Türkçe adlı) sürümlerin yazdığı dosyaları yeni adlarına taşır.

Yalnız yeniden adlandırır: hiçbir şey silinmez, var olan bir dosyanın üzerine yazılmaz. Açılışta bir kez
çalışır (`web.main()` ve `extract_senders.py`); içe aktarmada çalışmaz, böylece testler gerçek verilere dokunmaz.
"""
import os
import shutil

from . import accounts
from .config import BASE_DIR

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
# Korunanlar listesi eskiden bütün hesaplar için tek dosyaydı (önce korunanlar.json, sonra protected.json).
SHARED_PROTECTED_FILES = ('protected.json', 'korunanlar.json')
SHARED_PROTECTED_DONE_SUFFIX = '.migrated'


def _rename(old, new, moved):
    if os.path.exists(old) and not os.path.exists(new):
        os.replace(old, new)
        moved.append((old, new))


def run(base_dir=None, accounts_dir=None):
    """Taşınan (eski, yeni) yolların listesini döner."""
    base_dir = base_dir or BASE_DIR
    accounts_dir = accounts_dir or accounts.ACCOUNTS_DIR
    moved = []
    # Varsayılan hesap klasörü hesaplar/ → accounts/ (.env'de ACCOUNTS_DIR açıkça yazılıysa o klasöre dokunulmaz).
    if accounts_dir == os.path.join(base_dir, 'accounts'):
        _rename(os.path.join(base_dir, LEGACY_ACCOUNTS_DIR), accounts_dir, moved)
    folders = []
    if os.path.isdir(accounts_dir):
        for name in sorted(os.listdir(accounts_dir)):
            folder = os.path.join(accounts_dir, name)
            if os.path.isdir(folder):
                folders.append(folder)
                for old, new in LEGACY_ACCOUNT_FILES.items():
                    _rename(os.path.join(folder, old), os.path.join(folder, new), moved)
    _split_shared_protected(base_dir, folders, moved)
    return moved


def _split_shared_protected(base_dir, folders, moved):
    """Ortak korunanlar listesini her hesabın klasörüne kopyalar (hesabın kendi listesi varsa dokunmaz).

    Eski dosya silinmez: `.migrated` eklenerek yeniden adlandırılır, böylece iş bir kez yapılır ve geri dönüş mümkün olur.
    """
    for name in SHARED_PROTECTED_FILES:
        shared = os.path.join(base_dir, name)
        if not os.path.isfile(shared) or not folders:
            continue
        for folder in folders:
            target = os.path.join(folder, 'protected.json')
            if not os.path.exists(target):
                shutil.copyfile(shared, target)
                moved.append((shared, target))
        done = shared + SHARED_PROTECTED_DONE_SUFFIX
        _rename(shared, done, moved)
