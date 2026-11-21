# Shaadi.com playbook

Status: written from the site's public navigation labels; **verify on the
first run** with the calibration step (site_learning.md steps 1–5). Sites
redesign often — if a label below is missing, map it fresh and note the change
in the checkpoint. Do not rely on exact URLs; follow the links on the page.

## Open and log in
- Open `https://www.shaadi.com` (regional sites exist — use the one the user
  normally uses). The user logs in themselves; a phone OTP is common.
- "Sign in with Google" is refused by Google in program-controlled browsers
  ("This browser or app may not be secure"). Tell the user to use mobile
  number + OTP or email + password instead. Never try to get around Google's check.
- After login Shaadi may move to a subdomain (for example my.shaadi.com) — that
  is still the site.
- Logged in when the top navigation shows the user's matches and inbox and no
  login form is visible.

## Where the sources usually are
- Chats / messages: the Inbox area, or the chat panel. Open one thread at a
  time; use the thread's link to the person's full profile.
- Interests received: Inbox → Received (pending invitations). Read only —
  never press Accept or Decline.
- Matches: Matches area (new / today's / my matches lists).
- Search: Search results from the user's saved search. Do not change the
  user's saved search filters.

## Profile page — field map to confirm at calibration
Summary line near the name (age, height, city), then sections such as About,
Basic / Personal details, Religious background (religion, community, mother
tongue), Family details, Education & Career (education, profession, employer,
income if shown), Lifestyle (diet, smoking, drinking), Location, Partner
preferences, and an Astro / horoscope section that may be hidden or need a
click. Fields marked hidden or "visible on request" are unknown, never guessed.

## Watch for
- Premium-only fields: record as not shown.
- Pop-ups offering upgrades: close them, never purchase.
- Contact details (phone/email): never extract or store them.
- Limits on profile views: stop at the user's cap; if the site says the daily
  limit is reached, stop and save.
