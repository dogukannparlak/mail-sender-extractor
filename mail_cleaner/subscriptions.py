"""Abonelikler: bülten gönderenleri, çıkış durumu ve tarama sonrası bildirimler.

Veri, taramanın mail önbelleğinden (paths.scan_cache) okunur; önbellek girdisi
[adres, ad, kategori, abonelik_var_mı, tarih_ms, list_unsubscribe_başlığı]. Eski girdilerde son iki alan yoktur.
"""
import threading
import time
from collections import Counter

from .storage import read_json, write_json
from .unsubscribe import unsubscribe_links

NOTIFICATION_LIMIT = 200
LINK_SCHEMES = ('http://', 'https://', 'mailto:')  # javascript: gibi şemalar sayfada link olmasın
_lock = threading.Lock()


def _unpack(entry):
    key, name, category, has_unsubscribe = entry[:4]
    date = entry[4] if len(entry) > 4 else 0
    header = entry[5] if len(entry) > 5 else ''
    return key, name, category, has_unsubscribe, date, header


def _newer_count(cache, address, since):
    """Çıkış anından (saniye) sonra gelen mail sayısı; tarihi bilinmeyen eski girdiler sayılmaz."""
    since_ms = since * 1000
    return sum(1 for e in cache.values()
               if e and e[0] == address and len(e) > 4 and e[4] and e[4] > since_ms)


def rows(paths, cache, only_links=False, include_exited=False):
    """Abonelik başlığı görülen göndericiler, en çok mail atandan başlayarak.

    only_links=True: çıkış bağlantısı okunabilmiş olanlar (eski önbellek girdilerinde bağlantı yoktur).
    include_exited=True: mailleri silinip taramadan düşmüş olsa da çıkılmış göndericiler de listelenir (kayıtlı bilgiyle)."""
    senders = {}
    for entry in cache.values():
        if not entry:
            continue
        key, name, category, has_unsubscribe, date, header = _unpack(entry)
        info = senders.setdefault(key, {'adres': key, 'sayi': 0, 'son_mail': 0, 'abone': False,
                                        'adlar': Counter(), 'kategori': '', 'baglanti_tarihi': -1,
                                        'baglantilar': []})
        info['sayi'] += 1
        if name:
            info['adlar'][name] += 1
        if date >= info['son_mail']:
            info['son_mail'] = date
            info['kategori'] = category
        if has_unsubscribe:
            info['abone'] = True
            if header and date >= info['baglanti_tarihi']:  # en yeni başlık en güncel linktir
                info['baglanti_tarihi'] = date
                info['baglantilar'] = [u for u in unsubscribe_links(header) if u.lower().startswith(LINK_SCHEMES)]
    state = read_json(paths.subscriptions, {}).get('cikilanlar', {})
    result = []
    for info in senders.values():
        if not info['abone'] or (only_links and not info['baglantilar']):
            continue
        exit_info = state.get(info['adres'])
        info['ad'] = info['adlar'].most_common(1)[0][0] if info['adlar'] else ''
        info['cikis'] = exit_info
        info['yeni_mail'] = _newer_count(cache, info['adres'], exit_info['zaman']) if exit_info else 0
        del info['adlar'], info['baglanti_tarihi']
        result.append(info)
    if include_exited:
        listed = {r['adres'] for r in result}
        for address, exit_info in state.items():
            if address in listed:
                continue
            saved = exit_info.get('bilgi', {})  # çıkış anında/taramada saklanan son bilgi; eski kayıtlarda yoktur
            result.append({'adres': address, 'ad': saved.get('ad', ''), 'kategori': saved.get('kategori', ''),
                           'sayi': 0, 'son_mail': saved.get('son_mail', 0), 'abone': True,
                           'baglantilar': saved.get('baglantilar', []), 'cikis': exit_info,
                           'yeni_mail': 0, 'silindi': True, 'silinen': saved.get('silinen', 0)})
    return sorted(result, key=lambda i: -i['sayi'])


def exited_addresses(paths):
    """Çıkıldı olarak işaretli (otomatik ya da elle) gönderen adresleri."""
    return set(read_json(paths.subscriptions, {}).get('cikilanlar', {}))


def exit_links(paths):
    """Elle açılacak çıkış sayfası/mailto bağlantıları: {adres: {'status', 'url'}}."""
    return read_json(paths.subscriptions, {}).get('cikis_baglantilari', {})


def remember_exit_links(paths, links):
    """Satırda gösterilen çıkış bağlantısı sayfa yenilenince kaybolmasın diye saklanır."""
    if not links:
        return
    with _lock:
        state = read_json(paths.subscriptions, {})
        state.setdefault('cikis_baglantilari', {}).update(links)
        write_json(paths.subscriptions, state)


def _snapshot(info):
    return {'ad': info['ad'], 'kategori': info['kategori'], 'son_mail': info['son_mail'],
            'baglantilar': info['baglantilar']}


