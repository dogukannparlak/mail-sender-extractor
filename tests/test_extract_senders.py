import csv
from collections import Counter

from extract_senders import extract_senders, load_csv, save_to_csv, sender_key


def _metadata_response(sender_header_value):
    return {
        'payload': {
            'headers': [
                {'name': 'From', 'value': sender_header_value},
                {'name': 'Subject', 'value': 'irrelevant'},
            ]
        }
    }


def test_extract_senders_counts_by_from_header(fake_service_factory):
    service = fake_service_factory(
        list_pages=[
            {'messages': [{'id': 'm1'}, {'id': 'm2'}], 'nextPageToken': 'page2'},
            {'messages': [{'id': 'm3'}]},
        ],
        get_responses={
            'm1': _metadata_response('Alice <alice@example.com>'),
            'm2': _metadata_response('Bob <bob@example.com>'),
            'm3': _metadata_response('Alice <alice@example.com>'),
        },
        label_response={'messagesTotal': 3},
    )

    result = extract_senders(service)

    assert result == {
        'alice@example.com': {'ad': 'Alice', 'mail_sayisi': 2},
        'bob@example.com': {'ad': 'Bob', 'mail_sayisi': 1},
    }


def test_extract_senders_matches_from_header_case_insensitively(fake_service_factory):
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}]}],
        get_responses={'m1': {'payload': {'headers': [{'name': 'from', 'value': 'Alice <alice@example.com>'}]}}},
        label_response={'messagesTotal': 1},
    )

    assert extract_senders(service) == {'alice@example.com': {'ad': 'Alice', 'mail_sayisi': 1}}


def test_extract_senders_paginates_using_next_page_token(fake_service_factory):
    service = fake_service_factory(
        list_pages=[
            {'messages': [{'id': 'm1'}], 'nextPageToken': 'page2'},
            {'messages': [{'id': 'm2'}]},
        ],
        get_responses={
            'm1': _metadata_response('a@example.com'),
            'm2': _metadata_response('b@example.com'),
        },
    )

    extract_senders(service)

    assert len(service.messages_resource.list_calls) == 2
    assert service.messages_resource.list_calls[0].get('pageToken') is None
    assert service.messages_resource.list_calls[1]['pageToken'] == 'page2'


def test_extract_senders_ignores_messages_without_from_header(fake_service_factory):
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}]}],
        get_responses={'m1': {'payload': {'headers': [{'name': 'Subject', 'value': 'hi'}]}}},
    )

    result = extract_senders(service)

    assert result == {}


def test_extract_senders_returns_empty_when_inbox_empty(fake_service_factory):
    service = fake_service_factory(list_pages=[{'messages': []}])

    result = extract_senders(service)

    assert result == {}


def test_same_address_with_different_names_is_one_sender(fake_service_factory):
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}, {'id': 'm2'}, {'id': 'm3'}]}],
        get_responses={
            'm1': _metadata_response('"Ali (Classroom)" <no-reply@classroom.google.com>'),
            'm2': _metadata_response('"Ayşe (Classroom)" <no-reply@classroom.google.com>'),
            'm3': _metadata_response('"Ali (Classroom)" <No-Reply@Classroom.Google.com>'),
        },
    )

    assert extract_senders(service) == {
        'no-reply@classroom.google.com': {'ad': 'Ali (Classroom)', 'mail_sayisi': 3},
    }


def test_sender_key_keeps_invalid_headers_as_is():
    assert sender_key('spam@kotu.com OR label:inbox') == ('spam@kotu.com OR label:inbox', '')


def test_save_to_csv_writes_header_and_rows_sorted_by_count_desc(tmp_path):
    senders = {
        'a@example.com': {'ad': '', 'mail_sayisi': 1},
        'b@example.com': {'ad': 'Bee', 'mail_sayisi': 5},
        'c@example.com': {'ad': '', 'mail_sayisi': 3},
    }
    out_file = tmp_path / 'out.csv'

    save_to_csv(senders, filename=str(out_file))

    with open(out_file, encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows[0] == ['Adres', 'Ad', 'Mail Sayısı']
    assert rows[1:] == [
        ['b@example.com', 'Bee', '5'],
        ['c@example.com', '', '3'],
        ['a@example.com', '', '1'],
    ]


def test_save_to_csv_handles_empty_input(tmp_path):
    out_file = tmp_path / 'out.csv'

    save_to_csv({}, filename=str(out_file))

    with open(out_file, encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows == [['Adres', 'Ad', 'Mail Sayısı']]


def test_load_csv_round_trips_save_to_csv(tmp_path):
    senders = {'b@example.com': {'ad': 'Bee, Inc.', 'mail_sayisi': 5}, 'a@example.com': {'ad': '', 'mail_sayisi': 1}}
    out_file = tmp_path / 'out.csv'

    save_to_csv(senders, filename=str(out_file))

    assert load_csv(str(out_file)) == senders
