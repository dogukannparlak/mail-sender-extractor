import csv
from collections import Counter
from unittest.mock import MagicMock

import httplib2
import pytest
import requests
from googleapiclient.errors import HttpError

import app as app_module
from app import (
    app,
    extract_email,
    from_query,
    find_message_ids,
    is_safe_one_click_url,
    find_unsubscribe_info,
    _senders_payload,
    _validated_senders,
)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    return app.test_client()


def make_http_error(status, message):
    resp = httplib2.Response({'status': status})
    content = ('{"error": {"message": "%s"}}' % message).encode()
    return HttpError(resp, content)


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

class TestExtractEmail:
    def test_extracts_address_from_name_and_bracket_format(self):
        assert extract_email('Alice <alice@example.com>') == 'alice@example.com'

    def test_returns_stripped_value_when_no_brackets(self):
        assert extract_email('  bob@example.com  ') == 'bob@example.com'

    def test_uses_real_address_not_bracketed_display_name(self):
        # Görünen ad içine başka bir adres gizlenirse o adresin mailleri silinmemeli.
        assert extract_email('"<banka@ornek.com>" <spam@kotu.com>') == 'spam@kotu.com'

    def test_strips_trailing_comment(self):
        assert extract_email('a@b.com (Ali Veli)') == 'a@b.com'

    @pytest.mark.parametrize('sender', [
        'spam@kotu.com OR label:inbox',
        'spam@kotu.com label:inbox',
        'Kötü <a@b.com OR in:anywhere>',
        'adres-yok',
        '',
    ])
    def test_rejects_values_that_could_change_the_gmail_query(self, sender):
        with pytest.raises(ValueError):
            extract_email(sender)


class TestFromQuery:
    def test_quotes_address(self):
        assert from_query('a@b.com') == 'from:"a@b.com"'


class TestSendersPayload:
    def test_orders_by_count_desc_and_sums_total(self):
        payload = _senders_payload({
            'a@x.com': {'ad': 'A', 'mail_sayisi': 1},
            'b@x.com': {'ad': '', 'mail_sayisi': 5},
        })

        assert payload['toplam_mail_sayisi'] == 6
        assert payload['gonderenler'] == [
            {'gonderen': 'b@x.com', 'ad': '', 'mail_sayisi': 5},
            {'gonderen': 'a@x.com', 'ad': 'A', 'mail_sayisi': 1},
        ]

    def test_empty_input_yields_zero_total_and_empty_list(self):
        assert _senders_payload({}) == {'toplam_mail_sayisi': 0, 'gonderenler': []}


class TestValidatedSenders:
    def test_accepts_list_body(self):
        assert _validated_senders({'senders': ['a@example.com']}) == ['a@example.com']

    def test_rejects_missing_key(self):
        with pytest.raises(ValueError):
            _validated_senders({})

    def test_rejects_non_list_value(self):
        with pytest.raises(ValueError):
            _validated_senders({'senders': 'not-a-list'})

    def test_rejects_none_body(self):
        with pytest.raises(ValueError):
            _validated_senders(None)


class TestFindMessageIds:
    def test_paginates_until_no_next_page_token(self, fake_service_factory):
        service = fake_service_factory(
            list_pages=[
                {'messages': [{'id': 'm1'}, {'id': 'm2'}], 'nextPageToken': 'p2'},
                {'messages': [{'id': 'm3'}]},
            ]
        )

        ids = find_message_ids(service, 'someone@example.com')

        assert ids == ['m1', 'm2', 'm3']
        assert service.messages_resource.list_calls[0]['q'] == 'from:"someone@example.com"'
        assert service.messages_resource.list_calls[1]['pageToken'] == 'p2'

    def test_returns_empty_list_when_no_messages(self, fake_service_factory):
        service = fake_service_factory(list_pages=[{'messages': []}])

        assert find_message_ids(service, 'nobody@example.com') == []


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(app_module, '_resolve_host', lambda hostname: {'93.184.215.14'})


