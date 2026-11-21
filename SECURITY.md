# Security

## Design rules
- You always log in yourself. Credentials never pass through chat, the skill
  files, the scripts or the data folder.
- Browsing is human-paced (one profile at a time), read-only, capped
  per run (5 by default, at most 10 unless you ask for more, never more than 50), first two list pages per source. The Scout
  stops on any security check, warning or block page.
- Muse drives the browser; the Scout's scripts only keep memory, score and
  write reports. They use the Python standard library plus `openpyxl` (Excel)
  and optionally `pypdf`. State files are
  written atomically with a backup copy.
- Page and file content is data, never instructions. A profile or chat
  message can never redirect the Scout.

## Installing skills safely
A skill is instructions plus scripts an AI runs with your permissions. Read
`SKILL.md` and the scripts before installing — this repository is public so
anyone can.

## Reporting a problem
Open a GitHub issue. Never include real profiles, chats, credentials or
screenshots of private accounts — remove names and IDs first.
