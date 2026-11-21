"""
Matrimony Match Scout - rule-based extraction (stdlib only).

  extract_profile(text, url=None, heading=None, extra_aliases=None) -> record
  parse_chat(text, my_names=None, red_flags=None) -> chat state (summary only)
  detect_red_flags(texts, red_flags) -> ["asks for money (mentions 'gift card')", ...]

Works on the visible text of a profile page (what a browser's innerText
gives), a biodata text file, or a chat export. Fields the text does not
show stay None. Nothing is guessed. Chats are reduced to counts, who
wrote last, topics and flags - the message text itself is never returned.

The AI chat layer may use this as a first pass and correct it; the
terminal uses it as-is, after the user confirms one calibration profile.
"""
import re
from datetime import date
from urllib.parse import urlparse, parse_qs

MAX_ABOUT = 800

# label (normalised) -> schema field
ALIASES = {
    "name": ["name", "full name", "profile name"],
    "profile_id": ["profile id", "profile no", "profile number", "id"],
    "age": ["age"],
    "date_of_birth": ["date of birth", "dob", "birth date", "born on"],
    "height_text": ["height"],
    "location": ["lives in", "location", "current location", "residing in", "living in",
                 "based in"],
    "city": ["city", "current city", "residing city"],
    "state": ["state", "residing state"],
    "country": ["country", "country living in", "residing country"],
    "marital_status": ["marital status"],
    "mother_tongue": ["mother tongue", "language", "native language"],
    "religion": ["religion"],
    "community": ["community", "caste", "caste / community", "sub caste", "sub-community"],
    "education": ["education", "highest education", "qualification", "highest qualification",
                  "degree"],
    "education_detail": ["college", "university", "education details", "institution"],
    "profession": ["profession", "occupation", "works as", "working as", "job"],
    "employer": ["employer", "company", "working with", "works at", "organisation",
                 "organization"],
    "income_text": ["income", "annual income", "salary"],
    "food": ["diet", "food", "eating habits", "food habits"],
    "drinking": ["drinking", "drink", "drinks", "drinking habits"],
    "smoking": ["smoking", "smoke", "smokes", "smoking habits"],
    "has_children": ["children", "kids", "have children"],
    "relocate": ["willing to relocate", "open to relocate", "relocation", "open to relocation"],
    "settle_plans": ["plans to settle", "settle in", "want to settle", "settling plans"],
    "timeline": ["marriage timeline", "planning to marry", "timeline"],
    "rashi": ["rashi", "moon sign", "raasi", "rasi"],
    "nakshatra": ["nakshatra", "star", "birth star", "nakshatram"],
    "manglik": ["manglik", "manglik status", "chevvai dosham", "mangal dosha", "dosham"],
    "gothra": ["gothra", "gotra", "gothram"],
    "birth_time": ["time of birth", "birth time"],
    "birth_place": ["place of birth", "birth place"],
    "about_me": ["about me", "about her", "about him", "about", "in my own words",
                 "a few words about me", "about myself"],
    "family_summary": ["family", "about my family", "family details", "family background"],
    "partner_preference_text": ["partner preference", "partner preferences", "looking for",
                                "what i am looking for", "desired partner",
                                "what im looking for"],
}
BLOCK_FIELDS = {"about_me", "family_summary", "partner_preference_text"}
SECTION_HEADINGS = {"basic details", "education & career", "education and career", "lifestyle",
                    "horoscope", "horoscope details", "astro details", "contact", "photos",
                    "background", "family", "partner preference", "about me", "personal details",
                    "location", "career", "send message", "connect", "shortlist", "block",
                    "report profile", "similar profiles", "more profiles", "send interest",
                    "connect now", "accept", "decline", "chat now", "send message", "message",
                    "view contact", "shortlisted"}
