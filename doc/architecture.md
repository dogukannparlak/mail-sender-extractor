# Architecture

## How it works

```
browser (templates/*.html, static/css, static/js)
   │  fetch, same-origin only
   ▼
Flask mail_cleaner/web.py ── Host / Origin checks ── Gmail API (google-api-python-client)
   │                                     ├─ messages.list  (scan: -in:trash -in:sent -in:drafts, spam included;
   │                                     │                  delete/preview: from:"addr" in:inbox | -in:trash)
   │                                     ├─ batch messages.get (metadata)
   │                                     ├─ messages.batchModify (TRASH)
   │                                     └─ batch messages.untrash (undo)
   └─ local files: accounts/<address>/{token.json, credentials.json, senders.csv, scan_ids.json,
                   scan_cache.json, last_action.json, subscriptions.json, notifications.json,
                   activity_log.jsonl, protected.json}
```

Gmail's quota is per user, so every account has its own quota limiter and several accounts can be scanned at the same time.
The first scan reads every message's headers; they are cached in `scan_cache.json` and later scans only read new messages.

## Project layout

```
app.py                  web app entry point (python app.py)
demo.py                 demo mode entry point (python demo.py)
extract_senders.py      command-line tool: scan one account into a CSV
scripts/                helper scripts (make_screenshots.py)
doc/  doc-tr/           documentation in English / in Turkish (with their screenshots)
tests/                  pytest suite (fake Gmail service) and browser tests (Playwright)
mail_cleaner/           the application package
  ├─ config.py          .env settings                     ├─ templates/  pages (Jinja): base, index, subscriptions,
  ├─ auth.py            Google sign-in, tokens            │              notifications, activity_log + partials
  ├─ gmail.py           Gmail helpers, quota limiters     ├─ static/css/ app.css (main page), pages.css (other pages)
  ├─ scanner.py         scan with per-message cache       ├─ static/js/  one file per feature, see below
  ├─ accounts.py        account folders and files         └─ locales/    en.json, tr.json (all interface text)
  ├─ mailbox.py         count, trash, undo, preview
  ├─ unsubscribe.py     List-Unsubscribe, one-click       ├─ i18n.py     language selection and t() / tn()
  ├─ subscriptions.py   subscription list, notifications  ├─ migrate.py  renames files of older versions
  ├─ activity.py        per-account activity log          ├─ demo.py, demo_data.py  fake mailboxes (en, tr)
  ├─ protected.py       protected senders (per account)  ├─ storage.py  readable JSON files
  ├─ state.py           scan/delete state and locks       └─ web.py      Flask app: pages, JSON API, error mapping
```

### Front end

The pages are server-rendered Jinja templates (`templates/base.html` is the shared shell). The main page's behaviour lives in
`static/js/`, **one file per feature**, loaded in this order as plain scripts (no build step; they share one global scope):

| File | Job |
|---|---|
| `i18n.js` | `t()` / `tn()` translation helpers and the language picker |
| `state.js` | the page state object and constants |
| `util.js` | DOM helper `el()`, `api()` fetch wrapper, date and duration formatting |
| `ui.js` | notice area and confirm dialog |
| `senders.js` | filtering, sorting, grouping and drawing the sender list |
| `preview.js` | per-sender preview, domain address list, copy |
| `selection.js` | selection state, action bar, busy state |
| `protection.js` | protect / unprotect |
| `unsubscribe.js` | unsubscribe flow with confirmation |
| `delete.js` | move to Trash and undo |
| `accounts.js` | account picker, add / remove, sign-in |
| `scan.js` | scan, scan all accounts, progress |
| `main.js` | event wiring and start-up |
| `list.js` | search / filter / sort for the table pages |

### Interface text

All interface text lives in `mail_cleaner/locales/<language>.json` (flat `key → text`, `{name}` placeholders, `_one` / `_other` for
plurals). Python code and templates call `t('key')`; the page sends only the keys the JavaScript uses to the browser. A test keeps the
catalogs in sync (same keys and placeholders in every language, no missing or unused keys).

### Data format notes

Some stored and API field names are still Turkish (`gonderen`, `mail_sayisi`, `kategori`, `abonelik`, `tur`, `islem`, …) and
the category values are `bulten`, `promosyon`, `bildirim`, `kisisel`, `spam`. They are internal identifiers, never shown to the user;
they were kept so existing scan caches, logs and notifications keep working. Files and folders have English names; files from older
versions are renamed on start by `migrate.py` (never overwritten or deleted).

## Security notes

The app holds a token that can modify your mail, so it is built to be reachable only from your
own browser on `localhost`:

- Requests with any `Host` other than `localhost` / `127.0.0.1` / `[::1]` are rejected
  (DNS rebinding), and cross-site `POST`s are rejected using `Sec-Fetch-Site` and `Origin`.
- Sender addresses are parsed and validated before they go into a Gmail search, so a crafted
  `From` header can't widen the query (e.g. `x@y.com OR label:inbox`).
- Everything coming from mail headers is HTML-escaped before it reaches the page.
- One-click unsubscribe only goes to `https` URLs on public IP addresses, without following
  redirects, and only after you confirm.
- Unsubscribe links shown on the Subscriptions page are limited to `http`, `https` and `mailto:` and open with `rel="noopener noreferrer"`; anything else (e.g. `javascript:`) is dropped.
- `credentials.json`, the `accounts/` folder (tokens, scan cache, notifications, activity log) and the local data files are in `.gitignore`. The cache and log contain sender addresses and stay on your machine.

Don't expose this app on a network or run it on a shared server.
