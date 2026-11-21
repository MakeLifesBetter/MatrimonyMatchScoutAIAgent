# Tests

All people here are fictional.

```bash
# from the repository root
python3 -m unittest discover -s skills/matrimony_match_scout/tests -v
```

| File | Covers |
|---|---|
| `test_state.py` | memory: find by ID/URL/name, reopen, never shown twice, updated-with-diff, rejected never back, hand edits confirmed (accept / undo / broken), backups, checkpoint, lock |
| `test_extract.py` | page text to schema (3 layouts, DOB, height, horoscope), chats summarised without copying, red-flag evidence |
| `test_score.py` | hard filters and dealbreakers exclude, unknown neutral and flagged, red-flag cap, place aliases, AI judgement, no photo inputs |
| `test_reports.py` | top 3, Markdown, Excel's 3 sheets, empty before any scan, nothing new, updated rows, re-score with no network |
| `test_file_intake.py` | biodata txt/docx/pdf, broker CSV/XLSX, chat export, saved page text, screenshots |
| `test_timing.py` | estimate before a scan, quick-batch offer, time left from the measured pace, updates every 5 profiles |
| `test_internal.py` | the JSON actions Muse calls, end to end (incl. explain, seen, mark-unavailable, forget, run size, call summaries with consent rules) |
