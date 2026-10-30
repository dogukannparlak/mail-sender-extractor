"""Ayarlar: proje klasöründeki .env dosyasından (yoksa varsayılanlardan) okunur.

Gerçek ortam değişkenleri .env'deki değerin önüne geçer (ör. `DEMO=1 python app.py`).
Biçim: her satırda `AD=değer`; `#` ile başlayan satırlar yorumdur. Örnek: .env.example
"""
import os
import re

from .gmail import EMAIL_RE

# Proje klasörü (paketin bir üstü): .env, credentials.json ve veriler burada.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# MAIL_CLEANER_ENV_FILE başka bir dosyayı gösterebilir; boş verilirse .env hiç okunmaz (testler böyle çalışır).
ENV_PATH = os.environ.get('MAIL_CLEANER_ENV_FILE', os.path.join(BASE_DIR, '.env'))



class ConfigError(ValueError):
    pass


# Ayar hataları açılışta, istek yokken verilir: dil .env'deki / ortamdaki LANGUAGE'dan seçilir (yoksa İngilizce).
_ui_language = os.environ.get('LANGUAGE', '').strip().lower()


def _msg(key, **params):
    from .i18n import DEFAULT_LANGUAGE, LANGUAGES, t
    return t(key, lang=_ui_language if _ui_language in LANGUAGES else DEFAULT_LANGUAGE, **params)


def read_env_file(path):
    """Basit .env okuyucu: AD=değer, isteğe bağlı tırnak, # yorum. Bağımlılık eklememek için elle."""
    values = {}
    if not path or not os.path.exists(path):
        return values
    with open(path, encoding='utf-8') as f:
        for number, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                raise ConfigError(_msg('cfg.env_line', number=number, line=repr(line)))
            key, value = line.split('=', 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            values[key] = value
    return values


def _path(value):
    path = os.path.expanduser(value)
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def _bool(name, value):
    if value.lower() in ('1', 'true', 'evet', 'yes'):
        return True
    if value.lower() in ('0', 'false', 'hayir', 'hayır', 'no', ''):
        return False
    raise ConfigError(_msg('cfg.bool', name=name, value=repr(value)))


def _int(name, value, minimum):
    try:
        number = int(value)
    except ValueError:
        raise ConfigError(_msg('cfg.int', name=name, value=repr(value))) from None
    if number < minimum:
        raise ConfigError(_msg('cfg.int_min', name=name, minimum=minimum, value=number))
    return number


def _account_order(key):
    number = key.rsplit('_', 1)[-1]
    return int(number) if number.isdigit() else 0


def _extra_accounts(value):
    """EXTRA_ACCOUNTS=adres=token_yolu, adres=token_yolu"""
    accounts = {}
    for item in filter(None, (part.strip() for part in value.split(','))):
        if '=' not in item:
            raise ConfigError(_msg('cfg.account_format', item=repr(item)))
        address, token = (x.strip() for x in item.split('=', 1))
        address = address.lower()
        if not EMAIL_RE.match(address):
            raise ConfigError(_msg('cfg.account_address', address=repr(address)))
        if not token:
            raise ConfigError(_msg('cfg.account_token_empty', address=address))
        accounts[address] = _path(token)
    return accounts


class Settings:
    def __init__(self, env):
        global _ui_language
        _ui_language = env.get('LANGUAGE', '').strip().lower()
        get = lambda name, default: env.get(name, default)
        self.port = _int('PORT', get('PORT', '5050'), 1)
        self.demo = _bool('DEMO', get('DEMO', '0'))
        self.flask_debug = _bool('FLASK_DEBUG', get('FLASK_DEBUG', '0'))
        self.compact_files = _bool('COMPACT_FILES', get('COMPACT_FILES', '0'))
        self.credentials_path = _path(get('CREDENTIALS_PATH', 'credentials.json'))
        self.accounts_dir = _path(get('ACCOUNTS_DIR', 'accounts'))
        self.language = get('LANGUAGE', '').strip().lower()  # '' = tarayıcının diline göre
        if self.language not in ('', 'en', 'tr'):
            raise ConfigError(_msg('cfg.language', value=repr(self.language)))
        self.quota_per_minute = _int('GMAIL_QUOTA_PER_MINUTE', get('GMAIL_QUOTA_PER_MINUTE', '5400'), 0)
        self.default_scope = get('DEFAULT_SCOPE', 'inbox')
        if self.default_scope not in ('inbox', 'all'):
            raise ConfigError(_msg('cfg.scope', value=repr(self.default_scope)))
        # İki yazım da olur: ACCOUNT_1=adres=token_yolu (satır başına bir hesap) ve EXTRA_ACCOUNTS=a=x, b=y
        numbered = [env[k] for k in sorted(env, key=_account_order) if re.fullmatch(r'ACCOUNT_\d+', k) and env[k].strip()]
        self.extra_accounts = _extra_accounts(', '.join(numbered + [get('EXTRA_ACCOUNTS', '')]))


def load_settings(env_path=ENV_PATH, environ=None):
    environ = os.environ if environ is None else environ
    merged = {**read_env_file(env_path), **{k: v for k, v in environ.items()}}
    return Settings(merged)


# Uygulamanın kullandığı ayarlar (içe aktarılınca bir kez okunur). Hatalı .env → ConfigError.
settings = load_settings()