class TestIsSafeOneClickUrl:
    def test_accepts_public_https(self, public_dns):
        assert is_safe_one_click_url('https://example.com/unsub') is True

    @pytest.mark.parametrize('url', ['http://example.com/unsub', 'ftp://example.com/x', 'https:///x'])
    def test_rejects_non_https(self, public_dns, url):
        assert is_safe_one_click_url(url) is False

    @pytest.mark.parametrize('url', [
        'https://127.0.0.1\\@example.com/x',
        'https://127.0.0.1:8443\\@example.com/x',
        'https://nas.lan\\@example.com/',
        'https://user:pass@example.com/x',
        'https://127.0.0.1@example.com/x',
    ])
    def test_rejects_urls_parsed_differently_by_requests(self, public_dns, url):
        # public_dns her host'u public gösterir; reddin sebebi yalnız URL biçimi olmalı.
        assert is_safe_one_click_url(url) is False

    @pytest.mark.parametrize('addr', ['127.0.0.1', '10.0.0.1', '192.168.1.1', '169.254.169.254', '::1', 'fd00::1'])
    def test_rejects_private_and_loopback_targets(self, monkeypatch, addr):
        monkeypatch.setattr(app_module, '_resolve_host', lambda hostname: {addr})

        assert is_safe_one_click_url('https://unsub.example.com/x') is False

    def test_rejects_when_any_resolved_address_is_private(self, monkeypatch):
        monkeypatch.setattr(app_module, '_resolve_host', lambda hostname: {'93.184.215.14', '127.0.0.1'})

        assert is_safe_one_click_url('https://unsub.example.com/x') is False

    def test_rejects_unresolvable_host(self, monkeypatch):
        def fail(hostname):
            raise app_module.socket.gaierror('no such host')

        monkeypatch.setattr(app_module, '_resolve_host', fail)

        assert is_safe_one_click_url('https://nope.invalid/x') is False


