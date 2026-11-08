"""macOS penceresi: aynı yerel Flask sunucusunu kendi penceresinde açar (tarayıcı gerekmez).

Sunucu yalnız 127.0.0.1'de, boş bir portta başlar; pencere kapanınca sunucu da durur.
Gerekli ek paket: pywebview (requirements-desktop.txt).
"""
import os
import sys
import threading

TITLE = 'Mail Sender Extractor'


def main():
    try:
        import webview
    except ImportError:
        sys.exit('Pencere için pywebview gerekli: pip install -r requirements-desktop.txt')
    from werkzeug.serving import make_server
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
        webview.create_window(TITLE, url, width=1280, height=840, min_size=(900, 600))
        webview.start()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
