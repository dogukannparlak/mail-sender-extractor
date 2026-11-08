import json
import os
import re

import pytest

from mail_cleaner import i18n
from mail_cleaner.web import app
from mail_cleaner.i18n import t, tn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(i18n.__file__)))
LOCALES = os.path.join(os.path.dirname(i18n.__file__), 'locales')


@pytest.fixture
def client():
    app.config['TESTING'] = True
    return app.test_client()


def source_files():
    """Çeviri anahtarı kullanabilen bütün kaynaklar: paket + kökteki giriş dosyaları."""
    for folder, _, names in os.walk(os.path.join(ROOT, 'mail_cleaner')):
        if 'locales' in folder or '__pycache__' in folder:
            continue
        for name in names:
            if name.endswith(('.py', '.html', '.js')) and name != 'i18n.py':
                yield os.path.join(folder, name)
    for name in ('app.py', 'extract_senders.py'):
        yield os.path.join(ROOT, name)

PLACEHOLDER = re.compile(r'\{(\w+)\}')


def load(language):
    with open(os.path.join(LOCALES, f'{language}.json'), encoding='utf-8') as f:
        return json.load(f)


def test_every_language_has_the_same_keys_and_placeholders():
    english = load('en')
    for language in i18n.LANGUAGES:
        other = load(language)
        assert sorted(other) == sorted(english), f'{language}: keys differ'
        for key, text in english.items():
            # "1 message" gibi tekil metinler sayıyı yazıya gömebilir: {count} yalnız _one anahtarlarında serbest
            ignore = {'count'} if key.endswith('_one') else set()
            assert set(PLACEHOLDER.findall(other[key])) - ignore == set(PLACEHOLDER.findall(text)) - ignore, f'{language}: {key}'


def test_every_key_used_in_code_exists():
    used = set()
    for path in source_files():
        with open(path, encoding='utf-8') as f:
            text = f.read()
        used |= set(re.findall(r"""\bt\(\s*['"]([a-z][a-z_]*(?:\.[a-z_]+)+)['"]""", text))
        for base in re.findall(r"""\btn\(\s*['"]([a-z][a-z_]*(?:\.[a-z_]+)+)['"]""", text):
            used |= {base + '_one', base + '_other'}
    missing = sorted(key for key in used if key not in load('en'))
    assert missing == []


def test_unused_keys_are_not_left_behind():
    text = ''
    for path in source_files():
        with open(path, encoding='utf-8') as f:
            text += f.read()
    unused = []
    for key in load('en'):
        base = re.sub(r'_(one|other)$', '', key)
        # dinamik anahtarlar: 'category.' + değer, 'method.' ~ yöntem, 'unsub.status.' ~ durum, 'help.' ~ sayfa
        dynamic = any(key.startswith(prefix) for prefix in ('category.', 'method.', 'unsub.status.', 'help.'))
        if not dynamic and f"'{key}'" not in text and f"'{base}'" not in text and f'"{key}"' not in text:
            unused.append(key)
    assert unused == []


def test_t_fills_placeholders_and_falls_back_to_english_then_to_the_key():
    assert t('err.unknown_account', lang='en', account="'x'") == "Unknown account: 'x'"
    assert t('err.unknown_account', lang='tr', account="'x'") == "Bilinmeyen hesap: 'x'"
    assert t('no.such.key', lang='tr') == 'no.such.key'
    assert tn('unit.mail', 1, lang='en') == '1 message' and tn('unit.mail', 3, lang='en') == '3 messages'


def test_language_comes_from_query_then_cookie_then_setting_then_browser(client, monkeypatch):
    from mail_cleaner.config import settings
    monkeypatch.setattr(settings, 'language', '')
    page = lambda **kw: client.get('/notifications', **kw).get_data(as_text=True)

    assert '<html lang="en">' in page()                                                     # başlık yok → İngilizce
    assert '<html lang="tr">' in page(headers={'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8'})
    assert '<html lang="en">' in page(headers={'Accept-Language': 'de-DE,de;q=0.9'})
    monkeypatch.setattr(settings, 'language', 'tr')
    assert '<html lang="tr">' in page(headers={'Accept-Language': 'en-US'})                 # .env tarayıcıyı yener
    client.set_cookie('lang', 'en')
    assert '<html lang="en">' in page()                                                     # çerez .env'yi yener
    assert '<html lang="tr">' in page(query_string={'lang': 'tr'})                           # ?lang= çerezi yener


def test_lang_query_is_remembered_in_a_cookie(client):
    response = client.get('/notifications?lang=en')

    assert 'lang=en' in response.headers.get('Set-Cookie', '')
    assert 'Notifications' in response.get_data(as_text=True)
    assert 'Bildirimler' not in client.get('/notifications').get_data(as_text=True)


def test_pages_render_in_english_without_turkish_leftovers(client):
    for path in ('/', '/subscriptions', '/notifications', '/activity-log'):
        body = client.get(path + '?lang=en').get_data(as_text=True)
        assert not re.search(r'[ğüşıöçĞÜŞİÖÇ]', re.sub(r'<script>.*?</script>', '', body, flags=re.S).replace('Türkçe', '')), path


def test_page_carries_only_the_messages_javascript_needs(client):
    body = client.get('/subscriptions?lang=tr').get_data(as_text=True)
    payload = re.search(r'window\.I18N = (\{.*?\});', body, re.S).group(1)

    assert 'Çıkıldı' not in payload and 'log.account_added' not in payload
    assert 'row.copy' in payload


def test_background_threads_use_the_language_they_were_started_with():
    with i18n.use_language('en'):
        assert t('err.scan_running') == 'A scan is already running.'
    assert t('err.scan_running', lang='tr') == 'Tarama zaten sürüyor.'


def test_error_messages_follow_the_request_language(client):
    english = client.post('/api/scan?lang=en', json={'account': 'nobody@example.com'}).get_json()['error']
    turkish = client.post('/api/scan?lang=tr', json={'account': 'nobody@example.com'}).get_json()['error']

    assert english == "Unknown account: 'nobody@example.com'"
    assert turkish == "Bilinmeyen hesap: 'nobody@example.com'"
