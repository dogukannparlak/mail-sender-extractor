# Development

## Tests

The `pytest` suite runs against a fake Gmail service; no real account or network is touched.
`tests/test_ui.py` drives the page in headless Chromium against demo mode (skipped if Chromium
isn't installed).

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium   # for the browser tests in tests/test_ui.py and scripts/make_screenshots.py
python -m pytest tests/ -v
```

## Screenshots

`python scripts/make_screenshots.py` starts demo mode with fake data and writes the screenshots used in the docs:
`doc/screenshots/` (English interface) and `doc-tr/screenshots/` (Turkish interface). Pass `en` or `tr` to make only one set.
It needs Chromium (see above) and never touches real account files.

## Adding a language

1. Copy `mail_cleaner/locales/en.json` to `<code>.json` and translate the values (keep the keys and the `{placeholders}`; plurals
   use `_one` / `_other`).
2. Add the code to `LANGUAGES` in `mail_cleaner/i18n.py` and to the accepted values in `mail_cleaner/config.py`
   (`LANGUAGE`).
3. Optionally add a demo data set in `mail_cleaner/demo_data.py` (`DATASETS`).
4. Run the tests: `tests/test_i18n.py` fails if a key or a placeholder is missing, or if the page still contains text of another language.

## Notes

- The token uses the `gmail.modify` scope (read + modify), because the web app moves messages
  to Trash. `extract_senders.py` only reads, but shares the same token.
- If an account's sign-in stops working (expired or revoked), remove it in the header and add it again.

- Older versions used Turkish file and folder names (`hesaplar/`, `gonderenler.csv`, …). On start the app renames them to the English names (never overwriting or deleting). If your `.env` still says `ACCOUNTS_DIR=hesaplar`, that folder name is kept.
