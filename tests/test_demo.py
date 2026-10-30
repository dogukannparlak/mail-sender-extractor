from mail_cleaner import accounts, auth, config, gmail, mailbox, protected, scanner, state, unsubscribe, web
from mail_cleaner.demo import DEMO_ACCOUNTS


def test_demo_mode_has_two_accounts_without_credentials(demo_mode, inline_scan):
    client = web.app.test_client()

    listed = client.get('/api/accounts').get_json()
    assert listed['accounts'] == sorted(DEMO_ACCOUNTS) and listed['demo'] is True

    for account in DEMO_ACCOUNTS:
        assert client.post('/api/scan', json={'account': account}).status_code == 202
    first = client.get('/api/senders?account=demo@ornek.example').get_json()['gonderenler']
    second = client.get('/api/senders?account=is@ornek.example').get_json()['gonderenler']
    assert {g['kategori'] for g in first} == {'bulten', 'promosyon', 'bildirim', 'kisisel'}
    assert {g['gonderen'] for g in first} != {g['gonderen'] for g in second}
    # Demo verisi proje klasöründeki gerçek dosyalara yazılmamalı.
    assert not accounts.ACCOUNTS_DIR.startswith(config.BASE_DIR)
