"""
Matrimony Match Scout - report builder.

Reports are built LOCALLY from saved data; the browser is only a source.
From one list of report rows (see pipeline.report_rows) it writes, into
<data-dir>/reports/<date-time>/:
  digest.txt   the short top-3 message shown in chat
  report.md    full readable report to share with family
  report.xlsx  Excel: Ranked Matches / Profile Details / Updated Since Last Report
Only profiles that are new to you, or changed since you last saw them,
are in a report - the same profile is never shown twice.
"""
from datetime import datetime
from pathlib import Path

RANKED_COLUMNS = [
    ("rank", "Rank"), ("status", "New / Updated"), ("name", "Name"), ("score", "Score"),
    ("confidence", "Confidence"), ("age", "Age"), ("city", "City"), ("country", "Country"),
    ("education", "Education"), ("profession", "Profession"), ("why_fit", "Why it fits"),
    ("risks", "Risky or unknown"), ("judgement", "Judgement"), ("chat_status", "Chat"),
    ("next_step", "Suggested next step"), ("profile_url", "Profile link"),
    ("profile_id", "Profile ID"),
]
DETAIL_COLUMNS = [
    ("profile_id", "Profile ID"), ("name", "Name"), ("age", "Age"), ("height_text", "Height"),
    ("city", "City"), ("state", "State"), ("country", "Country"),
    ("education", "Education"), ("education_detail", "Education detail"),
    ("profession", "Profession"), ("employer", "Employer"), ("income_text", "Income"),
    ("religion", "Religion"), ("community", "Community"), ("mother_tongue", "Mother tongue"),
    ("marital_status", "Marital status"), ("food", "Food"), ("drinking", "Drinking"),
    ("smoking", "Smoking"), ("relocate", "Open to relocate"), ("settle_plans", "Settle plans"),
    ("horoscope_text", "Horoscope"), ("family_summary", "Family"),
    ("about_me", "About me"), ("partner_preference_text", "Partner preference"),
    ("chat_status", "Chat"), ("sources", "Found in"), ("profile_url", "Profile link"),
]


def _join(v):
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v if x)
    return "" if v is None else str(v)


def _pretty(v):
    return _join(v).replace("_", " ") if isinstance(v, str) else _join(v)


def headline(r):
    bits = [r.get("name") or "Name not shown"]
    if r.get("age"):
        bits.append(str(r["age"]))
    if r.get("city") or r.get("country"):
        bits.append(r.get("city") or r.get("country"))
    line = ", ".join(bits)
    if r.get("profession"):
        line += f" - {r['profession']}"
    return line


def build_digest(rows, updated_count=0, excluded_count=0):
    if not rows:
        return "Nothing new since your last report. I did not repeat anyone you have already seen."
    new_count = sum(1 for r in rows if r["status"] == "New")
    n = min(3, len(rows))
    head = (f"Here are your top {n}" if n == 3 else "Here is your match" if n == 1
            else f"Here are your {n} matches")
    head += f" ({new_count} new" + (f", {updated_count} updated" if updated_count else "") + ")"
    lines = [head + ":"]
    for r in rows[:3]:
        tag = " [UPDATED]" if r["status"] == "Updated" else ""
        lines.append(f"{r['rank']}. {headline(r)}.{tag} Score {r['score']}/100 "
                     f"(confidence {r['confidence']}).")
        if r["status"] == "Updated" and r.get("changes"):
            lines.append("   What changed: " + "; ".join(r["changes"][:3]))
        lines.append("   Why it fits: " + (_join(r["why_fit"]) or "passes all your must-haves"))
        lines.append("   Risky or unknown: " + (_join(r["risks"]) or "nothing spotted"))
        lines.append(f"   Chat: {r['chat_status']}. Next: {r['next_step']}.")
    if len(rows) > 3:
        more = len(rows) - 3
        lines.append(f"{more} more {'is' if more == 1 else 'are'} in the full report and Excel sheet.")
    if excluded_count:
        lines.append(f"{excluded_count} profile(s) were left out by your filters or dealbreakers.")
    return "\n".join(lines)


