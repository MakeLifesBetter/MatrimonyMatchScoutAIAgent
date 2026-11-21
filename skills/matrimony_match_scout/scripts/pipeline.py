"""
Matrimony Match Scout - glue between the store, scoring and reports.
Used by scout.py, the actions the Muse skill calls.
"""
from collections import Counter
from datetime import datetime

import build_report
from score import score_profile

PRETTY = {"age_min": "youngest age", "age_max": "oldest age", "places": "places",
          "dealbreakers": "dealbreakers", "min_education": "minimum education",
          "religion_must": "religion (must match)", "religion_preferred": "religion (preferred)",
          "community_must": "community (must match)", "community_preferred": "community (preferred)",
          "mother_tongue": "mother tongue", "must_match_tongue": "mother tongue must match",
          "marital_statuses": "marital status accepted", "food_ok": "food that is okay",
          "drinking_ok": "drinking that is okay", "smoking_ok": "smoking that is okay",
          "relocation_needed": "must be open to relocating", "timeline": "marriage timeline",
          "red_flags": "red flags", "green_flags": "green flags",
          "profession_keywords": "professions you like", "good_match_words": "a good match is",
          "height_min_cm": "minimum height (cm)", "height_max_cm": "maximum height (cm)",
          "site": "site", "search_for": "searching for", "max_profiles_per_run": "profiles per scan"}
FIELD_WORDS = {"chat.last_message_by": "who messaged last", "chat.message_count": "number of messages",
               "chat.last_message_summary": "chat", "chat.exists": "chat started",
               "chat.open_questions": "open questions", "chat.red_flags": "chat red flags",
               "income_text": "income", "about_me": "about me", "family_summary": "family",
               "partner_preference_text": "partner preference", "height_text": "height",
               "height_cm": None, "marital_status": "marital status", "mother_tongue": "mother tongue",
               "chat.initiated_by": None}


def _val(v):
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v)
    s = "not shown" if v in (None, "") else str(v).replace("_", " ")
    return s if len(s) <= 60 else s[:57] + "..."


def criteria_summary(c):
    """Plain-English read-back of saved interests."""
    if not c:
        return "nothing saved yet"
    bits = []
    if c.get("site"):
        bits.append(f"site {c['site']}")
    if c.get("search_for"):
        bits.append(f"searching for {c['search_for']}")
    if c.get("age_min") is not None or c.get("age_max") is not None:
        bits.append(f"age {c.get('age_min', 'any')} to {c.get('age_max', 'any')}")
    places = (c.get("places") or []) + (c.get("cities") or []) + (c.get("countries") or [])
    bits.append("places: " + (", ".join(places) if places else "anywhere"))
    bits.append("dealbreakers: " + (", ".join(c.get("dealbreakers") or []) or "none"))
    for key in ("min_education", "religion_must", "religion_preferred", "community_must",
                "community_preferred", "mother_tongue", "marital_statuses", "food_ok",
                "drinking_ok", "smoking_ok", "timeline", "profession_keywords",
                "red_flags", "green_flags", "good_match_words", "height_min_cm", "height_max_cm"):
        v = c.get(key)
        if v not in (None, "", [], False):
            bits.append(f"{PRETTY[key]}: {_val(v)}")
    if c.get("must_match_tongue"):
        bits.append("mother tongue must match")
    if c.get("max_profiles_per_run"):
        bits.append(f"profiles per run: {c['max_profiles_per_run']}")
    if c.get("relocation_needed"):
        bits.append("must be open to relocating")
    return "; ".join(bits)


def _reason_bucket(reason):
    r = reason.lower()
    for word, label in (("age", "age outside your range"), ("lives in", "location not in your places"),
                        ("marital", "marital status"), ("education", "education below your minimum"),
                        ("mother tongue", "mother tongue"), ("religion", "religion"),
                        ("community", "community"), ("height", "height"), ("food", "food"),
                        ("drinking", "drinking"), ("smoking", "smoking")):
        if r.startswith(word):
            return label
    if r.startswith("dealbreaker"):
        return r.split(":")[0].replace("dealbreaker", "your dealbreaker")
    return r.split(":")[0]


def score_all(store, criteria=None):
    """[(record, result)] for every available profile."""
    c = store.criteria() if criteria is None else criteria
    judgements = store.load_judgements()
    out = []
    for pid, rec in store.load_profiles().items():
        if not rec.get("available", True):
            continue
        j = judgements.get(pid)
        if j and j.get("for_hash") == rec.get("hash"):
            res = score_profile(rec["data"], c, qualitative=j["qualitative"], judgement=j["text"])
        else:
            res = score_profile(rec["data"], c)
        out.append((rec, res))
    return out


def chat_status(chat):
    chat = chat or {}
    if not chat.get("exists"):
        return "No chat yet"
    return (chat.get("last_message_summary") or "Chat exists").rstrip(".")


