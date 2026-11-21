# Changelog

## 0.3.6 — 2026-11-20
- First-run welcome: right after install (status `first_run`), Muse opens with a
  crisp ten-line summary of what the Scout can do (`welcome`), in the person's
  language, then starts the five questions; "what can you do?" shows it again
- README install section shows the welcome; START-HERE mentions it
- 65 tests

## 0.3.5 — 2026-11-20
- Call summaries: new `add-call <id> <file> --consent notes-only|recorded-with-consent`
  saves a short summary (600 characters max) with green flags, red flags,
  promises, contradictions and topics; transcripts and audio are refused.
  Call red flags cap the score at 40 and show in "Need your attention"; a new
  call marks the profile Updated; Excel and the full report show calls
- Consent rules for Muse (references/call_notes.md): never listen live; ask
  whether the other person agreed before using a recording; delete audio and
  transcripts; no voice, tone or lie-detection judgements
- After every report Muse adds a call tip that includes the consent warning
  (`call_tip`)
- Languages: Muse talks in the person's language (Telugu, Hindi, Tamil, ...,
  Hinglish) and reads profiles, chats and calls in other languages
- README: new "After a call" section with the compliance warning (California
  Penal Code 632 / 632.7) and iPhone recording steps, and "Talk in your own
  language"; START-HERE and PRIVACY updated
- 64 tests

## 0.3.4 — 2026-11-20
- Excel is the main deliverable: every report attaches the Excel sheet first
  (`report` returns `excel`), with the full report alongside
