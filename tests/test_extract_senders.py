import csv
from collections import Counter

from extract_senders import extract_senders, save_to_csv


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

    assert result == Counter({'Alice <alice@example.com>': 2, 'Bob <bob@example.com>': 1})


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

    assert result == Counter()


def test_extract_senders_returns_empty_counter_when_inbox_empty(fake_service_factory):
    service = fake_service_factory(list_pages=[{'messages': []}])

    result = extract_senders(service)

    assert result == Counter()


def test_save_to_csv_writes_header_and_rows_sorted_by_count_desc(tmp_path):
    senders = Counter({'a@example.com': 1, 'b@example.com': 5, 'c@example.com': 3})
    out_file = tmp_path / 'out.csv'

    save_to_csv(senders, filename=str(out_file))

    with open(out_file, encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows[0] == ['İsim/Adres', 'Mail Sayısı']
    assert rows[1:] == [
        ['b@example.com', '5'],
        ['c@example.com', '3'],
        ['a@example.com', '1'],
    ]


def test_save_to_csv_handles_empty_counter(tmp_path):
    out_file = tmp_path / 'out.csv'

    save_to_csv(Counter(), filename=str(out_file))

    with open(out_file, encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows == [['İsim/Adres', 'Mail Sayısı']]
