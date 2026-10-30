"""Yapılan işlemlerin basit günlüğü: hesap klasöründe satır başına bir JSON (islem_gunlugu.jsonl).

Günlük yazılamazsa asıl işlem bozulmasın diye hatalar yutulur. /gunluk sayfası bütün hesapları birleştirir.
"""
import json
import threading
import time

from . import accounts

_lock = threading.Lock()


def record(paths, action, **details):
    line = json.dumps({'zaman': time.time(), 'hesap': paths.account, 'islem': action, **details},
                      ensure_ascii=False)
    try:
        with _lock, open(paths.log, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def _read(paths):
    try:
        with open(paths.log, encoding='utf-8') as f:
            lines = f.readlines()
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:  # yarım yazılmış satır
            continue
    return events


def recent(limit=500):
    """Bütün hesapların son olayları, en yenisi önce."""
    events = [e for name in accounts.list_accounts() for e in _read(accounts.AccountPaths(name))]
    events.sort(key=lambda e: e.get('zaman', 0), reverse=True)
    return events[:limit]
