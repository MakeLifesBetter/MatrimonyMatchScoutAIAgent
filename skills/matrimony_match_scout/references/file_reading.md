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

`scout.py --data-dir <D> read-files <folder>` does all of this except
screenshots and scanned PDFs, and returns records you can check and `ingest`.
Ask the user to put files in `<D>/files_to_read/` (or attach them in chat).

Rules:
- One file with several people → one record each; confirm the count first.
- The store dedupes the same person across files and the site.
- Supplied files are the user's data: keep results in the data folder only.
