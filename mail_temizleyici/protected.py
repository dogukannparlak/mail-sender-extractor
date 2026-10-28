"""Korunan gönderenler (banka, okul…): seçilemez, taşınamaz, abonelikten çıkılamaz.

Liste bütün hesaplar için ortak. Alan adı girdisi ("@garanti.com.tr") alt alan adlarını da kapsar.
"""
import os
import re

from .config import BASE_DIR
from .gmail import EMAIL_RE
from .storage import read_json, write_json

PROTECTED_PATH = os.path.join(BASE_DIR, 'korunanlar.json')
DOMAIN_RE = re.compile(r'^@[\w-]+(\.[\w-]+)+$')


def load_protected():
    stored = read_json(PROTECTED_PATH, {})
    return {'adresler': sorted(stored.get('adresler', [])), 'alanlar': sorted(stored.get('alanlar', []))}


def is_protected(email, protected):
    email = email.lower()
    domain = email.rsplit('@', 1)[-1]
    if email in protected['adresler']:
        return True
    return any(domain == d[1:] or domain.endswith('.' + d[1:]) for d in protected['alanlar'])


def reject_protected(emails):
    protected = load_protected()
    blocked = [email for email in emails if is_protected(email, protected)]
    if blocked:
        raise ValueError('Korunan gönderenlere işlem yapılamaz: ' + ', '.join(blocked))


def set_protected(value, make_protected):
    """Adresi ya da @alan adını listeye ekler/çıkarır; güncel listeyi döner."""
    if not isinstance(value, str):
        raise ValueError("İstek gövdesinde 'value' adında bir metin bekleniyor.")
    value = value.strip().lower()
    if DOMAIN_RE.match(value):
        field = 'alanlar'
    elif EMAIL_RE.match(value):
        field = 'adresler'
    else:
        raise ValueError(f'Geçersiz adres ya da alan adı: {value!r} (alan adı için "@ornek.com" yaz).')

    protected = load_protected()
    entries = set(protected[field])
    if make_protected:
        entries.add(value)
    else:
        entries.discard(value)
    protected[field] = sorted(entries)
    write_json(PROTECTED_PATH, protected)
    return protected
