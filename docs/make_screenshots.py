"""README ekran görüntülerini demo modunda üretir: python docs/make_screenshots.py

Yalnızca sahte veri kullanılır (DEMO=1 ile aynı iki sahte hesap); Gmail'e bağlanılmaz, gerçek hesap
dosyalarına dokunulmaz. Kurulum: pip install -r requirements-dev.txt && python -m playwright install chromium
Çıktı: docs/screenshots/*.png
"""
import json
import os
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from mail_cleaner import accounts, activity, demo, subscriptions, web  # noqa: E402

OUT = os.path.join(ROOT, 'docs', 'screenshots')
VIEWPORT = {'width': 1280, 'height': 800}
ACCOUNT = 'demo@ornek.example'
OTHER_ACCOUNT = 'is@ornek.example'


def post(base, path, body):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def scan_all(base):
    post(base, '/api/scan/all', {})
    while any(a['running'] for a in json.load(urllib.request.urlopen(base + '/api/scan/status/all'))['accounts']):
        time.sleep(0.2)


def seed_activity(base):
    """Gerçek işlemleri demo kutusunda yapar; günlük, abonelik durumu ve bildirimler bunlardan oluşur."""
    paths = accounts.AccountPaths(ACCOUNT)
    scan_all(base)
    post(base, '/api/delete', {'account': ACCOUNT, 'senders': ['no-reply@okul.example'], 'scope': 'all'})
    post(base, '/api/undo', {'account': ACCOUNT})
    post(base, '/api/unsubscribe', {'account': ACCOUNT, 'senders': ['kampanya@ornekmarket.example'],
                                    'confirm_one_click': True})
    scan_all(base)
    now = time.time()
    subscriptions._add_notifications(paths, [
        {'zaman': now - 7200, 'tur': 'yeni_abonelik', 'gonderen': 'firsat@seyahat.example',
         'ad': 'Seyahat Fırsatları', 'sayi': 4, 'okundu': True},
        {'zaman': now - 600, 'tur': 'mail_geliyor', 'gonderen': 'kampanya@ornekmarket.example',
         'ad': 'Örnek Market', 'sayi': 2, 'okundu': False},
        {'zaman': now - 60, 'tur': 'yeni_abonelik', 'gonderen': 'haber@teknohafta.example',
         'ad': 'Teknoloji Haftası', 'sayi': 1, 'okundu': False},
    ])


def write_fake_log(paths, now):
    """Günlüğü gerçekçi zamanlarla yeniden yazar (demo işlemleri aynı saniyede biter, tabloda sıkıcı görünür)."""
    def at(minutes_ago, islem, **details):
        return {'zaman': now - minutes_ago * 60, 'hesap': ACCOUNT, 'islem': islem, **details}
    events = [
        at(2900, 'hesap_eklendi'),
        at(2890, 'tarama', tam=True, mail=4812, yeni_okunan=4812, gonderen=213, sure_sn=1620),
        at(1450, 'silme', kapsam='all', toplam=137,
           gonderenler={'bulten@kitapkulubu.example': 64, 'indirim@yemek.example': 41, 'firsat@seyahat.example': 32}),
        at(1445, 'geri_alma', geri_alinan=32, bulunamayan=0, gonderenler=['firsat@seyahat.example']),
        at(300, 'tarama', tam=False, mail=4790, yeni_okunan=36, gonderen=209, sure_sn=14),
        at(120, 'abonelik', onayli=False, sonuclar={'kampanya@ornekmarket.example': 'one_click_available',
                                                    'haber@teknohafta.example': 'manual_link'}),
        at(118, 'abonelik', onayli=True, sonuclar={'kampanya@ornekmarket.example': 'done'}),
        at(90, 'tarama', tam=False, mail=4801, yeni_okunan=11, gonderen=209, sure_sn=9),
        at(40, 'tarama', tam=True, hata='Gmail API hatası (429): Rate limit exceeded'),
        at(5, 'tarama', tam=False, mail=4812, yeni_okunan=11, gonderen=210, sure_sn=11),
    ]
    with open(paths.log, 'w', encoding='utf-8') as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')


def shoot(page, name, **kwargs):
    page.screenshot(path=os.path.join(OUT, name), **kwargs)
    print('yazıldı:', os.path.join('docs', 'screenshots', name))


def main():
    os.makedirs(OUT, exist_ok=True)
    demo.enable()
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    seed_activity(base)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, color_scheme='light', device_scale_factor=1.5)

        # Ana sayfa: bütün hesapları aynı anda tara, sonuçta gönderen listesi
        page.goto(base)
        page.click('#scanAllBtn')
        page.wait_for_selector('#notice >> text=taraması tamamlandı')
        page.wait_for_selector('.sender-row')
        shoot(page, 'main.png')

        # Alan adı görünümü: bir alan adının adresleri, her birinin kendi seçenekleri
        page.select_option('#viewSelect', 'domain')
        page.select_option('#sortSelect', 'members_desc')
        group = page.locator('.sender-item', has=page.locator('.sender-name', has_text='ornekmarket.example'))
        group.get_by_role('button', name='Adresler').click()
        member = group.locator('.member-item', has_text='siparis@ornekmarket.example')
        member.get_by_role('button', name='Önizle').click()
        member.locator('.member-preview .preview-item').first.wait_for()
        page.evaluate('window.scrollTo(0, 0)')
        shoot(page, 'domains.png')

        # Çok hesaplı tarama ilerlemesi: sahte, ortasında bir an
        fake = {'accounts': [
            {'account': ACCOUNT, 'running': True, 'processed': 3120, 'total': 4800, 'error': None, 'started_at': time.time() - 200},
            {'account': OTHER_ACCOUNT, 'running': True, 'processed': 640, 'total': 2100, 'error': None, 'started_at': time.time() - 200},
            {'account': 'okul@ornek.example', 'running': False, 'processed': 900, 'total': 900, 'error': None, 'started_at': time.time() - 200},
        ]}
        page.route('**/api/scan/status/all', lambda route: route.fulfill(content_type='application/json', body=json.dumps(fake)))
        page.evaluate("""() => { state.busy = false; pollAllScans(new Set(['demo@ornek.example', 'is@ornek.example', 'okul@ornek.example'])); }""")
        page.wait_for_selector('.all-scan-row')
        page.evaluate('window.scrollTo(0, 0)')
        shoot(page, 'scan-all.png', clip={'x': 0, 'y': 0, 'width': VIEWPORT['width'], 'height': 330})
        page.unroute('**/api/scan/status/all')

        write_fake_log(accounts.AccountPaths(ACCOUNT), time.time())  # arayüzdeki taramanın satırı sahte sayılarla çelişmesin
        for name, path in (('subscriptions.png', 'abonelikler'), ('notifications.png', 'bildirimler'),
                           ('log.png', 'gunluk')):
            page.goto(f'{base}/{path}?account={ACCOUNT}')
            shoot(page, name)
        browser.close()
    server.shutdown()


if __name__ == '__main__':
    main()