class TestFindUnsubscribeInfo:
    def test_not_found_when_sender_has_no_messages(self, fake_service_factory):
        service = fake_service_factory(list_pages=[{'messages': []}])

        assert find_unsubscribe_info(service, 'x@example.com') == {'status': 'not_found'}

    def test_none_when_no_messages_carry_the_header(self, fake_service_factory):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={'m1': {'payload': {'headers': []}}},
        )

        assert find_unsubscribe_info(service, 'x@example.com') == {'status': 'none'}

    def test_manual_link_for_http_url_without_one_click(self, fake_service_factory):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={
                'm1': {
                    'payload': {
                        'headers': [
                            {'name': 'List-Unsubscribe', 'value': '<https://example.com/unsub>'},
                        ]
                    }
                }
            },
        )

        assert find_unsubscribe_info(service, 'x@example.com') == {
            'status': 'manual_link',
            'url': 'https://example.com/unsub',
        }

    def test_manual_mailto_when_only_mailto_present(self, fake_service_factory):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={
                'm1': {
                    'payload': {
                        'headers': [
                            {'name': 'List-Unsubscribe', 'value': '<mailto:unsub@example.com>'},
                        ]
                    }
                }
            },
        )

        assert find_unsubscribe_info(service, 'x@example.com') == {
            'status': 'manual_mailto',
            'url': 'mailto:unsub@example.com',
        }

    def test_one_click_success_posts_and_returns_done(self, fake_service_factory, monkeypatch, public_dns):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={
                'm1': {
                    'payload': {
                        'headers': [
                            {'name': 'list-unsubscribe', 'value': '<https://example.com/unsub>'},
                            {'name': 'list-unsubscribe-post', 'value': 'List-Unsubscribe=One-Click'},
                        ]
                    }
                }
            },
        )
        ok_response = MagicMock(ok=True, is_redirect=False)
        post_mock = MagicMock(return_value=ok_response)
        monkeypatch.setattr(requests, 'post', post_mock)

        result = find_unsubscribe_info(service, 'x@example.com', confirm_one_click=True)

        assert result == {'status': 'done', 'url': 'https://example.com/unsub'}
        post_mock.assert_called_once_with(
            'https://example.com/unsub', data={'List-Unsubscribe': 'One-Click'},
            timeout=10, allow_redirects=False,
        )

    def test_one_click_is_not_posted_to_private_network(self, fake_service_factory, monkeypatch):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={
                'm1': {
                    'payload': {
                        'headers': [
                            {'name': 'List-Unsubscribe', 'value': '<https://router.local/unsub>'},
                            {'name': 'List-Unsubscribe-Post', 'value': 'List-Unsubscribe=One-Click'},
                        ]
                    }
                }
            },
        )
        monkeypatch.setattr(app_module, '_resolve_host', lambda hostname: {'192.168.1.1'})
        post_mock = MagicMock()
        monkeypatch.setattr(requests, 'post', post_mock)

        result = find_unsubscribe_info(service, 'x@example.com', confirm_one_click=True)

        post_mock.assert_not_called()
        assert result == {'status': 'manual_link', 'url': 'https://router.local/unsub'}

    def test_one_click_redirect_is_not_treated_as_done(self, fake_service_factory, monkeypatch, public_dns):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={
                'm1': {
                    'payload': {
                        'headers': [
                            {'name': 'List-Unsubscribe', 'value': '<https://example.com/unsub>'},
                            {'name': 'List-Unsubscribe-Post', 'value': 'One-Click'},
                        ]
                    }
                }
            },
        )
        monkeypatch.setattr(requests, 'post', MagicMock(return_value=MagicMock(ok=True, is_redirect=True)))

        result = find_unsubscribe_info(service, 'x@example.com', confirm_one_click=True)

        assert result == {'status': 'manual_link', 'url': 'https://example.com/unsub'}

    def test_one_click_falls_back_to_manual_link_on_non_ok_response(self, fake_service_factory, monkeypatch, public_dns):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={
                'm1': {
                    'payload': {
                        'headers': [
                            {'name': 'List-Unsubscribe', 'value': '<https://example.com/unsub>'},
                            {'name': 'List-Unsubscribe-Post', 'value': 'One-Click'},
                        ]
                    }
                }
            },
        )
        monkeypatch.setattr(requests, 'post', MagicMock(return_value=MagicMock(ok=False)))

        result = find_unsubscribe_info(service, 'x@example.com', confirm_one_click=True)

        assert result == {'status': 'manual_link', 'url': 'https://example.com/unsub'}

    def test_one_click_falls_back_to_manual_link_on_request_exception(self, fake_service_factory, monkeypatch, public_dns):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={
                'm1': {
                    'payload': {
                        'headers': [
                            {'name': 'List-Unsubscribe', 'value': '<https://example.com/unsub>'},
                            {'name': 'List-Unsubscribe-Post', 'value': 'One-Click'},
                        ]
                    }
                }
            },
        )
        monkeypatch.setattr(requests, 'post', MagicMock(side_effect=requests.RequestException('boom')))

        result = find_unsubscribe_info(service, 'x@example.com', confirm_one_click=True)

        assert result == {'status': 'manual_link', 'url': 'https://example.com/unsub'}

    def test_skips_messages_without_header_to_find_one_that_has_it(self, fake_service_factory):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}, {'id': 'm2'}]}],
            get_responses={
                'm1': {'payload': {'headers': []}},
                'm2': {
                    'payload': {
                        'headers': [{'name': 'List-Unsubscribe', 'value': '<mailto:unsub@example.com>'}]
                    }
                },
            },
        )

        assert find_unsubscribe_info(service, 'x@example.com') == {
            'status': 'manual_mailto',
            'url': 'mailto:unsub@example.com',
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class TestApiSenders:
    def test_reads_from_csv_and_sums_total(self, client, monkeypatch, tmp_path):
        csv_path = tmp_path / 'gonderenler.csv'
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['İsim/Adres', 'Mail Sayısı'])
            writer.writerow(['a@example.com', '3'])
            writer.writerow(['b@example.com', '2'])
        monkeypatch.setattr(app_module, 'CSV_PATH', str(csv_path))

        resp = client.get('/api/senders')

        assert resp.status_code == 200
        assert resp.get_json() == {
            'toplam_mail_sayisi': 5,
            'gonderenler': [
                {'gonderen': 'a@example.com', 'ad': '', 'mail_sayisi': 3},
                {'gonderen': 'b@example.com', 'ad': '', 'mail_sayisi': 2},
            ],
        }

    def test_legacy_csv_is_merged_by_address(self, client, monkeypatch, tmp_path):
        csv_path = tmp_path / 'gonderenler.csv'
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['İsim/Adres', 'Mail Sayısı'])
            writer.writerow(['"Ali (Classroom)" <no-reply@classroom.google.com>', '5'])
            writer.writerow(['"Ayşe (Classroom)" <No-Reply@classroom.google.com>', '2'])
        monkeypatch.setattr(app_module, 'CSV_PATH', str(csv_path))

        assert client.get('/api/senders').get_json()['gonderenler'] == [
            {'gonderen': 'no-reply@classroom.google.com', 'ad': 'Ali (Classroom)', 'mail_sayisi': 7},
        ]

    def test_missing_csv_returns_empty_payload(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(app_module, 'CSV_PATH', str(tmp_path / 'missing.csv'))

        resp = client.get('/api/senders')

        assert resp.status_code == 200
        assert resp.get_json() == {'toplam_mail_sayisi': 0, 'gonderenler': []}


class _InlineThread:
    """threading.Thread yerine: taramayı start() çağrısında hemen çalıştırır."""

    def __init__(self, target, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


@pytest.fixture
def inline_scan(monkeypatch):
    monkeypatch.setattr(app_module.threading, 'Thread', _InlineThread)
    monkeypatch.setitem(app_module._scan_state, 'running', False)


class TestApiScan:
    def test_scans_in_background_and_persists_csv(self, client, monkeypatch, inline_scan):
        monkeypatch.setattr(app_module, 'get_service', lambda: 'fake-service')

        def fake_extract(service, progress):
            progress(1, 2)
            progress(2, 2)
            return {'a@example.com': {'ad': '', 'mail_sayisi': 2}}
        monkeypatch.setattr(app_module, 'extract_senders', fake_extract)

        resp = client.post('/api/scan')
        status = client.get('/api/scan/status').get_json()

        assert resp.status_code == 202
        assert status['running'] is False and status['error'] is None
        assert (status['processed'], status['total']) == (2, 2)
        assert client.get('/api/senders').get_json() == {
            'toplam_mail_sayisi': 2,
            'gonderenler': [{'gonderen': 'a@example.com', 'ad': '', 'mail_sayisi': 2}],
        }

    def test_second_scan_while_running_is_rejected(self, client, monkeypatch, inline_scan):
        monkeypatch.setitem(app_module._scan_state, 'running', True)
        get_service_mock = MagicMock()
        monkeypatch.setattr(app_module, 'get_service', get_service_mock)

        resp = client.post('/api/scan')

        assert resp.status_code == 409
        get_service_mock.assert_not_called()

    def test_scan_error_is_reported_in_status(self, client, monkeypatch, inline_scan):
        monkeypatch.setattr(app_module, 'get_service', lambda: 'fake-service')

        def failing_extract(service, progress):
            raise make_http_error(500, 'backend error')
        monkeypatch.setattr(app_module, 'extract_senders', failing_extract)

        client.post('/api/scan')
        status = client.get('/api/scan/status').get_json()

        assert status['running'] is False
        assert 'Gmail API hatası (500)' in status['error']

    def test_login_error_is_returned_directly_and_frees_the_lock(self, client, monkeypatch, inline_scan):
        def missing_credentials():
            raise FileNotFoundError('credentials.json bulunamadı')
        monkeypatch.setattr(app_module, 'get_service', missing_credentials)

        resp = client.post('/api/scan')

        assert resp.status_code == 500
        assert client.get('/api/scan/status').get_json()['running'] is False


class TestApiDelete:
    def test_rejects_body_without_senders_list(self, client):
        resp = client.post('/api/delete', json={})

        assert resp.status_code == 400
        assert 'senders' in resp.get_json()['error']

    def test_trashes_messages_in_chunks_of_1000(self, client, monkeypatch, fake_service_factory):
        message_ids = [{'id': f'm{i}'} for i in range(1500)]
        service = fake_service_factory(list_pages=[{'messages': message_ids}])
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        resp = client.post('/api/delete', json={'senders': ['Alice <alice@example.com>']})

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['total_deleted'] == 1500
        assert body['details'] == [{'sender': 'Alice <alice@example.com>', 'email': 'alice@example.com', 'deleted': 1500}]

        calls = service.messages_resource.batch_modify_calls
        assert [len(c['body']['ids']) for c in calls] == [1000, 500]
        for c in calls:
            assert c['body']['addLabelIds'] == ['TRASH']
            assert c['body']['removeLabelIds'] == ['INBOX', 'UNREAD']


    def test_deleted_senders_are_removed_from_saved_csv(self, client, monkeypatch, fake_service_factory, tmp_path):
        csv_path = tmp_path / 'gonderenler.csv'
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['İsim/Adres', 'Mail Sayısı'])
            writer.writerow(['Alice <alice@example.com>', '3'])
            writer.writerow(['Bob <bob@example.com>', '2'])
        monkeypatch.setattr(app_module, 'CSV_PATH', str(csv_path))
        service = fake_service_factory(list_pages=[{'messages': [{'id': 'm1'}]}])
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        resp = client.post('/api/delete', json={'senders': ['Alice <alice@example.com>']})

        assert resp.status_code == 200
        assert client.get('/api/senders').get_json() == {
            'toplam_mail_sayisi': 2,
            'gonderenler': [{'gonderen': 'bob@example.com', 'ad': 'Bob', 'mail_sayisi': 2}],
        }

    def test_delete_without_saved_csv_does_not_create_one(self, client, monkeypatch, fake_service_factory, tmp_path):
        csv_path = tmp_path / 'gonderenler.csv'
        monkeypatch.setattr(app_module, 'CSV_PATH', str(csv_path))
        service = fake_service_factory(list_pages=[{'messages': []}])
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        resp = client.post('/api/delete', json={'senders': ['Alice <alice@example.com>']})

        assert resp.status_code == 200
        assert not csv_path.exists()

    def test_invalid_sender_rejects_whole_request_before_trashing(self, client, monkeypatch, fake_service_factory):
        service = fake_service_factory(list_pages=[{'messages': [{'id': 'm1'}]}])
        get_service_mock = MagicMock(return_value=service)
        monkeypatch.setattr(app_module, 'get_service', get_service_mock)

        resp = client.post('/api/delete', json={
            'senders': ['Alice <alice@example.com>', 'spam@kotu.com OR label:inbox'],
        })

        assert resp.status_code == 400
        get_service_mock.assert_not_called()
        assert service.messages_resource.list_calls == []
        assert service.messages_resource.batch_modify_calls == []


def _scope_aware_service(fake_service_factory, inbox_ids, archived_ids):
    """`in:inbox` sorgusunda yalnız gelen kutusu, diğerinde arşiv dahil tümü döner."""
    def handler(kwargs):
        ids = inbox_ids if 'in:inbox' in kwargs['q'] else inbox_ids + archived_ids
        return {'messages': [{'id': i} for i in ids]}
    return fake_service_factory(list_handler=handler)


class TestDeleteScope:
    def test_default_scope_is_inbox_like_the_scan(self, client, monkeypatch, fake_service_factory):
        service = _scope_aware_service(fake_service_factory, ['i1', 'i2'], ['a1'])
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        resp = client.post('/api/delete', json={'senders': ['a@example.com']})

        assert resp.get_json()['total_deleted'] == 2
        assert service.messages_resource.list_calls[0]['q'] == 'from:"a@example.com" in:inbox'

    def test_all_scope_includes_archived_mail(self, client, monkeypatch, fake_service_factory):
        service = _scope_aware_service(fake_service_factory, ['i1', 'i2'], ['a1'])
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        resp = client.post('/api/delete', json={'senders': ['a@example.com'], 'scope': 'all'})

        assert resp.get_json()['total_deleted'] == 3
        assert service.messages_resource.batch_modify_calls[0]['body']['ids'] == ['i1', 'i2', 'a1']

    def test_unknown_scope_is_rejected_before_gmail(self, client, monkeypatch):
        get_service_mock = MagicMock()
        monkeypatch.setattr(app_module, 'get_service', get_service_mock)

        resp = client.post('/api/delete', json={'senders': ['a@example.com'], 'scope': 'in:anywhere'})

        assert resp.status_code == 400
        get_service_mock.assert_not_called()

    @pytest.mark.parametrize('scope, expected', [('inbox', 2), ('all', 3)])
    def test_count_matches_what_delete_trashes(self, client, monkeypatch, fake_service_factory, scope, expected):
        service = _scope_aware_service(fake_service_factory, ['i1', 'i2'], ['a1'])
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        count = client.post('/api/count', json={'senders': ['a@example.com'], 'scope': scope}).get_json()
        deleted = client.post('/api/delete', json={'senders': ['a@example.com'], 'scope': scope}).get_json()

        assert count['total'] == expected
        assert count['details'] == [{'sender': 'a@example.com', 'email': 'a@example.com', 'count': expected}]
        assert deleted['total_deleted'] == count['total']

    def test_count_does_not_modify_anything(self, client, monkeypatch, fake_service_factory):
        service = _scope_aware_service(fake_service_factory, ['i1'], [])
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        client.post('/api/count', json={'senders': ['a@example.com']})

        assert service.messages_resource.batch_modify_calls == []

    def test_preview_uses_the_same_scope(self, client, monkeypatch, fake_service_factory):
        service = _scope_aware_service(fake_service_factory, [], [])
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        client.post('/api/preview', json={'sender': 'a@example.com', 'scope': 'inbox'})

        assert service.messages_resource.list_calls[0]['q'] == 'from:"a@example.com" in:inbox'


class TestProtectedSenders:
    def test_protected_address_is_never_trashed(self, client, monkeypatch, fake_service_factory):
        service = fake_service_factory(list_pages=[{'messages': [{'id': 'm1'}]}])
        get_service_mock = MagicMock(return_value=service)
        monkeypatch.setattr(app_module, 'get_service', get_service_mock)
        client.post('/api/protected', json={'value': 'Banka@Ornek.com'})

        resp = client.post('/api/delete', json={'senders': ['a@example.com', 'Banka <banka@ornek.com>']})

        assert resp.status_code == 400
        assert 'banka@ornek.com' in resp.get_json()['error']
        get_service_mock.assert_not_called()

    @pytest.mark.parametrize('email', ['x@garanti.com.tr', 'x@mail.garanti.com.tr'])
    def test_protected_domain_covers_subdomains(self, client, monkeypatch, email):
        monkeypatch.setattr(app_module, 'get_service', MagicMock())
        client.post('/api/protected', json={'value': '@garanti.com.tr'})

        assert client.post('/api/delete', json={'senders': [email]}).status_code == 400
        assert client.post('/api/unsubscribe', json={'senders': [email]}).status_code == 400

    def test_lookalike_domain_is_not_protected(self):
        protected = {'adresler': [], 'alanlar': ['@garanti.com.tr']}
        assert not app_module.is_protected('x@notgaranti.com.tr', protected)

    def test_unprotect_removes_entry(self, client):
        client.post('/api/protected', json={'value': 'a@b.com'})
        resp = client.post('/api/protected', json={'value': 'a@b.com', 'protected': False})

        assert resp.get_json() == {'adresler': [], 'alanlar': []}
        assert client.get('/api/protected').get_json() == {'adresler': [], 'alanlar': []}

    @pytest.mark.parametrize('value', ['garanti.com.tr', 'a@b.com OR x', '@', 42])
    def test_rejects_invalid_entries(self, client, value):
        assert client.post('/api/protected', json={'value': value}).status_code == 400


class LabelledMailbox:
    """Etiket durumunu tutan sahte posta kutusu: list sorguyu etiketlere göre süzer, batchModify etiketleri değiştirir."""

    def __init__(self, fake_service_factory, labels_by_id):
        self.labels = {i: set(l) for i, l in labels_by_id.items()}
        self.service = fake_service_factory(list_handler=self._list)
        self.service.messages_resource.batchModify = self._batch_modify

    def _list(self, kwargs):
        q = kwargs['q']
        ids = [i for i, l in self.labels.items() if 'TRASH' not in l
               and ('in:inbox' not in q or 'INBOX' in l)
               and ('is:unread' not in q or 'UNREAD' in l)]
        return {'messages': [{'id': i} for i in ids]}

    def _batch_modify(self, userId, body):
        for i in body['ids']:
            self.labels[i] |= set(body['addLabelIds'])
            self.labels[i] -= set(body['removeLabelIds'])
        from conftest import _Executable
        return _Executable({})


class TestUndo:
    LABELS = {
        'inbox_unread': {'INBOX', 'UNREAD', 'CATEGORY_PROMOTIONS'},
        'inbox_read': {'INBOX'},
        'archived_unread': {'UNREAD'},
        'archived_read': set(),
    }

    @pytest.mark.parametrize('scope', ['inbox', 'all'])
    def test_delete_then_undo_restores_original_labels(self, client, monkeypatch, fake_service_factory, scope):
        box = LabelledMailbox(fake_service_factory, self.LABELS)
        monkeypatch.setattr(app_module, 'get_service', lambda: box.service)
        before = {i: set(l) for i, l in box.labels.items()}

        deleted = client.post('/api/delete', json={'senders': ['a@example.com'], 'scope': scope}).get_json()
        trashed = {i for i, l in box.labels.items() if 'TRASH' in l}
        undone = client.post('/api/undo')

        assert deleted['total_deleted'] == (2 if scope == 'inbox' else 4)
        assert trashed == ({'inbox_unread', 'inbox_read'} if scope == 'inbox' else set(self.LABELS))
        assert undone.status_code == 200
        assert box.labels == before

    def test_undo_restores_csv_rows_and_is_single_use(self, client, monkeypatch, fake_service_factory, tmp_path):
        from extract_senders import save_to_csv
        save_to_csv({'a@example.com': {'ad': 'A', 'mail_sayisi': 2}, 'b@example.com': {'ad': '', 'mail_sayisi': 1}},
                    filename=app_module.CSV_PATH)
        box = LabelledMailbox(fake_service_factory, {'m1': {'INBOX'}})
        monkeypatch.setattr(app_module, 'get_service', lambda: box.service)

        client.post('/api/delete', json={'senders': ['a@example.com']})
        info = client.get('/api/undo').get_json()
        client.post('/api/undo')

        assert info == {'available': True, 'zaman': info['zaman'], 'count': 1, 'senders': ['a@example.com']}
        assert [g['gonderen'] for g in client.get('/api/senders').get_json()['gonderenler']] == [
            'a@example.com', 'b@example.com']
        assert client.get('/api/undo').get_json() == {'available': False}
        assert client.post('/api/undo').status_code == 400

    def test_delete_with_no_matches_keeps_previous_undo(self, client, monkeypatch, fake_service_factory):
        box = LabelledMailbox(fake_service_factory, {'m1': {'INBOX'}})
        monkeypatch.setattr(app_module, 'get_service', lambda: box.service)
        client.post('/api/delete', json={'senders': ['a@example.com']})

        client.post('/api/delete', json={'senders': ['a@example.com']})  # artık eşleşme yok

        assert client.get('/api/undo').get_json()['count'] == 1


class TestOneClickConfirmation:
    def _service(self, fake_service_factory):
        return fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={'m1': {'payload': {'headers': [
                {'name': 'List-Unsubscribe', 'value': '<https://example.com/u>'},
                {'name': 'List-Unsubscribe-Post', 'value': 'List-Unsubscribe=One-Click'},
            ]}}},
        )

    def test_no_post_is_sent_without_confirmation(self, client, monkeypatch, fake_service_factory, public_dns):
        post_mock = MagicMock()
        monkeypatch.setattr(app_module.requests, 'post', post_mock)
        service = self._service(fake_service_factory)
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        resp = client.post('/api/unsubscribe', json={'senders': ['x@example.com']})

        post_mock.assert_not_called()
        assert resp.get_json()['results'][0]['status'] == 'one_click_available'

    @pytest.mark.parametrize('flag', ['true', 1, 'yes'])
    def test_only_boolean_true_confirms(self, client, monkeypatch, fake_service_factory, public_dns, flag):
        post_mock = MagicMock()
        monkeypatch.setattr(app_module.requests, 'post', post_mock)
        service = self._service(fake_service_factory)
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        client.post('/api/unsubscribe', json={'senders': ['x@example.com'], 'confirm_one_click': flag})

        post_mock.assert_not_called()

    def test_confirmed_request_posts_once(self, client, monkeypatch, fake_service_factory, public_dns):
        post_mock = MagicMock(return_value=MagicMock(ok=True, is_redirect=False))
        monkeypatch.setattr(app_module.requests, 'post', post_mock)
        service = self._service(fake_service_factory)
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        resp = client.post('/api/unsubscribe', json={'senders': ['x@example.com'], 'confirm_one_click': True})

        post_mock.assert_called_once()
        assert resp.get_json()['results'][0]['status'] == 'done'


