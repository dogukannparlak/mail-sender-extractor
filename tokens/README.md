# tokens/

For accounts whose token file you already have. Files in this folder are not committed to git (except this README).

1. Copy the token file here and rename it, e.g. `second.json`.
2. In `.env`, remove the `#` at the start of the matching line and write the address:
   `ACCOUNT_2=second@gmail.com=tokens/second.json`
3. Restart the app; the account shows up in the "Scanned account" picker at the top.

If you don't have a token file you don't need to put anything here: sign in with "+ Add account" in the app and the token is written
to `accounts/<address>/token.json` by itself.
