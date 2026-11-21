# File reading

Use when the user gives profiles outside the website. Every file becomes the
same extraction schema and is scored in the same report. Record the file name
(and row) in `source_detail`, `source: "file"`.

| Input | How |
|---|---|
| Biodata PDF / Word / text | Read the text; DOB → age; extract every schema field you can see. Scanned PDFs: read the page images with vision. |
| Profile screenshot | Read only the visible TEXT with vision. Fields cut off or blurred are null. Never describe, judge or compare the photo or face. |
| Chat export (e.g. WhatsApp .txt) | Find the two people, count messages, who started / wrote last, topics, open questions, red flags → `chat`. Match it to an existing profile by name if you can. Never copy the export. |
| Broker spreadsheet (CSV / Excel) | One row = one person. Map columns to fields; keep the row number; tell the user which columns you could not map. Never copy phone or email columns. |
| Terminal captures | See below. |

`scout.py --data-dir <D> read-files <folder>` does all of this except
screenshots and scanned PDFs, and returns records you can check and `ingest`.
In the terminal, the user drops files in `<D>/files_to_read/` and says
"read my files".

## The terminal's captured pages
After a terminal scan, `<D>/captures/<run-id>/` holds:
- `index.json` — site, run ID, and the URL of every saved page
- `list_matches_1.txt`, `list_search_1.txt`, `list_interests_received_1.txt` —
  page text of list pages
- `list_chats_1.txt` — inbox NAMES AND LINKS ONLY (chat text is never saved)
- `profile_<id>.txt` — page text of each profile read (first line `URL: …`)
The same profiles are already in `profiles.json`; read the captures when the
user wants you to double-check or enrich what the terminal extracted.

Rules:
- One file with several people → one record each; confirm the count first.
- The store dedupes the same person across files and the site.
- Supplied files are the user's data: keep results in the data folder only.