def change_lines(diff):
    lines = []
    chat_changed = False
    for d in diff:
        f = d["field"]
        if f.startswith("chat."):
            chat_changed = True
            continue
        word = FIELD_WORDS.get(f, f.replace("_", " "))
        if word is None:
            continue
        lines.append(f"{word}: {_val(d['from'])} -> {_val(d['to'])}")
    if chat_changed:
        lines.insert(0, "new chat activity")
    return lines


def _row(rec, res, status, diff):
    d = rec["data"]
    horo = d.get("horoscope") or {}
    row = {k: d.get(k) for k in ("name", "age", "height_text", "city", "state", "country",
                                  "education", "education_detail", "profession", "employer",
                                  "income_text", "religion", "community", "mother_tongue",
                                  "marital_status", "food", "drinking", "smoking", "relocate",
                                  "settle_plans", "family_summary", "about_me",
                                  "partner_preference_text", "profile_url")}
    row.update({"profile_id": rec["profile_id"], "status": status, "score": res["score"],
                "confidence": res["confidence"], "why_fit": res["why_fit"], "risks": res["risks"],
                "unknowns": res["unknowns"], "judgement": res["judgement"],
                "next_step": res["next_step"], "chat_status": chat_status(d.get("chat")),
                "horoscope_text": "; ".join(f"{k.replace('_', ' ')} {v}" for k, v in horo.items()),
                "sources": ", ".join(rec.get("sources") or []),
                "changes": change_lines(diff) if status == "Updated" else [],
                "change_rows": diff if status == "Updated" else [],
                "_interested": rec.get("user_status") == "interested",
                "_last_seen": rec.get("last_seen") or ""})
    return row


def report_rows(store):
    """-> (rows, excluded_tally, counts). Only new / changed-since-shown profiles."""
    scored = {rec["profile_id"]: (rec, res) for rec, res in score_all(store)}
    cand = store.digest_candidates()
    told = store.state().get("told_excluded") or {}
    rows, tally, newly_told = [], Counter(), {}
    for status, recs in (("New", cand["new"]), ("Updated", cand["updated"])):
        for rec in recs:
            rec_res = scored.get(rec["profile_id"])
            if not rec_res:
                continue
            _, res = rec_res
            if res["excluded"]:
                key = rec["hash"] + str(store.state().get("interests_version"))
                if told.get(rec["profile_id"]) != key:  # tell about each exclusion once
                    tally[_reason_bucket(res["exclude_reasons"][0])] += 1
                    newly_told[rec["profile_id"]] = key
                continue
            diff = store.diff_since_shown(rec["profile_id"]) if status == "Updated" else []
            rows.append(_row(rec, res, status, diff))
    rows.sort(key=lambda r: (-r["score"], len(r["unknowns"]), not r["_interested"],
                             r["profile_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows, dict(tally), {"profiles": len(scored), "told": newly_told,
                               "candidates": len(cand["new"]) + len(cand["updated"])}


def make_report(store, mark_shown=True):
    """Build the report. Returns a dict with 'status':
    no_profiles | all_excluded | nothing_new | ok."""
    rows, tally, counts = report_rows(store)
    if counts["profiles"] == 0:
        return {"status": "no_profiles"}
    if mark_shown and counts["told"]:
        told = store.state().get("told_excluded") or {}
        told.update(counts["told"])
        store.update_state(told_excluded=told)
    if not rows and tally:
        return {"status": "all_excluded", "excluded": tally}
    if not rows:
        return {"status": "nothing_new", "profiles": counts["profiles"]}
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    n = 1
    while (store.dir / "reports" / stamp).exists():
        n += 1
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S") + f"-{n}"
    out = build_report.build_all(rows, store.dir / "reports" / stamp, excluded=tally,
                                 criteria_summary=criteria_summary(store.criteria()))
    report_id = f"report-{stamp}"
    if mark_shown:
        store.mark_shared([r["profile_id"] for r in rows], report_id)
        store.update_state(last_report={"id": report_id, "at": stamp,
                                        "ranks": {str(r["rank"]): r["profile_id"] for r in rows}})
    return {"status": "ok", "report_id": report_id, "rows": rows, "excluded": tally,
            "new": sum(r["status"] == "New" for r in rows),
            "updated": sum(r["status"] == "Updated" for r in rows), **out}


def rescore(store):
    """Re-score every stored profile from saved data - no browsing."""
    shown = {r["profile_id"] for r in store.shown_log()}
    res = score_all(store)
    passing = [r for r, s in res if not s["excluded"]]
    cand = store.digest_candidates()
    cand_ids = {r["profile_id"] for r in cand["new"] + cand["updated"]}
    newly = [r for r in passing if r["profile_id"] in cand_ids]
    scores = {r["profile_id"]: {"score": s["score"], "excluded": s["excluded"]} for r, s in res}
    store.update_state(scores_stale=False, scores=scores,
                       scored_with_version=store.state().get("interests_version"))
    return {"stored": len(res), "passing": len(passing), "excluded": len(res) - len(passing),
            "ready_to_show": len(newly),
            "shown_before_now_excluded": sum(1 for r, s in res
                                            if s["excluded"] and r["profile_id"] in shown)}
