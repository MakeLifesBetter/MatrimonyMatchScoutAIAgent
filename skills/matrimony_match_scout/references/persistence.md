# Persistence and memory

You have no memory between sessions. The data folder is the memory, and all
access goes through `scripts/state_store.py` (directly, or via `scout.py`).

## Data folder (private, in the Muse workspace, outside the skill folder; default ~/matrimony-scout-data)
The person never needs to open it: reports reach them as chat attachments.
| File | What it is |
|---|---|
| `interests.json` | The user's criteria, versioned. Human-editable. |
| `interests_history.jsonl` | Every change: when, who, why, field diff. |
| `profiles.json` | Every profile ever seen, deduped, with content hash, sources, availability, user verdict, and a copy of what the user last saw. |
| `judgements.json` | AI / rule judgements, kept apart from the hash. |
| `shared_log.jsonl` | Every profile ever shown in a report, with its hash then. |
| `run_state.json` | Checkpoint (phase + cursor), scan progress and timing, calibration per site, interests snapshot, last report ranks, flags. |
| `reports/` | Generated reports (top 3, Markdown, Excel). |
| `files_to_read/` | Files the person attached in chat, saved here for `read-files`. |

## Startup
1. `status`. If `interests_hand_edited` → show the diff and confirm (accept or
   revert). Never overwrite a hand edit silently; saving refuses until confirmed.
   If the file is broken → explain the line; restore only if the user says so
   (the broken copy is kept).
2. Resume a paused scan / checkpoint instead of restarting.
3. If `scores_stale`, `rescore` from saved data — no browsing.

## No-repeat rule
A profile appears in a report only if it was never shown, or its content
changed since it was shown — then it is marked UPDATED with what changed
compared with what the user saw. Volatile fields (last active, online now,
views, source, judgement) never count as a change. Rejected and unavailable
profiles never appear again. Profiles are marked shown only when the report is
actually shown (`report`, not `report --preview`). Each excluded profile is
mentioned in the "left out" count once per interests version.

## Writes
Atomic (temp file, fsync, rename) with a `.bak` of the previous good copy.
A corrupt data file is restored from `.bak` and reported in plain English.
The scan checkpoint is saved after every single profile.

## Deleting
"Forget <name>" (`forget <id>`, after the person confirms) removes that
profile's record; the shown-log keeps a "forgotten" line. "Delete everything" / "start fresh": confirm with the person in plain words
(it cannot be undone), then run `delete-all --confirm`.
