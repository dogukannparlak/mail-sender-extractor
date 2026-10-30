"""Arayüz testleri: demo posta kutusuyla gerçek bir tarayıcıda (Playwright, headless Chromium).

Kurulum: `pip install -r requirements-dev.txt && python -m playwright install chromium`.
Chromium kurulu değilse bu dosya atlanır.
"""
import json
import threading

import pytest

playwright_sync = pytest.importorskip('playwright.sync_api')

from werkzeug.serving import make_server

from mail_temizleyici import accounts, auth, gmail, mailbox, protected, scanner, state, unsubscribe, web
from mail_temizleyici.demo import DEMO_SENDERS

ADDRESSES = {address for _, address, *_ in DEMO_SENDERS}
WITH_UNSUBSCRIBE = {address for _, address, _, _, unsub, _ in DEMO_SENDERS if unsub}


@pytest.fixture(scope='module')
def ui_browser():
    with playwright_sync.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # tarayıcı indirilmemiş
            pytest.skip(f'Chromium yok: {e}')
        yield browser
        browser.close()


@pytest.fixture(scope='module')
def server_url():
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()


def _open(ui_browser, server_url, **context_options):
    context = ui_browser.new_context(**context_options)
    page = context.new_page()
    page.goto(server_url)
    page.click('#scanBtn')
    page.wait_for_selector('#notice >> text=Tarama tamamlandı')
    return context, page


@pytest.fixture
def ui_page(ui_browser, server_url, demo_mode):
    context, page = _open(ui_browser, server_url)
    yield page
    context.close()


def row(page, email):
    return page.locator('.sender-row', has=page.locator('.sender-email', has_text=email))


def confirm(page):
    page.locator('#confirmOk').click()


def test_header_text_is_shown_as_text_not_html(ui_browser, server_url, demo_mode):
    context = ui_browser.new_context()
    page = context.new_page()
    evil = '<img src=x onerror="window.__xss=1">"Kötü" Ad'
    page.route('**/api/senders?*', lambda route: route.fulfill(content_type='application/json', body=json.dumps({
        'toplam_mail_sayisi': 1,
        'gonderenler': [{'gonderen': 'x@kotu.example', 'ad': evil, 'mail_sayisi': 1}],
    })))
    page.goto(server_url)

    assert page.locator('.sender-name').inner_text().startswith(evil)
    assert page.locator('.sender-info').get_attribute('title') == f'{evil} <x@kotu.example>'
    assert page.evaluate('window.__xss') is None
    context.close()


def test_demo_badge_and_list(ui_page):
    page = ui_page
    assert page.locator('.demo-badge').is_visible()
    assert page.locator('.sender-row').count() == len(ADDRESSES)


def test_search_and_select_visible_only(ui_page):
    page = ui_page
    page.fill('#searchInput', 'banka')
    assert page.locator('.sender-row').count() == 2
    assert page.inner_text('#selectAllLabel') == 'Görünenleri seç (2)'
    page.check('#selectAll')
    page.fill('#searchInput', '')
    assert '2 gönderen seçildi' in page.inner_text('#selectedInfo')


def test_empty_filter_offers_reset(ui_page):
    page = ui_page
    page.fill('#searchInput', 'hiçbiriyleeşleşmez')
    page.click('text=Filtreleri temizle')
    assert page.locator('.sender-row').count() == len(ADDRESSES)


def test_category_and_unsubscribe_filters(ui_page):
    page = ui_page
    page.select_option('#categorySelect', 'kisisel')
    assert sorted(page.locator('.sender-email').all_inner_texts()) == ['ali@ornek.example', 'ayse@ornek.example']
    page.select_option('#categorySelect', '')
    page.check('#unsubFilter')
    assert page.locator('.sender-row').count() == len(WITH_UNSUBSCRIBE)


def test_locked_sender_cannot_be_selected_and_keeps_focus(ui_page):
    page = ui_page
    lock = row(page, 'bilgi@ornekbanka.example').locator('.lock-btn')
    lock.click()
    page.wait_for_selector('#notice >> text=korunuyor')
    locked_row = row(page, 'bilgi@ornekbanka.example')
    assert locked_row.locator('.sender-checkbox').is_disabled()
    assert locked_row.locator('.lock-btn').get_attribute('aria-pressed') == 'true'
    # Liste yeniden çizildi ama klavye odağı aynı satırın kilit butonunda kaldı.
    assert page.evaluate("document.activeElement.closest('.sender-row').dataset.key") == 'bilgi@ornekbanka.example'
    page.check('#selectAll')
    assert f'{len(ADDRESSES) - 1} gönderen seçildi' in page.inner_text('#selectedInfo')


