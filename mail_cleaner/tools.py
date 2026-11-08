"""Uygulama içi araçlar: ayarlar sayfası, CSV dışa aktarma, veri klasörü/yedek, belgeler, dış bağlantılar.

Hepsi yerel sunucuda çalışır; böylece hem macOS penceresinde hem tarayıcıda aynı şekilde kullanılır.
"""
import datetime
import os
import re
import subprocess
import sys
import webbrowser
import zipfile

from flask import Blueprint, abort, jsonify, render_template, request, send_from_directory

from . import accounts, storage
from . import config
from .config import BASE_DIR
from .gmail import quota
from .i18n import current_language, t

bp = Blueprint('tools', __name__)

# Kaynak klasörü: PyInstaller paketinde belgeler _MEIPASS içindedir.
RESOURCE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HELP_PAGES = ['README', 'setup', 'features', 'configuration', 'architecture', 'development']
# Ayarlar sayfasından değiştirilebilen .env anahtarları (PORT/DEMO/hesap yolları dosyada elle kalır).
EDITABLE = ('LANGUAGE', 'DEFAULT_SCOPE', 'GMAIL_QUOTA_PER_MINUTE', 'COMPACT_FILES')


def downloads_dir():
    return os.path.expanduser('~/Downloads')


def reveal(path):
    """macOS'ta dosyayı Finder'da gösterir; başka sistemde sessizce geçer."""
    if sys.platform == 'darwin':
        subprocess.run(['open', '-R', path], check=False)


def _json_error(message, status=400):
    return jsonify({'error': message}), status


# --- Ayarlar ------------------------------------------------------------------

def update_env_file(path, changes):
    """`.env` içinde yalnız verilen anahtarları değiştirir; yorumlar ve diğer satırlar korunur."""
    lines = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            lines = f.read().splitlines()
    remaining = dict(changes)
    for i, line in enumerate(lines):
        match = re.match(r'\s*([A-Z_][A-Z0-9_]*)\s*=', line)
        if match and match.group(1) in remaining:
            lines[i] = f'{match.group(1)}={remaining.pop(match.group(1))}'
    lines.extend(f'{key}={value}' for key, value in remaining.items())
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, path)


def current_values():
    s = config.settings
    return {'LANGUAGE': s.language, 'DEFAULT_SCOPE': s.default_scope,
            'GMAIL_QUOTA_PER_MINUTE': str(s.quota_per_minute), 'COMPACT_FILES': '1' if s.compact_files else '0'}


@bp.route('/settings')
def settings_page():
    return render_template('settings.html', values=current_values(), data_dir=BASE_DIR, env_path=config.ENV_PATH,
                           account_list=accounts.list_accounts())


@bp.route('/api/settings', methods=['POST'])
def api_settings():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _json_error(t('err.unexpected'))
    changes = {k: str(body[k]).strip() for k in EDITABLE if k in body}
    merged = {**config.read_env_file(config.ENV_PATH), **changes}
    try:
        candidate = config.Settings(merged)  # aynı doğrulama: hatalı değer ConfigError (ValueError) fırlatır
    except ValueError as e:
        return _json_error(str(e))
    update_env_file(config.ENV_PATH, changes)
    # Canlı uygula: yeniden başlatmak gerekmesin.
    s = config.settings
    s.language, s.default_scope = candidate.language, candidate.default_scope
    s.quota_per_minute, s.compact_files = candidate.quota_per_minute, candidate.compact_files
    from . import web
    web.DEFAULT_SCOPE = candidate.default_scope
    storage.COMPACT = candidate.compact_files
    quota.units_per_minute = candidate.quota_per_minute
    return jsonify({'ok': True})


# --- Dışa aktarma ve yedek ----------------------------------------------------

@bp.route('/api/export/csv', methods=['POST'])
def api_export_csv():
    body = request.get_json(silent=True) or {}
    try:
        paths = accounts.resolve(request.args.get('account') or body.get('account'))
    except ValueError as e:
        return _json_error(str(e))
    if not os.path.exists(paths.csv):
        return _json_error(t('tools.csv_missing'))
    stamp = datetime.date.today().strftime('%Y%m%d')
    target = os.path.join(downloads_dir(), f'senders-{paths.account}-{stamp}.csv')
    os.makedirs(downloads_dir(), exist_ok=True)
    with open(paths.csv, 'rb') as src, open(target, 'wb') as dst:
        dst.write(src.read())
    reveal(target)
    return jsonify({'path': target})


@bp.route('/api/data/open', methods=['POST'])
def api_data_open():
    os.makedirs(BASE_DIR, mode=0o700, exist_ok=True)
    if sys.platform == 'darwin':
        subprocess.run(['open', BASE_DIR], check=False)
    return jsonify({'path': BASE_DIR})


@bp.route('/api/data/backup', methods=['POST'])
def api_data_backup():
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M')
    target = os.path.join(downloads_dir(), f'mail-sender-extractor-backup-{stamp}.zip')
    os.makedirs(downloads_dir(), exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # içinde token var: yalnız sahibi okusun
    with os.fdopen(fd, 'wb') as raw, zipfile.ZipFile(raw, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name in ('accounts', '.env'):
            full = os.path.join(BASE_DIR, name)
            if os.path.isfile(full):
                zf.write(full, name)
            for folder, _dirs, files in os.walk(full if os.path.isdir(full) else os.devnull):
                for file in files:
                    path = os.path.join(folder, file)
                    zf.write(path, os.path.relpath(path, BASE_DIR))
    reveal(target)
    return jsonify({'path': target})


# --- Dış bağlantılar ----------------------------------------------------------

@bp.route('/api/open-url', methods=['POST'])
def api_open_url():
    """Pencere içinden tıklanan dış bağlantı varsayılan tarayıcıda açılır (pencere sitelere gitmesin)."""
    url = (request.get_json(silent=True) or {}).get('url', '')
    if not re.match(r'https?://', url or '', re.I):
        return _json_error(t('tools.url_invalid'))
    webbrowser.open(url)
    return jsonify({'ok': True})


# --- Belgeler -----------------------------------------------------------------

def _doc_dir():
    return os.path.join(RESOURCE_DIR, 'doc-tr' if current_language() == 'tr' else 'doc')


def _render_markdown(text):
    import markdown
    html = markdown.markdown(text, extensions=['tables', 'fenced_code', 'toc'])
    html = re.sub(r'(src=")(?:\.\./|doc/|doc-tr/)*screenshots/([^"]+)"', r'\1/help-img/\2"', html)

    def page_link(match):
        name = os.path.basename(match.group(1))[:-3]
        return f'href="/help/{name}{match.group(2)}"' if name in HELP_PAGES else match.group(0)

    return re.sub(r'href="(?!https?:|#|/)([^"#]*\.md)(#[^"]*)?"', page_link, html)


@bp.route('/help')
@bp.route('/help/<name>')
def help_page(name='README'):
    if name not in HELP_PAGES:
        abort(404)
    path = os.path.join(_doc_dir(), name + '.md')
    if not os.path.isfile(path):
        abort(404)
    with open(path, encoding='utf-8') as f:
        body = _render_markdown(f.read())
    return render_template('help.html', body=body, name=name, pages=HELP_PAGES)


@bp.route('/help-img/<path:filename>')
def help_image(filename):
    return send_from_directory(os.path.join(_doc_dir(), 'screenshots'), filename)
