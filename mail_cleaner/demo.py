"""Demo modu: Gmail hesabı bağlamadan, bellekteki sahte posta kutularıyla çalışır.

Çalıştırma: `DEMO=1 python app.py` (ya da `python demo.py`, ya da .env'de DEMO=1).
Veriler (CSV, korunanlar, son işlem) geçici bir klasöre yazılır; gerçek dosyalara dokunulmaz.
Abonelikten çıkma istekleri dışarı gitmez.
"""
import os
import random
import re
import tempfile
import time

from .demo_data import DATASETS
from .i18n import t

# Eski adlar (testler Türkçe takımı kullanır).
DEMO_ACCOUNTS = DATASETS['tr']['accounts']
DEMO_SENDERS = DEMO_ACCOUNTS['demo@ornek.example'][0]


class _Call:
    def __init__(self, fn):
        self._fn = fn

    def execute(self, num_retries=0):
        return self._fn()


class _Batch:
    def __init__(self, callback):
        self._callback = callback
        self._requests = []

    def add(self, request, callback=None, request_id=None):
        self._requests.append((request, callback or self._callback, request_id))

    def execute(self):
        for request, callback, request_id in self._requests:
            callback(request_id, request.execute(), None)


class DemoMailbox:
    """googleapiclient'ın uygulamada kullanılan kısmını taklit eder: list, get, batchModify, batch."""

    def __init__(self, senders=DEMO_SENDERS, seed=7, dataset=None):
        dataset = dataset or DATASETS['tr']
        rng = random.Random(seed)
        now_ms = int(time.time() * 1000)
        self.store = {}
        n = 0
        for name, address, count, tab, unsubscribe, one_click in senders:
            for _ in range(count):
                n += 1
                labels = {tab}
                if rng.random() < 0.85:
                    labels.add('INBOX')
                if rng.random() < 0.4:
                    labels.add('UNREAD')
                headers = [
                    {'name': 'From', 'value': f'"{name.replace(chr(34), chr(92) + chr(34))}" <{address}>'},
                    {'name': 'Subject', 'value': rng.choice(dataset['subjects'][tab])},
                ]
                if unsubscribe:
                    domain = address.split('@')[1]
                    headers.append({'name': 'List-Unsubscribe',
                                    'value': f"<https://{domain}/{dataset['unsubscribe_path']}>, <mailto:{dataset['unsubscribe_mailbox']}@{domain}>"})
                    if one_click:
                        headers.append({'name': 'List-Unsubscribe-Post', 'value': 'List-Unsubscribe=One-Click'})
                self.store[f'demo{n:04d}'] = {
                    'labels': labels,
                    'headers': headers,
                    'date': now_ms - rng.randint(0, 400) * 86_400_000,
                    'snippet': dataset['snippet'],
                }

    # --- googleapiclient yüzeyi ---
    def users(self):
        return self

    def messages(self):
        return self

    def new_batch_http_request(self, callback=None):
        return _Batch(callback)

    def _matches(self, msg, q, label_ids, include_spam=False):
        if 'TRASH' in msg['labels']:
            return False
        if label_ids and not set(label_ids) <= msg['labels']:
            return False
        if q:
            sender = re.search(r'from:"([^"]+)"', q)
            if sender:
                from_value = next(h['value'] for h in msg['headers'] if h['name'] == 'From')
                if f'<{sender.group(1).lower()}>' not in from_value.lower():
                    return False
            if 'in:inbox' in q and 'INBOX' not in msg['labels']:
                return False
            if 'is:unread' in q and 'UNREAD' not in msg['labels']:
                return False
            if 'in:spam' in q and 'SPAM' not in msg['labels']:
                return False
            if 'SPAM' in msg['labels'] and not include_spam:
                return False
        return True

    def list(self, userId='me', q=None, labelIds=None, maxResults=100, pageToken=None, includeSpamTrash=False):
        def run():
            ids = sorted((i for i, m in self.store.items() if self._matches(m, q, labelIds, includeSpamTrash)),
                         key=lambda i: -self.store[i]['date'])
            start = int(pageToken or 0)
            page = ids[start:start + maxResults]
            resp = {'messages': [{'id': i} for i in page]}
            if start + maxResults < len(ids):
                resp['nextPageToken'] = str(start + maxResults)
            return resp
        return _Call(run)

    def get(self, userId='me', id=None, format=None, metadataHeaders=None):
        def run():
            msg = self.store[id]
            wanted = {h.lower() for h in (metadataHeaders or [])}
            return {
                'id': id,
                'labelIds': sorted(msg['labels']),
                'internalDate': str(msg['date']),
                'snippet': msg['snippet'],
                'payload': {'headers': [h for h in msg['headers'] if h['name'].lower() in wanted]},
            }
        return _Call(run)

    def untrash(self, userId='me', id=None):
        def run():
            self.store[id]['labels'].discard('TRASH')
            return {'id': id}
        return _Call(run)

    def batchModify(self, userId='me', body=None):
        def run():
            for i in body['ids']:
                self.store[i]['labels'] |= set(body.get('addLabelIds', []))
                self.store[i]['labels'] -= set(body.get('removeLabelIds', []))
            return {}
        return _Call(run)


class _DemoResponse:
    ok = True
    is_redirect = False


def enable(language=None):
    """Uygulamayı sahte posta kutularına ve geçici bir veri klasörüne bağlar (gerçek dosyalara dokunmaz)."""
    from . import accounts, gmail, protected, unsubscribe, web

    from .config import settings
    dataset = DATASETS[language or settings.language or 'en']  # LANGUAGE boşsa İngilizce
    mailboxes = {account: DemoMailbox(senders, seed, dataset) for account, (senders, seed) in dataset['accounts'].items()}
    data_dir = tempfile.mkdtemp(prefix='mail-cleaner-demo-')
    accounts.ACCOUNTS_DIR = os.path.join(data_dir, 'accounts')
    accounts.EXTRA_ACCOUNT_TOKENS = {}  # .env'deki gerçek hesaplar demo'ya karışmasın
    accounts.LEGACY_TOKEN_PATH = os.path.join(data_dir, 'token.json')
    for account in mailboxes:
        os.makedirs(os.path.join(accounts.ACCOUNTS_DIR, account))
        # Hesap listesi token dosyasına bakar; demo'da token hiç okunmaz (get_service sahte kutuyu döner).
        with open(os.path.join(accounts.ACCOUNTS_DIR, account, 'token.json'), 'w') as f:
            f.write('{}')
    accounts.get_service = lambda account: mailboxes[account]
    protected.PROTECTED_PATH = os.path.join(data_dir, 'protected.json')
    gmail.quota.units_per_minute = 0  # sahte kutuda Gmail kotası yok
    # .example alan adları çözülmez; one-click kontrolü genel IP görsün, istek dışarı gitmesin.
    unsubscribe._resolve_host = lambda hostname: {'93.184.215.14'}
    unsubscribe.requests.post = lambda *args, **kwargs: _DemoResponse()
    web.DEMO_MODE = True
    total = sum(len(m.store) for m in mailboxes.values())
    print(t('demo.banner', accounts=len(mailboxes), messages=total, folder=data_dir))
    return mailboxes