def test_delete_shows_real_count_then_undo_from_notice(ui_page):
    page = ui_page
    page.select_option('#scopeSelect', 'all')
    row(page, 'kampanya@ornekmarket.example').locator('.sender-checkbox').check()
    page.click('#deleteBtn')

    page.wait_for_selector('#confirmDialog[open]')
    title = page.inner_text('#confirmTitle')
    total = sum(count for _, address, count, *_ in DEMO_SENDERS if address == 'kampanya@ornekmarket.example')
    assert title == f"{total} mail Çöp Kutusu'na taşınsın mı?"
    # Odak "Vazgeç"te başlar: Enter'a yanlışlıkla basmak işlemi başlatmaz.
    assert page.evaluate('document.activeElement.id') == 'confirmCancel'
    assert 'null' not in page.inner_text('#confirmContent')
    confirm(page)

    page.wait_for_selector(f"#notice >> text={total} mail Çöp Kutusu'na taşındı (demo@ornek.example).")
    assert row(page, 'kampanya@ornekmarket.example').count() == 0
    page.locator('#notice').get_by_role('button', name='Geri al').click()
    page.wait_for_selector("#notice >> text=Çöp Kutusu'ndan geri alındı")
    assert row(page, 'kampanya@ornekmarket.example').count() == 1


def test_cancelling_the_dialog_trashes_nothing(ui_page):
    page = ui_page
    row(page, 'haber@teknohafta.example').locator('.sender-checkbox').check()
    page.click('#deleteBtn')
    page.wait_for_selector('#confirmDialog[open]')
    page.keyboard.press('Escape')
    page.wait_for_selector('#confirmDialog:not([open])', state='attached')
    assert row(page, 'haber@teknohafta.example').count() == 1
    assert page.is_hidden('#undoBtn')


def test_one_click_needs_confirmation(ui_page):
    page = ui_page
    r = row(page, 'kampanya@ornekmarket.example')
    r.locator('.unsub-btn').click()
    page.wait_for_selector('#confirmDialog[open]')
    assert 'kampanya@ornekmarket.example' in page.inner_text('#confirmContent')
    page.locator('#confirmCancel').click()
    link = r.locator('.unsub-result a')
    link.wait_for()
    assert link.inner_text() == '🔗 Çıkış sayfasını aç'
    assert link.get_attribute('rel') == 'noopener noreferrer'


def test_bulk_unsubscribe_writes_results_into_rows(ui_page):
    page = ui_page
    row(page, 'kampanya@ornekmarket.example').locator('.sender-checkbox').check()
    row(page, 'haber@teknohafta.example').locator('.sender-checkbox').check()
    page.click('#unsubBtn')
    page.wait_for_selector('#confirmDialog[open]')
    confirm(page)
    page.wait_for_selector('#notice >> text=1 gönderenden otomatik çıkıldı')
    assert row(page, 'kampanya@ornekmarket.example').locator('.unsub-result').inner_text() == '✅ Otomatik olarak çıkıldı'
    assert row(page, 'haber@teknohafta.example').locator('.unsub-result a').count() == 1


@pytest.mark.parametrize('status, body', [
    (502, '{"error": "Gmail API hatası (502): test"}'),
    (502, '<html>Bad Gateway</html>'),  # JSON olmayan hata sayfası
])
def test_server_errors_are_readable(ui_page, status, body):
    page = ui_page
    page.route('**/api/count*', lambda route: route.fulfill(status=status, content_type='text/html', body=body))
    row(page, 'haber@teknohafta.example').locator('.sender-checkbox').check()
    page.click('#deleteBtn')
    expected = 'Gmail API hatası (502): test' if body.startswith('{') else 'Sunucu hatası (502)'
    page.wait_for_selector(f'#notice.error >> text={expected}')
    assert not page.is_disabled('#deleteBtn')


def test_mobile_layout_has_no_horizontal_scroll(ui_browser, server_url, demo_mode):
    context, page = _open(ui_browser, server_url, viewport={'width': 390, 'height': 844})
    overflow = page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
    assert overflow <= 0
    context.close()


