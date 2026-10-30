"""Gmail API ile konuşan ortak parçalar: adres ayrıştırma, kota sınırlayıcı, batch istekler."""
import re
import threading
import time
from collections import deque
from email.utils import parseaddr

from googleapiclient.errors import HttpError
from .i18n import t

# Gmail arama sözdizimine sızabilecek karakterler (boşluk, tırnak, parantez, ':') adreste olamaz.
EMAIL_RE = re.compile(r'^[^@\s"()<>,;:\\\[\]]+@[\w-]+(\.[\w-]+)+$')

def message_headers(msg):
    """Gmail metadata yanıtındaki başlıklar; ad büyük/küçük harfe duyarsız (List-Unsubscribe = list-unsubscribe)."""
    return {h['name'].lower(): h['value'] for h in (msg or {}).get('payload', {}).get('headers', [])}


def from_address(msg):
    """Mailin From adresi (küçük harf); başlık yoksa None."""
    headers = message_headers(msg)
    return sender_key(headers['from'])[0] if 'from' in headers else None


def sender_key(header):
    """From başlığını (adres, görünen ad) çiftine çevirir.

    Aynı adres farklı görünen adlarla gelebilir ("Ali (Classroom)" <no-reply@...>);
    sayım adrese göre yapılır. Adres geçerli değilse ham başlık anahtar olur.
    """
    name, addr = parseaddr(header)
    if EMAIL_RE.match(addr):
        return addr.lower(), name.strip()
    return header.strip(), ''


# Gmail, 50'den büyük batch'lerde hız sınırına takılabileceğini söylüyor.
BATCH_SIZE = 50
MAX_ATTEMPTS = 5


# Gmail kullanıcı kotası dakikada 6.000 birim; mail okuma (messages.get) 20 birim,
# yani dakikada en fazla ~300 mail okunabilir (developers.google.com/workspace/gmail/api/reference/quota,
# 2026-10-28). Kotaya çarpıp 429 yemek yerine harcamayı önceden sınırlıyoruz; biraz pay bırakıldı.
QUOTA_UNITS = {'get': 20, 'list': 5, 'batchModify': 50, 'untrash': 5}


class QuotaLimiter:
    """Son 60 saniyede harcanan birimi izler; sınır aşılacaksa bekler. units_per_minute=0 → sınırsız."""

    def __init__(self, units_per_minute=5400, clock=time.monotonic, sleep=time.sleep):
        self.units_per_minute = units_per_minute
        self._clock, self._sleep = clock, sleep
        self._spent = deque()  # (zaman, birim)
        self._lock = threading.Lock()  # tarama ve diğer istekler aynı kullanıcı kotasını paylaşır

    def spend(self, units):
        if not self.units_per_minute:
            return
        with self._lock:
            while True:
                now = self._clock()
                while self._spent and now - self._spent[0][0] >= 60:
                    self._spent.popleft()
                used = sum(u for _, u in self._spent)
                if not self._spent or used + units <= self.units_per_minute:
                    self._spent.append((now, units))
                    return
                self._sleep(max(60 - (now - self._spent[0][0]), 0.05))


quota = QuotaLimiter()


class AccountQuota(QuotaLimiter):
    """Bir hesabın kendi harcama geçmişi. Gmail kotası kullanıcı başınadır; hesaplar birbirinin kotasını
    yemez, o yüzden paralel taranabilir. Dakikalık sınır `quota` ile aynı ayardan gelir."""

    @property
    def units_per_minute(self):
        return quota.units_per_minute

    @units_per_minute.setter
    def units_per_minute(self, value):
        pass


_account_limiters = {}
_account_limiters_lock = threading.Lock()


def account_limiter(account):
    with _account_limiters_lock:
        return _account_limiters.setdefault(account, AccountQuota())


def limiter_for(service):
    """Servisin hesabına ait sınırlayıcı (accounts.get_service takar); yoksa ortak `quota`."""
    limiter = getattr(service, 'quota_limiter', None)
    return limiter if isinstance(limiter, QuotaLimiter) else quota


def gmail_execute(request, method, service=None):
    """Tekil Gmail çağrısı: kotayı say, 429/5xx'te googleapiclient'ın kendi geri çekilmesiyle yeniden dene."""
    limiter_for(service).spend(QUOTA_UNITS[method])
    return request.execute(num_retries=3)


# 403 gövdesinde "rateLimitExceeded" ya da "userRateLimitExceeded" geçebilir.
RATE_LIMIT_REASONS = ('ratelimitexceeded', 'backenderror')


def _is_retryable(exc):
    if not isinstance(exc, HttpError):
        return False
    if exc.status_code == 429 or exc.status_code >= 500:
        return True
    body = str(exc.content).lower()
    return exc.status_code == 403 and any(reason in body for reason in RATE_LIMIT_REASONS)


# Tarama sürerken silinen bir mail 404 döner; bu, bütün taramayı düşürmemeli.
SKIPPABLE_STATUSES = {400, 404}


def run_batched(service, ids, make_request, sleep=time.sleep, method='get'):
    """make_request(id) isteklerini BATCH_SIZE'lık batch'lerle çalıştırır.

    Her id için bir kez (id, yanıt) üretir; yanıt None ise mail artık yok (404/400).
    Hız sınırına takılanlar (tek istek ya da batch'in tamamı) bekleyip yeniden denenir;
    ilerleme olan turlarda deneme sayacı sıfırlanır.
    """
    pending = list(dict.fromkeys(ids))  # aynı request_id iki kez eklenirse batch KeyError verir
    attempt = 0
    while pending:
        retry = []
        progressed = False
        for i in range(0, len(pending), BATCH_SIZE):
            chunk = pending[i:i + BATCH_SIZE]
            finished, failed = [], []

            def callback(request_id, response, exception):
                if exception is None:
                    finished.append((request_id, response))
                elif isinstance(exception, HttpError) and exception.status_code in SKIPPABLE_STATUSES:
                    finished.append((request_id, None))
                elif _is_retryable(exception):
                    failed.append(request_id)
                else:
                    raise exception

            limiter_for(service).spend(QUOTA_UNITS[method] * len(chunk))  # batch kotayı azaltmaz: her çağrı ayrı sayılır
            batch = service.new_batch_http_request(callback=callback)
            for msg_id in chunk:
                batch.add(make_request(msg_id), request_id=msg_id)
            try:
                batch.execute()
            except HttpError as e:
                if not _is_retryable(e):
                    raise
                done_ids = {request_id for request_id, _ in finished}
                failed = [msg_id for msg_id in chunk if msg_id not in done_ids]

            if finished:
                progressed = True
                yield from finished
            if failed:
                retry.extend(failed)
                if i + BATCH_SIZE < len(pending):
                    sleep(1)  # kota dolmuş; sıradaki batch'i hemen göndermeyelim

        if retry:
            attempt = 1 if progressed else attempt + 1
            if attempt >= MAX_ATTEMPTS:
                raise RuntimeError(t('err.rate_limited', count=len(retry), attempts=MAX_ATTEMPTS))
            sleep(2 ** (attempt - 1))
        pending = list(dict.fromkeys(retry))


def fetch_metadata(service, ids, headers, sleep=time.sleep):
    messages = service.users().messages()
    return run_batched(service, ids, lambda msg_id: messages.get(
        userId='me', id=msg_id, format='metadata', metadataHeaders=headers
    ), sleep)
