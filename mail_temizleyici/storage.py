"""Küçük dosya yardımcıları."""
import json
import os


def write_json(path, payload, compact=False):
    """Önce geçici dosyaya yazar, sonra yerine koyar: yarım dosya okunmasın."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        if compact:  # binlerce id içeren dosyalar (geri alma, tarama dizini)
            json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        else:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)
