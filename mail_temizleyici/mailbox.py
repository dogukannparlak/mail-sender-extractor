"""Gönderen başına Gmail işlemleri: sayma, Çöp Kutusu'na taşıma, geri alma, önizleme."""
import os
import threading
import time
from email.utils import parseaddr

from . import accounts
from .gmail import EMAIL_RE, fetch_metadata, from_address, gmail_execute, message_headers, run_batched
from .protected import is_protected, load_protected
from .storage import read_json, write_json

# Tarama yalnız gelen kutusunu sayar; "all" arşivdeki mailleri de kapsar.
# Gmail'in from: araması çöp ve spam kutusunu zaten dışarıda bırakır.
SCOPE_QUERIES = {'inbox': ' in:inbox', 'all': ''}
PREVIEW_LIMIT = 5


def extract_email(sender):
    # From başlığını gönderen yazar; adres doğrulanmadan Gmail sorgusuna girerse
    # "x@y.com OR label:inbox" gibi bir değer bütün gelen kutusunu eşleştirir.
    _, email = parseaddr(sender)
    if not EMAIL_RE.match(email):
        raise ValueError(f'Geçersiz gönderen adresi: {sender!r}')
    return email


def from_query(email, scope='all', unread_only=False):
    return f'from:"{email}"' + SCOPE_QUERIES[scope] + (' is:unread' if unread_only else '')


def find_message_ids(service, email, scope='all', unread_only=False):
    ids = []
    next_page_token = None
    while True:
        resp = gmail_execute(service.users().messages().list(
            userId='me', q=from_query(email, scope, unread_only), maxResults=500,
            pageToken=next_page_token
        ), 'list')
        ids.extend(m['id'] for m in resp.get('messages', []))
        next_page_token = resp.get('nextPageToken')
        if not next_page_token:
            break
    return ids


def load_scan_ids(paths):
    return read_json(paths.scan_ids, {})


# /api/count'un doğruladığı id'ler kısa süre saklanır; hemen ardından gelen silme
# aynı doğrulamayı (mail başına 20 kota birimi) ikinci kez yapmasın.
VERIFY_CACHE_SECONDS = 600
_verify_cache = {}
_verify_lock = threading.Lock()


def clear_verify_cache(account=None):
    with _verify_lock:
        for key in [k for k in _verify_cache if account is None or k[0] == account]:
            del _verify_cache[key]


def verified_message_ids(service, paths, email, scope, scan_ids=None):
    """from: araması kelime bazlıdır; adı ya da benzer bir adresi eşleşen başka gönderenlerin
    mailleri de dönebilir (ör. korunan x@alan.com.tr). Yalnız From adresi birebir aynı olanları,
    korunan bir göndereni de kapsamıyorsa döndürür. İkinci değer: elenen mail sayısı.

    Taramada bu adresten geldiği görülen mailler yeniden okunmaz; yalnız yeni ya da
    arşivdeki mailler için From okunur.
    """
    wanted = email.lower()
    candidates = find_message_ids(service, email, scope)
    if not candidates:
        return [], 0
    cache_key = (paths.account, wanted, scope)
    with _verify_lock:
        cached = _verify_cache.get(cache_key)
    if cached and time.time() - cached['zaman'] < VERIFY_CACHE_SECONDS:
        known_good, known_bad = cached['kept'], cached['dropped']
    else:
        known_good = set((scan_ids if scan_ids is not None else load_scan_ids(paths)).get(wanted, []))
        known_bad = set()

    protected = load_protected()
    unknown = [i for i in candidates if i not in known_good and i not in known_bad]
    for msg_id, msg in fetch_metadata(service, unknown, ['From']):
        address = from_address(msg)
        if address == wanted and not is_protected(address, protected):
            known_good.add(msg_id)
        else:
            known_bad.add(msg_id)
    with _verify_lock:
        _verify_cache[cache_key] = {'zaman': time.time(), 'kept': known_good, 'dropped': known_bad}

    ids = [i for i in candidates if i in known_good]
    return ids, len(candidates) - len(ids)


def count(paths, senders, emails, scope):
    """Silme onayında gösterilecek gerçek eşleşme sayısı (taramadaki sayı yalnız gelen kutusu)."""
    service = accounts.get_service(paths.account)
    details = []
    for sender, email in zip(senders, emails):
        ids, skipped = verified_message_ids(service, paths, email, scope)
        details.append({'sender': sender, 'email': email, 'count': len(ids), 'skipped': skipped})
    return {'account': paths.account, 'scope': scope,
            'total': sum(d['count'] for d in details), 'details': details}


def batch_modify(service, ids, add=(), remove=()):
    for i in range(0, len(ids), 1000):
        gmail_execute(service.users().messages().batchModify(
            userId='me',
            body={'ids': ids[i:i + 1000], 'addLabelIds': list(add), 'removeLabelIds': list(remove)}
        ), 'batchModify')


