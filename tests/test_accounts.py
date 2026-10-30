"""Çoklu hesap: hesap başına veri, hesap ekleme/çıkarma ve eski tek hesaplı düzenden taşıma."""
from unittest.mock import MagicMock

import pytest

from mail_temizleyici import accounts, auth, gmail, mailbox, protected, scanner, state, unsubscribe, web
from mail_temizleyici import auth as gmail_auth
from conftest import TEST_ACCOUNT

OTHER = 'is@example.com'


@pytest.fixture
def client():
    web.app.config['TESTING'] = True
    return web.app.test_client()


@pytest.fixture
def two_accounts():
    paths = accounts.AccountPaths(OTHER)
    import os
    os.makedirs(paths.root)
    with open(paths.token, 'w') as f:
        f.write('{}')
    return paths


def test_single_account_is_used_when_none_is_given(client):
    assert client.get('/api/senders').status_code == 200


def test_account_is_required_when_there_are_several(client, two_accounts):
    resp = client.get('/api/senders')
    assert resp.status_code == 400
    assert 'hesap' in resp.get_json()['error']


@pytest.mark.parametrize('account', ['yok@example.com', '../ben@example.com', 'x'])
def test_unknown_or_malformed_account_is_rejected(client, monkeypatch, account):
    get_service = MagicMock()
    monkeypatch.setattr(accounts, 'get_service', get_service)
    resp = client.post('/api/delete', json={'account': account, 'senders': ['a@b.example']})
    assert resp.status_code == 400
    get_service.assert_not_called()


def test_each_account_has_its_own_data(client, two_accounts, fake_service_factory, monkeypatch, inline_scan):
    services = {
        TEST_ACCOUNT: fake_service_factory(list_pages=[{'messages': [{'id': 'm1'}]}], default_from='a@x.example'),
        OTHER: fake_service_factory(list_pages=[{'messages': [{'id': 'm9'}]}], default_from='b@y.example'),
    }
    monkeypatch.setattr(accounts, 'get_service', lambda account: services[account])

    client.post('/api/scan', json={'account': TEST_ACCOUNT})
    client.post('/api/scan', json={'account': OTHER})

    mine = client.get(f'/api/senders?account={TEST_ACCOUNT}').get_json()['gonderenler']
    theirs = client.get(f'/api/senders?account={OTHER}').get_json()['gonderenler']
    assert [g['gonderen'] for g in mine] == ['a@x.example']
    assert [g['gonderen'] for g in theirs] == ['b@y.example']


def test_undo_belongs_to_the_account_that_deleted(client, two_accounts, fake_service_factory, monkeypatch):
    service = fake_service_factory(list_handler=lambda kw: {'messages': [{'id': 'm1'}]}, default_from='a@x.example')
    monkeypatch.setattr(accounts, 'get_service', lambda account: service)

    client.post('/api/delete', json={'account': TEST_ACCOUNT, 'senders': ['a@x.example']})

    assert client.get(f'/api/undo?account={TEST_ACCOUNT}').get_json()['available'] is True
    assert client.get(f'/api/undo?account={OTHER}').get_json() == {'available': False}


def test_scan_of_one_account_does_not_block_another(client, two_accounts, monkeypatch):
    monkeypatch.setitem(state.scans, TEST_ACCOUNT, dict(state.scan_state(TEST_ACCOUNT), running=True))
    monkeypatch.setattr(accounts, 'get_service', lambda account: MagicMock())
    monkeypatch.setattr(mailbox, 'delete_senders', lambda paths, *a: {'ok': paths.account, 'total_deleted': 0, 'details': []})

    blocked = client.post('/api/delete', json={'account': TEST_ACCOUNT, 'senders': ['a@x.example']})
    allowed = client.post('/api/delete', json={'account': OTHER, 'senders': ['a@x.example']})

    assert blocked.status_code == 409
    assert allowed.get_json() == {'ok': OTHER, 'total_deleted': 0, 'details': []}


CLIENT = {'installed': {'client_id': 'id.apps.googleusercontent.com', 'client_secret': 's',
                        'redirect_uris': ['http://localhost']}}


