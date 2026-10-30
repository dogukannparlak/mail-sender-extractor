"""README/doc ekran görüntülerini demo modunda üretir: python scripts/make_screenshots.py [en|tr]

Yalnızca sahte veri kullanılır (DEMO=1 ile aynı iki sahte hesap); Gmail'e bağlanılmaz, gerçek hesap
dosyalarına dokunulmaz. Kurulum: pip install -r requirements-dev.txt && python -m playwright install chromium
Çıktı: doc/screenshots/*.png (İngilizce arayüz) ve doc-tr/screenshots/*.png (Türkçe arayüz).
Dil verilmezse ikisi de üretilir (her dil ayrı bir süreçte çalışır: demo durumu karışmasın).
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWPORT = {'width': 1280, 'height': 800}
OUTPUT = {'en': os.path.join(ROOT, 'doc', 'screenshots'), 'tr': os.path.join(ROOT, 'doc-tr', 'screenshots')}

# Dile göre değişenler: demo verisindeki adresler ve arayüz metinleri.
SETTINGS = {
    'en': {
        'account': 'demo@mail.example', 'other': 'work@mail.example', 'third': 'school@mail.example',
        'undo_sender': 'no-reply@university.example', 'unsub_sender': 'deals@examplemarket.example',
        'domain': 'examplemarket.example', 'member': 'orders@examplemarket.example',
        'new_subs': [('offers@traveldeals.example', 'Travel Deals', 4), ('digest@techweekly.example', 'Tech Weekly', 1)],
        'still_mailing': ('deals@examplemarket.example', 'Example Market', 2),
        'log_error': 'Gmail API error (429): Rate limit exceeded',
        'delete_senders': {'news@bookclub.example': 64, 'offers@fooddelivery.example': 41, 'offers@traveldeals.example': 32},
        'restore_sender': 'offers@traveldeals.example',
        'scan_done': 'scans finished', 'addresses_button': 'Addresses', 'preview_button': 'Preview',
    },
    'tr': {
        'account': 'demo@ornek.example', 'other': 'is@ornek.example', 'third': 'okul@ornek.example',
        'undo_sender': 'no-reply@okul.example', 'unsub_sender': 'kampanya@ornekmarket.example',
        'domain': 'ornekmarket.example', 'member': 'siparis@ornekmarket.example',
        'new_subs': [('firsat@seyahat.example', 'Seyahat Fırsatları', 4), ('haber@teknohafta.example', 'Teknoloji Haftası', 1)],
        'still_mailing': ('kampanya@ornekmarket.example', 'Örnek Market', 2),
        'log_error': 'Gmail API hatası (429): Rate limit exceeded',
        'delete_senders': {'bulten@kitapkulubu.example': 64, 'indirim@yemek.example': 41, 'firsat@seyahat.example': 32},
        'restore_sender': 'firsat@seyahat.example',
        'scan_done': 'taraması tamamlandı', 'addresses_button': 'Adresler', 'preview_button': 'Önizle',
    },
}


def post(base, path, body):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def scan_all(base):
    post(base, '/api/scan/all', {})
    while any(a['running'] for a in json.load(urllib.request.urlopen(base + '/api/scan/status/all'))['accounts']):
        time.sleep(0.2)


def write_fake_log(paths, cfg, now):
    """Günlüğü gerçekçi zamanlarla yazar (demo işlemleri aynı saniyede biter, tabloda sıkıcı görünür)."""
    def at(minutes_ago, action, **details):
        return {'zaman': now - minutes_ago * 60, 'hesap': cfg['account'], 'islem': action, **details}
    undo = cfg['restore_sender']
    events = [
        at(2900, 'hesap_eklendi'),
        at(2890, 'tarama', tam=True, mail=4812, yeni_okunan=4812, gonderen=213, sure_sn=1620),
        at(1450, 'silme', kapsam='all', toplam=sum(cfg['delete_senders'].values()), gonderenler=cfg['delete_senders']),
        at(1445, 'geri_alma', geri_alinan=cfg['delete_senders'][undo], bulunamayan=0, gonderenler=[undo]),
        at(300, 'tarama', tam=False, mail=4790, yeni_okunan=36, gonderen=209, sure_sn=14),
        at(120, 'abonelik', onayli=False, sonuclar={cfg['unsub_sender']: 'one_click_available',
                                                    cfg['new_subs'][1][0]: 'manual_link'}),
        at(118, 'abonelik', onayli=True, sonuclar={cfg['unsub_sender']: 'done'}),
        at(90, 'tarama', tam=False, mail=4801, yeni_okunan=11, gonderen=209, sure_sn=9),
        at(40, 'tarama', tam=True, hata=cfg['log_error']),
        at(5, 'tarama', tam=False, mail=4812, yeni_okunan=11, gonderen=210, sure_sn=11),
    ]
    with open(paths.log, 'w', encoding='utf-8') as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')


def seed_activity(base, cfg, accounts, subscriptions):
    paths = accounts.AccountPaths(cfg['account'])
    scan_all(base)
    post(base, '/api/delete', {'account': cfg['account'], 'senders': [cfg['undo_sender']], 'scope': 'all'})
    post(base, '/api/undo', {'account': cfg['account']})
    post(base, '/api/unsubscribe', {'account': cfg['account'], 'senders': [cfg['unsub_sender']], 'confirm_one_click': True})
    scan_all(base)
    now = time.time()
    (first, first_name, first_count), (second, second_name, second_count) = cfg['new_subs']
    sender, name, count = cfg['still_mailing']
    subscriptions._add_notifications(paths, [
        {'zaman': now - 7200, 'tur': 'yeni_abonelik', 'gonderen': first, 'ad': first_name, 'sayi': first_count, 'okundu': True},
        {'zaman': now - 600, 'tur': 'mail_geliyor', 'gonderen': sender, 'ad': name, 'sayi': count, 'okundu': False},
        {'zaman': now - 60, 'tur': 'yeni_abonelik', 'gonderen': second, 'ad': second_name, 'sayi': second_count, 'okundu': False},
    ])


def run(language):
    os.environ['LANGUAGE'] = language  # sunucu ve JS bu dilde çalışsın; demo verisi de aynı dilde
    sys.path.insert(0, ROOT)
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server
    from mail_cleaner import accounts, demo, subscriptions, web

    cfg, out = SETTINGS[language], OUTPUT[language]
    os.makedirs(out, exist_ok=True)

    def shoot(page, name, **kwargs):
        page.screenshot(path=os.path.join(out, name), **kwargs)
        print('wrote:', os.path.relpath(os.path.join(out, name), ROOT))

    demo.enable(language)
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    seed_activity(base, cfg, accounts, subscriptions)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, color_scheme='light', device_scale_factor=1.5, locale=language)

        # Ana sayfa: bütün hesapları aynı anda tara, sonuçta gönderen listesi
        page.goto(base)
        page.click('#scanAllBtn')
        page.wait_for_selector(f"#notice >> text={cfg['scan_done'] if language == 'tr' else 'finished'}")
        page.wait_for_selector('.sender-row')
        shoot(page, 'main.png')

        # Alan adı görünümü: bir alan adının adresleri, her birinin kendi seçenekleri
        page.select_option('#viewSelect', 'domain')
        page.select_option('#sortSelect', 'members_desc')
        group = page.locator('.sender-item', has=page.locator('.sender-name', has_text=cfg['domain']))
        group.get_by_role('button', name=cfg['addresses_button']).click()
        member = group.locator('.member-item', has_text=cfg['member'])
        member.get_by_role('button', name=cfg['preview_button']).click()
        member.locator('.member-preview .preview-item').first.wait_for()
        page.evaluate('window.scrollTo(0, 0)')
        shoot(page, 'domains.png')

        # Çok hesaplı tarama ilerlemesi: sahte, ortasında bir an (demo kutusunda tarama anında biter)
        fake = {'accounts': [
            {'account': cfg['account'], 'running': True, 'processed': 3120, 'total': 4800, 'error': None, 'started_at': time.time() - 200},
            {'account': cfg['other'], 'running': True, 'processed': 640, 'total': 2100, 'error': None, 'started_at': time.time() - 200},
            {'account': cfg['third'], 'running': False, 'processed': 900, 'total': 900, 'error': None, 'started_at': time.time() - 200},
        ]}
        page.route('**/api/scan/status/all', lambda route: route.fulfill(content_type='application/json', body=json.dumps(fake)))
        accounts_js = json.dumps([cfg['account'], cfg['other'], cfg['third']])
        page.evaluate(f"() => {{ state.busy = false; pollAllScans(new Set({accounts_js})); }}")
        page.wait_for_selector('.all-scan-row')
        page.evaluate('window.scrollTo(0, 0)')
        shoot(page, 'scan-all.png', clip={'x': 0, 'y': 0, 'width': VIEWPORT['width'], 'height': 330})
        page.unroute('**/api/scan/status/all')

        write_fake_log(accounts.AccountPaths(cfg['account']), cfg, time.time())  # arayüzdeki taramanın satırı çelişmesin
        for name, path in (('subscriptions.png', 'subscriptions'), ('notifications.png', 'notifications'),
                           ('log.png', 'activity-log')):
            page.goto(f"{base}/{path}?account={cfg['account']}")
            shoot(page, name)
        browser.close()
    server.shutdown()


def main():
    languages = sys.argv[1:] or ['en', 'tr']
    if len(languages) == 1:
        run(languages[0])
    else:
        for language in languages:
            subprocess.run([sys.executable, os.path.abspath(__file__), language], check=True)


if __name__ == '__main__':
    main()