def test_switching_accounts_shows_that_accounts_list(ui_page):
    page = ui_page
    assert page.input_value('#accountSelect') == 'demo@ornek.example'
    row(page, 'kampanya@ornekmarket.example').locator('.sender-checkbox').check()

    page.select_option('#accountSelect', 'is@ornek.example')
    page.wait_for_selector('text=Henüz veri yok')
    page.click('#scanBtn')
    page.wait_for_selector('#notice >> text=Tarama tamamlandı')

    assert row(page, 'bildirim@proje.example').count() == 1
    assert row(page, 'kampanya@ornekmarket.example').count() == 0
    # Seçim önceki hesaba aitti; yeni hesapta seçim yok.
    assert page.inner_text('#selectedInfo') == 'is@ornek.example · Seçim yok'

    page.select_option('#accountSelect', 'demo@ornek.example')
    page.wait_for_selector('.sender-row')
    assert row(page, 'kampanya@ornekmarket.example').count() == 1


def test_confirm_dialog_names_the_account(ui_page):
    page = ui_page
    row(page, 'haber@teknohafta.example').locator('.sender-checkbox').check()
    page.click('#deleteBtn')
    page.wait_for_selector('#confirmDialog[open]')
    assert 'Hesap: demo@ornek.example' in page.inner_text('#confirmContent')
    page.locator('#confirmCancel').click()


def test_add_account_is_explained_in_demo(ui_page):
    page = ui_page
    page.click('#addAccountBtn')
    page.wait_for_selector('#notice.error >> text=Demo modunda hesap eklenmez')


def test_add_account_dialog_offers_file_and_pending_accounts(ui_browser, server_url, demo_mode, monkeypatch):
    import os
    from mail_temizleyici import web
    monkeypatch.setattr(web, 'DEMO_MODE', False)  # pencereyi göstermek için; giriş denenmez
    pending = os.path.join(accounts.ACCOUNTS_DIR, 'yeni@ornek.example')
    os.makedirs(pending)
    with open(os.path.join(pending, 'credentials.json'), 'w') as f:
        f.write('{"installed": {"client_id": "x", "client_secret": "y"}}')
    context = ui_browser.new_context()
    page = context.new_page()
    page.goto(server_url)
    page.wait_for_selector('#accountSelect:not([hidden])')

    page.click('#addAccountBtn')
    page.wait_for_selector('#addAccountDialog[open]')
    assert page.locator('#clientFileInput').is_visible()
    assert page.get_by_role('button', name='yeni@ornek.example için giriş yap').is_visible()
    page.locator('#addAccountCancel').click()
    context.close()


def test_addresses_inside_a_domain_group_have_their_own_actions(ui_page):
    page = ui_page
    page.select_option('#viewSelect', 'domain')
    group = page.locator('.sender-item', has=page.locator('.sender-name', has_text='ornekmarket.example'))
    group.get_by_role('button', name='Adresler').click()
    member = group.locator('.member-item', has_text='kampanya@ornekmarket.example')

    # Önizle: yalnız bu adresin mailleri
    member.get_by_role('button', name='Önizle').click()
    member.locator('.member-preview .preview-item').first.wait_for()
    assert member.locator('.member-preview.open').count() == 1

    # Seç: grup kutusu kısmi seçili görünür, seçim sayacı güncellenir
    member.locator('.member-checkbox').check()
    assert group.locator('.sender-row .sender-checkbox').evaluate('c => c.indeterminate')
    assert '1 gönderen seçildi' in page.locator('#selectedInfo').inner_text()

    # Abonelikten çık: sonuç bu adresin satırına yazılır
    member.get_by_role('button', name='aboneliğinden çık').click()
    page.locator('#confirmOk').click()
    member = group.locator('.member-item', has_text='kampanya@ornekmarket.example')
    member.locator('.unsub-result', has_text='Otomatik olarak çıkıldı').wait_for()

    # Koru: yalnız bu adres korunur, grup açık kalır
    member.get_by_role('button', name='Koru').click()
    group.locator('.member-item', has_text='kampanya@ornekmarket.example').get_by_role('button', name='Korunuyor').wait_for()
    assert 'kampanya@ornekmarket.example' in page.evaluate('state.protectedList.adresler')


