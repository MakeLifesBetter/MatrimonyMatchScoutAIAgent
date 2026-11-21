# Call notes and call recordings

The person can get a short summary of a call with someone on their list, with
green and red flags, added to that profile. Muse never listens to a live call.

## The two ways in
| Way | What the person sends | Consent value |
|---|---|---|
| Notes (recommended) | After the call, their own words — typed or a voice note: "she asked about my job twice, would not say where she lives…" | `notes-only` |
| Recording | A recording or transcript of the call, **only if the other person agreed to be recorded** | `recorded-with-consent` |

## Compliance — check before analysing anything
- **Ask, every time a recording is sent:** "Did they agree to this call being
  recorded?" Continue only on a clear yes. If no, or unsure: do not listen to,
  read or analyse it; say the file will not be used, delete it, and offer the
  notes route instead.
- Recording a call without everyone's consent is illegal in many places. In
  California every party must consent, including for calls you are on yourself
  (Cal. Penal Code §§ 632, 632.7). Rules differ by country and state — say so
  plainly, and that you are not giving legal advice.
- An iPhone's built-in call recording (iOS 18.1+, some regions) announces itself
  to both people; third-party recorders may not — the announcement does not
  replace asking.
- WhatsApp calls cannot be recorded by the iPhone recorder; with consent, the
  person can switch to a normal call or record on a second device on speaker.

## What to produce (then save with `add-call`)
```json
{"date": "2026-11-21",
 "summary": "One short paragraph in your own words, 600 characters at most.",
 "green_flags": ["answered questions about family openly"],
 "red_flags": ["asked to borrow money for a visa fee"],
 "promises": ["will share horoscope on Sunday"],
 "contradictions": ["said she lives in Austin; profile says Seattle"],
 "topics": ["work", "family", "where to settle"]}
```
`scout.py add-call <profile_id> call.json --consent notes-only|recorded-with-consent`

- Flags come only from what was actually said, with a few words of evidence.
  Use the person's own red / green flag lists first, then the common ones
  (money requests, pressure, secrecy, dodging basic questions, contradictions).
- Patterns: compare with earlier calls and the chat summary for that profile
  ("has postponed meeting the family three times").
- **Never:** judge voice, accent or tone; "lie detection"; psychological or
  medical labels; anything about appearance.
- **Never store** the recording or a transcript. `add-call` refuses them. After
  saving, delete the audio and transcript files and tell the person you did.
- A new call makes the profile show as **Updated** in the next report; call red
  flags cap its score at 40 like chat red flags.
