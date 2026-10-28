import csv

import pytest

from extract_senders import extract_senders, load_csv, message_category, save_to_csv, sender_key


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
    )

    result = extract_senders(service)

    assert result == {
        'alice@example.com': {'ad': 'Alice', 'mail_sayisi': 2, 'kategori': 'kisisel', 'abonelik': False},
        'bob@example.com': {'ad': 'Bob', 'mail_sayisi': 1, 'kategori': 'kisisel', 'abonelik': False},
    }


def test_extract_senders_matches_from_header_case_insensitively(fake_service_factory):
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}]}],
        get_responses={'m1': {'payload': {'headers': [{'name': 'from', 'value': 'Alice <alice@example.com>'}]}}},
    )

    assert extract_senders(service) == {'alice@example.com': {'ad': 'Alice', 'mail_sayisi': 1, 'kategori': 'kisisel', 'abonelik': False}}


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
        'no-reply@classroom.google.com': {'ad': 'Ali (Classroom)', 'mail_sayisi': 3, 'kategori': 'kisisel', 'abonelik': False},
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

    assert rows[0] == ['Adres', 'Ad', 'Mail Sayısı', 'Kategori', 'Abonelik']
    assert rows[1:] == [
        ['b@example.com', 'Bee', '5', '', ''],
        ['c@example.com', '', '3', '', ''],
        ['a@example.com', '', '1', '', ''],
    ]


def test_save_to_csv_handles_empty_input(tmp_path):
    out_file = tmp_path / 'out.csv'

    save_to_csv({}, filename=str(out_file))

    with open(out_file, encoding='utf-8') as f:
        rows = list(csv.reader(f))

    assert rows == [['Adres', 'Ad', 'Mail Sayısı', 'Kategori', 'Abonelik']]


def test_load_csv_round_trips_save_to_csv(tmp_path):
    senders = {
        'b@example.com': {'ad': 'Bee, Inc.', 'mail_sayisi': 5, 'kategori': 'bulten', 'abonelik': True},
        'a@example.com': {'ad': '', 'mail_sayisi': 1},
    }
    out_file = tmp_path / 'out.csv'

    save_to_csv(senders, filename=str(out_file))

    assert load_csv(str(out_file)) == senders


def _rate_limit_error():
    import httplib2
    from googleapiclient.errors import HttpError
    return HttpError(httplib2.Response({'status': 429}), b'{"error": {"message": "rate limit"}}')


def test_scans_250_messages_in_batches_of_50(fake_service_factory):
    ids = [{'id': f'm{i}'} for i in range(250)]
    service = fake_service_factory(
        list_pages=[{'messages': ids[:200], 'nextPageToken': 'p2'}, {'messages': ids[200:]}],
        get_responses={m['id']: _metadata_response('a@example.com') for m in ids},
    )
    seen = []

    result = extract_senders(service, progress=lambda done, total: seen.append((done, total)))

    assert service.batch_sizes == [50] * 5
    assert result == {'a@example.com': {'ad': '', 'mail_sayisi': 250, 'kategori': 'kisisel', 'abonelik': False}}
    assert seen[0] == (0, 250) and seen[-1] == (250, 250)


def test_rate_limited_messages_are_retried_after_a_pause(fake_service_factory):
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}, {'id': 'm2'}]}],
        get_responses={
            'm1': _metadata_response('a@example.com'),
            'm2': [_rate_limit_error(), _metadata_response('b@example.com')],
        },
    )
    sleeps = []

    result = extract_senders(service, progress=lambda *a: None, sleep=sleeps.append)

    assert set(result) == {'a@example.com', 'b@example.com'}
    assert service.batch_sizes == [2, 1]
    assert sleeps == [1]


def test_gives_up_after_repeated_rate_limits(fake_service_factory):
    import pytest
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}]}],
        get_responses={'m1': [_rate_limit_error()]},
    )

    with pytest.raises(RuntimeError):
        extract_senders(service, progress=lambda *a: None, sleep=lambda s: None)


@pytest.mark.parametrize('labels, has_unsubscribe, expected', [
    (['INBOX', 'CATEGORY_PROMOTIONS'], True, 'promosyon'),
    (['INBOX', 'CATEGORY_PROMOTIONS'], False, 'promosyon'),
    (['INBOX', 'CATEGORY_SOCIAL'], True, 'bildirim'),
    (['INBOX', 'CATEGORY_FORUMS'], False, 'bildirim'),
    (['INBOX', 'CATEGORY_UPDATES'], True, 'bulten'),
    (['INBOX'], True, 'bulten'),
    (['INBOX', 'CATEGORY_UPDATES'], False, 'bildirim'),
    (['INBOX', 'CATEGORY_PERSONAL'], False, 'kisisel'),
    (None, False, 'kisisel'),
])
def test_message_category_rules(labels, has_unsubscribe, expected):
    assert message_category(labels, has_unsubscribe) == expected


