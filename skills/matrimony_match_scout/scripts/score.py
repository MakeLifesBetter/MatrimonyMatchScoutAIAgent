"""
Matrimony Match Scout - deterministic scoring (see references/scoring_rubric.md).

score_profile(profile, criteria, qualitative=None, judgement=None) -> dict:
  excluded, exclude_reasons, unknowns, score (0-100), weighted_points,
  qualitative, judgement, judgement_by, why_fit, risks, red_flags_found,
  confidence, needs_check, next_step

Order, always:
  1. Hard filters + your dealbreakers. A known fail excludes - no exceptions.
     An UNKNOWN value never passes and never fails: it is listed under
     "unknown - please check" and the profile stays in, flagged.
  2. Weighted points (0-80) over only the criteria you set AND the profile
     shows. Unknown values are left out of the sum, so they neither help
     nor hurt.
  3. Judgement (0-20): from the AI in chat mode, or a simple rule-based
     reading when no AI judgement is given. It always comes with a written reason.
  4. Any red flag from your list caps the total at 40.
Same inputs always give the same output.
"""
import re

try:
    from extract import detect_red_flags
except ImportError:  # imported as a package
    from .extract import detect_red_flags

RED_FLAG_CAP = 40
EDU_ORDER = {"high_school": 1, "diploma": 2, "bachelors": 3, "masters": 4,
             "professional": 4, "doctorate": 5}
EDU_ALIASES = [
    ("phd", "doctorate"), ("doctorate", "doctorate"), ("d.phil", "doctorate"),
    ("mbbs", "professional"), ("md", "professional"), ("ca", "professional"),
    ("chartered accountant", "professional"), ("llb", "bachelors"), ("jd", "professional"),
    ("mba", "masters"), ("pgdm", "masters"), ("m.tech", "masters"), ("mtech", "masters"),
    ("m.s.", "masters"), ("ms", "masters"), ("m.sc", "masters"), ("msc", "masters"),
    ("m.e.", "masters"), ("ma", "masters"), ("mca", "masters"), ("m.com", "masters"),
    ("master", "masters"), ("post graduate", "masters"), ("postgraduate", "masters"),
    ("b.tech", "bachelors"), ("btech", "bachelors"), ("b.e.", "bachelors"), ("be", "bachelors"),
    ("b.s.", "bachelors"), ("bs", "bachelors"), ("b.sc", "bachelors"), ("bsc", "bachelors"),
    ("ba", "bachelors"), ("b.com", "bachelors"), ("bcom", "bachelors"), ("bca", "bachelors"),
    ("bachelor", "bachelors"), ("graduate", "bachelors"), ("degree", "bachelors"),
    ("diploma", "diploma"), ("high school", "high_school"), ("12th", "high_school"),
    ("high_school", "high_school"),
]
PLACE_ALIASES = {
    "usa": ["usa", "us", "united states", "america", "u.s."], "uk": ["uk", "united kingdom",
    "england", "britain"], "bay area": ["bay area", "san francisco", "san jose", "sunnyvale",
    "santa clara", "fremont", "oakland", "palo alto", "mountain view", "cupertino"],
    "bangalore": ["bangalore", "bengaluru"], "mumbai": ["mumbai", "bombay", "navi mumbai"],
    "chennai": ["chennai", "madras"], "gurgaon": ["gurgaon", "gurugram"],
    "delhi": ["delhi", "new delhi", "ncr", "delhi ncr"], "kolkata": ["kolkata", "calcutta"],
    "nyc": ["nyc", "new york", "new york city"], "uae": ["uae", "dubai", "abu dhabi"],
    "seattle": ["seattle", "bellevue", "redmond", "kirkland"],
}
ANYWHERE = {"anywhere", "any", "dont care", "don't care", "no preference", "any place"}