def _fake_add(calls):
    def fake_add(accounts_dir, client_config, expected_email=None, on_url=None):
        if on_url:
            on_url('https://accounts.google.com/o/oauth2/auth?fake=1')
        import os
        calls.append((client_config, expected_email))
        account = expected_email or OTHER
        os.makedirs(os.path.join(accounts_dir, account), exist_ok=True)
        open(os.path.join(accounts_dir, account, 'token.json'), 'w').close()
        return account
    return fake_add


@pytest.fixture
def idle_sign_in(monkeypatch):
    monkeypatch.setattr(web, '_signin', {'state': 'idle', 'url': None, 'account': None, 'expected': None,
                                         'error': None})


def test_add_account_with_uploaded_client_file(client, monkeypatch, inline_scan, idle_sign_in):
    calls = []
    monkeypatch.setattr(gmail_auth, 'add_account', _fake_add(calls))

    resp = client.post('/api/accounts/add', json={'client': CLIENT})
    status = client.get('/api/accounts/add/status').get_json()

    assert resp.status_code == 202
    assert status['state'] == 'done' and status['account'] == OTHER
    # Tarayıcı kendiliğinden açılmazsa arayüz bu adresi link olarak gösterir.
    assert status['url'].startswith('https://accounts.google.com/')
    assert calls == [(CLIENT, None)]
    assert client.get('/api/accounts').get_json()['accounts'] == sorted([TEST_ACCOUNT, OTHER])


def test_sign_in_error_is_reported_in_status(client, monkeypatch, inline_scan, idle_sign_in):
    def wrong(accounts_dir, client_config, expected_email=None, on_url=None):
        raise gmail_auth.WrongAccount('başka hesapla giriş yapıldı')
    monkeypatch.setattr(gmail_auth, 'add_account', wrong)

    client.post('/api/accounts/add', json={'client': CLIENT})

    assert client.get('/api/accounts/add/status').get_json()['error'] == 'başka hesapla giriş yapıldı'


def test_second_sign_in_while_waiting_is_rejected(client, monkeypatch):
    monkeypatch.setattr(web, '_signin', {'state': 'waiting', 'url': None, 'account': None, 'expected': None,
                                         'error': None})
    add = MagicMock()
    monkeypatch.setattr(gmail_auth, 'add_account', add)

    assert client.post('/api/accounts/add', json={'client': CLIENT}).status_code == 409
    add.assert_not_called()


def test_add_account_without_client_file_explains_what_to_do(client, monkeypatch, tmp_path):
    monkeypatch.setattr(gmail_auth, 'CREDENTIALS_PATH', str(tmp_path / 'yok.json'))
    add = MagicMock()
    monkeypatch.setattr(gmail_auth, 'add_account', add)

    resp = client.post('/api/accounts/add', json={})

    assert resp.status_code == 400 and 'client_secret' in resp.get_json()['error']
    add.assert_not_called()


def test_pending_folder_signs_in_with_its_own_client(client, monkeypatch, inline_scan, idle_sign_in):
    import json, os
    pending = 'bekleyen@example.com'
    folder = os.path.join(accounts.ACCOUNTS_DIR, pending)
    os.makedirs(folder)
    with open(os.path.join(folder, 'credentials.json'), 'w') as f:
        json.dump(CLIENT, f)
    calls = []
    monkeypatch.setattr(gmail_auth, 'add_account', _fake_add(calls))

    assert client.get('/api/accounts').get_json()['pending'] == [pending]
    client.post('/api/accounts/add', json={'pending': pending})

    assert client.get('/api/accounts/add/status').get_json()['account'] == pending
    assert calls == [(CLIENT, pending)]
    assert client.get('/api/accounts').get_json()['pending'] == []


def test_client_file_of_wrong_type_is_rejected():
    import pytest as _pytest
    with _pytest.raises(ValueError, match='Desktop app'):
        gmail_auth.validate_client_config({'web': {'client_id': 'x', 'client_secret': 'y'}})
    with _pytest.raises(ValueError, match='istemci dosyası değil'):
        gmail_auth.validate_client_config({'installed': {}})


