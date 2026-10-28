"""Abonelikten çıkma: List-Unsubscribe başlığı ve tek tıkla çıkış (RFC 8058)."""
import ipaddress
import re
import socket
from urllib.parse import urlparse

import requests
from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

from .gmail import fetch_metadata, from_address, gmail_execute, message_headers
from .mailbox import from_query

# Bir gönderenin en yeni maili çoğu zaman işlemsel (sipariş/onay) olur ve
# List-Unsubscribe başlığı taşımaz; bülten mailleri birkaç mail geride olabilir.
# Bu yüzden tek mail yerine en yeni birkaç maile bakıyoruz.
UNSUBSCRIBE_SCAN_LIMIT = 15


def _first_unsubscribe_headers(service, email, ids):
    """En yeniden eskiye, From'u bu adres olan ve List-Unsubscribe taşıyan ilk mailin başlıkları."""
    fetched = dict(fetch_metadata(service, ids, ['From', 'List-Unsubscribe', 'List-Unsubscribe-Post']))
    for msg_id in ids:
        msg = fetched.get(msg_id)
        headers = message_headers(msg)
        # Başka bir gönderenin (adı bu adrese benzeyen) mailindeki link kullanılmasın.
        if headers.get('list-unsubscribe') and from_address(msg) == email.lower():
            return headers['list-unsubscribe'], headers.get('list-unsubscribe-post', '')
    return None, ''


def _resolve_host(hostname):
    return {info[4][0] for info in socket.getaddrinfo(hostname, 443)}


def is_safe_one_click_url(url, resolve=True):
    """One-click isteği sunucudan gider; yerel ağa/loopback'e istek atılmasını engeller."""
    # urlparse ile requests (urllib3) URL'yi farklı ayrıştırabilir:
    # "https://127.0.0.1\\@x.com/" urlparse'a göre x.com, requests'e göre 127.0.0.1.
    # Kimlik bilgisi/ters eğik çizgi içeren URL'leri reddedip iki ayrıştırıcının
    # aynı host'u görmesini şart koşuyoruz.
    if '\\' in url:
        return False
    parsed = urlparse(url)
    try:
        u3 = parse_url(url)
    except LocationParseError:
        return False
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or u3.auth:
        return False
    if (u3.host or '').strip('[]').lower() != parsed.hostname.lower():
        return False
    if not resolve:  # onaydan önce DNS sorgusu bile gönderene "çıkmaya çalıştı" bilgisini sızdırır
        return True
    try:
        addresses = _resolve_host(parsed.hostname)
    except (socket.gaierror, UnicodeError):
        return False
    for addr in addresses:
        ip = ipaddress.ip_address(addr.split('%')[0])
        if not ip.is_global:
            return False
    return bool(addresses)


def find_unsubscribe_info(service, email, confirm_one_click=False):
    """confirm_one_click=False iken hiçbir isteği göndermez; one-click mümkünse bunu bildirir.

    Tek tıkla çıkış geri alınamaz, bu yüzden POST yalnız kullanıcı onayından sonra gider.
    """
    resp = gmail_execute(service.users().messages().list(
        userId='me', q=from_query(email), maxResults=UNSUBSCRIBE_SCAN_LIMIT
    ), 'list')
    messages = resp.get('messages', [])
    if not messages:
        return {'status': 'not_found'}

    list_unsub, list_unsub_post = _first_unsubscribe_headers(service, email, [m['id'] for m in messages])
    if not list_unsub:
        return {'status': 'none'}

    urls = re.findall(r'<([^>]+)>', list_unsub)
    if not urls:  # bazı gönderenler <> kullanmadan düz adres yazar
        urls = [u.strip() for u in list_unsub.split(',') if u.strip()]
    http_url = next((u for u in urls if u.startswith('http')), None)
    mailto_url = next((u for u in urls if u.startswith('mailto:')), None)

    if http_url and 'one-click' in list_unsub_post.lower() and is_safe_one_click_url(http_url, resolve=False):
        if not confirm_one_click:
            return {'status': 'one_click_available', 'url': http_url}
        if not is_safe_one_click_url(http_url):
            return {'status': 'manual_link', 'url': http_url}
        try:
            r = requests.post(http_url, data={'List-Unsubscribe': 'One-Click'},
                              timeout=10, allow_redirects=False)
            if r.ok and not r.is_redirect:
                return {'status': 'done', 'url': http_url}
            return {'status': 'manual_link', 'url': http_url}
        except requests.RequestException:
            return {'status': 'manual_link', 'url': http_url}

    if http_url:
        return {'status': 'manual_link', 'url': http_url}
    if mailto_url:
        return {'status': 'manual_mailto', 'url': mailto_url}
    return {'status': 'none'}
