"""Hesap başına tarama ve taşıma durumu.

Tarama binlerce mailde dakikalar sürer; arka planda çalışır, arayüz durumu sorar.
Tarama ile taşıma/geri alma aynı hesapta aynı anda çalışmaz (tarama sonucu silineni geri yazardı).
"""
import threading
from contextlib import contextmanager
from .i18n import t

lock = threading.Lock()
scans = {}
mutations = {}


class Busy(Exception):
    pass


def scan_state(account):
    """Kilit altında çağrılmalı."""
    return scans.setdefault(account, {'running': False, 'processed': 0, 'total': 0, 'error': None,
                                      'started_at': None, 'finished_at': None})


def snapshot(account):
    with lock:
        return dict(scan_state(account))


def update_scan(account, **changes):
    with lock:
        scan_state(account).update(changes)


def start_scan(account, now):
    """Taramayı başlatır; olmuyorsa (zaten sürüyor / taşıma var) hata metni ve durumu döner."""
    with lock:
        state = scan_state(account)
        if state['running']:
            return t('err.scan_running'), dict(state)
        if mutations.get(account):
            return t('err.mutation_running_start'), dict(state)
        state.update(running=True, processed=0, total=0, error=None, started_at=now, finished_at=None)
        return None, dict(state)


@contextmanager
def mutation(account):
    with lock:
        if scan_state(account)['running']:
            raise Busy(t('err.scan_blocks_mutation'))
        if mutations.get(account):  # iki sekme ya da çift tıklama: ikinci işlem birincinin geri alma kaydını ezerdi
            raise Busy(t('err.mutation_running'))
        mutations[account] = 1
    try:
        yield
    finally:
        with lock:
            mutations[account] = 0
