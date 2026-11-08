# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.5.0] - 2026-11-08

First release with a macOS app. The unsigned `.dmg` is attached to the GitHub release.

### Added
- **macOS app** (`Mail Sender Extractor.app`): the same local app in its own window, native menu, app icon,
  external links open in the default browser, optional "Open in browser". Build with `packaging/macos/build.sh`
  (`install` copies it to /Applications). Data lives in `~/Library/Application Support/Mail Sender Extractor/`
  (override with `MAIL_CLEANER_HOME`).
- **In-app settings** (⌘,): language, default delete scope, Gmail quota, compact files; applied live.
- **Export and backup from the app:** sender list as CSV, data-folder shortcut, backup zip (to Downloads).
- **Built-in documentation** (Help): setup, features, configuration in English and Turkish.
- **Scanning:** cancel button for running scans, full scan for all accounts, and an "Anything new?" check that looks
  for new mail in every account without scanning.
- **Notifications:** select rows and mark them read or unread; clicking a notification marks it read.
- **Sign in again:** renew the Google session of an account whose token expired or was revoked.
- One **active account** shared by every page and tab, remembered between launches.
- Subscriptions: unsubscribed senders stay listed after their mails are deleted, missing names and links are filled
  from Gmail, multi-select category filter, full-width table; home page sorted by last mail date.

### Fixed
- "Mark all as read" on the Notifications page did nothing because of a leftover script error.
- A background check with an expired token reported a missing `credentials.json` instead of asking to sign in again.

### Notes
- If your Google Cloud project is in "Testing" status, Google expires the sign-in about every 7 days; set the
  publishing status to "In production" to avoid it (see `doc/setup.md`).
