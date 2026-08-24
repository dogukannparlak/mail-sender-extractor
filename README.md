# Mail Sender Extractor

*Diğer diller: [🇹🇷 Türkçe](README.tr.md)*

A web app that scans your Gmail inbox, groups messages by sender with counts, and lets you
bulk-trash or one-click unsubscribe from the senders you pick. Senders are shown as a single,
sortable list. If you only want a CSV export without the web UI, `extract_senders.py` also runs
standalone as a CLI script.

## Features

- **Scan:** Scans the inbox, lists senders by message count, and writes the result to `gonderenler.csv`.
- **Sort:** Sort by message count (high→low / low→high) or by name (A–Z / Z–A).
- **Bulk select:** A "select all" checkbox to select every sender in one click.
- **Copy address:** Copy any sender's email address to the clipboard.
- **Preview:** See a sender's most recent message subjects/dates before deleting anything.
- **Move to trash:** Move all of the selected senders' messages to Gmail Trash (recoverable for 30 days).
- **Unsubscribe:** Uses the `List-Unsubscribe` header to offer automatic (one-click) unsubscribe,
  or a manual unsubscribe link/address when one-click isn't supported.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Google Cloud credentials (credentials.json)

You need an OAuth client secret file with Gmail API access:

1. Create (or select) a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Under **APIs & Services > Library**, enable the **Gmail API**.
3. Under **APIs & Services > Credentials**, choose **Create Credentials > OAuth client ID**.
   - Application type: **Desktop app**
4. Download the resulting client ID JSON and save it in this folder as `credentials.json`.

## Running (web app, recommended)

```bash
source venv/bin/activate
python app.py
```

Open `http://localhost:5050` in your browser. On first run (or the first time you click "Scan
Inbox"), a browser window will open asking you to sign in with your Google account. Once
approved, a `token.json` file is created so you won't need to sign in again on later runs.

The "Scan Inbox" button scans the inbox and rewrites `gonderenler.csv` with the current sender
list. You can sort the list by message count or name, bulk-select with "select all", copy any
sender's address, and use "Preview" to see that sender's recent subjects before deleting
anything. You can move the selected senders' messages to trash, or unsubscribe (when the sender
supports it).

## Running (CSV only, CLI)

If you just want the scan/CSV output without the web UI:

```bash
source venv/bin/activate
python extract_senders.py
```

The result is written to `gonderenler.csv`: one row per sender (name/address) with the number of
messages from that sender.

## Tests

The project has a `pytest` suite that runs entirely against a fake Gmail service — no real
Gmail account or network access is touched.

```bash
source venv/bin/activate
pip install pytest
python -m pytest tests/ -v
```

## Notes

- `credentials.json` and `token.json` contain secrets and are excluded via `.gitignore`.
- Because `app.py` can delete messages, the shared `token.json` is created with the
  `gmail.modify` scope (read + modify). `extract_senders.py` itself only makes read-only Gmail
  requests and never deletes or modifies messages — but since it shares the same token as the web
  app, that token's permission scope is broader. If you have an older `token.json` created before
  this change, delete it (`rm token.json`) and sign in again.