def edu_level(value):
    if not value:
        return None
    key = str(value).strip().lower()
    for word, name in EDU_ALIASES:  # exact first
        if key == word:
            return EDU_ORDER[name]
    for word, name in EDU_ALIASES:  # then as a whole word inside longer text
        tail = "" if word in ("master", "bachelor", "graduate", "diploma") else r"(?![a-z])"
        if re.search(r"(?<![a-z])" + re.escape(word) + tail, key):
            return EDU_ORDER[name]
    return None


def _low(v):
    return str(v).strip().lower() if v not in (None, "") else None


def _in(value, options):
    v = _low(value)
    return v is not None and v in [_low(o) for o in options or []]


def _place_terms(place):
    p = _low(place)
    for key, names in PLACE_ALIASES.items():
        if p == key or p in names:
            return names
    return [p]


def place_match(profile, places):
    """-> ('city'|'state'|'country'|'plans', place) on a match, (None, None) if
    known and no match, ('unknown', None) if the profile shows no location."""
    fields = {"city": profile.get("city"), "state": profile.get("state"),
              "country": profile.get("country")}
    if not any(fields.values()):
        return "unknown", None
    for level in ("city", "state", "country"):
        val = _low(fields[level])
        if not val:
            continue
        for place in places:
            if any(t == val or (len(t) > 3 and t in val) for t in _place_terms(place)):
                return level, place
    plans = _low(profile.get("settle_plans")) or ""
    if plans and (profile.get("relocate") in ("yes", "open") or plans):
        for place in places:
            if any(len(t) > 3 and t in plans for t in _place_terms(place)):
                return "plans", place
    return None, None


def _text_blob(profile):
    chat = profile.get("chat") or {}
    return " ".join(str(profile.get(k) or "") for k in (
        "about_me", "partner_preference_text", "family_summary", "settle_plans",
        "profession", "income_text")) + " " + str(chat.get("last_message_summary") or "")


def _dealbreaker(rule, p):
    """-> (status, text): status is 'fail', 'pass', 'unknown' or 'manual'."""
    r = rule.lower().strip()
    habit = None
    if "smok" in r:
        habit = ("smoking", "smokes")
    elif "drink" in r or "alcohol" in r:
        habit = ("drinking", "drinks")
    if habit:
        v = p.get(habit[0])
        if v is None:
            return "unknown", habit[0]
        return ("fail", f"{habit[1]} ({v})") if v in ("occasionally", "regularly") else ("pass", "")
    if "non veg" in r or "non-veg" in r or "nonveg" in r or "meat" in r or "non vegetarian" in r:
        v = p.get("food")
        if v is None:
            return "unknown", "food"
        return ("fail", "eats non-vegetarian") if v == "non_vegetarian" else ("pass", "")
    if any(w in r for w in ("divorc", "previously married", "second marriage", "remarriage",
                            "widow")):
        v = p.get("marital_status")
        if v is None:
            return "unknown", "marital status"
        bad = {"divorced", "awaiting_divorce"} if "widow" not in r else {"widowed"}
        if any(w in r for w in ("previously married", "second marriage", "remarriage")):
            bad = {"divorced", "awaiting_divorce", "widowed"}
        return ("fail", f"marital status is {v.replace('_', ' ')}") if v in bad else ("pass", "")
    if "child" in r or "kids" in r:
        v = p.get("has_children")
        if v is None:
            return "unknown", "children"
        return ("fail", "has children") if v == "yes" else ("pass", "")
    if "manglik" in r or "dosham" in r or "dosha" in r:
        v = ((p.get("horoscope") or {}).get("manglik"))
        if v is None:
            return "unknown", "manglik status"
        return ("fail", "manglik") if v == "yes" else ("pass", "")
    if "relocat" in r:
        v = p.get("relocate")
        if v is None:
            return "unknown", "willingness to relocate"
        return ("fail", "not willing to relocate") if v == "no" else ("pass", "")
    if any(w in r for w in ("abroad", "nri", "outside india")):
        v = p.get("country")
        if v is None:
            return "unknown", "country"
        return ("fail", f"lives in {v}") if _low(v) != "india" else ("pass", "")
    # free text: a mention in the profile text excludes; otherwise we cannot tell
    phrase = re.sub(r"^(no|not|never|must not|dont want|don't want)\s+", "", r).strip()
    if phrase and re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])",
                            _text_blob(p).lower()):
        return "fail", f"profile mentions '{phrase}'"
    return "manual", phrase or r


