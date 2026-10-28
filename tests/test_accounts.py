"""Çoklu hesap: hesap başına veri, hesap ekleme/çıkarma ve eski tek hesaplı düzenden taşıma."""
from unittest.mock import MagicMock

import pytest

import app as app_module
import gmail_auth
from conftest import TEST_ACCOUNT

OTHER = 'is@example.com'


@pytest.fixture
def client():
    app_module.app.config['TESTING'] = True
    return app_module.app.test_client()


@pytest.fixture
def two_accounts():
    paths = app_module.AccountPaths(OTHER)
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
    monkeypatch.setattr(app_module, 'get_service', get_service)
    resp = client.post('/api/delete', json={'account': account, 'senders': ['a@b.example']})
    assert resp.status_code == 400
    get_service.assert_not_called()


def test_each_account_has_its_own_data(client, two_accounts, fake_service_factory, monkeypatch, inline_scan):
    services = {
        TEST_ACCOUNT: fake_service_factory(list_pages=[{'messages': [{'id': 'm1'}]}], default_from='a@x.example'),
        OTHER: fake_service_factory(list_pages=[{'messages': [{'id': 'm9'}]}], default_from='b@y.example'),
    }
    monkeypatch.setattr(app_module, 'get_service', lambda account: services[account])

    client.post('/api/scan', json={'account': TEST_ACCOUNT})
    client.post('/api/scan', json={'account': OTHER})

    mine = client.get(f'/api/senders?account={TEST_ACCOUNT}').get_json()['gonderenler']
    theirs = client.get(f'/api/senders?account={OTHER}').get_json()['gonderenler']
    assert [g['gonderen'] for g in mine] == ['a@x.example']
    assert [g['gonderen'] for g in theirs] == ['b@y.example']


def test_undo_belongs_to_the_account_that_deleted(client, two_accounts, fake_service_factory, monkeypatch):
    service = fake_service_factory(list_handler=lambda kw: {'messages': [{'id': 'm1'}]}, default_from='a@x.example')
    monkeypatch.setattr(app_module, 'get_service', lambda account: service)

    client.post('/api/delete', json={'account': TEST_ACCOUNT, 'senders': ['a@x.example']})

    assert client.get(f'/api/undo?account={TEST_ACCOUNT}').get_json()['available'] is True
    assert client.get(f'/api/undo?account={OTHER}').get_json() == {'available': False}


def test_scan_of_one_account_does_not_block_another(client, two_accounts, monkeypatch):
    monkeypatch.setitem(app_module._scans, TEST_ACCOUNT, dict(app_module._scan_state(TEST_ACCOUNT), running=True))
    monkeypatch.setattr(app_module, 'get_service', lambda account: MagicMock())
    monkeypatch.setattr(app_module, '_delete', lambda paths, *a: app_module.jsonify({'ok': paths.account}))

    blocked = client.post('/api/delete', json={'account': TEST_ACCOUNT, 'senders': ['a@x.example']})
    allowed = client.post('/api/delete', json={'account': OTHER, 'senders': ['a@x.example']})

    assert blocked.status_code == 409
    assert allowed.get_json() == {'ok': OTHER}


def test_add_account_signs_in_and_lists_it(client, monkeypatch):
    def fake_add(accounts_dir):
        import os
        os.makedirs(os.path.join(accounts_dir, OTHER))
        open(os.path.join(accounts_dir, OTHER, 'token.json'), 'w').close()
        return OTHER
    monkeypatch.setattr(gmail_auth, 'add_account', fake_add)

    resp = client.post('/api/accounts/add', json={})

    assert resp.get_json() == {'account': OTHER, 'accounts': sorted([TEST_ACCOUNT, OTHER])}


def test_add_account_is_refused_in_demo_mode(client, monkeypatch):
    monkeypatch.setattr(app_module, 'DEMO_MODE', True)
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
    monkeypatch.setitem(app_module._scans, TEST_ACCOUNT, dict(app_module._scan_state(TEST_ACCOUNT), running=True))

    assert client.post('/api/accounts/remove', json={'account': TEST_ACCOUNT}).status_code == 409


def test_legacy_single_account_files_are_moved(client, monkeypatch, tmp_path):
    import os
    monkeypatch.setattr(app_module, 'BASE_DIR', str(tmp_path))
    monkeypatch.setattr(app_module, 'LEGACY_TOKEN_PATH', str(tmp_path / 'token.json'))
    (tmp_path / 'token.json').write_text('{"eski": true}')
    (tmp_path / 'gonderenler.csv').write_text('Adres,Ad,Mail Sayısı\na@x.example,,3\n')
    monkeypatch.setattr(gmail_auth, 'get_service', lambda token_path=None: 'svc')
    monkeypatch.setattr(gmail_auth, 'account_email', lambda service: 'Eski@Example.com'.lower())

    body = client.get('/api/accounts').get_json()

    assert body['migrated'] == 'eski@example.com'
    assert body['accounts'] == sorted([TEST_ACCOUNT, 'eski@example.com'])
    moved = app_module.AccountPaths('eski@example.com')
    assert open(moved.token).read() == '{"eski": true}'
    assert os.path.exists(moved.csv)
    assert not (tmp_path / 'token.json').exists() and not (tmp_path / 'gonderenler.csv').exists()