def _trash_sender(service, paths, email, scope, undo, scan_ids):
    """Bir göndericinin maillerini çöpe taşır; önce geri alma kaydına ekler. (taşınan, elenen) döner."""
    message_ids, skipped = verified_message_ids(service, paths, email, scope, scan_ids)
    if not message_ids:
        return 0, skipped
    # Geri alma için her mailin çöpe gitmeden önceki INBOX/UNREAD durumu saklanır;
    # "tüm mailler"de arşivdeki mailler geri alınınca gelen kutusuna düşmemeli.
    in_scope = set(message_ids)
    inbox_ids = message_ids if scope == 'inbox' else [
        i for i in find_message_ids(service, email, 'inbox') if i in in_scope]
    unread_ids = [i for i in find_message_ids(service, email, scope, unread_only=True) if i in in_scope]
    undo['ids'] += message_ids
    undo['inbox'] += inbox_ids
    undo['unread'] += unread_ids
    # Çöpe taşımadan önce yaz: işlem yarıda kesilirse taşınanlar yine geri alınabilsin.
    write_json(paths.undo, undo)
    batch_modify(service, message_ids, add=['TRASH'], remove=['INBOX', 'UNREAD'])
    return len(message_ids), skipped


def delete_senders(paths, senders, emails, scope):
    service = accounts.get_service(paths.account)
    saved = accounts.load_saved_senders(paths)
    scan_ids = load_scan_ids(paths)
    undo = {'zaman': time.time(), 'scope': scope, 'ids': [], 'inbox': [], 'unread': [], 'gonderenler': {}}
    results = []
    finished = []
    try:
        for sender, email in zip(senders, emails):
            undo['gonderenler'][email.lower()] = saved.get(email.lower())
            deleted, skipped = _trash_sender(service, paths, email, scope, undo, scan_ids)
            if not deleted:
                undo['gonderenler'].pop(email.lower())
            finished.append(email.lower())
            results.append({'sender': sender, 'email': email, 'deleted': deleted, 'skipped': skipped})
    finally:
        accounts.remove_senders(paths, finished)
        clear_verify_cache(paths.account)
    return {'account': paths.account, 'scope': scope,
            'total_deleted': sum(r['deleted'] for r in results), 'details': results}


def load_undo(paths):
    return read_json(paths.undo)


def undo_info(paths):
    undo = load_undo(paths)
    if not undo:
        return {'available': False}
    return {'available': True, 'zaman': undo['zaman'], 'count': len(undo['ids']),
            'senders': sorted(undo['gonderenler'])}


def undo_last(paths):
    """Son taşımayı geri alır: çöpten çıkarır, INBOX/UNREAD etiketlerini eski haline getirir."""
    undo = load_undo(paths)
    if not undo:
        raise ValueError('Geri alınacak bir silme işlemi yok.')
    service = accounts.get_service(paths.account)
    # Resmi yol messages.untrash; çöp boşaltılmışsa ya da 30 gün geçmişse mail 404 döner, atlanır.
    messages = service.users().messages()
    restored = {msg_id for msg_id, resp in run_batched(
        service, undo['ids'], lambda msg_id: messages.untrash(userId='me', id=msg_id), method='untrash')
        if resp is not None}
    batch_modify(service, [i for i in undo['inbox'] if i in restored], add=['INBOX'])
    batch_modify(service, [i for i in undo['unread'] if i in restored], add=['UNREAD'])

    accounts.restore_senders(paths, undo['gonderenler'])
    os.remove(paths.undo)
    clear_verify_cache(paths.account)
    return {'restored': len(restored), 'missing': len(set(undo['ids']) - restored),
            'senders': sorted(undo['gonderenler'])}


def preview(paths, sender, email, scope):
    service = accounts.get_service(paths.account)
    resp = gmail_execute(service.users().messages().list(
        userId='me', q=from_query(email, scope), maxResults=PREVIEW_LIMIT
    ), 'list')
    ids = [m['id'] for m in resp.get('messages', [])]
    fetched = dict(fetch_metadata(service, ids, ['From', 'Subject']))

    previews = []
    for msg_id in ids:
        msg = fetched.get(msg_id)
        # Silmeyle aynı kural: yalnız From adresi birebir bu gönderen olan mailler.
        if from_address(msg) != email.lower():
            continue
        headers = message_headers(msg)
        internal = msg.get('internalDate')
        previews.append({
            'subject': headers.get('subject', '(konu yok)'),
            'date': int(internal) if internal else None,
            'snippet': msg.get('snippet', ''),
        })
    return {'sender': sender, 'email': email, 'previews': previews}
