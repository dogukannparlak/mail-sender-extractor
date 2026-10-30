# Setup

How to run the app: a quick demo without Gmail, then the full setup for real accounts (Google Cloud client, adding accounts, several accounts).
Settings are in [configuration.md](configuration.md).

## Try it without a Gmail account (demo mode)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
DEMO=1 python app.py
```

Open `http://localhost:5050`. Demo mode uses two in-memory fake accounts (about 500 messages);
data files go to a temporary folder and unsubscribe requests never leave your machine.

## Use it with your Gmail

There is no "main" account: **every Gmail account connects on its own**, with an OAuth client
from its own Google Cloud project. Nobody else's project, approval or test-user list is involved.
Do steps 1–2 once, then steps 3–4 for **each** account you want to add.

### 1. Install

```bash
git clone https://github.com/dogukannparlak/mail-sender-extractor.git
cd mail-sender-extractor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optional: settings, see configuration.md
```

### 2. Run

```bash
source venv/bin/activate
python app.py
```

Open `http://localhost:5050`. Keep this terminal open while you use the app; `Ctrl+C` stops it.

### 3. Google Cloud setup (once per account, ~10 minutes)

Sign in to the [Google Cloud Console](https://console.cloud.google.com/) **with the Gmail account
you are about to add**. Google renames menu items now and then; if a name differs, look for the
closest one.

1. **Create a project.** Click the project picker at the top › **New project** › give it a name
   (e.g. `mail-cleaner`) › **Create**. Make sure the new project is selected at the top.
2. **Turn on the Gmail API.** Open
   [APIs & Services › Library › Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
   and click **Enable**.
3. **Set up the sign-in screen.** Open
   [Google Auth Platform](https://console.cloud.google.com/auth/overview) › **Get started**:
   - **App information:** any app name (e.g. `Mail Cleaner`) and your address as support email.
   - **Audience:** **External**.
   - **Contact information:** your address. Accept the policy › **Create**.
4. **Add yourself as a test user** (needed even though it is your own project).
   **Audience** › **Test users** › **Add users** › type the Gmail address of this account followed
   by a comma, so it turns into a chip › **Save**. Check that the list now shows "1 user (1 test)".
   Without this, sign-in fails with `Error 403: access_denied`.
5. **Allow the Gmail permission** (recommended). **Data access** › **Add or remove scopes** › find
   `https://www.googleapis.com/auth/gmail.modify` (or paste it under "Manually add scopes") ›
   **Update** › **Save**.
6. **Create the client.** **Clients** › **Create client** › Application type **Desktop app** › any
   name › **Create** › **Download JSON**. You get a file like `client_secret_1234….json`.
   Keep it private: it identifies your project.

### 4. Add the account in the app

1. Click **+ Add account** at the top of the page.
2. Choose the `client_secret_….json` file from step 3.6.
3. A Google window opens. Pick **the same account**, then:
   - "Google hasn't verified this app" appears because the project is in testing mode and only
     you use it. Click **Continue**.
   - Allow access to Gmail (read and change, so the app can move mail to Trash).
4. Back in the app you see "<address> added". Click **Scan inbox**.

The app stores that account's client file and sign-in token in `accounts/<address>/` (git
ignores this folder). Deleted messages go to Gmail's **Trash**, not straight to permanent
deletion; Gmail empties the Trash after 30 days.

**Other ways to add an account:**

| You have | Do this |
|---|---|
| The account's `client_secret_….json` and want to prepare folders by hand | Create `accounts/<address>/`, put the file there as `credentials.json`. The account shows up in **+ Add account** as "waiting for sign-in"; click it. Signing in with a different Google account is refused. |
| A ready `token.json` made with that account's client | Put it in `tokens/` and add a line `ACCOUNT_2=<address>=tokens/<file>.json` to `.env` (see [configuration.md](configuration.md)). |
| One shared `credentials.json` in the project folder | Still works: **+ Add account** offers it. Then every account must be a test user of that one project. |

**Testing mode note:** Google may sign apps in testing mode out after about 7 days. When that
happens the app says the session expired: **Remove account**, then add it again with the same
file. (Publishing the app in Google Auth Platform › Audience avoids this, at the cost of an
"unverified app" warning; I have not verified Google's current rules for this.)

### 5. Multiple accounts

You can manage several Gmail accounts (personal, school, work) from the same page.

1. **Add:** follow steps 3–4 above for each account. Google shows its account picker, so the
   account that happens to be signed in to your browser is not chosen silently.
2. **Switch:** choose the account in the picker at the top. The list, selection, previews and
   "Undo" belong to that account; switching never carries a selection over.
3. **Work:** scan, trash, undo and unsubscribe always act on the selected account only. The confirm
   dialog and the bottom bar show the account name, so you can't trash mail in the wrong one.
4. **Remove:** **Remove account** deletes only that account's sign-in token on this computer. Your
   mail is not touched, and the saved sender list stays, so re-adding the account brings it back.
   To revoke the app's access at Google as well, use
   [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

| What | Per account or shared? |
|---|---|
| Google Cloud client, sign-in token, sender list, scan index and cache, last-trash record, subscriptions, notifications, activity log | Per account: `accounts/<address>/` |
| Protected senders (`protected.json`) | Shared: a bank you lock is protected in every account |
| Gmail quota (~300 message reads per minute) | Gmail counts it per account, and so does the app: every account has its own budget, so several accounts can be scanned at the same time (*Scan all accounts*) |

**Upgrading from the single-account version:** on first start an existing `token.json` and its
data files (`senders.csv`, `scan_ids.json`, `last_action.json`) are moved into the folder of
the account they belong to, and so is `credentials.json` if that token was made with it. The page
tells you which account they were moved to.
