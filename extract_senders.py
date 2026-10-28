"""Yalnız CSV: bir hesabın gelen kutusunu tarar, o hesabın gonderenler.csv dosyasını yazar (web arayüzü olmadan).

python extract_senders.py                 → tek hesap varsa onu tarar
python extract_senders.py adres@gmail.com → o hesabı tarar
"""
import sys

from mail_temizleyici import accounts
from mail_temizleyici.scanner import extract_senders, print_progress

if __name__ == '__main__':
    try:
        accounts.migrate_legacy_account()
        paths = accounts.resolve(sys.argv[1] if len(sys.argv) > 1 else None)
    except ValueError as e:
        sys.exit(f'{e} Hesaplar: {", ".join(accounts.list_accounts()) or "yok"}')
    senders = extract_senders(accounts.get_service(paths.account), progress=print_progress)
    print()
    accounts.save_senders(paths, senders)
    print(f'{len(senders)} gönderen yazıldı: {paths.csv}')
