"""macOS penceresi: aynı yerel Flask sunucusunu kendi penceresinde açar (tarayıcı gerekmez).

Sunucu yalnız 127.0.0.1'de, boş bir portta başlar; pencere kapanınca sunucu da durur.
Gerekli ek paket: pywebview (requirements-desktop.txt).
"""
import os
import sys
import threading

TITLE = 'Mail Sender Extractor'

# Menü metinleri (arayüz dili: .env'deki LANGUAGE, boşsa sistem dili)
MENU = {
    'tr': {'go': 'Git', 'home': 'Ana sayfa', 'subs': 'Abonelikler', 'notif': 'Bildirimler', 'log': 'Etkinlik günlüğü',
           'settings': 'Ayarlar…', 'file': 'Dosya', 'csv': 'CSV dışa aktar', 'data': 'Veri klasörünü aç',
           'backup': 'Yedekle', 'browser': 'Tarayıcıda aç', 'help': 'Yardım', 'setup': 'Kurulum rehberi', 'features': 'Özellikler',
           'config': 'Yapılandırma'},
    'en': {'go': 'Go', 'home': 'Home', 'subs': 'Subscriptions', 'notif': 'Notifications', 'log': 'Activity log',
           'settings': 'Settings…', 'file': 'File', 'csv': 'Export CSV', 'data': 'Open data folder',
           'backup': 'Back up', 'browser': 'Open in browser', 'help': 'Help', 'setup': 'Setup guide', 'features': 'Features',
           'config': 'Configuration'},
}


def menu_language(configured):
    if configured in MENU:
        return configured
    system = (os.environ.get('LANG') or '').lower()
    try:
        from Foundation import NSLocale
        system = str((NSLocale.preferredLanguages() or [system])[0]).lower()
    except ImportError:
        pass
    return 'tr' if system.startswith('tr') else 'en'


def build_menu(window, language):
    """Yerel macOS menüsü: sayfalar, dosya işlemleri ve yardım. Eylemler sayfadaki JS'e iletilir."""
    from webview.menu import Menu, MenuAction, MenuSeparator
    m = MENU[language]

    def go(path):
        return lambda: window.evaluate_js(f'appGo({path!r})')

    def post(url):
        js = f"appPost({url!r})"
        return lambda: window.evaluate_js(js)

    return [
        Menu(m['file'], [MenuAction(m['settings'], go('/settings')), MenuSeparator(),
                         MenuAction(m['csv'], post('/api/export/csv')), MenuAction(m['backup'], post('/api/data/backup')),
                         MenuAction(m['data'], post('/api/data/open')), MenuSeparator(),
                         MenuAction(m['browser'], lambda: window.evaluate_js('openInBrowser()'))]),
        Menu(m['go'], [MenuAction(m['home'], go('/')), MenuAction(m['subs'], go('/subscriptions')),
                       MenuAction(m['notif'], go('/notifications')), MenuAction(m['log'], go('/activity-log'))]),
        Menu(m['help'], [MenuAction(m['setup'], go('/help/setup')), MenuAction(m['features'], go('/help/features')),
                         MenuAction(m['config'], go('/help/configuration'))]),
    ]


def main():
    try:
        import webview
    except ImportError:
        sys.exit('Pencere için pywebview gerekli: pip install -r requirements-desktop.txt')
    from werkzeug.serving import make_server
    os.environ['MAIL_CLEANER_APP'] = '1'  # şablonlar uygulama kipini bilsin (data-app)
    try:
        from .config import BASE_DIR, settings
        from .web import app
    except ValueError as e:  # config.ConfigError: .env'de hatalı değer
        sys.exit(f'Config error: {e}')
    from . import demo, migrate

    os.makedirs(BASE_DIR, mode=0o700, exist_ok=True)
    if settings.demo:
        demo.enable()
    else:
        migrate.run()

    server = make_server('127.0.0.1', 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'
    try:
        window = webview.create_window(TITLE, url, width=1280, height=840, min_size=(900, 600))
        webview.start(menu=build_menu(window, menu_language(settings.language)))
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
