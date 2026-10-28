import json

from mail_temizleyici import storage


def test_readable_format_round_trips_and_keeps_short_lists_on_one_line(tmp_path):
    payload = {'zaman': 1.5, 'ids': ['a', 'b'], 'gonderenler': {'x@y.example': {'ad': 'Ç', 'mail_sayisi': 2}}}
    path = tmp_path / 'f.json'

    storage.write_json(str(path), payload, compact=False)
    text = path.read_text(encoding='utf-8')

    assert json.loads(text) == payload
    assert '"ids": ["a", "b"]' in text
    assert '"ad": "Ç"' in text  # Türkçe karakter kaçırılmadan
    assert text.count('\n') > 3


def test_long_id_lists_wrap_within_line_width():
    ids = [f'18c{i:013x}' for i in range(40)]

    text = storage.format_json({'kisi@ornek.example': ids})

    assert json.loads(text) == {'kisi@ornek.example': ids}
    assert max(len(line) for line in text.splitlines()) <= storage.LINE_WIDTH


def test_compact_format_is_one_line(tmp_path):
    path = tmp_path / 'f.json'
    storage.write_json(str(path), {'a': [1, 2]}, compact=True)
    assert path.read_text() == '{"a":[1,2]}'