class TestApiPreview:
    def test_rejects_missing_sender(self, client):
        resp = client.post('/api/preview', json={})

        assert resp.status_code == 400

    def test_returns_recent_message_previews(self, client, monkeypatch, fake_service_factory):
        service = fake_service_factory(
            list_pages=[{'messages': [{'id': 'm1'}]}],
            get_responses={
                'm1': {
                    'payload': {'headers': [{'name': 'Subject', 'value': 'Hello'}]},
                    'internalDate': '1700000000000',
                    'snippet': 'a snippet',
                }
            },
        )
        monkeypatch.setattr(app_module, 'get_service', lambda: service)

        resp = client.post('/api/preview', json={'sender': 'Alice <alice@example.com>'})

        assert resp.status_code == 200
        assert resp.get_json() == {
            'sender': 'Alice <alice@example.com>',
            'email': 'alice@example.com',
            'previews': [{'subject': 'Hello', 'date': 1700000000000, 'snippet': 'a snippet'}],
        }


class TestErrorHandling:
    def test_http_error_maps_to_502_with_scope_hint_on_403(self, client, monkeypatch):
        def raise_http_error():
            raise make_http_error(403, 'insufficient scope')

        monkeypatch.setattr(app_module, 'get_service', raise_http_error)

        resp = client.post('/api/scan')

        assert resp.status_code == 502
        assert 'token.json' in resp.get_json()['error']

    def test_file_not_found_maps_to_500(self, client, monkeypatch):
        def raise_missing_credentials():
            raise FileNotFoundError('credentials.json bulunamadi')

        monkeypatch.setattr(app_module, 'get_service', raise_missing_credentials)

        resp = client.post('/api/scan')

        assert resp.status_code == 500

    def test_unexpected_exception_maps_to_500(self, client, monkeypatch):
        def raise_runtime_error():
            raise RuntimeError('boom')

        monkeypatch.setattr(app_module, 'get_service', raise_runtime_error)

        resp = client.post('/api/scan')

        assert resp.status_code == 500

    def test_unexpected_exception_does_not_leak_internal_message(self, client, monkeypatch):
        def raise_runtime_error():
            raise RuntimeError('/Users/gizli/yol ayrıntısı')

        monkeypatch.setattr(app_module, 'get_service', raise_runtime_error)

        resp = client.post('/api/scan')

        assert 'gizli' not in resp.get_json()['error']


