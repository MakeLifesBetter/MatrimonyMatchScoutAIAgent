# Privacy

Matrimony Match Scout runs on your own laptop, with your own login. There is
no server, no account with us, and no analytics.

## What it reads
Only your own matrimony account, and only the parts you agree to: chats,
interests received, matches and search results — plus any files you give it
(biodata, screenshots in the AI app, chat exports, broker spreadsheets).

## What it stores, and where
One folder you own (default `~/matrimony-scout-data`):
- `interests.json` — what you are looking for (versioned, editable by you)
- `profiles.json` — structured notes on each profile, deduped
- `shared_log.jsonl` — which profiles you were shown, and when
- `run_state.json` — where a scan stopped, so it can resume
- `captures/` — the text of profile and list pages read (inbox: names and links only)
- `reports/` — your top 3, Markdown report and Excel sheet
- `browser_profile/` — the terminal browser's own profile. Like any browser it
  keeps the site's login cookie so you stay logged in; the Scout never reads
  or copies it. Delete this folder to log the Scout's browser out.

## What it never does
- Never asks for, sees, types or stores your password or one-time codes
- Never copies your conversations — chats become a one-line summary
- Never stores phone numbers or email addresses from profiles or spreadsheets
- Never sends a message, or accepts / declines / shortlists anyone, without
  your approval of that exact action
- Never runs face recognition or scores photos or looks
- Never uploads your data anywhere

## Deleting everything
Delete the data folder. There are no other copies.

## A note to contributors
Never commit a data folder, a report, or a real profile. Examples, demos and
tests use fictional people only (`tests/mock_site.py` is a made-up site).
