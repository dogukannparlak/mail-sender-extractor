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
    find_message_ids,
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


class TestSendersPayload:
    def test_from_counter_orders_by_count_desc_and_sums_total(self):
        payload = _senders_payload(Counter({'a': 1, 'b': 5}))

        assert payload['toplam_mail_sayisi'] == 6
        assert payload['gonderenler'] == [
            {'gonderen': 'b', 'mail_sayisi': 5},
            {'gonderen': 'a', 'mail_sayisi': 1},
        ]

    def test_from_plain_pairs_preserves_input_order(self):
        payload = _senders_payload([('x', 2), ('y', 3)])

        assert payload['toplam_mail_sayisi'] == 5
        assert payload['gonderenler'] == [
            {'gonderen': 'x', 'mail_sayisi': 2},
            {'gonderen': 'y', 'mail_sayisi': 3},
        ]

    def test_empty_input_yields_zero_total_and_empty_list(self):
        assert _senders_payload([]) == {'toplam_mail_sayisi': 0, 'gonderenler': []}


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
        assert service.messages_resource.list_calls[0]['q'] == 'from:someone@example.com'
        assert service.messages_resource.list_calls[1]['pageToken'] == 'p2'

    def test_returns_empty_list_when_no_messages(self, fake_service_factory):
        service = fake_service_factory(list_pages=[{'messages': []}])

        assert find_message_ids(service, 'nobody@example.com') == []


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

    def test_one_click_success_posts_and_returns_done(self, fake_service_factory, monkeypatch):
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
        ok_response = MagicMock(ok=True)
        post_mock = MagicMock(return_value=ok_response)
        monkeypatch.setattr(requests, 'post', post_mock)

        result = find_unsubscribe_info(service, 'x@example.com')

        assert result == {'status': 'done', 'url': 'https://example.com/unsub'}
        post_mock.assert_called_once_with(
            'https://example.com/unsub', data={'List-Unsubscribe': 'One-Click'}, timeout=10
        )

    def test_one_click_falls_back_to_manual_link_on_non_ok_response(self, fake_service_factory, monkeypatch):
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

        result = find_unsubscribe_info(service, 'x@example.com')

        assert result == {'status': 'manual_link', 'url': 'https://example.com/unsub'}

    def test_one_click_falls_back_to_manual_link_on_request_exception(self, fake_service_factory, monkeypatch):
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

        result = find_unsubscribe_info(service, 'x@example.com')

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
                {'gonderen': 'a@example.com', 'mail_sayisi': 3},
                {'gonderen': 'b@example.com', 'mail_sayisi': 2},
            ],
        }

    def test_missing_csv_returns_empty_payload(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(app_module, 'CSV_PATH', str(tmp_path / 'missing.csv'))

        resp = client.get('/api/senders')

        assert resp.status_code == 200
        assert resp.get_json() == {'toplam_mail_sayisi': 0, 'gonderenler': []}


class TestApiScan:
    def test_scans_and_persists_csv(self, client, monkeypatch):
        monkeypatch.setattr(app_module, 'get_service', lambda: 'fake-service')
        monkeypatch.setattr(app_module, 'extract_senders', lambda service: Counter({'a@example.com': 2}))
        save_mock = MagicMock()
        monkeypatch.setattr(app_module, 'save_to_csv', save_mock)

        resp = client.post('/api/scan')

        assert resp.status_code == 200
        assert resp.get_json() == {
            'toplam_mail_sayisi': 2,
            'gonderenler': [{'gonderen': 'a@example.com', 'mail_sayisi': 2}],
        }
        save_mock.assert_called_once()


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
