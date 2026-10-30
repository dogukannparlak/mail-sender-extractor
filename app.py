"""Web uygulamasını başlatır: python app.py → http://localhost:5050 (ayarlar .env'de)."""
import sys

try:
    from mail_cleaner.web import app, main  # noqa: F401  (app: testler ve WSGI için)
except ValueError as e:  # config.ConfigError: .env'de hatalı bir değer
    sys.exit(f'Config error: {e}')

if __name__ == '__main__':
    main()
