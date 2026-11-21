# Tests

All people and sites here are fictional.

```bash
# from the repository root
python3 -m unittest discover -s skills/matrimony_match_scout/tests -v
# scripted two-day terminal demo against the mock site -> tests/demo_transcript.txt
python3 skills/matrimony_match_scout/tests/run_scripted_demo.py
# try the mock site by hand (any username/password - it is fake)
python3 skills/matrimony_match_scout/tests/mock_site.py
```

| File | Covers |
|---|---|
| `test_state.py` | memory: reopen, never shown twice, updated-with-diff, rejected never back, hand edits confirmed (accept / undo / broken), backups, checkpoint, lock |
| `test_extract.py` | page text to schema (3 layouts, DOB, height, horoscope), chats summarised without copying, red-flag evidence |
| `test_score.py` | hard filters and dealbreakers exclude, unknown neutral and flagged, red-flag cap, place aliases, AI judgement, no photo inputs |
| `test_reports.py` | top 3, Markdown, Excel's 3 sheets, empty-before-scan, nothing new, updated rows, re-score without browsing |
| `test_file_intake.py` | biodata txt/docx/pdf, broker CSV/XLSX, chat export, screenshots, captures |
| `test_browser_scan.py` | real headless browser on the mock site: user logs in, calibration, cap, pace, read-only, resume after disconnect, updates, security check, failures |
| `test_terminal.py` | scripted terminal sessions with messy input ("lets start", "open the app then", "how can you read the data?") |
| `test_internal.py` | JSON actions used by the AI chat skill |

Browser tests skip themselves if Playwright is not installed.
