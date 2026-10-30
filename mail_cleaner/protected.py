"""Korunan gönderenler (banka, okul…): seçilemez, taşınamaz, abonelikten çıkılamaz.

Liste her hesapta ayrıdır (accounts/<adres>/protected.json). Alan adı girdisi ("@garanti.com.tr") alt alan adlarını da kapsar.
"""
import re

from .gmail import EMAIL_RE
from .storage import read_json, write_json
from .i18n import t

DOMAIN_RE = re.compile(r'^@[\w-]+(\.[\w-]+)+$')


def load_protected(paths):
    stored = read_json(paths.protected, {})
    return {'adresler': sorted(stored.get('adresler', [])), 'alanlar': sorted(stored.get('alanlar', []))}


def is_protected(email, protected):
    email = email.lower()
    domain = email.rsplit('@', 1)[-1]
    if email in protected['adresler']:
        return True
    return any(domain == d[1:] or domain.endswith('.' + d[1:]) for d in protected['alanlar'])


def reject_protected(paths, emails):
    protected = load_protected(paths)
    blocked = [email for email in emails if is_protected(email, protected)]
    if blocked:
        raise ValueError(t('err.protected_senders', senders=', '.join(blocked)))


def set_protected(paths, value, make_protected):
    """Adresi ya da @alan adını listeye ekler/çıkarır; güncel listeyi döner."""
    if not isinstance(value, str):
        raise ValueError(t('err.value_required'))
    value = value.strip().lower()
    if DOMAIN_RE.match(value):
        field = 'alanlar'
    elif EMAIL_RE.match(value):
        field = 'adresler'
    else:
        raise ValueError(t('err.invalid_protect_value', value=repr(value)))

    protected = load_protected(paths)
    entries = set(protected[field])
    if make_protected:
        entries.add(value)
    else:
        entries.discard(value)
    protected[field] = sorted(entries)
    write_json(paths.protected, protected)
    return protected
