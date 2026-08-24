import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


class _Executable:
    """Mimics the `...().execute()` tail of every googleapiclient call."""

    def __init__(self, data):
        self._data = data

    def execute(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class FakeMessagesResource:
    """Fakes `service.users().messages()`.

    - `list_pages`: list of response dicts returned in order, one per `.list()` call
      (lets tests simulate pagination via successive nextPageToken values).
    - `get_responses`: dict of message id -> response dict, used by `.get()`.
    - `batch_modify_result`: value returned by `.batchModify()`.
    All calls are recorded on `list_calls` / `get_calls` / `batch_modify_calls`
    so tests can assert on query params (e.g. `q=from:...`, chunk sizes).
    """

    def __init__(self, list_pages=None, get_responses=None, batch_modify_result=None):
        self._list_pages = list(list_pages or [])
        self._get_responses = get_responses or {}
        self._batch_modify_result = batch_modify_result if batch_modify_result is not None else {}
        self.list_calls = []
        self.get_calls = []
        self.batch_modify_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        if not self._list_pages:
            return _Executable({'messages': []})
        return _Executable(self._list_pages.pop(0))

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        msg_id = kwargs.get('id')
        response = self._get_responses.get(msg_id, {})
        return _Executable(response)

    def batchModify(self, **kwargs):
        self.batch_modify_calls.append(kwargs)
        return _Executable(self._batch_modify_result)


class FakeLabelsResource:
    def __init__(self, label_response=None):
        self._label_response = label_response or {'messagesTotal': 0}

    def get(self, **kwargs):
        return _Executable(self._label_response)


class FakeUsersResource:
    def __init__(self, messages, labels):
        self._messages = messages
        self._labels = labels

    def messages(self):
        return self._messages

    def labels(self):
        return self._labels


class FakeGmailService:
    """Fakes the top-level object returned by `googleapiclient.discovery.build('gmail', 'v1', ...)`."""

    def __init__(self, list_pages=None, get_responses=None, batch_modify_result=None, label_response=None):
        self.messages_resource = FakeMessagesResource(list_pages, get_responses, batch_modify_result)
        self.labels_resource = FakeLabelsResource(label_response)
        self._users = FakeUsersResource(self.messages_resource, self.labels_resource)

    def users(self):
        return self._users


@pytest.fixture
def fake_service_factory():
    return FakeGmailService
