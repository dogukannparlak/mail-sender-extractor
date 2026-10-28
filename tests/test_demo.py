import os

import app as app_module


def test_demo_mode_fills_the_list_without_credentials(demo_mode, inline_scan):
    client = app_module.app.test_client()

    assert client.post('/api/scan').status_code == 202
    senders = client.get('/api/senders').get_json()['gonderenler']
    assert len(senders) > 10
    assert {g['kategori'] for g in senders} == {'bulten', 'promosyon', 'bildirim', 'kisisel'}
    # Demo verisi proje klasöründeki gerçek dosyalara yazılmamalı.
    assert not app_module.CSV_PATH.startswith(app_module.BASE_DIR)
