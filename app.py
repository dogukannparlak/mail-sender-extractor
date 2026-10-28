"""Web uygulamasını başlatır: python app.py → http://localhost:5050 (ayarlar .env'de)."""
import sys

try:
    from mail_temizleyici.web import app, main  # noqa: F401  (app: testler ve WSGI için)
except ValueError as e:  # config.ConfigError: .env'de hatalı bir değer
    sys.exit(f'Ayar hatası: {e}')

if __name__ == '__main__':
    main()
