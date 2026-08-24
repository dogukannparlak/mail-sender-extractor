from unittest.mock import MagicMock

import pytest

import gmail_auth


class FakeCreds:
    def __init__(self, valid=True, expired=False, refresh_token=None):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refresh_called = False

    def refresh(self, request):
        self.refresh_called = True
        self.valid = True

    def to_json(self):
        return '{"fake": "creds"}'


@pytest.fixture
def patched_paths(monkeypatch, tmp_path):
    token_path = tmp_path / 'token.json'
    creds_path = tmp_path / 'credentials.json'
    monkeypatch.setattr(gmail_auth, 'TOKEN_PATH', str(token_path))
    monkeypatch.setattr(gmail_auth, 'CREDENTIALS_PATH', str(creds_path))
    return token_path, creds_path


def test_get_service_raises_when_no_token_and_no_credentials(patched_paths):
    with pytest.raises(FileNotFoundError):
        gmail_auth.get_service()


def test_get_service_uses_existing_valid_token_without_reauth(patched_paths, monkeypatch):
    token_path, _ = patched_paths
    token_path.write_text('{"existing": true}')

    valid_creds = FakeCreds(valid=True)
    monkeypatch.setattr(gmail_auth.Credentials, 'from_authorized_user_file', lambda path, scopes: valid_creds)

    flow_mock = MagicMock()
    monkeypatch.setattr(gmail_auth.InstalledAppFlow, 'from_client_secrets_file', flow_mock)

    build_mock = MagicMock(return_value='fake-service')
    monkeypatch.setattr(gmail_auth, 'build', build_mock)

    service = gmail_auth.get_service()

    assert service == 'fake-service'
    flow_mock.assert_not_called()
    build_mock.assert_called_once_with('gmail', 'v1', credentials=valid_creds)
    assert token_path.read_text() == '{"existing": true}'


def test_get_service_refreshes_expired_token_with_refresh_token(patched_paths, monkeypatch):
    token_path, _ = patched_paths
    token_path.write_text('{"existing": true}')

    expired_creds = FakeCreds(valid=False, expired=True, refresh_token='rt')
    monkeypatch.setattr(gmail_auth.Credentials, 'from_authorized_user_file', lambda path, scopes: expired_creds)
    monkeypatch.setattr(gmail_auth, 'build', MagicMock(return_value='fake-service'))

    service = gmail_auth.get_service()

    assert service == 'fake-service'
    assert expired_creds.refresh_called is True
    assert token_path.read_text() == '{"fake": "creds"}'


def test_get_service_runs_oauth_flow_when_no_token_but_credentials_exist(patched_paths, monkeypatch):
    token_path, creds_path = patched_paths
    creds_path.write_text('{"installed": {}}')

    new_creds = FakeCreds(valid=True)
    flow_instance = MagicMock()
    flow_instance.run_local_server.return_value = new_creds
    monkeypatch.setattr(
        gmail_auth.InstalledAppFlow, 'from_client_secrets_file', MagicMock(return_value=flow_instance)
    )
    monkeypatch.setattr(gmail_auth, 'build', MagicMock(return_value='fake-service'))

    service = gmail_auth.get_service()

    assert service == 'fake-service'
    flow_instance.run_local_server.assert_called_once_with(port=0)
    assert token_path.read_text() == '{"fake": "creds"}'
