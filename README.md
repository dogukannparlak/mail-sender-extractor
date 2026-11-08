# Mail Sender Extractor

*Other languages: [🇹🇷 Türkçe](doc-tr/README.md)*

A local web app that scans your Gmail (inbox, spam and archive), groups messages by sender, and lets you bulk-trash or unsubscribe
from the senders you pick, with an undo for the last delete. It also lists every newsletter with its unsubscribe link, warns you when
a sender keeps mailing after you unsubscribed, and keeps a log of what you did. The interface is available in **English** and
**Türkçe**. It runs only on your own machine (`localhost`); nothing is sent anywhere except Gmail's own API.

![Sender list in demo mode](doc/screenshots/main.png)

## Highlights

- Fast rescans: headers are cached, so later scans only read new messages; several accounts can be scanned **at the same time**.
- One row per sender, **domain view** with per-address actions, search, filters and sorting, categories without any model.
- Safe deletes: moves to Trash with the real count, **undo**, protected senders; unsubscribe only where a link exists, one-click only after you confirm.
- **Subscriptions**, **Notifications** and **Activity log** pages for each account.
- Every Gmail account connects with its own Google Cloud client; no shared project or test-user list.

## Download (macOS)

Get `Mail-Sender-Extractor-0.5.0.dmg` from the [Releases](https://github.com/dogukannparlak/mail-sender-extractor/releases)
page, drag the app to Applications. The app is not signed: on first launch right-click it › **Open**.
Everything else (Google Cloud client, adding accounts) is explained in the in-app **Help** or [setup](doc/setup.md).

## Quick start

Try it without a Gmail account (fake data, nothing leaves your machine):

```bash
git clone https://github.com/dogukannparlak/mail-sender-extractor.git
cd mail-sender-extractor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
DEMO=1 python app.py
```

Open `http://localhost:5050`. To use your real Gmail, follow the [setup guide](doc/setup.md).

## Documentation

| Guide | What is in it |
|---|---|
| [Setup](doc/setup.md) | Demo mode, installing, the Google Cloud client, adding one or several Gmail accounts |
| [Features](doc/features.md) | Everything the app does, screenshots, the Subscriptions / Notifications / Activity log pages |
| [Configuration](doc/configuration.md) | `.env` settings, interface language, the command-line tool |
| [Architecture](doc/architecture.md) | How it works, project layout, front-end and translation structure, security notes |
| [Development](doc/development.md) | Tests, regenerating screenshots, adding a language |

Documentation in Turkish: [doc-tr](doc-tr/README.md).
