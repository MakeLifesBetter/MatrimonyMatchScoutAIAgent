# Conversation map

The person talks to Muse in plain English. Map what they say to an action,
confirm consequential changes in one sentence, and answer in sentences —
never JSON, file paths or tool names unless they ask.

| They say something like | Action |
|---|---|
| "run matrimony scout", "lets start", "help me find matches" | Start: `status`, then intake if no interests (SKILL.md 0–1) |
| "scan", "check my chats", "open shaadi", "find new matches", "carry on" | Login → one-profile check → `scan-start` estimate → unattended scan |
| "how long will this take?", "how much is left?" | `scan-start` estimate before; `scan-progress` during |
| "just do a few", "quick one" | `scan-start` (default 5) |
| "read 10 this time", "do 8" | `scan-start --cap N` (up to 10) |
| "read 25", "do all my matches", "more than 10" | `scan-start --cap N --user-asked` (max 50) |
| "read the next 5", "keep going" | Another run from the checkpoint/backlog, same rules |
| "always do 20" | Save `max_profiles_per_run: 20`, then scan |
| "give me the report", "show my matches", "excel sheet", "top 3" | `report` (explain if empty / nothing new) |
| "how do you read my data?", "is my data safe?" | Own login in the browser, read-only, summaries only, one local folder |
| "change my age range to 26 to 30", "add Pune", "my dealbreaker is smoking" | New interests version, read back, `rescore` (no browsing) |
| "refine my criteria", "ask me more" | Fuller intake using real profiles as examples |
| "check status" | Interests version, profiles seen / shown / passed, paused scan |
| "what did you show me before" | `history` |
| "pass on 2", "not interested in Divya" | `set-status <id> rejected` (Scout notes only — nothing sent) |
| "interested in Asha", "I like the first one" | `set-status <id> interested` |
| "why is 1 ranked first" | Explain points, judgement, risks from the report |
| "draft a reply to Asha" | Draft only; send only after they approve the exact text |
| "read my files" + attachments | `read-files` / vision for screenshots, then `ingest` |
| "show me a demo" | `demo` (fictional profiles) |
| "stop" | Save the checkpoint, say where it stopped, offer to carry on later |

Rules:
- A number means the rank in the last report; a name matches the start of a
  name; two matches → ask which one.
- During an unattended scan, never ask questions — note uncertainties in the report.
- Errors are one plain sentence with the next step.
