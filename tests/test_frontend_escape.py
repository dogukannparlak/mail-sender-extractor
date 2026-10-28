import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / 'templates' / 'index.html'


def _escape_html_source():
    html = TEMPLATE.read_text(encoding='utf-8')
    match = re.search(r'const HTML_ESCAPES = .*?\nfunction escapeHtml\(str\) \{.*?\n\}', html, re.S)
    assert match, 'escapeHtml bulunamadı'
    return match.group(0)


@pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
def test_escape_html_escapes_attribute_breaking_quotes():
    script = _escape_html_source() + r'''
const out = escapeHtml(`"x" onmouseover='alert(1)' <a@b.com> & `);
process.stdout.write(out);
'''
    out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout

    assert out == '&quot;x&quot; onmouseover=&#39;alert(1)&#39; &lt;a@b.com&gt; &amp; '
