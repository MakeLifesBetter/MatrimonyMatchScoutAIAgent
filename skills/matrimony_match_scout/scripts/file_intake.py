"""
Matrimony Match Scout - read profiles from files you supply.

Put files in <data-dir>/files_to_read/ (or point at any folder) and say
"read my files" (or run scout.py read-files FOLDER). Supported:
  .txt .md          biodata text, or a chat export (e.g. WhatsApp .txt)
  .pdf              biodata PDF (text PDFs; Muse reads scanned pages with vision)
  .docx             biodata Word file
  .csv .xlsx        broker spreadsheets - one row per person
  .json             records already in the extraction schema
Images (.png/.jpg screenshots) are listed for Muse to read with vision. Nothing is guessed.
Chat exports are reduced to a summary - the export itself is not copied.
"""
import csv
import json
import re
import zipfile
from pathlib import Path

import extract

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".gif"}
COLUMN_ALIASES = {k: v for v, labels in extract.ALIASES.items() for k in labels}
COLUMN_ALIASES.update({"place": "location", "residence": "location", "qualification": "education",
                       "work": "profession", "phone": None, "mobile": None, "contact": None,
                       "email": None, "photo": None})


def _is_chat_export(text):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    hits = sum(1 for ln in lines if extract._TS_PREFIX.match(ln.strip()))
    return hits >= max(2, len(lines) // 2)


def _pdf_text(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception:
        return None


def _docx_text(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception:
        return None
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return re.sub(r"<[^>]+>", "", xml)


def _rows_from_sheet(path):
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    from openpyxl import load_workbook
    ws = load_workbook(path, read_only=True, data_only=True).active
    it = ws.iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(it, [])]
    return [dict(zip(header, ["" if v is None else str(v) for v in row])) for row in it
            if any(v not in (None, "") for v in row)]


def _sheet_records(path):
    rows = _rows_from_sheet(path)
    recs, unmapped = [], set()
    for i, row in enumerate(rows, start=2):
        lines = []
        for col, val in row.items():
            key = extract._norm_label(col or "")
            field = COLUMN_ALIASES.get(key, "?")
            if field is None:
                continue  # contact details are never copied
            if field == "?":
                unmapped.add(col)
                continue
            label = extract.ALIASES[field][0] if field in extract.ALIASES else col
            if val:
                lines.append(f"{label}: {val}")
        rec = extract.extract_profile("\n".join(lines))
        rec.pop("_unreadable", None)
        rec["source"], rec["source_detail"] = "file", f"{path.name} row {i}"
        if rec.get("name") or rec.get("profile_id"):
            recs.append(rec)
    return recs, sorted(c for c in unmapped if c)


def _chat_record(path, text, criteria, store):
    m = re.search(r"chat with (.+?)(?:\.txt)?$", path.stem, re.I)
    other = m.group(1).strip() if m else None
    my_names = [criteria.get("my_name")] if criteria.get("my_name") else []
    chat = extract.parse_chat(text, my_names=my_names, red_flags=criteria.get("red_flags"))
    if not my_names and chat["exists"]:
        senders = {s for s, _ in (extract._MSG.match(extract._TS_PREFIX.sub("", ln.strip())).groups()
                                  for ln in text.splitlines()
                                  if extract._MSG.match(extract._TS_PREFIX.sub("", ln.strip())))}
        if other:
            mine = [s for s in senders if s.lower() != other.lower()]
            if mine:
                chat = extract.parse_chat(text, my_names=mine, red_flags=criteria.get("red_flags"))
    match = None
    if other:
        for pid, rec in store.load_profiles().items():
            if (rec["data"].get("name") or "").lower().startswith(other.lower()):
                match = dict(rec["data"])
                break
    rec = match or dict(extract.empty_record(), name=other)
    rec["chat"] = chat
    rec["source"], rec["source_detail"] = "file", path.name
    return rec


def read_folder(store, folder, criteria=None):
    """-> {"records": [...], "skipped": [(name, why)], "unmapped": {file: [cols]}}"""
    criteria = criteria or {}
    folder = Path(folder).expanduser()
    out = {"records": [], "skipped": [], "unmapped": {}}
    if not folder.exists():
        return out
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        ext = path.suffix.lower()
        if path.name in ("index.json",) or path.name.startswith(("list_", ".")):
            continue
        try:
            if ext in IMAGE_EXT:
                out["skipped"].append((path.name, "a screenshot - Muse reads these with vision"))
                continue
            if ext in (".csv", ".xlsx"):
                recs, unmapped = _sheet_records(path)
                out["records"] += recs
                if unmapped:
                    out["unmapped"][path.name] = unmapped
                continue
            if ext == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                for i, item in enumerate(data if isinstance(data, list) else [data]):
                    item.setdefault("source", "file")
                    item.setdefault("source_detail", f"{path.name} #{i + 1}")
                    out["records"].append(item)
                continue
            if ext == ".pdf":
                text = _pdf_text(path)
            elif ext == ".docx":
                text = _docx_text(path)
            elif ext in (".txt", ".md", ""):
                text = path.read_text(encoding="utf-8", errors="ignore")
            else:
                out["skipped"].append((path.name, "a file type I cannot read here"))
                continue
            if not text or not text.strip():
                out["skipped"].append((path.name, "no readable text (maybe a scanned image)"))
                continue
            if _is_chat_export(text):
                out["records"].append(_chat_record(path, text, criteria, store))
                continue
            url = None
            m = re.match(r"URL:\s*(\S+)", text)
            if m:
                url = m.group(1)
            rec = extract.extract_profile(text, url=url)
            if rec.pop("_unreadable", False):
                out["skipped"].append((path.name, "I could not find a name or profile ID in it"))
                continue
            rec["source"], rec["source_detail"] = ("scan_capture" if url else "file"), path.name
            out["records"].append(rec)
        except Exception as exc:  # one bad file never stops the rest
            out["skipped"].append((path.name, f"could not be opened ({exc.__class__.__name__})"))
    return out
