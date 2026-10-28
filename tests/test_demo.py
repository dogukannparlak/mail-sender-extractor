import app as app_module
import demo


class _InlineThread:
    def __init__(self, target, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


def test_demo_mode_fills_the_list_without_credentials(monkeypatch):
    # demo.enable modül özniteliklerini doğrudan değiştirir; test sonrası geri alınsınlar.
    for name in ('get_service', 'CSV_PATH', 'PROTECTED_PATH', 'UNDO_PATH', '_resolve_host'):
        monkeypatch.setattr(app_module, name, getattr(app_module, name))
    monkeypatch.setattr(app_module.requests, 'post', app_module.requests.post)
    monkeypatch.setattr(app_module.threading, 'Thread', _InlineThread)
    monkeypatch.setitem(app_module._scan_state, 'running', False)

    demo.enable(app_module)
    client = app_module.app.test_client()

    assert client.post('/api/scan').status_code == 202
    senders = client.get('/api/senders').get_json()['gonderenler']
    assert len(senders) > 10
    assert {g['kategori'] for g in senders} == {'bulten', 'promosyon', 'bildirim', 'kisisel'}
    assert 'mail-temizleyici-demo-' in app_module.CSV_PATH