def build_markdown(rows, path, excluded=None, generated=None, criteria_summary=""):
    generated = generated or datetime.now().strftime("%d %b %Y, %H:%M")
    excluded = excluded or {}
    new = [r for r in rows if r["status"] == "New"]
    upd = [r for r in rows if r["status"] == "Updated"]
    L = ["# Matrimony Match Scout - report", "",
         f"_Made on {generated}. Private: share only with family you trust._", "",
         f"**{len(new)} new** and **{len(upd)} updated** profile(s) in this report. "
         "People you have seen before only appear again if their profile or chat changed.", ""]
    if criteria_summary:
        L += [f"**What you asked for:** {criteria_summary}", ""]
    L += ["## Top 3", ""]
    for r in rows[:3]:
        L += [f"### {r['rank']}. {headline(r)}" + (" - UPDATED" if r["status"] == "Updated" else ""),
              f"**Score {r['score']}/100** - confidence {r['confidence']}", "",
              f"- **Why it fits:** {_join(r['why_fit']) or 'passes all your must-haves'}",
              f"- **Risky or unknown:** {_join(r['risks']) or 'nothing spotted'}",
              f"- **Judgement:** {r['judgement']}",
              f"- **Chat:** {r['chat_status']}",
              f"- **Suggested next step:** {r['next_step']}"]
        if r.get("profile_url"):
            L.append(f"- **Profile:** {r['profile_url']}")
        L.append("")
    if rows:
        L += ["## Ranked list", "",
              "| # | Name | Score | Age | City | Education | Profession | New / Updated |",
              "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['rank']} | {r.get('name') or '-'} | {r['score']} | {r.get('age') or '?'} | "
                     f"{r.get('city') or '?'} | {r.get('education') or '?'} | "
                     f"{r.get('profession') or '?'} | {r['status']} |")
        L.append("")
        L += ["## Every profile in this report", ""]
        for r in rows:
            L += [f"### {r['rank']}. {headline(r)} - {r['score']}/100",
                  f"- Height: {r.get('height_text') or 'unknown'}; marital status: "
                  f"{_pretty(r.get('marital_status')) or 'unknown'}; mother tongue: "
                  f"{r.get('mother_tongue') or 'unknown'}",
                  f"- Religion / community: {r.get('religion') or 'unknown'} / "
                  f"{r.get('community') or 'unknown'}",
                  f"- Food / drinking / smoking: {_pretty(r.get('food')) or 'unknown'} / "
                  f"{_pretty(r.get('drinking')) or 'unknown'} / {_pretty(r.get('smoking')) or 'unknown'}",
                  f"- Income: {r.get('income_text') or 'not shown'}",
                  f"- Horoscope: {r.get('horoscope_text') or 'not shown'}",
                  f"- Why it fits: {_join(r['why_fit']) or '-'}",
                  f"- Risky or unknown: {_join(r['risks']) or 'nothing spotted'}",
                  f"- Chat: {r['chat_status']}",
                  f"- About (their words, trimmed): {(r.get('about_me') or 'not shown')[:300]}", ""]
    if upd:
        L += ["## Updated since last report", ""]
        for r in upd:
            L.append(f"- **{r.get('name')}**: " + ("; ".join(r.get("changes") or []) or
                                                   "profile or chat changed"))
        L.append("")
    if excluded:
        L += ["## Left out by your filters", "",
              f"{sum(excluded.values())} profile(s) did not pass your must-haves:", ""]
        for reason, n in sorted(excluded.items(), key=lambda kv: -kv[1]):
            L.append(f"- {reason}: {n}")
        L.append("")
    L += ["## How to read this", "",
          "- **Score** = up to 80 points for how well the profile matches what you set, plus up to "
          "20 for the judgement. Any red flag from your list caps the score at 40.",
          "- **Unknown** means the profile does not show it. Unknowns never count for or against "
          "anyone - please check them yourself.",
          "- **Confidence** says how much of what you care about the profile actually shows.",
          "- Nothing was sent, accepted or rejected on the site. The Scout only reads.", ""]
    Path(path).write_text("\n".join(L), encoding="utf-8")


def build_excel(rows, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="7A2E4D")
    wrap = Alignment(wrap_text=True, vertical="top")

    def sheet(ws, columns, data, widths):
        ws.append([label for _, label in columns])
        for cell in ws[1]:
            cell.font, cell.fill = head_font, head_fill
        for item in data:
            ws.append([_join(item.get(k)) if isinstance(item.get(k), (list, tuple))
                       else item.get(k) for k, _ in columns])
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = wrap
        ws.freeze_panes = "A2"
        if data:
            ws.auto_filter.ref = ws.dimensions
        for i, (k, _) in enumerate(columns, start=1):
            ws.column_dimensions[get_column_letter(i)].width = widths.get(k, 16)

    wb = Workbook()
    ws = wb.active
    ws.title = "Ranked Matches"
    sheet(ws, RANKED_COLUMNS, rows, {"why_fit": 45, "risks": 50, "judgement": 40,
                                      "chat_status": 34, "next_step": 30, "profile_url": 34,
                                      "name": 20, "rank": 6, "score": 8, "age": 6})
    sheet(wb.create_sheet("Profile Details"), DETAIL_COLUMNS, rows,
          {"about_me": 60, "family_summary": 40, "partner_preference_text": 40,
           "chat_status": 34, "profile_url": 34, "horoscope_text": 30})
    changes = []
    for r in rows:
        if r["status"] != "Updated":
            continue
        for d in r.get("change_rows") or [{"field": "profile or chat", "from": "", "to": "changed"}]:
            changes.append({"name": r.get("name"), "profile_id": r.get("profile_id"),
                            "field": d["field"], "from": _join(d.get("from")),
                            "to": _join(d.get("to"))})
    sheet(wb.create_sheet("Updated Since Last Report"),
          [("name", "Name"), ("profile_id", "Profile ID"), ("field", "What changed"),
           ("from", "Before"), ("to", "Now")], changes,
          {"name": 20, "field": 26, "from": 40, "to": 40})
    wb.save(path)


def build_all(rows, out_dir, excluded=None, updated_count=None, criteria_summary=""):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    upd = sum(1 for r in rows if r["status"] == "Updated") if updated_count is None else updated_count
    digest = build_digest(rows, upd, sum((excluded or {}).values()))
    (out / "digest.txt").write_text(digest, encoding="utf-8")
    build_markdown(rows, out / "report.md", excluded, criteria_summary=criteria_summary)
    build_excel(rows, out / "report.xlsx")
    return {"digest": digest, "markdown": str(out / "report.md"),
            "excel": str(out / "report.xlsx"), "folder": str(out)}