def _seed_subscription_data():
    from mail_temizleyici import subscriptions
    from mail_temizleyici.storage import write_json
    paths = accounts.AccountPaths('demo@ornek.example')
    unsub = '<https://x.example/u>'
    write_json(paths.scan_cache, {
        'a1': ['alfa@x.example', 'Alfa', 'bulten', True, 3_000, unsub],
        'a2': ['alfa@x.example', 'Alfa', 'bulten', True, 4_000, unsub],
        'a3': ['alfa@x.example', 'Alfa', 'bulten', True, 5_000, unsub],
        'b1': ['beta@x.example', 'Beta', 'promosyon', True, 9_000, unsub],
        'c1': ['gama@x.example', 'Gama', 'bulten', True, 1_000, ''],
    })
    subscriptions.mark(paths, 'beta@x.example', True)
    subscriptions._add_notifications(paths, [
        {'zaman': 100, 'tur': 'yeni_abonelik', 'gonderen': 'alfa@x.example', 'ad': 'Alfa', 'sayi': 3, 'okundu': True},
        {'zaman': 200, 'tur': 'mail_geliyor', 'gonderen': 'beta@x.example', 'ad': 'Beta', 'sayi': 2, 'okundu': False},
    ])
    return paths


def _names(page):
    return [t.strip() for t in page.locator('tbody tr:visible td:first-child').all_inner_texts()]


def test_subscriptions_page_sorts_and_filters(ui_page, server_url):
    _seed_subscription_data()
    page = ui_page
    page.goto(f'{server_url}/abonelikler?account=demo@ornek.example')

    assert [n.split('\n')[0] for n in _names(page)] == ['Alfa', 'Beta']  # bağlantısız Gama listede yok
    page.select_option('#sort', 'son:desc')
    assert [n.split('\n')[0] for n in _names(page)] == ['Beta', 'Alfa']
    page.select_option('#fKategori', 'promosyon')
    assert len(_names(page)) == 1 and page.locator('#count').inner_text() == '1 / 2 gösteriliyor'
    page.select_option('#fKategori', '')
    page.select_option('#fDurum', 'cikildi')
    assert [n.split('\n')[0] for n in _names(page)] == ['Beta']
    page.select_option('#fDurum', '')
    page.fill('#q', 'nonexistent')
    assert page.locator('#noMatch').is_visible()


def test_notifications_page_filters_by_type_and_unread(ui_page, server_url):
    _seed_subscription_data()
    page = ui_page
    page.goto(f'{server_url}/bildirimler?account=demo@ornek.example')

    assert len(_names(page)) == 2
    page.select_option('#fTur', 'mail_geliyor')
    assert len(_names(page)) == 1
    page.select_option('#fTur', '')
    page.check('#fOkunmamis')
    assert len(_names(page)) == 1 and 'beta@x.example' in page.locator('tbody tr:visible').inner_text()
    page.uncheck('#fOkunmamis')
    page.select_option('#sort', 'zaman:asc')
    assert 'alfa@x.example' in page.locator('tbody tr').first.inner_text()


def test_domain_view_can_be_sorted_by_address_count(ui_page):
    page = ui_page
    assert page.locator('#sortSelect option[value="members_desc"]').is_disabled()
    page.select_option('#viewSelect', 'domain')
    page.select_option('#sortSelect', 'members_desc')
    first = page.locator('.sender-item .sender-name').first.inner_text()
    counts = page.locator('.sender-item .sender-email').all_inner_texts()
    assert first.startswith('ornekmarket.example') or first.startswith('ornek.example') or first.startswith('okul.example')
    numbers = [int(c.split()[0]) for c in counts]
    assert numbers == sorted(numbers, reverse=True)
    page.select_option('#viewSelect', 'address')
    assert page.locator('#sortSelect').input_value() == 'count_desc'


def test_unsubscribe_button_only_on_senders_with_an_unsubscribe_link(ui_page):
    page = ui_page
    for email in ADDRESSES:
        buttons = row(page, email).locator('.unsub-btn').count()
        assert buttons == (1 if email in WITH_UNSUBSCRIBE else 0), email

    # Seçilenlerin hiçbirinde bağlantı yoksa toplu buton kapalı kalır
    only_without = sorted(ADDRESSES - WITH_UNSUBSCRIBE)[0]
    row(page, only_without).locator('.sender-checkbox').check()
    assert page.locator('#unsubBtn').is_disabled()
    with_link = sorted(WITH_UNSUBSCRIBE)[0]
    row(page, with_link).locator('.sender-checkbox').check()
    assert page.locator('#unsubBtn').is_enabled()