def mark(paths, address, unsubscribed, how='manual'):
    """Göndericiyi "çıkıldı" olarak işaretler (ya da işareti kaldırır)."""
    with _lock:
        state = read_json(paths.subscriptions, {})
        exits = state.setdefault('cikilanlar', {})
        if unsubscribed:
            exits[address] = {'zaman': time.time(), 'yontem': how, 'uyarilan': 0}
            # Mailler sonradan silinirse gönderen taramadan düşer; sayfada görünmesi için bilgisi saklanır.
            current = next((r for r in rows(paths, read_json(paths.scan_cache, {})) if r['adres'] == address), None)
            if current:
                exits[address]['bilgi'] = _snapshot(current)
            state.get('cikis_baglantilari', {}).pop(address, None)  # çıkıldı: bağlantıya gerek kalmadı
        else:
            exits.pop(address, None)
        write_json(paths.subscriptions, state)


def backfill_from_history(paths):
    """Çıkılmış ama bilgisi saklanmamış göndericileri eldeki geçmişten doldurur (tek seferlik, tekrar çalışması zararsız).

    Kaynaklar: etkinlik günlüğü (silinen mail sayısı), son silmenin geri alma kaydı ve kayıtlı gönderen listesi (ad, kategori).
    """
    from . import activity  # döngüsel içe aktarmayı önlemek için burada
    with _lock:
        state = read_json(paths.subscriptions, {})
        exits = state.get('cikilanlar', {})
        if not exits:
            return 0
        deleted = Counter()
        for event in activity._read(paths):
            senders = event.get('gonderenler')
            if event.get('islem') == 'silme' and isinstance(senders, dict):
                deleted.update({k: v for k, v in senders.items() if isinstance(v, int)})
        known = {}
        for address, info in read_json(paths.undo, {}).get('gonderenler', {}).items():
            known[address] = info
        try:
            import csv
            with open(paths.csv, encoding='utf-8', newline='') as f:
                for row in csv.DictReader(f):
                    known.setdefault(row['Address'], {'ad': row.get('Name', ''), 'kategori': row.get('Category', '')})
        except (OSError, KeyError):
            pass
        changed = 0
        for address, exit_info in exits.items():
            saved = exit_info.setdefault('bilgi', {}) if (address in known or address in deleted) else exit_info.get('bilgi')
            if saved is None:
                continue
            before = dict(saved)
            if address in known:
                saved.setdefault('ad', known[address].get('ad', ''))
                saved.setdefault('kategori', known[address].get('kategori', ''))
            if address in deleted:
                saved.setdefault('silinen', deleted[address])
            if saved != before:
                changed += 1
        if changed:
            write_json(paths.subscriptions, state)
        return changed


def _add_notifications(paths, items):
    if not items:
        return
    notes = read_json(paths.notifications, [])
    notes.extend(items)
    write_json(paths.notifications, notes[-NOTIFICATION_LIMIT:])


def after_scan(paths, cache):
    """Tarama bittikten sonra: yeni abonelikleri ve çıkılan göndericilerden gelen yeni mailleri bildirir.

    İlk taramada (daha önce görülen listesi yokken) yeni abonelik bildirimi üretilmez; hepsi "yeni" olurdu.
    """
    subscribed = {r['adres']: r for r in rows(paths, cache)}
    now = time.time()
    notes = []
    with _lock:
        state = read_json(paths.subscriptions, {})
        seen = state.get('gorulen')
        if seen is not None:
            for address, info in subscribed.items():
                if address not in seen:
                    notes.append({'zaman': now, 'tur': 'yeni_abonelik', 'gonderen': address, 'ad': info['ad'],
                                  'sayi': info['sayi'], 'okundu': False})
        for address, exit_info in state.get('cikilanlar', {}).items():
            if address in subscribed:
                exit_info['bilgi'] = _snapshot(subscribed[address])
            newer = _newer_count(cache, address, exit_info['zaman'])
            if newer > exit_info.get('uyarilan', 0):
                name = subscribed.get(address, {}).get('ad', '')
                notes.append({'zaman': now, 'tur': 'mail_geliyor', 'gonderen': address, 'ad': name,
                              'sayi': newer, 'okundu': False})
                exit_info['uyarilan'] = newer
        state['gorulen'] = sorted(set(seen or []) | set(subscribed))
        write_json(paths.subscriptions, state)
        _add_notifications(paths, notes)
    return notes


def all_notifications(paths, limit=200):
    items = read_json(paths.notifications, [])
    items.sort(key=lambda n: n.get('zaman', 0), reverse=True)
    return items[:limit]


def unread_count(paths):
    return sum(1 for n in read_json(paths.notifications, []) if not n.get('okundu'))


def mark_all_read(paths):
    with _lock:
        notes = read_json(paths.notifications, [])
        if any(not n.get('okundu') for n in notes):
            write_json(paths.notifications, [{**n, 'okundu': True} for n in notes])
