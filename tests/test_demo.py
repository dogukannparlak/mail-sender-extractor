import app as app_module
from demo import DEMO_ACCOUNTS


def test_demo_mode_has_two_accounts_without_credentials(demo_mode, inline_scan):
    client = app_module.app.test_client()

    accounts = client.get('/api/accounts').get_json()
    assert accounts['accounts'] == sorted(DEMO_ACCOUNTS) and accounts['demo'] is True

    for account in DEMO_ACCOUNTS:
        assert client.post('/api/scan', json={'account': account}).status_code == 202
    first = client.get('/api/senders?account=demo@ornek.example').get_json()['gonderenler']
    second = client.get('/api/senders?account=is@ornek.example').get_json()['gonderenler']
    assert {g['kategori'] for g in first} == {'bulten', 'promosyon', 'bildirim', 'kisisel'}
    assert {g['gonderen'] for g in first} != {g['gonderen'] for g in second}
    # Demo verisi proje klasöründeki gerçek dosyalara yazılmamalı.
    assert not app_module.ACCOUNTS_DIR.startswith(app_module.BASE_DIR)
