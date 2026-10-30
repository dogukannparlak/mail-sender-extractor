import os

from mail_cleaner import migrate


def touch(path, text='x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def test_renames_old_turkish_files_without_overwriting_or_deleting(tmp_path):
    base = str(tmp_path / 'project')  # tmp_path'in kendisinde autouse fixture'ın accounts/ klasörü var
    old = os.path.join(base, 'hesaplar', 'a@x.example')
    for name in migrate.LEGACY_ACCOUNT_FILES:
        touch(os.path.join(old, name), name)
    touch(os.path.join(old, 'token.json'), 'secret')
    touch(os.path.join(base, 'korunanlar.json'), '{}')

    moved = migrate.run(base, os.path.join(base, 'accounts'), os.path.join(base, 'protected.json'))

    folder = os.path.join(base, 'accounts', 'a@x.example')
    assert sorted(os.listdir(folder)) == sorted(list(migrate.LEGACY_ACCOUNT_FILES.values()) + ['token.json'])
    assert open(os.path.join(folder, 'token.json')).read() == 'secret'
    assert open(os.path.join(folder, 'senders.csv')).read() == 'gonderenler.csv'
    assert os.path.exists(os.path.join(base, 'protected.json')) and not os.path.exists(os.path.join(base, 'korunanlar.json'))
    assert not os.path.exists(os.path.join(base, 'hesaplar'))
    assert len(moved) == 1 + len(migrate.LEGACY_ACCOUNT_FILES) + 1


def test_never_overwrites_an_existing_new_file(tmp_path):
    base = str(tmp_path / 'project')  # tmp_path'in kendisinde autouse fixture'ın accounts/ klasörü var
    folder = os.path.join(base, 'accounts', 'a@x.example')
    touch(os.path.join(folder, 'gonderenler.csv'), 'old')
    touch(os.path.join(folder, 'senders.csv'), 'new')

    assert migrate.run(base, os.path.join(base, 'accounts'), os.path.join(base, 'protected.json')) == []

    assert open(os.path.join(folder, 'senders.csv')).read() == 'new'
    assert open(os.path.join(folder, 'gonderenler.csv')).read() == 'old'


def test_custom_accounts_dir_from_env_is_left_where_it_is(tmp_path):
    base = str(tmp_path / 'project')  # tmp_path'in kendisinde autouse fixture'ın accounts/ klasörü var
    custom = os.path.join(base, 'hesaplar')  # .env'de ACCOUNTS_DIR=hesaplar yazıyorsa klasör adı korunur
    touch(os.path.join(custom, 'a@x.example', 'gonderenler.csv'))

    migrate.run(base, custom, os.path.join(base, 'protected.json'))

    assert os.path.exists(os.path.join(custom, 'a@x.example', 'senders.csv'))
