"""Arayüz testleri: demo posta kutusuyla gerçek bir tarayıcıda (Playwright, headless Chromium).

Kurulum: `pip install -r requirements-dev.txt && python -m playwright install chromium`.
Chromium kurulu değilse bu dosya atlanır.
"""
import threading

import pytest

playwright_sync = pytest.importorskip('playwright.sync_api')

from werkzeug.serving import make_server

import app as app_module
import demo


@pytest.fixture(scope='module')
def ui_browser():
    with playwright_sync.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # tarayıcı indirilmemiş
            pytest.skip(f'Chromium yok: {e}')
        yield b
        b.close()


@pytest.fixture(scope='module')
def server_url():
    server = make_server('127.0.0.1', 0, app_module.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()


@pytest.fixture
def ui_page(ui_browser, server_url, monkeypatch):
    # demo.enable modül özniteliklerini değiştirir; test sonrası geri alınsınlar.
    for name in ('get_service', 'CSV_PATH', 'PROTECTED_PATH', 'UNDO_PATH', '_resolve_host'):
        monkeypatch.setattr(app_module, name, getattr(app_module, name))
    monkeypatch.setattr(app_module.requests, 'post', app_module.requests.post)
    monkeypatch.setitem(app_module._scan_state, 'running', False)
    demo.enable(app_module)

    context = ui_browser.new_context()
    pg = context.new_page()
    pg.goto(server_url)
    pg.click('#scanBtn')
    pg.wait_for_selector('text=Tarama tamamlandı')
    yield pg
    context.close()


def row(page, email):
    return page.locator('.sender-row', has=page.locator('.sender-email', has_text=email))


def test_escape_html_handles_quotes_and_title_shows_full_name(ui_page):
    page = ui_page
    assert page.evaluate("escapeHtml('\"<>')") == '&quot;&lt;&gt;'
    assert row(page, 'ali@ornek.example').locator('.sender-info').get_attribute('title') == \
        'Ali "Usta" Yılmaz <ali@ornek.example>'


def test_search_filters_and_select_all_only_selects_visible(ui_page):
    page = ui_page
    page.fill('#searchInput', 'banka')
    assert page.locator('.sender-row').count() == 2
    page.check('#selectAll')
    assert page.inner_text('#selectedInfo').startswith('2 gönderen')
    page.fill('#searchInput', '')
    assert '2 gönderen' in page.inner_text('#selectedInfo')


def test_category_and_unsubscribe_filters(ui_page):
    page = ui_page
    page.select_option('#categorySelect', 'kisisel')
    names = page.locator('.sender-email').all_inner_texts()
    assert sorted(names) == ['ali@ornek.example', 'ayse@ornek.example']
    page.select_option('#categorySelect', '')
    page.check('#unsubFilter')
    assert page.locator('.sender-row').count() == 8


def test_locked_sender_cannot_be_selected(ui_page):
    page = ui_page
    row(page, 'bilgi@ornekbanka.example').locator('.lock-btn').click()
    page.wait_for_selector('.sender-row.protected')
    assert row(page, 'bilgi@ornekbanka.example').locator('.sender-checkbox').is_disabled()
    page.check('#selectAll')
    assert page.inner_text('#selectedInfo').startswith('14 gönderen')


def test_delete_confirm_shows_real_count_then_undo_restores(ui_page):
    page = ui_page
    messages = []
    page.on('dialog', lambda d: (messages.append(d.message), d.accept()))
    page.select_option('#scopeSelect', 'all')
    row(page, 'kampanya@ornekmarket.example').locator('.sender-checkbox').check()
    page.click('#deleteBtn')
    page.wait_for_selector('text=Tamamlandı. Toplam 64 mail')

    assert 'bulunan 64 mail' in messages[0]
    assert row(page, 'kampanya@ornekmarket.example').count() == 0

    page.click('#undoBtn')
    page.wait_for_selector('text=64 mail çöpten geri alındı')
    assert row(page, 'kampanya@ornekmarket.example').count() == 1


def test_one_click_needs_confirmation(ui_page):
    page = ui_page
    page.on('dialog', lambda d: d.dismiss())
    r = row(page, 'kampanya@ornekmarket.example')
    r.locator('.unsub-btn').click()
    link = r.locator('.unsub-result a')
    link.wait_for()
    assert link.inner_text() == '🔗 Çıkış sayfasını aç'
    assert link.get_attribute('rel') == 'noopener noreferrer'


def test_server_error_is_shown_readably(ui_page):
    page = ui_page
    page.route('**/api/count', lambda route: route.fulfill(
        status=502, content_type='application/json', body='{"error": "Gmail API hatası (502): test"}'))
    row(page, 'haber@teknohafta.example').locator('.sender-checkbox').check()
    page.click('#deleteBtn')
    page.wait_for_selector('text=Hata oluştu: Gmail API hatası (502): test')
    assert not page.is_disabled('#deleteBtn')