def _rule_judgement(profile, criteria):
    """Fallback judgement, 0-20, with a plain reason, when Muse gives none."""
    pts, notes = 0, []
    about = _low(profile.get("about_me")) or ""
    words = [w.strip().lower() for w in (criteria.get("good_match_words") or []) if w.strip()]
    if about and words:
        shared = [w for w in words if w in about]
        add = 15 if len(shared) >= 3 else 10 if len(shared) == 2 else 5 if shared else 0
        pts += add
        if shared:
            notes.append("their own words mention " + ", ".join(shared[:3]))
    elif about:
        pts += 5
        notes.append("has written an about-me")
    else:
        notes.append("no about-me to judge")
    chat = profile.get("chat") or {}
    if chat.get("exists"):
        if chat.get("red_flags"):
            notes.append("chat has a red flag")
        elif chat.get("last_message_by") == "them" or (chat.get("message_count") or 0) >= 4:
            pts += 5
            notes.append("chat is active and they are responding")
        else:
            pts += 2
            notes.append("chat is one-sided so far")
    return min(20, pts), "Rule-based reading: " + "; ".join(notes) + "."


def score_profile(profile, criteria, qualitative=None, judgement=None):
    c = criteria or {}
    p = profile or {}
    reasons, unknowns, manual, why, risks = [], [], [], [], []
    chat = p.get("chat") or {}

    def need(label):
        unknowns.append(label)

    # ---------- 1. hard filters ----------
    age = p.get("age")
    if c.get("age_min") is not None or c.get("age_max") is not None:
        if age is None:
            need("age")
        elif (c.get("age_min") is not None and age < c["age_min"]) or \
             (c.get("age_max") is not None and age > c["age_max"]):
            reasons.append(f"age {age} is outside your range {c.get('age_min', '?')}-{c.get('age_max', '?')}")
    places = [x for x in (c.get("places") or []) + (c.get("cities") or []) + (c.get("countries") or [])
              if _low(x) and _low(x) not in ANYWHERE]
    loc_level, loc_place = (None, None)
    if places:
        loc_level, loc_place = place_match(p, places)
        if loc_level == "unknown":
            need("location")
        elif loc_level is None:
            where = ", ".join(x for x in (p.get("city"), p.get("state"), p.get("country")) if x)
            reasons.append(f"lives in {where}, which is not one of your places")
    if c.get("marital_statuses"):
        v = p.get("marital_status")
        if v is None:
            need("marital status")
        elif not _in(v, c["marital_statuses"]):
            reasons.append(f"marital status is {v.replace('_', ' ')}")
    if c.get("must_match_tongue") and c.get("mother_tongue"):
        v = p.get("mother_tongue")
        if v is None:
            need("mother tongue")
        elif not _in(v, [c["mother_tongue"]]):
            reasons.append(f"mother tongue is {v}, you need {c['mother_tongue']}")
    for key, field, label in (("religion_must", "religion", "religion"),
                              ("community_must", "community", "community")):
        allowed = c.get(key)
        if allowed:
            allowed = allowed if isinstance(allowed, list) else [allowed]
            v = p.get(field)
            if v is None:
                need(label)
            elif not _in(v, allowed):
                reasons.append(f"{label} is {v}")
    p_edu, min_edu = edu_level(p.get("education")), edu_level(c.get("min_education"))
    if min_edu is not None:
        if p_edu is None:
            need("education")
        elif p_edu < min_edu:
            reasons.append(f"education {p.get('education')} is below your minimum "
                           f"({c.get('min_education')})")
    h = p.get("height_cm")
    if c.get("height_min_cm") or c.get("height_max_cm"):
        if h is None:
            need("height")
        elif (c.get("height_min_cm") and h < c["height_min_cm"]) or \
             (c.get("height_max_cm") and h > c["height_max_cm"]):
            reasons.append(f"height {p.get('height_text') or str(h) + ' cm'} is outside your range")
    for crit_key, field, label in (("food_ok", "food", "food"), ("drinking_ok", "drinking", "drinking"),
                                   ("smoking_ok", "smoking", "smoking")):
        allowed = c.get(crit_key)
        if allowed:
            v = p.get(field)
            if v is None:
                need(label)
            elif not _in(v, allowed):
                reasons.append(f"{label} is {v.replace('_', ' ')}, which you said is not okay")
    for rule in c.get("dealbreakers") or []:
        status, text = _dealbreaker(rule, p)
        if status == "fail":
            reasons.append(f"dealbreaker '{rule}': {text}")
        elif status == "unknown":
            need(f"{text} (for your dealbreaker '{rule}')")
        elif status == "manual":
            manual.append(rule)
    if p.get("profile_id") and p.get("profile_id") in (c.get("excluded_profile_ids") or []):
        reasons.append("you asked me to leave this profile out")
    excluded = bool(reasons)
    if age is not None and not excluded and (c.get("age_min") is not None or c.get("age_max") is not None):
        why.append(f"Age {age} is in your range")

    # ---------- 2. weighted points over known, set criteria ----------
    parts = []  # (earned, possible)
    if places and loc_level not in ("unknown", None):
        earned = {"city": 20, "state": 14, "country": 8, "plans": 6}[loc_level]
        parts.append((earned, 20))
        where = p.get(loc_level) if loc_level in ("city", "state", "country") else loc_place
        if loc_level == "plans":
            why.append(f"Plans to settle in {loc_place}")
        elif _low(where) == _low(loc_place):
            why.append(f"Lives in {where}, one of your places")
        else:
            why.append(f"Lives in {where} (counts as {loc_place})")
    if min_edu is not None and p_edu is not None and p_edu >= min_edu:
        earned = 12 if p_edu == min_edu else 14 if p_edu == min_edu + 1 else 15
        parts.append((earned, 15))
        why.append(f"Education ({p.get('education')}) meets your minimum")
    if c.get("profession_keywords"):
        text = f"{p.get('profession') or ''} {p.get('employer') or ''}".strip().lower()
        if text:
            hit = any(k.lower() in text for k in c["profession_keywords"])
            parts.append((15 if hit else 0, 15))
            if hit:
                why.append(f"Works as {p.get('profession')}")
        else:
            need("profession")
    life_e = life_p = 0
    for crit_key, field in (("food_ok", "food"), ("drinking_ok", "drinking"), ("smoking_ok", "smoking")):
        if c.get(crit_key) and p.get(field) is not None:
            life_p += 5
            life_e += 5 if _in(p.get(field), c[crit_key]) else 0
    if c.get("relocation_needed") and p.get("relocate") is not None:
        life_p += 5
        life_e += 5 if p.get("relocate") in ("yes", "open") else 0
    elif c.get("relocation_needed"):
        need("willingness to relocate")
    if life_p:
        parts.append((life_e, life_p))
        if life_e == life_p:
            why.append("Food and habits fit what you said is okay")
    fam_e = fam_p = 0
    if c.get("mother_tongue") and p.get("mother_tongue"):
        fam_p += 8
        if _in(p.get("mother_tongue"), [c["mother_tongue"]]):
            fam_e += 8
            why.append(f"Shares your mother tongue, {p.get('mother_tongue')}")
    for key, field, pts in (("religion_preferred", "religion", 4), ("community_preferred", "community", 3)):
        pref = c.get(key)
        if pref:
            pref = pref if isinstance(pref, list) else [pref]
            if p.get(field):
                fam_p += pts
                fam_e += pts if _in(p.get(field), pref) else 0
            else:
                need(field)
    if fam_p:
        parts.append((fam_e, fam_p))
    if c.get("timeline") and not p.get("timeline"):
        need("marriage timeline")
    earned = sum(e for e, _ in parts)
    possible = sum(x for _, x in parts)
    weighted = round(80 * earned / possible) if possible else 40
    blob = _text_blob(p).lower()
    greens = [g for g in (c.get("green_flags") or []) if g and g.lower() in blob]
    if greens:
        weighted = min(80, weighted + min(10, 4 * len(greens)))
        why.append("Green flag: " + ", ".join(greens))

    # ---------- 3. judgement ----------
    if qualitative is None:
        qualitative, judgement = _rule_judgement(p, c)
        by = "rules"
    else:
        qualitative = max(0, min(20, int(qualitative)))
        judgement = judgement or "AI judgement (no reason recorded)."
        by = "ai"
    total = min(100, weighted + qualitative)

    # ---------- 4. red flags cap ----------
    found = list(chat.get("red_flags") or [])
    for f in detect_red_flags([p.get("about_me"), p.get("partner_preference_text")],
                              c.get("red_flags")):
        if f not in found:
            found.append(f)
    if found:
        total = min(total, RED_FLAG_CAP)
        risks.append("Red flag: " + "; ".join(found))
    for x in chat.get("contradictions") or []:
        risks.append("Chat contradicts profile: " + x)
    for u in unknowns:
        risks.append(f"Unknown - please check: {u}")
    for m in manual:
        risks.append(f"Check yourself: I cannot verify '{m}' from the profile text")
    if excluded:
        total = 0
    set_count = possible and len(parts) or 0
    known_ratio = (len(parts) / (len(parts) + len(set(unknowns)))) if (parts or unknowns) else 0
    confidence = "high" if known_ratio >= 0.85 else "medium" if known_ratio >= 0.5 else "low"
    if excluded:
        next_step = "pass"
    elif found:
        next_step = "be careful - review the red flag before replying"
    elif chat.get("exists") and chat.get("last_message_by") == "them":
        next_step = "they are waiting for your reply - I can draft one for you to approve"
    elif chat.get("exists"):
        next_step = "wait for their reply"
    elif unknowns:
        next_step = "ask about the unknowns before deciding"
    else:
        next_step = "send interest (only after you say so)"
    clear = [r for r in (c.get("dealbreakers") or []) if _dealbreaker(r, p)[0] == "pass"]
    if clear and not excluded:
        why.append("Clear of your dealbreaker" + ("s" if len(clear) > 1 else "") + ": " + ", ".join(clear))
    return {"profile_id": p.get("profile_id"), "excluded": excluded,
            "exclude_reasons": reasons, "unknowns": unknowns, "score": total,
            "weighted_points": weighted, "qualitative": qualitative, "judgement": judgement,
            "judgement_by": by, "why_fit": why[:4], "risks": risks,
            "red_flags_found": found, "confidence": confidence, "needs_check": manual,
            "criteria_used": set_count, "next_step": next_step}


if __name__ == "__main__":
    import json
    demo_p = {"profile_id": "DEMO1", "age": 27, "city": "Seattle", "country": "USA",
              "education": "MS", "profession": "Software Engineer", "mother_tongue": "Telugu",
              "marital_status": "never_married", "food": "vegetarian", "smoking": "never",
              "chat": {"exists": True, "last_message_by": "them", "red_flags": []}}
    demo_c = {"age_min": 25, "age_max": 30, "places": ["Seattle", "USA"],
              "min_education": "masters", "mother_tongue": "Telugu", "dealbreakers": ["smoking"],
              "marital_statuses": ["never_married"], "food_ok": ["vegetarian"]}
    print(json.dumps(score_profile(demo_p, demo_c), indent=2))