class TestHostCheck:
    @pytest.mark.parametrize('host', ['localhost', 'localhost:5050', '127.0.0.1:5050', '[::1]:5050'])
    def test_allows_local_hosts(self, client, monkeypatch, tmp_path, host):
        monkeypatch.setattr(app_module, 'CSV_PATH', str(tmp_path / 'missing.csv'))

        resp = client.get('/api/senders', headers={'Host': host})

        assert resp.status_code == 200

    def test_allows_same_origin_post(self, client, monkeypatch, inline_scan):
        monkeypatch.setattr(app_module, 'get_service', lambda: 'fake')
        monkeypatch.setattr(app_module, 'extract_senders', lambda service, progress: {})
        monkeypatch.setattr(app_module, 'save_to_csv', MagicMock())

        resp = client.post('/api/scan', headers={
            'Origin': 'http://localhost:5050', 'Sec-Fetch-Site': 'same-origin',
        })

        assert resp.status_code == 202

    @pytest.mark.parametrize('headers', [
        {'Sec-Fetch-Site': 'cross-site'},
        {'Sec-Fetch-Site': 'same-site'},
        {'Origin': 'https://evil.com'},
        {'Origin': 'null'},
    ])
    def test_rejects_cross_site_post_even_with_local_host(self, client, monkeypatch, headers):
        scan_mock = MagicMock()
        monkeypatch.setattr(app_module, 'get_service', scan_mock)

        resp = client.post('/api/scan', headers=headers)

        assert resp.status_code == 403
        scan_mock.assert_not_called()

    @pytest.mark.parametrize('host', ['evil.com', 'evil.com:5050', 'localhost.evil.com'])
    def test_rejects_foreign_hosts(self, client, monkeypatch, host):
        scan_mock = MagicMock()
        monkeypatch.setattr(app_module, 'get_service', scan_mock)

        resp = client.post('/api/scan', headers={'Host': host})

        assert resp.status_code == 403
        scan_mock.assert_not_called()