HOROSCOPE_FIELDS = ("rashi", "nakshatra", "manglik", "gothra", "birth_time", "birth_place")
COUNTRIES = {"usa": "USA", "us": "USA", "u.s.": "USA", "united states": "USA", "america": "USA",
             "india": "India", "uk": "UK", "united kingdom": "UK", "england": "UK",
             "canada": "Canada", "australia": "Australia", "uae": "UAE", "dubai": "UAE",
             "singapore": "Singapore", "germany": "Germany", "new zealand": "New Zealand",
             "ireland": "Ireland", "netherlands": "Netherlands", "qatar": "Qatar",
             "saudi arabia": "Saudi Arabia", "kuwait": "Kuwait", "malaysia": "Malaysia"}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _norm_label(s):
    s = s.strip().lower().replace("’", "'").replace("'", "")
    s = re.sub(r"[\s:–-]+$", "", s)
    return re.sub(r"\s+", " ", s)


def _label_map(extra_aliases=None):
    m = {}
    for field, labels in ALIASES.items():
        for lab in labels:
            m[_norm_label(lab)] = field
    for lab, field in (extra_aliases or {}).items():
        m[_norm_label(lab)] = field
    return m


def _clean_value(v):
    v = (v or "").strip().strip("|").strip()
    if v.lower() in ("", "-", "--", "n/a", "na", "not specified", "not mentioned",
                     "not shown", "hidden", "will tell later", "ask me", "null", "none given"):
        return None
    return v


# ---------------- normalisers ----------------

def norm_marital(v):
    if not v:
        return None
    s = v.lower()
    if "awaiting" in s or "separated" in s:
        return "awaiting_divorce"
    if "divorc" in s:
        return "divorced"
    if "widow" in s:
        return "widowed"
    if "never" in s or "unmarried" in s or s.strip() in ("single", "bachelor", "spinster"):
        return "never_married"
    return s.strip().replace(" ", "_")


def norm_food(v):
    if not v:
        return None
    s = v.lower().replace("-", " ")
    if "non veg" in s or "nonveg" in s or "non vegetarian" in s or "meat" in s:
        return "non_vegetarian"
    if "egg" in s:
        return "eggetarian"
    if "vegan" in s:
        return "vegan"
    if "jain" in s:
        return "jain"
    if "veg" in s:
        return "vegetarian"
    return s.strip().replace(" ", "_")


def norm_habit(v):
    if not v:
        return None
    s = v.lower()
    if any(w in s for w in ("occasion", "social", "sometimes", "rarely")):
        return "occasionally"
    if any(w in s for w in ("never", "doesn", "does not", "non ", "non-", "don't", "dont")) \
            or s.strip() in ("no", "nil", "none"):
        return "never"
    if any(w in s for w in ("yes", "regular", "daily", "often")):
        return "regularly"
    return s.strip()


def norm_yes_no(v):
    if not v:
        return None
    s = v.lower().strip()
    if s.startswith(("yes", "y ", "open", "willing", "maybe", "flexible", "ok")) or s == "y":
        return "yes" if not s.startswith(("maybe", "flexible", "open")) else "open"
    if s.startswith(("no", "not", "n ", "never", "unwilling")) or s == "n":
        return "no"
    return s