- WhatsApp: after each report Muse asks "Want me to send this to WhatsApp?";
  if WhatsApp is not connected it prompts the person to connect it; it asks who
  to send to, shows the exact message (`whatsapp_text`, top 3 + "full list in
  the attached Excel sheet") and the attachment, and sends only after a yes
- README rewritten: detailed and colour-coded (badges, coloured callouts,
  colour-coded flow diagrams, 🟢🟡🔴 tables) covering install, first run,
  timing, delivery, WhatsApp, scoring, memory, phrases, privacy, fixes
- The chat message is now a three-part summary - Summary, Match your
  interests (score 60+, no red flag), Need your attention (waiting for your
  reply, red flags, contradictions, changed profiles, things to check) - while
  the attached files stay comprehensive: the Excel sheet gains a "Needs
  attention" column, the full report gains Summary / Matches / Needs-attention
  sections before every profile in detail; WhatsApp message follows the same shape
- PRIVACY.md and START-HERE describe the WhatsApp step
- 63 tests

## 0.3.3 — 2026-11-20
- Reports are delivered in the Muse chat: top 3 as the message, the Excel sheet
  and full report attached (pasted in the chat if attaching is not possible);
  Muse never points the person to a folder or file path
- `report` returns `attach` (files) and `share_text` (a ready-to-forward note);
  sending to family only after the person approves the exact text and recipient
- New `delete-all --confirm` ("delete all my scout data"); refuses folders that
  are not Scout data
- Docs say where data really lives: a private folder in the Muse workspace,
  not "on your laptop"; files are attached in chat instead of dropped in a folder
- 61 tests

## 0.3.2 — 2026-11-20
- Consistency pass: every action SKILL.md and the conversation map mention
  now exists - new `explain`, `seen` (read unseen profiles first for "the
  next 5"), `mark-unavailable` and `forget`; `demo` used for the demo
- Removed terminal-era leftovers (scan queue in the store, captures folder,
  calibration field in status, test helpers); `scan_capture` source renamed
  `page_capture`
- Muse-only release tooling: version now in `VERSION`; the Claude plugin
  manifest and Claude zip are gone; build_release.py checks the README link
  and badge match; PUBLISH.md rewritten
- Run size shown in the interests read-back; data folder added to .gitignore
- 60 tests

## 0.3.1 — 2026-11-20
- Profiles per run: 5 by default, at most 10 per run; more only when the
  person asks (`scan-start --cap N --user-asked`, or a number they saved as
  max_profiles_per_run), and never more than 50
- Muse offers "up to 10" or "the next 5" instead of long runs; docs updated
- 58 tests

## 0.3.0 — 2026-11-20
- Muse only: the terminal (CLI) route is removed - the conversational
  terminal, the Playwright scanner and their tests are gone. scout.py is now
  just the actions Muse calls (memory, scoring, reports, file reading)
- Time estimates: `scan-start` tells the person up front how long a scan will
  take (about 30-60 s per profile) and offers a quick first batch of 5;
  every `ingest` returns progress with time left, switching to the measured
  pace after a few profiles; `scan-progress`, `scan-end` give the rest
- SKILL.md: say the estimate before starting, post "10 of 20 read - about 6
  minutes left" updates, never ask questions after the one-profile check so
  the scan finishes unattended, and lead with the shortlist when it is done
- README and START-HERE rewritten for Muse: start it, log in, check one
  profile, then leave or close the app and come back later
- New reference: conversation_map.md (replaces conversational_terminal.md)
- 57 tests

## 0.2.1 — 2026-11-20
- Login check now requires the browser to be on the matrimony site itself
  (any subdomain, e.g. my.shaadi.com) - a Google error page no longer counts
  as "logged in"; the Scout explains to use mobile OTP or email instead
- Links on subdomains of the site are followed (was: exact host only)
- If a page (Inbox, Matches, ...) cannot be found by its menu name, the Scout
  asks you to click to it in the window, then remembers where it is
- Waits for script-heavy pages to finish loading and scrolls lists before reading;
  recognises Shaadi-style profile IDs in links
- When a page shows no recognisable profiles, saves diagnostics_<page>.txt
  (link texts and addresses only) so the layout can be taught
- Says when it closes the browser window; calibration no longer forgets
  learned page locations
- 78 tests

## 0.2.0 — 2026-11-20
- Terminal is now the complete flow: 5-question intake with read-back,
  "scan" / "open the app" opens a Playwright window with a persistent login,
  waits for Enter, finds Inbox / Interests received / Matches / Search,
  calibrates on ONE profile (with corrections, and learns new labels), then
  reads profiles at a human pace up to a per-run cap (max 50)
- Checkpoint after every profile: a disconnect, closed window or Ctrl+C
  resumes exactly where it stopped; leftovers beyond the cap go first next time
- Rule-based extractor for all schema fields incl. height, income, horoscope;
  chats reduced to summaries (chat page text is never written to disk)
- Scoring: dealbreakers as hard filters; unknown values neutral and flagged,
  never assumed to pass or fail; confidence level; red-flag cap 40; green flags
- Reports: top 3 in plain English, Markdown, Excel (Ranked Matches / Profile
  Details / Updated Since Last Report with before → now); never repeats;
  explains instead of printing an empty report
- Memory: hand edits to interests.json are shown and confirmed (accept or
  undo), never overwritten - including broken edits; interest changes re-score
  stored profiles without browsing; "undo"
- Plain-English requests with or without apostrophes, including "lets start",
  "open the app then", "how can you read the data?", "why is 1 ranked first",
  "pass on 2", "draft a reply to Asha", "read my files", "refine my criteria"
- File intake in the terminal: biodata txt/PDF/Word, chat exports, broker
  CSV/Excel (contact columns never copied), captured pages
- Understands more ways of asking: "run matrimony scout", "check the website",
  "can you open chrome", "mark someone interested", "mark Riya as rejected";
  anything mentioning the site or browser offers to scan instead of a dead end
- Shaadi.com playbook (verify at calibration); updated skill references
- 74 tests incl. a fictional mock matrimony site driven by a real headless
  browser, and a scripted two-day demo transcript (tests/demo_transcript.txt)

## Earlier unreleased notes
- README rewritten: shorter, badges and a flow diagram, install reduced
  to 2 options (command line, or Muse / Claude app UI) with direct
  download links to the zips in this repo instead of the Releases page
- START-HERE now links back to the main README and its install steps
- Terminal: every answer now uses a visible "Response:" prompt, and
  "lets start" (with or without the apostrophe) runs a real 5-question
  Quick Start intake that saves your interests
- Terminal scan: saying "scan" opens the matrimony site in a browser
  window (Playwright, persistent profile so the login is remembered);
  you log in yourself, press Enter in the terminal, and the matches /
  search / inbox pages are captured into your data folder for scoring
- Install is Terminal + Muse only: the Claude.ai option was removed
  at the author's direction (Muse is the route with browser access)

## 0.1.1 — 2026-11-20
- START-HERE guide written for the end user, plus a demo mode on
  fictional profiles
- Quick Start intake: 5 questions before the first run, full criteria
  refined after the first report
- First run defaults: chats only, cap of 20 profiles, top 3 first
- Plain-English per-source permission before reading private sources
- Progress reporting in sentences during scans

## 0.1.0 — 2026-11-20
- First working version: SKILL.md orchestration with 8 reference prompts
- Persistence layer: versioned interests file, dedupe, shared log with
  no-repeat rule, resumable checkpoints, atomic writes with backup
  recovery (13/13 tests)
- Deterministic scoring: hard filters, weighted points, red-flag cap,
  unknowns flagged (6/6 tests)
- Reports generated locally: conversational digest, Markdown, Excel
  with Ranked Matches / Profile Details / Updated sheets
- Conversational terminal in plain English (no commands to learn)
- Generic site playbook with a one-profile calibration step
- File intake: biodata documents, screenshots, chat exports,
  broker spreadsheets
