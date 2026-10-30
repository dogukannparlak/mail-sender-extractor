"""Küçük dosya yardımcıları.

Uygulamanın yazdığı JSON dosyaları varsayılan olarak okunaklıdır: girintili, her anahtar ayrı satırda,
uzun id listeleri satırlara bölünmüş. .env'de COMPACT_FILES=1 tek satırlık sıkışık biçime geçirir.
"""
import json
import os

LINE_WIDTH = 100
COMPACT = False  # config.settings.compact_files ile web açılışında ayarlanır


def _is_scalar(value):
    return value is None or isinstance(value, (str, int, float, bool))


def format_json(value, indent=0):
    """json.dumps(indent=2) gibi; ama sayı/metin listelerini alt alta değil satırlara sığdırarak yazar."""
    pad, inner = '  ' * indent, '  ' * (indent + 1)
    if isinstance(value, dict):
        if not value:
            return '{}'
        items = [f'{inner}{json.dumps(str(k), ensure_ascii=False)}: {format_json(v, indent + 1)}'
                 for k, v in value.items()]
        return '{\n' + ',\n'.join(items) + '\n' + pad + '}'
    if isinstance(value, (list, tuple)):
        if not value:
            return '[]'
        if all(_is_scalar(v) for v in value):
            parts = [json.dumps(v, ensure_ascii=False) for v in value]
            one_line = '[' + ', '.join(parts) + ']'
            if len(inner) + len(one_line) <= LINE_WIDTH:
                return one_line
            lines, line = [], ''
            for part in parts:
                candidate = f'{line}, {part}' if line else part
                if line and len(inner) + len(candidate) > LINE_WIDTH:
                    lines.append(line)
                    candidate = part
                line = candidate
            lines.append(line)
            return '[\n' + ',\n'.join(inner + l for l in lines) + '\n' + pad + ']'
        return '[\n' + ',\n'.join(inner + format_json(v, indent + 1) for v in value) + '\n' + pad + ']'
    return json.dumps(value, ensure_ascii=False)


def dumps(payload, compact=None):
    compact = COMPACT if compact is None else compact
    if compact:
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    return format_json(payload) + '\n'


def write_json(path, payload, compact=None):
    """Önce geçici dosyaya yazar, sonra yerine koyar: yarım dosya okunmasın."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(dumps(payload, compact))
    os.replace(tmp, path)


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)