def parse_height_cm(v):
    if not v:
        return None
    s = v.lower()
    m = re.search(r"(\d{3})\s*cm", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d)\s*(?:'|ft|feet|foot)\s*(\d{1,2})?", s)
    if m:
        ft, inch = int(m.group(1)), int(m.group(2) or 0)
        return round((ft * 12 + inch) * 2.54)
    return None


def age_from_dob(v, today=None):
    if not v:
        return None
    today = today or date.today()
    s = v.lower()
    y = mo = d = None
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = re.search(r"(\d{1,2})\s+([a-z]{3})[a-z]*,?\s+(\d{4})", s)
            if m and m.group(2) in MONTHS:
                d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
            else:
                m = re.search(r"([a-z]{3})[a-z]*\s+(\d{1,2}),?\s+(\d{4})", s)
                if m and m.group(1) in MONTHS:
                    mo, d, y = MONTHS[m.group(1)], int(m.group(2)), int(m.group(3))
    if not y:
        return None
    try:
        born = date(y, mo, d)
    except ValueError:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def split_location(v):
    """'Seattle, Washington, USA' -> (city, state, country)."""
    if not v:
        return None, None, None
    parts = [p.strip() for p in re.split(r",|/|\|", v) if p.strip()]
    country = None
    if parts and parts[-1].lower() in COUNTRIES:
        country = COUNTRIES[parts.pop().lower()]
    city = parts[0] if parts else None
    state = parts[1] if len(parts) > 1 else None
    return city, state, country


def profile_id_from_url(url):
    if not url:
        return None
    u = urlparse(url)
    q = parse_qs(u.query)
    for key in ("profileid", "profile_id", "pid", "id"):
        for k, vals in q.items():
            if k.lower() == key and vals:
                return vals[0]
    m = re.search(r"/(?:profile|profiles|member|view|p)/([A-Za-z0-9_-]{3,})", u.path, re.I)
    if m:
        return m.group(1)
    seg = [s for s in u.path.split("/") if s]
    if seg and re.search(r"\d", seg[-1]):
        return seg[-1]
    return None


# ---------------- profile extraction ----------------

def _line_pairs(lines, label_map):
    """Yield (field, value, index) for 'Label: value', 'Label<TAB>value',
    and 'Label' line followed by a value line."""
    i = 0
    while i < len(lines):
        line = lines[i]
        hit = None
        for sep in ("\t", ":"):
            if sep in line:
                lab, val = line.split(sep, 1)
                f = label_map.get(_norm_label(lab))
                if f:
                    hit = (f, val.strip(), i)
                    break
        if hit is None:
            f = label_map.get(_norm_label(line))
            if f and f not in BLOCK_FIELDS and i + 1 < len(lines):
                nxt = lines[i + 1]
                if not label_map.get(_norm_label(nxt.split(":")[0])):
                    hit = (f, nxt.strip(), i + 1)
                    i += 1
        if hit:
            yield hit
        i += 1


def _is_heading(line, label_map):
    n = _norm_label(line)
    if n in SECTION_HEADINGS or n in label_map:
        return True
    for sep in ("\t", ":"):
        if sep in line and label_map.get(_norm_label(line.split(sep, 1)[0])):
            return True
    return False


def _blocks(lines, label_map):
    """Multi-line sections such as About me / Family / Partner preference."""
    out = {}
    for i, line in enumerate(lines):
        n = _norm_label(line.split(":", 1)[0]) if ":" in line else _norm_label(line)
        f = label_map.get(n)
        if f not in BLOCK_FIELDS or f in out:
            continue
        body = []
        if ":" in line and line.split(":", 1)[1].strip():
            body.append(line.split(":", 1)[1].strip())
        for nxt in lines[i + 1:]:
            if _is_heading(nxt, label_map):
                break
            body.append(nxt)
            if sum(len(b) for b in body) > MAX_ABOUT:
                break
        text = " ".join(b.strip() for b in body if b.strip())
        if text:
            out[f] = text[:MAX_ABOUT]
    return out


def empty_record():
    return {"profile_id": None, "profile_url": None, "name": None, "age": None,
            "height_cm": None, "height_text": None, "city": None, "state": None,
            "country": None, "marital_status": None, "mother_tongue": None, "religion": None,
            "community": None, "education": None, "education_detail": None,
            "profession": None, "employer": None, "income_text": None, "food": None,
            "drinking": None, "smoking": None, "has_children": None, "relocate": None,
            "settle_plans": None, "timeline": None, "family_summary": None, "about_me": None,
            "partner_preference_text": None, "horoscope": None,
            "chat": {"exists": None}}


def extract_profile(text, url=None, heading=None, extra_aliases=None, today=None):
    label_map = _label_map(extra_aliases)
    lines = [ln.strip() for ln in (text or "").replace("\r", "").split("\n") if ln.strip()]
    rec = empty_record()
    rec["profile_url"] = url
    raw = {}
    for field, value, _ in _line_pairs(lines, label_map):
        value = _clean_value(value)
        if value and field not in raw and field not in BLOCK_FIELDS:
            raw[field] = value
    raw.update({k: v for k, v in _blocks(lines, label_map).items() if v})

    rec["name"] = raw.get("name") or _clean_value(heading)
    rec["profile_id"] = raw.get("profile_id") or profile_id_from_url(url)
    if raw.get("age"):
        m = re.search(r"\d{2}", raw["age"])
        rec["age"] = int(m.group()) if m else None
    if rec["age"] is None and raw.get("date_of_birth"):
        rec["age"] = age_from_dob(raw["date_of_birth"], today)
    if rec["age"] is None:
        m = re.search(r"\b(\d{2})\s*(?:yrs|years|yr)\b", text or "", re.I)
        if m:
            rec["age"] = int(m.group(1))
    rec["height_text"] = raw.get("height_text")
    rec["height_cm"] = parse_height_cm(raw.get("height_text"))
    city, state, country = split_location(raw.get("location"))
    rec["city"] = raw.get("city") or city
    rec["state"] = raw.get("state") or state
    rec["country"] = COUNTRIES.get((raw.get("country") or "").lower(), raw.get("country")) or country
    rec["marital_status"] = norm_marital(raw.get("marital_status"))
    for f in ("mother_tongue", "religion", "community", "education", "education_detail",
              "profession", "employer", "income_text", "settle_plans", "timeline",
              "about_me", "family_summary", "partner_preference_text"):
        rec[f] = raw.get(f)
    rec["food"] = norm_food(raw.get("food"))
    rec["drinking"] = norm_habit(raw.get("drinking"))
    rec["smoking"] = norm_habit(raw.get("smoking"))
    rec["has_children"] = norm_yes_no(raw.get("has_children"))
    rec["relocate"] = norm_yes_no(raw.get("relocate"))
    horo = {f: raw.get(f) for f in HOROSCOPE_FIELDS if raw.get(f)}
    if horo.get("manglik"):
        horo["manglik"] = norm_yes_no(horo["manglik"]) or horo["manglik"]
    rec["horoscope"] = horo or None
    if rec["profile_id"] is None and rec["name"] is None:
        rec["_unreadable"] = True
    return rec


def found_fields(rec):
    return [k for k, v in rec.items() if not k.startswith("_") and k != "chat"
            and v not in (None, "", [], {})]


# ---------------- chats ----------------

_TS_PREFIX = re.compile(
    r"^\[?\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?\]?\s*[-–]?\s*",
    re.I)
_MSG = re.compile(r"^([A-Za-z][\w .'-]{0,40}?)\s*(?:\([^)]{0,30}\)|\[[^\]]{0,30}\])?\s*:\s*(.+)$")

TOPICS = [
    ("a phone or video call", [r"\bcall\b", r"\bvideo\b", r"\bphone\b", r"\bzoom\b"]),
    ("meeting in person", [r"\bmeet\b", r"\bcoffee\b", r"\bin person\b"]),
    ("family", [r"\bfamily\b", r"\bparents?\b", r"\bmother\b", r"\bfather\b", r"\bsister\b",
                r"\bbrother\b"]),
    ("work", [r"\bjob\b", r"\bwork\b", r"\boffice\b", r"\bcareer\b", r"\bcompany\b"]),
    ("where to settle", [r"\bsettl", r"\breloca", r"\bmove to\b", r"\bmoving\b"]),
    ("horoscope", [r"\bhoroscope\b", r"\bkundli\b", r"\bkundali\b", r"\bnakshatra\b",
                   r"\bmatching stars\b"]),
    ("education", [r"\bstud(y|ied)\b", r"\bcollege\b", r"\buniversity\b", r"\bdegree\b"]),
    ("hobbies", [r"\bhobb", r"\bmusic\b", r"\btravel", r"\bmovies?\b", r"\bbooks?\b",
                 r"\bhiking\b", r"\bcricket\b"]),
    ("the weekend", [r"\bweekend\b", r"\bsaturday\b", r"\bsunday\b"]),
    ("food", [r"\bfood\b", r"\bcook", r"\bvegetarian\b"]),
    ("money", [r"\bmoney\b", r"\bloan\b", r"\binvest", r"\bbank\b", r"\bpayment\b"]),
    ("contact details", [r"\bwhatsapp\b", r"\bnumber\b", r"\btelegram\b", r"\bemail\b"]),
    ("timeline for marriage", [r"\btimeline\b", r"\bthis year\b", r"\bnext year\b",
                               r"\bwhen.*marr"]),
]

RED_FLAG_DETECTORS = {
    "money": ["send money", "lend me", "loan", "western union", "gift card", "bitcoin",
              "crypto", "invest with", "investment opportunity", "bank details", "wire transfer",
              "transfer the", "pay for my", "need money", "customs fee", "processing fee"],
    "off_platform": ["whatsapp me", "on whatsapp", "telegram", "my personal number",
                     "call me on", "email me at", "outside this site", "off this app",
                     "move to whatsapp"],
    "pressure": ["decide today", "right now", "urgent", "hurry", "immediately",
                 "don't tell your family", "dont tell your family"],
    "evasive": ["why do you ask", "not important", "will tell later", "don't ask",
                "dont ask"],
}


def _detector_for(flag):
    f = flag.lower()
    if any(w in f for w in ("money", "loan", "financial", "payment", "cash")):
        return RED_FLAG_DETECTORS["money"]
    if any(w in f for w in ("off-platform", "off platform", "whatsapp", "telegram",
                            "number", "move off")):
        return RED_FLAG_DETECTORS["off_platform"]
    if any(w in f for w in ("pressure", "rush", "hurry", "urgent")):
        return RED_FLAG_DETECTORS["pressure"]
    if any(w in f for w in ("evasive", "avoids", "dodg")):
        return RED_FLAG_DETECTORS["evasive"]
    if "contradict" in f:
        return []  # judged by comparing chat and profile - the AI layer does this
    words = re.sub(r"^(no|not|never|avoid)\s+", "", f).strip()
    return [words] if len(words) >= 4 else []


def detect_red_flags(texts, red_flags):
    """Return the user's red flags found in the given texts, each with a short
    keyword as evidence (never a full quote)."""
    blob = " \n".join(t for t in texts if t).lower()
    found = []
    for flag in red_flags or []:
        for kw in _detector_for(flag):
            if re.search(r"(?<![a-z])" + re.escape(kw.lower()) + r"(?![a-z])", blob):
                found.append(f"{flag} (mentions '{kw}')")
                break
    return found


def _topics(texts):
    blob = " ".join(texts).lower()
    return [name for name, pats in TOPICS if any(re.search(p, blob) for p in pats)]


def parse_chat(text, my_names=None, red_flags=None, label_map=None):
    """Chat thread text (page innerText or an exported .txt) -> chat state.
    Returns only counts, who wrote first/last, topics and flags."""
    my = {n.lower() for n in (my_names or [])} | {"you", "me", "myself"}
    labels = label_map or _label_map()
    msgs = []
    for raw in (text or "").replace("\r", "").split("\n"):
        line = _TS_PREFIX.sub("", raw.strip())
        m = _MSG.match(line)
        if not m:
            continue
        sender, body = m.group(1).strip(), m.group(2).strip()
        if _norm_label(sender) in labels or len(body) < 1:
            continue
        msgs.append((sender, body))
    if not msgs:
        return {"exists": False, "initiated_by": None, "message_count": 0,
                "last_message_by": None, "last_message_summary": None,
                "open_questions": [], "contradictions": [], "red_flags": []}

    def who(sender):
        return "user" if sender.lower() in my else "them"

    their = [b for s, b in msgs if who(s) == "them"]
    last_user_idx = max([i for i, (s, _) in enumerate(msgs) if who(s) == "user"], default=-1)
    pending_q = [b for i, (s, b) in enumerate(msgs)
                 if i > last_user_idx and who(s) == "them" and "?" in b]
    open_q = ["asked about " + t for t in _topics(pending_q)] or \
             (["asked a question you have not answered"] if pending_q else [])
    first, last = who(msgs[0][0]), who(msgs[-1][0])
    topics = _topics([b for _, b in msgs])
    starter = {"them": "they", "user": "you"}
    sender = {"them": "them", "user": "you"}
    summary = (f"{len(msgs)} message(s); {starter[first]} started; last message from "
               f"{sender[last]}")
    if last == "them" and "?" in msgs[-1][1]:
        summary += " and it asks you something"
    if topics:
        summary += ". Talked about " + ", ".join(topics[:4])
    return {"exists": True, "initiated_by": first, "message_count": len(msgs),
            "last_message_by": last, "last_message_summary": summary[:240] + ".",
            "open_questions": open_q, "contradictions": [],
            "red_flags": detect_red_flags(their, red_flags)}