def test_shared_credentials_move_to_the_account_they_belong_to(monkeypatch, tmp_path):
    import json, os
    shared = tmp_path / 'credentials.json'
    shared.write_text(json.dumps({'installed': {'client_id': 'ortak-id', 'client_secret': 's'}}))
    monkeypatch.setattr(gmail_auth, 'CREDENTIALS_PATH', str(shared))
    paths = accounts.AccountPaths(TEST_ACCOUNT)
    with open(paths.token, 'w') as f:
        json.dump({'client_id': 'ortak-id', 'refresh_token': 'r'}, f)

    assert accounts.adopt_shared_client(paths) is True
    assert not shared.exists() and os.path.exists(paths.client)


def test_shared_credentials_of_another_client_stay(monkeypatch, tmp_path):
    import json
    shared = tmp_path / 'credentials.json'
    shared.write_text(json.dumps({'installed': {'client_id': 'baska-id', 'client_secret': 's'}}))
    monkeypatch.setattr(gmail_auth, 'CREDENTIALS_PATH', str(shared))
    paths = accounts.AccountPaths(TEST_ACCOUNT)
    with open(paths.token, 'w') as f:
        json.dump({'client_id': 'ortak-id'}, f)

    assert accounts.adopt_shared_client(paths) is False and shared.exists()


def test_add_account_is_refused_in_demo_mode(client, monkeypatch):
    monkeypatch.setattr(web, 'DEMO_MODE', True)
    add = MagicMock()
    monkeypatch.setattr(gmail_auth, 'add_account', add)

    assert client.post('/api/accounts/add', json={}).status_code == 400
    add.assert_not_called()


def test_remove_account_deletes_only_the_token(client, two_accounts):
    with open(two_accounts.csv, 'w') as f:
        f.write('Adres,Ad,Mail Sayısı\n')

    resp = client.post('/api/accounts/remove', json={'account': OTHER})

    assert resp.get_json()['accounts'] == [TEST_ACCOUNT]
    import os
    assert not os.path.exists(two_accounts.token)
    assert os.path.exists(two_accounts.csv)  # yeniden eklenince liste geri gelir


def test_remove_is_blocked_while_that_account_scans(client, monkeypatch):
    monkeypatch.setitem(state.scans, TEST_ACCOUNT, dict(state.scan_state(TEST_ACCOUNT), running=True))

    assert client.post('/api/accounts/remove', json={'account': TEST_ACCOUNT}).status_code == 409


def test_legacy_single_account_files_are_moved(client, monkeypatch, tmp_path):
    import os
    monkeypatch.setattr(accounts, 'BASE_DIR', str(tmp_path))
    monkeypatch.setattr(accounts, 'LEGACY_TOKEN_PATH', str(tmp_path / 'token.json'))
    (tmp_path / 'token.json').write_text('{"eski": true}')
    (tmp_path / 'gonderenler.csv').write_text('Adres,Ad,Mail Sayısı\na@x.example,,3\n')
    monkeypatch.setattr(gmail_auth, 'get_service', lambda token_path=None: 'svc')
    monkeypatch.setattr(gmail_auth, 'account_email', lambda service: 'Eski@Example.com'.lower())

    body = client.get('/api/accounts').get_json()

    assert body['migrated'] == 'eski@example.com'
    assert body['accounts'] == sorted([TEST_ACCOUNT, 'eski@example.com'])
    moved = accounts.AccountPaths('eski@example.com')
    assert open(moved.token).read() == '{"eski": true}'
    assert os.path.exists(moved.csv)
    assert not (tmp_path / 'token.json').exists() and not (tmp_path / 'gonderenler.csv').exists()


def test_sign_in_explains_disabled_gmail_api(client, monkeypatch, inline_scan, idle_sign_in):
    import httplib2
    from googleapiclient.errors import HttpError

    def disabled(accounts_dir, client_config, expected_email=None, on_url=None):
        raise HttpError(httplib2.Response({'status': 403}),
                        b'{"error": {"message": "Gmail API has not been used in project 1", "errors": '
                        b'[{"reason": "accessNotConfigured"}]}}')
    monkeypatch.setattr(gmail_auth, 'add_account', disabled)

    client.post('/api/accounts/add', json={'client': CLIENT})

    assert 'Gmail API açık değil' in client.get('/api/accounts/add/status').get_json()['error']
