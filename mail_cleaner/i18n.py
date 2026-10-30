"""Çok dillilik: İngilizce (en) ve Türkçe (tr).

Metinler `locales/<dil>.json` dosyalarındadır: düz `anahtar → metin`, değişkenler `{ad}` biçiminde.
Yeni bir dil eklemek için `locales/<dil>.json` dosyasını kopyalayıp çevirmek ve `LANGUAGES`'e eklemek yeter.

Dil şu sırayla seçilir: arka plan işi için atanan dil › `?lang=` › `lang` çerezi › `.env`'deki LANGUAGE ›
tarayıcının Accept-Language başlığı › İngilizce. Eksik anahtar İngilizceye, o da yoksa anahtarın kendisine düşer.
"""
import json
import os
import re
import threading
from contextlib import contextmanager

from flask import has_request_context, request

LANGUAGES = {'en': 'English', 'tr': 'Türkçe'}
DEFAULT_LANGUAGE = 'en'
COOKIE_NAME = 'lang'

_LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locales')
_catalogs = {}
_local = threading.local()


def catalog(language):
    if language not in _catalogs:
        with open(os.path.join(_LOCALES_DIR, f'{language}.json'), encoding='utf-8') as f:
            _catalogs[language] = json.load(f)
    return _catalogs[language]


def configured_language():
    from .config import settings  # config içe aktarılırken bu modülü de kullanabilir; döngü olmasın
    return settings.language


def current_language():
    forced = getattr(_local, 'language', None)
    if forced:
        return forced
    if has_request_context():
        for candidate in (request.args.get('lang'), request.cookies.get(COOKIE_NAME)):
            if candidate in LANGUAGES:
                return candidate
    if configured_language():
        return configured_language()
    if has_request_context():
        best = request.accept_languages.best_match(list(LANGUAGES))
        if best:
            return best
    return DEFAULT_LANGUAGE


@contextmanager
def use_language(language):
    """Arka plan iş parçacığında (istek yokken) belirli bir dilde çalışır, ör. taramanın hata metinleri."""
    previous = getattr(_local, 'language', None)
    _local.language = language
    try:
        yield
    finally:
        _local.language = previous


def t(key, lang=None, **params):
    """Anahtarın metnini döner; `{ad}` yer tutucuları params ile doldurulur."""
    language = lang or current_language()
    text = catalog(language).get(key)
    if text is None:
        text = catalog(DEFAULT_LANGUAGE).get(key, key)
    if params:
        text = re.sub(r'\{(\w+)\}', lambda m: str(params.get(m.group(1), m.group(0))), text)
    return text


_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'js')
_js_keys = None


def _used_by_js():
    """static/js dosyalarında geçen anahtarlar (şablonlardaki anahtarlar sunucuda çizilir, sayfaya gömülmez): 'a.b' ile 'a.' önekleri.

    `tn('x.y', n)` için x.y_one / x.y_other da gerekir; 'category.' + değer gibi dinamik anahtarlar önekle yakalanır.
    """
    global _js_keys
    if _js_keys is None:
        sources = []
        for name in os.listdir(_STATIC_DIR):
            if name.endswith('.js'):
                with open(os.path.join(_STATIC_DIR, name), encoding='utf-8') as f:
                    sources.append(f.read())
        text = '\n'.join(sources)
        exact = set(re.findall(r"""['"]([a-z][a-z_]*(?:\.[a-z_]+)+)['"]""", text))
        prefixes = set(re.findall(r"""['"]([a-z][a-z_]*\.)['"]""", text))
        everything = catalog(DEFAULT_LANGUAGE).keys()
        _js_keys = {k for k in everything
                    if k in exact or
                    (k.endswith(('_one', '_other')) and k.rsplit('_', 1)[0] in exact) or
                    any(k.startswith(prefix) for prefix in prefixes)}
    return _js_keys


def messages_for(language):
    """Sayfadaki JS için gereken metinler (eksikler İngilizceyle tamamlanır). Bütün katalog sayfaya gömülmez."""
    merged = {**catalog(DEFAULT_LANGUAGE), **catalog(language)}
    return {key: merged[key] for key in _used_by_js()}


def tn(key, count, **params):
    """Çoğul: `anahtar_one` (count == 1) ya da `anahtar_other`; {count} otomatik doldurulur."""
    return t(f'{key}_one' if count == 1 else f'{key}_other', count=count, **params)
