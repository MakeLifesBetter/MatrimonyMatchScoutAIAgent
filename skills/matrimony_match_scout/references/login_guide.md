# Login guide

The user ALWAYS logs in themselves. Never ask for, type, read, or store a
password, one-time code or CAPTCHA answer — not in chat, not in a file.

## Step 0: which browser route is available? (always first)
Never assume you can see a browser.

- Route A — the user's own Chrome (preferred for repeat use: the site already
  knows that browser). In Muse this is the Muse for Chrome extension
  (https://muse.ai/chrome-extension, official "Muse from Meta" listing): the
  user opens it from the Extensions button, signs in, finishes the intro, and
  turns on "Use this browser" if asked. They must be messaging from that same
  computer (Chrome side panel, muse.ai in the same Chrome, or the Mac app).
  If the conversation reports no device browser, say so — do not claim you can
  see their Chrome.
- Route B — the assistant's own browser. A separate browser; the user signs in
  through takeover. Warn that the site may treat it as a new device and ask
  for an extra code.
- No route: explain the two routes in plain English and stop. Do not scan.

## Step 1: guide the login (say, in this order)
1. "I will open <site> in the browser now."
2. "Please log in yourself, in that window. Never type your password here."
3. "If the site sends a code or shows a puzzle, complete it in the browser."
4. "Tell me 'logged in' when you can see your home page or inbox."

## Step 2: verify
- Logged in = the user's name/avatar or an Inbox/Matches link is visible, and
  no password field is visible.
- If not: check, once each — wrong regional site or account; code still
  pending; page still loading; logged in on a different browser.
- After two failed checks, offer takeover or another route.

## Step 3: during the run
- Login page, "session expired", or a new code: save the checkpoint FIRST,
  ask the user to log in again, then resume from the cursor.
- A security check or "unusual activity" page: stop, save, explain in one
  sentence, and let the user deal with it in the browser.

## What is stored
Nothing about the login is stored by the Scout. The browser keeps its own
normal login for the site, as it always does; the Scout never reads or copies it.

## Before the person walks away
After login and the one-profile check, tell them how long the scan will take
(`scan-start`) and that they can close Muse or step away. If the site later
logs them out mid-scan, save the checkpoint and leave one sentence for when
they are back: "The site logged you out after 12 profiles - log in again and
say 'carry on'."
