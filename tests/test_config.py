import os

import pytest

from mail_cleaner import accounts, auth, gmail, mailbox, protected, scanner, state, unsubscribe, web
from mail_cleaner import config
from conftest import TEST_ACCOUNT


def write_env(tmp_path, text):
    path = tmp_path / '.env'
    path.write_text(text, encoding='utf-8')
    return str(path)


def test_defaults_without_env_file(tmp_path):
    settings = config.load_settings(str(tmp_path / 'yok.env'), environ={})

    assert (settings.port, settings.demo, settings.default_scope, settings.quota_per_minute) == (5050, False, 'inbox', 5400)
    assert settings.accounts_dir == os.path.join(config.BASE_DIR, 'accounts')
    assert settings.extra_accounts == {}


def test_reads_values_comments_and_quotes(tmp_path):
    env = write_env(tmp_path, '''
# yorum
PORT=6060
DEMO=1
DEFAULT_SCOPE="all"
ACCOUNTS_DIR=~/mail-hesaplar
EXTRA_ACCOUNTS=Okul@Ogr.Example=~/tokenlar/okul.json, is@ornek.example=/tmp/is.json
''')
    settings = config.load_settings(env, environ={})

    assert (settings.port, settings.demo, settings.default_scope) == (6060, True, 'all')
    assert settings.accounts_dir == os.path.expanduser('~/mail-hesaplar')
    assert settings.extra_accounts == {
        'okul@ogr.example': os.path.expanduser('~/tokenlar/okul.json'),
        'is@ornek.example': '/tmp/is.json',
    }


def test_real_environment_wins_over_env_file(tmp_path):
    env = write_env(tmp_path, 'DEMO=0\nPORT=6060\n')

    settings = config.load_settings(env, environ={'DEMO': '1'})

    assert settings.demo is True and settings.port == 6060


@pytest.mark.parametrize('text, word', [
    ('PORT=abc', 'PORT'),
    ('DEMO=belki', 'DEMO'),
    ('DEFAULT_SCOPE=hepsi', 'DEFAULT_SCOPE'),
    ('EXTRA_ACCOUNTS=adres-degil=/tmp/x.json', 'geçersiz adres'),
    ('EXTRA_ACCOUNTS=a@b.example', 'adres=token'),
    ('BOYLE BIR SATIR', 'satır 1'),
])
def test_invalid_values_explain_what_is_wrong(tmp_path, text, word):
    with pytest.raises(config.ConfigError, match=word):
        config.load_settings(write_env(tmp_path, text), environ={})


def test_extra_account_with_external_token_is_listed_and_cannot_be_removed(tmp_path, monkeypatch):
    token = tmp_path / 'disarida' / 'okul.json'
    token.parent.mkdir()
    token.write_text('{}')
    monkeypatch.setattr(accounts, 'EXTRA_ACCOUNT_TOKENS', {'okul@ogr.example': str(token)})
    client = web.app.test_client()

    assert client.get('/api/accounts').get_json()['accounts'] == sorted(['okul@ogr.example', TEST_ACCOUNT])
    assert accounts.AccountPaths('okul@ogr.example').token == str(token)
    resp = client.post('/api/accounts/remove', json={'account': 'okul@ogr.example'})
    assert resp.status_code == 400 and 'EXTRA_ACCOUNTS' in resp.get_json()['error']
    assert token.exists()


def test_extra_account_without_token_file_is_hidden(tmp_path, monkeypatch):
    monkeypatch.setattr(accounts, 'EXTRA_ACCOUNT_TOKENS', {'okul@ogr.example': str(tmp_path / 'yok.json')})

    assert accounts.list_accounts() == [TEST_ACCOUNT]


def test_env_example_parses():
    settings = config.load_settings(os.path.join(config.BASE_DIR, '.env.example'), environ={})
    assert settings.port == 5050


def test_numbered_account_lines_are_read_in_order(tmp_path):
    env = write_env(tmp_path, '''
ACCOUNT_2=ikinci@gmail.example=tokenlar/ikinci.json
ACCOUNT_10=onuncu@gmail.example=tokenlar/onuncu.json
ACCOUNT_1=birinci@gmail.example=tokenlar/birinci.json
ACCOUNT_3=
EXTRA_ACCOUNTS=ek@gmail.example=/tmp/ek.json
''')
    settings = config.load_settings(env, environ={})

    assert list(settings.extra_accounts) == [
        'birinci@gmail.example', 'ikinci@gmail.example', 'onuncu@gmail.example', 'ek@gmail.example']
    assert settings.extra_accounts['birinci@gmail.example'] == os.path.join(config.BASE_DIR, 'tokenlar', 'birinci.json')


def test_bad_numbered_account_line_names_the_problem(tmp_path):
    with pytest.raises(config.ConfigError, match='geçersiz adres'):
        config.load_settings(write_env(tmp_path, 'ACCOUNT_1=adres-yok=tokenlar/x.json'), environ={})