def test_sender_category_is_the_most_common_and_unsubscribe_is_any(fake_service_factory):
    def msg(labels, unsubscribe):
        headers = [{'name': 'From', 'value': 'Shop <news@shop.com>'}]
        if unsubscribe:
            headers.append({'name': 'List-Unsubscribe', 'value': '<https://shop.com/u>'})
        return {'labelIds': labels, 'payload': {'headers': headers}}

    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}, {'id': 'm2'}, {'id': 'm3'}]}],
        get_responses={
            'm1': msg(['INBOX', 'CATEGORY_PROMOTIONS'], True),
            'm2': msg(['INBOX', 'CATEGORY_PROMOTIONS'], False),
            'm3': msg(['INBOX', 'CATEGORY_UPDATES'], False),
        },
    )

    info = extract_senders(service, progress=lambda *a: None)['news@shop.com']

    assert (info['kategori'], info['abonelik']) == ('promosyon', True)
    assert service.messages_resource.get_calls[0]['metadataHeaders'] == ['From', 'List-Unsubscribe']


def test_message_deleted_during_scan_is_skipped(fake_service_factory):
    import httplib2
    from googleapiclient.errors import HttpError
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}, {'id': 'm2'}]}],
        get_responses={
            'm1': HttpError(httplib2.Response({'status': 404}), b'{"error": {"message": "not found"}}'),
            'm2': _metadata_response('a@example.com'),
        },
    )
    seen = []

    result = extract_senders(service, progress=lambda done, total: seen.append((done, total)))

    assert result['a@example.com']['mail_sayisi'] == 1
    assert seen[-1] == (2, 2)


def test_whole_batch_rate_limit_is_retried(fake_service_factory):
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}]}],
        get_responses={'m1': _metadata_response('a@example.com')},
    )
    service.batch_errors = [_rate_limit_error()]
    sleeps = []

    result = extract_senders(service, progress=lambda *a: None, sleep=sleeps.append)

    assert result['a@example.com']['mail_sayisi'] == 1
    assert service.batch_sizes == [1, 1] and sleeps == [1]


def test_duplicate_ids_across_pages_are_counted_once(fake_service_factory):
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}], 'nextPageToken': 'p2'}, {'messages': [{'id': 'm1'}, {'id': 'm2'}]}],
        get_responses={'m1': _metadata_response('a@example.com'), 'm2': _metadata_response('a@example.com')},
    )

    assert extract_senders(service, progress=lambda *a: None)['a@example.com']['mail_sayisi'] == 2


def test_progress_resets_retry_budget(fake_service_factory):
    # Her turda bir mail ilerliyorsa 5 denemeden fazla tur sürse de tarama bitmeli.
    ids = [f'm{i}' for i in range(7)]
    responses = {}
    for n, msg_id in enumerate(ids):
        responses[msg_id] = [_rate_limit_error()] * n + [_metadata_response('a@example.com')]
    service = fake_service_factory(list_pages=[{'messages': [{'id': i} for i in ids]}], get_responses=responses)

    result = extract_senders(service, progress=lambda *a: None, sleep=lambda s: None)

    assert result['a@example.com']['mail_sayisi'] == 7


def test_csv_neutralises_formulas_and_round_trips(tmp_path):
    senders = {'a@example.com': {'ad': '=HYPERLINK("https://evil.example")', 'mail_sayisi': 1}}
    out_file = tmp_path / 'out.csv'

    save_to_csv(senders, filename=str(out_file))

    with open(out_file, encoding='utf-8') as f:
        assert list(csv.reader(f))[1][1] == '\'=HYPERLINK("https://evil.example")'
    assert load_csv(str(out_file)) == senders


def test_quota_limiter_waits_when_the_minute_budget_is_spent():
    from extract_senders import QuotaLimiter
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    limiter = QuotaLimiter(units_per_minute=1000, clock=lambda: now[0], sleep=sleep)
    limiter.spend(600)
    limiter.spend(400)   # tam sınırda: beklemez
    assert sleeps == []
    limiter.spend(100)   # bütçe doldu: ilk harcamanın 60 sn'den çıkmasını bekler
    assert sleeps == [60.0]


def test_user_rate_limit_403_is_retried():
    import httplib2
    from googleapiclient.errors import HttpError
    from extract_senders import _is_retryable
    err = HttpError(httplib2.Response({'status': 403}),
                    b'{"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}')
    assert _is_retryable(err)


def test_scan_fills_the_id_index(fake_service_factory):
    service = fake_service_factory(
        list_pages=[{'messages': [{'id': 'm1'}, {'id': 'm2'}]}],
        get_responses={'m1': _metadata_response('A <a@example.com>'), 'm2': _metadata_response('b@example.com')},
    )
    index = {}

    extract_senders(service, id_index=index)

    assert index == {'a@example.com': ['m1'], 'b@example.com': ['m2']}
