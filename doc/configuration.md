# Configuration

## Settings (`.env`)

Settings live in a `.env` file in the project folder (not committed). Start from the example:

```bash
cp .env.example .env
```

| Setting | Default | What it does |
|---|---|---|
| `PORT` | `5050` | Port of `http://localhost:<PORT>` |
| `LANGUAGE` | empty | Interface language: `en` or `tr`. Empty = follow the browser's language (English if it is neither) |
| `DEMO` | `0` | `1` = demo mode with fake accounts, no Gmail |
| `FLASK_DEBUG` | `0` | Flask debug mode (development only) |
| `COMPACT_FILES` | `0` | `0` = the JSON files the app writes are indented and easy to read, `1` = one compact line |
| `CREDENTIALS_PATH` | `credentials.json` | Optional shared OAuth client; normally each account brings its own file instead |
| `ACCOUNTS_DIR` | `accounts` | Folder with one sub-folder per account |
| `ACCOUNT_1`, `ACCOUNT_2`, … | empty | One line per account whose token file you already have: `address=token_path` (e.g. `tokens/second.json`) |
| `EXTRA_ACCOUNTS` | empty | The same on one line: `address=token_path, address=token_path` |
| `GMAIL_QUOTA_PER_MINUTE` | `5400` | Quota units per minute the app allows itself (Gmail's limit is 6,000) |
| `DEFAULT_SCOPE` | `inbox` | Default delete/preview scope: `inbox` or `all` |

A value given on the command line wins over `.env` (`DEMO=1 python app.py`). Relative paths are
relative to the project folder; `~` is expanded. A wrong value stops the app at start with a
message naming the setting. Accounts listed in `ACCOUNT_n` / `EXTRA_ACCOUNTS` can't be removed from the page
(the token file is yours); delete the line instead.

## Language

The interface is available in **English** and **Türkçe**. Use the language picker in the page header
(and on the Subscriptions, Notifications and Activity log pages); the choice is remembered in a cookie.

The language is chosen in this order: `?lang=en` in the address › the cookie › the `LANGUAGE` setting in `.env` ›
the browser's `Accept-Language` › English. Server messages (errors, `.env` problems) follow the same rule; messages created
by a background scan use the language of the browser tab that started it.

Demo mode uses fake data in the same language (`LANGUAGE`, English if empty). To add a language see
[development.md](development.md#adding-a-language).

## CSV only (CLI)

```bash
python extract_senders.py                    # the only account, if there is just one
python extract_senders.py someone@gmail.com  # a specific account
```

Writes that account's `accounts/<address>/senders.csv`: one row per address with display name,
count, category and whether an unsubscribe link was seen. Older CSV files (raw `From` header +
count) are still read and merged by address.
