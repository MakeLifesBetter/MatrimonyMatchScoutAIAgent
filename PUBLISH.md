# Publishing this repo (for the author — not part of the public docs)

Prepared locally on 2026-11-20 with a first git commit. The GitHub CLI
on this machine is not logged in, and publishing needs the author's own
GitHub account, so the push itself is a manual 5-minute step:

## Option A — GitHub CLI (fastest)
```
cd ~/workspace/matrimony-match-scout/github-repo
gh auth login
gh repo create matrimony-match-scout --public --source . --push
```

## Option B — website + git
1. On github.com, create a new public repository named
   `matrimony-match-scout`. Do NOT add a README or .gitignore there.
2. Then:
```
cd ~/workspace/matrimony-match-scout/github-repo
git remote add origin https://github.com/<your-github-username>/matrimony-match-scout.git
git push -u origin main
```

## After the first push
1. Replace `<your-github-username>` in README.md (Claude Code section).
2. Build the release zips: `python3 tools/build_release.py`
3. Create a GitHub Release tagged `v0.3.0` and attach both zips from
   `dist/` (the Muse zip and the Claude zip). The README install steps
   link to the latest release.
4. Licence is settled: all rights reserved (see LICENSING.md). Do NOT
   add a LICENSE file.
5. Validate the Claude plugin before announcing the Claude Code route:
   `claude plugin validate .` (needs Claude Code installed).
6. Delete this PUBLISH.md from the published repo, or keep it — it
   contains no secrets, only steps.

## Sharing link
Share the repo link, or better the Releases page, on WhatsApp and
social posts. People download the zip from Releases; nobody needs git.
