"""Demo modunu başlatır: python demo.py (gerçek Gmail'e bağlanmaz)."""
import sys

try:
    from mail_temizleyici import demo, web
    from mail_temizleyici.config import settings
except ValueError as e:
    sys.exit(f'Ayar hatası: {e}')

if __name__ == '__main__':
    demo.enable()
    web.app.run(port=settings.port, threaded=True)
