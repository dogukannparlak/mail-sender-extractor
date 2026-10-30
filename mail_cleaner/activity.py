"""Yapılan işlemlerin basit günlüğü: hesap klasöründe satır başına bir JSON (activity_log.jsonl).

Günlük yazılamazsa asıl işlem bozulmasın diye hatalar yutulur. Her hesabın günlüğü ayrıdır.
"""
import json
import threading
import time

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


def recent(paths, limit=500):
    """Bu hesabın son olayları, en yenisi önce."""
    events = _read(paths)
    events.sort(key=lambda e: e.get('zaman', 0), reverse=True)
    return events[:limit]
