import os
import sys
from pathlib import Path

# Testler kullanıcının .env dosyasından etkilenmesin (ör. EXTRA_ACCOUNTS, ACCOUNTS_DIR).
os.environ['MAIL_CLEANER_ENV_FILE'] = ''
# Testlerin çoğu Türkçe metinleri bekler; dil testleri dili kendisi seçer.
os.environ['LANGUAGE'] = 'tr'
for _name in ('PORT', 'DEMO', 'FLASK_DEBUG', 'CREDENTIALS_PATH', 'ACCOUNTS_DIR', 'GMAIL_QUOTA_PER_MINUTE',
              'DEFAULT_SCOPE', 'EXTRA_ACCOUNTS'):
    os.environ.pop(_name, None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


class _Executable:
    """Mimics the `...().execute()` tail of every googleapiclient call."""

    def __init__(self, data):
        self._data = data

    def execute(self, num_retries=0):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class FakeMessagesResource:
    """Fakes `service.users().messages()`.

    - `list_pages`: list of response dicts returned in order, one per `.list()` call
      (lets tests simulate pagination via successive nextPageToken values).
    - `get_responses`: dict of message id -> response dict, used by `.get()`.
    - `batch_modify_result`: value returned by `.batchModify()`.
    - `list_handler`: optional function(kwargs) -> response; overrides `list_pages`
      when the answer must depend on the query (e.g. `in:inbox` vs all mail).
    All calls are recorded on `list_calls` / `get_calls` / `batch_modify_calls`
    so tests can assert on query params (e.g. `q=from:...`, chunk sizes).
    """

    def __init__(self, list_pages=None, get_responses=None, batch_modify_result=None, list_handler=None,
                 default_from=None):
        self._list_pages = list(list_pages or [])
        self._default_from = default_from
        self._list_handler = list_handler
        self._get_responses = get_responses or {}
        self._batch_modify_result = batch_modify_result if batch_modify_result is not None else {}
        self.list_calls = []
        self.get_calls = []
        self.batch_modify_calls = []
        self.untrash_calls = []
        self.untrash_responses = {}

    def untrash(self, **kwargs):
        self.untrash_calls.append(kwargs)
        return _Executable(self.untrash_responses.get(kwargs.get('id'), {'id': kwargs.get('id')}))

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        if self._list_handler:
            return _Executable(self._list_handler(kwargs))
        if not self._list_pages:
            return _Executable({'messages': []})
        return _Executable(self._list_pages.pop(0))

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        msg_id = kwargs.get('id')
        response = self._get_responses.get(msg_id, {})
        if isinstance(response, list):  # art arda çağrılarda sırayla dön (ör. önce 429, sonra başarı)
            response = response.pop(0) if len(response) > 1 else response[0]
        if self._default_from and isinstance(response, dict):
            # Uygulama silmeden önce her mailin From adresini doğrular; test mailleri bu gönderenden gelsin.
            headers = response.get('payload', {}).get('headers', [])
            if not any(h['name'].lower() == 'from' for h in headers):
                response = {**response, 'payload': {**response.get('payload', {}),
                            'headers': headers + [{'name': 'From', 'value': self._default_from}]}}
        return _Executable(response)

    def batchModify(self, **kwargs):
        self.batch_modify_calls.append(kwargs)
        return _Executable(self._batch_modify_result)


class FakeUsersResource:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class FakeBatch:
    """`service.new_batch_http_request()`: istekleri toplar, execute'ta callback'leri çağırır."""

    def __init__(self, service, callback):
        self._service = service
        self._callback = callback
        self._requests = []

    def add(self, request, callback=None, request_id=None):
        # Gerçek BatchHttpRequest de aynı id'yi ikinci kez kabul etmez.
        if request_id in {rid for _, _, rid in self._requests}:
            raise KeyError(request_id)
        if len(self._requests) >= 1000:
            raise ValueError('batch en fazla 1000 istek alır')
        self._requests.append((request, callback or self._callback, request_id))

    def execute(self):
        self._service.batch_sizes.append(len(self._requests))
        if self._service.batch_errors:  # batch isteğinin kendisi (dış HTTP) hata verirse
            error = self._service.batch_errors.pop(0)
            if error is not None:
                raise error
        for request, callback, request_id in self._requests:
            try:
                response, exception = request.execute(), None
            except Exception as e:  # gerçek batch de hatayı callback'e verir
                response, exception = None, e
            callback(request_id, response, exception)


class FakeGmailService:
    """Fakes the top-level object returned by `googleapiclient.discovery.build('gmail', 'v1', ...)`."""

    def __init__(self, list_pages=None, get_responses=None, batch_modify_result=None,
                 list_handler=None, default_from=None):
        self.messages_resource = FakeMessagesResource(list_pages, get_responses, batch_modify_result, list_handler,
                                                      default_from)
        self._users = FakeUsersResource(self.messages_resource)
        self.batch_sizes = []
        self.batch_errors = []

    def users(self):
        return self._users

    def new_batch_http_request(self, callback=None):
        return FakeBatch(self, callback)


@pytest.fixture
def fake_service_factory():
    return FakeGmailService


TEST_ACCOUNT = 'ben@example.com'


def acct_paths():
    from mail_cleaner import accounts, auth, gmail, mailbox, protected, scanner, state, unsubscribe, web
    return accounts.AccountPaths(TEST_ACCOUNT)


@pytest.fixture(autouse=True)
def isolate_data_files(tmp_path, monkeypatch):
    """Testler gerçek senders.csv / json dosyalarına asla yazmasın."""
    from mail_cleaner import accounts, auth, gmail, mailbox, protected, scanner, state, unsubscribe, web
    # Tek bir test hesabı: account alanı verilmeyen istekler onu kullanır.
    accounts_dir = tmp_path / 'accounts'
    (accounts_dir / TEST_ACCOUNT).mkdir(parents=True)
    (accounts_dir / TEST_ACCOUNT / 'token.json').write_text('{}')
    monkeypatch.setattr(accounts, 'ACCOUNTS_DIR', str(accounts_dir))
    monkeypatch.setattr(accounts, 'EXTRA_ACCOUNT_TOKENS', {})
    monkeypatch.setattr(protected, 'PROTECTED_PATH', str(tmp_path / 'protected.json'))
    monkeypatch.setattr(accounts, 'LEGACY_TOKEN_PATH', str(tmp_path / 'token.json'))
    # Ortak istemci dosyası: testler gerçek credentials.json'u okumasın ve asla taşımasın.
    monkeypatch.setattr(auth, 'CREDENTIALS_PATH', str(tmp_path / 'credentials.json'))
    monkeypatch.setattr(state, 'scans', {})
    monkeypatch.setattr(state, 'mutations', {})
    mailbox.clear_verify_cache()
    # Kota sınırlayıcı testlerde gerçekten beklemesin (kendi testinde ayrıca denetleniyor).
    from mail_cleaner import gmail
    monkeypatch.setattr(gmail.quota, 'units_per_minute', 0)


class InlineThread:
    """threading.Thread yerine: hedefi start() çağrısında hemen çalıştırır (arka plan taramasını eşzamanlı yapar)."""

    def __init__(self, target, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


@pytest.fixture
def inline_scan(monkeypatch):
    from mail_cleaner import accounts, auth, gmail, mailbox, protected, scanner, state, unsubscribe, web
    monkeypatch.setattr(web.threading, 'Thread', InlineThread)


@pytest.fixture
def demo_mode(monkeypatch):
    """demo.enable modül özniteliklerini doğrudan değiştirir; monkeypatch test sonunda geri alsın."""
    from mail_cleaner import accounts, demo, gmail, protected, unsubscribe, web
    for module, name in ((accounts, 'get_service'), (accounts, 'ACCOUNTS_DIR'), (accounts, 'EXTRA_ACCOUNT_TOKENS'),
                         (accounts, 'LEGACY_TOKEN_PATH'), (protected, 'PROTECTED_PATH'),
                         (unsubscribe, '_resolve_host'), (web, 'DEMO_MODE')):
        monkeypatch.setattr(module, name, getattr(module, name))
    monkeypatch.setattr(unsubscribe.requests, 'post', unsubscribe.requests.post)
    monkeypatch.setattr(gmail.quota, 'units_per_minute', gmail.quota.units_per_minute)
    return demo.enable()
