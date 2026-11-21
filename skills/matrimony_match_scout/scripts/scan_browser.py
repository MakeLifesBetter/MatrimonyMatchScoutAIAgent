"""
Matrimony Match Scout - browser login, calibration and scan (terminal mode).

What happens, in order:
  1. A browser window opens on your matrimony site (Playwright Chromium with
     a PERSISTENT profile in <data-dir>/browser_profile, so your login is
     remembered next time).
  2. YOU log in, in that window. The Scout never reads, types, or stores a
     password, code or cookie. You press Enter in the terminal when done.
  3. It finds your Inbox / Interests received / Matches / Search pages and
     lists the profiles on them (first 2 list pages each, same site only).
  4. CALIBRATION (first scan on a site): it reads ONE profile, shows you every
     field it extracted, and waits until you confirm or correct it.
  5. It reads profiles one at a time, at a human pace (several seconds apart),
     up to the per-run cap you set (max 50). After EVERY profile the record and
     the scan position are saved, so a disconnect resumes instead of restarting.
  6. Page text of profile and matches/search pages is saved under
     <data-dir>/captures/<run>/. Chat pages are NEVER saved - only a short
     summary (counts, who wrote last, topics, flags).
Read-only: it never clicks Send, Accept, Decline, Shortlist or Block.

Test hooks (never needed in normal use):
  SCOUT_HEADLESS=1          run the browser without a window
  SCOUT_PACE_SECONDS=0.1    shorter pause between pages
  SCOUT_SITE_URL_OVERRIDE   open this URL instead of the real site
"""
import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import extract

HARD_CAP = 50
DEFAULT_CAP = 20
LIST_PAGES_PER_SOURCE = 2
MAX_TEXT = 30000

SOURCES = {
    "chats": ["inbox", "chats", "chat", "messages", "conversations", "my chats"],
    "interests_received": ["interests received", "received interests", "received", "requests",
                           "invitations", "interests"],
    "matches": ["my matches", "new matches", "todays matches", "today's matches",
                "daily matches", "recommended", "matches"],
    "search": ["search results", "search"],
}
SOURCE_ORDER = ["chats", "interests_received", "matches", "search"]
SOURCE_WORDS = {"chats": "chats", "interests_received": "interests received",
                "matches": "matches", "search": "search results"}
PROFILE_HREF = re.compile(
    r"/(profile|profiles|member|members|view-?profile|viewprofile|p)/[A-Za-z0-9_-]{3,}|[?&](profileid|pid)=",
    re.I)
THREAD_HREF = re.compile(
    r"/(chat|chats|message|messages|conversation|conversations|thread|inbox)/[A-Za-z0-9_-]{3,}|[?&](threadid|chatid)=",
    re.I)
OWN_PROFILE = re.compile(r"my-?profile|edit|settings|logout|log-out|signout|upgrade|payment", re.I)
BLOCK_WORDS = ("captcha", "unusual activity", "are you a robot", "access denied",
               "too many requests", "temporarily blocked", "verify you are human",
               "suspicious activity")
GONE_WORDS = ("profile is deleted", "profile has been deleted", "no longer available",
              "deactivated", "profile not found", "this profile is hidden")
CONFIRM = re.compile(r"^(y|yes|yeah|yep|ok|okay|correct|right|fine|looks good|looks right|"
                     r"all good|perfect|thats right|that is right|good|go ahead|continue)\b")
CORRECT_FIELDS = {
    "name": "name", "age": "age", "height": "height_text", "city": "city", "state": "state",
    "country": "country", "education": "education", "degree": "education",
    "profession": "profession", "job": "profession", "occupation": "profession",
    "employer": "employer", "company": "employer", "income": "income_text",
    "salary": "income_text", "religion": "religion", "community": "community",
    "caste": "community", "mother tongue": "mother_tongue", "language": "mother_tongue",
    "marital status": "marital_status", "food": "food", "diet": "food",
    "drinking": "drinking", "smoking": "smoking", "about me": "about_me", "about": "about_me",
    "family": "family_summary", "profile id": "profile_id", "id": "profile_id",
    "rashi": "rashi", "nakshatra": "nakshatra", "star": "nakshatra", "manglik": "manglik",
}
SHOW_FIELDS = [("name", "Name"), ("age", "Age"), ("height_text", "Height"), ("city", "City"),
               ("state", "State"), ("country", "Country"), ("education", "Education"),
               ("profession", "Profession"), ("employer", "Employer"), ("income_text", "Income"),
               ("religion", "Religion"), ("community", "Community"),
               ("mother_tongue", "Mother tongue"), ("marital_status", "Marital status"),
               ("food", "Food"), ("drinking", "Drinking"), ("smoking", "Smoking"),
               ("about_me", "About me"), ("horoscope", "Horoscope"), ("profile_url", "Profile link")]


class ScanError(Exception):
    """A plain-English, one-sentence reason the scan stopped. Progress is saved."""


def resolve_url(site):
    """'shaadi', 'Shaadi.com', 'www.shaadi.com/x' or a full URL -> https URL."""
    override = os.environ.get("SCOUT_SITE_URL_OVERRIDE")
    if override:
        return override
    s = (site or "").strip().strip(".")
    if not s:
        return None
    if s.startswith(("http://", "https://")):
        return s
    s = s.split()[0].strip("/").lower()
    if "." not in s:
        s = f"{s}.com"
    if not s.startswith("www.") and s.count(".") == 1:
        s = "www." + s
    return "https://" + s


def pace(kind="profile"):
    fixed = os.environ.get("SCOUT_PACE_SECONDS")
    if fixed is not None:
        time.sleep(float(fixed))
        return
    lo, hi = (4.0, 9.0) if kind == "profile" else (3.0, 6.0)
    time.sleep(random.uniform(lo, hi))


def show_record(rec):
    lines = []
    for key, label in SHOW_FIELDS:
        v = rec.get(key)
        if isinstance(v, dict):
            v = "; ".join(f"{k} {x}" for k, x in v.items())
        if isinstance(v, str):
            v = v.replace("_", " ") if key in ("marital_status", "food") else v
            v = v if len(v) <= 120 else v[:117] + "..."
        lines.append(f"  {label}: {v if v not in (None, '') else 'not shown (unknown)'}")
    chat = rec.get("chat") or {}
    if chat.get("exists"):
        lines.append(f"  Chat: {chat.get('last_message_summary')}")
    return lines


def parse_correction(text):
    """'age is 28' / 'city should be Pune' / 'education: MBA' -> (field, value)."""
    t = text.strip().rstrip(".")
    m = re.match(r"^(?:the\s+)?([a-z ]{2,20}?)\s*(?:is|should be|=|:|was)\s+(.+)$", t, re.I)
    if not m:
        return None, None
    key = m.group(1).strip().lower()
    key = re.sub(r"^(her|his|their)\s+", "", key)
    field = CORRECT_FIELDS.get(key)
    return (field, m.group(2).strip()) if field else (None, None)


def apply_correction(rec, field, value):
    if value.lower() in ("unknown", "not shown", "blank", "empty", "none", "nothing"):
        value = None
    if field == "age":
        m = re.search(r"\d{2}", value or "")
        rec["age"] = int(m.group()) if m else None
    elif field == "height_text":
        rec["height_text"], rec["height_cm"] = value, extract.parse_height_cm(value)
    elif field == "marital_status":
        rec[field] = extract.norm_marital(value)
    elif field == "food":
        rec[field] = extract.norm_food(value)
    elif field in ("drinking", "smoking"):
        rec[field] = extract.norm_habit(value)
    elif field in ("rashi", "nakshatra", "manglik"):
        horo = dict(rec.get("horoscope") or {})
        horo[field] = value
        rec["horoscope"] = horo
    else:
        rec[field] = value
    return rec


def learn_alias(page_text, field, value):
    """If the corrected value sits next to a label we did not know, learn it."""
    if not value:
        return None
    known = extract._label_map()
    for line in (page_text or "").split("\n"):
        for sep in ("\t", ":"):
            if sep in line:
                lab, val = line.split(sep, 1)
                if value.lower() in val.lower() and extract._norm_label(lab) not in known \
                        and 1 <= len(lab.strip()) <= 30:
                    return extract._norm_label(lab)
    return None


class Scanner:
    def __init__(self, store, site_url, ui, cap=DEFAULT_CAP, sources=None):
        self.store = store
        self.site_url = site_url
        self.domain = urlparse(site_url).netloc
        self.ui = ui
        self.cap = max(1, min(HARD_CAP, int(cap or DEFAULT_CAP)))
        self.sources = sources or SOURCE_ORDER
        crit = store.criteria()
        self.red_flags = crit.get("red_flags") or []
        self.my_names = [n for n in (crit.get("my_name"),) if n]
        calib = (store.state().get("calibration") or {}).get(self.domain) or {}
        self.calibrated = bool(calib.get("confirmed"))
        self.aliases = calib.get("aliases") or {}
        self.counts = {"new": 0, "updated": 0, "unchanged": 0, "unavailable": 0}
        self.unreadable_streak = 0

    def _drop_if_empty(self, scan):
        """Nothing was found or read yet: do not leave a 'paused' scan behind."""
        if not scan.get("read") and not scan.get("queue"):
            st = self.store.state()
            st.pop("scan", None)
            self.store._atomic_write_json(self.store.state_path, st)

    # ----- browser helpers -----
    def _open(self, pw):
        profile_dir = self.store.dir / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.ctx = pw.chromium.launch_persistent_context(
                str(profile_dir), headless=os.environ.get("SCOUT_HEADLESS") == "1",
                args=["--no-sandbox"], viewport={"width": 1280, "height": 900})
        except Exception as exc:
            msg = str(exc).lower()
            if "executable doesn't exist" in msg or "playwright install" in msg:
                raise ScanError("The browser is not installed yet - run "
                                "'python3 -m playwright install chromium' once, then say scan again.")
            if "lock" in msg or "already in use" in msg or "singleton" in msg:
                raise ScanError("The Scout's browser window is already open somewhere - close it "
                                "and say scan again.")
            raise ScanError("I could not open the browser window on this computer.")
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()

    def _goto(self, url, retries=1):
        for attempt in range(retries + 1):
            try:
                resp = self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                self.page.wait_for_timeout(600)
                if resp is not None and resp.status in (403, 429):
                    raise ScanError(f"{self.domain} is refusing to show pages right now "
                                    "(it may be limiting visits), so I stopped and saved my place.")
                return
            except ScanError:
                raise
            except Exception as exc:
                name = exc.__class__.__name__
                if "TargetClosed" in name or "closed" in str(exc).lower():
                    raise ScanError("The browser window was closed, so I paused and saved my "
                                    "place - say scan to carry on.")
                if attempt < retries:
                    pace("list")
                    continue
                raise ScanError(f"I lost the connection to {self.domain}, so I paused and saved "
                                "my place - say scan when you are back online.")

    def _text(self):
        try:
            return self.page.inner_text("body")[:MAX_TEXT]
        except Exception:
            return ""

    def _heading(self):
        try:
            h = self.page.locator("h1")
            return h.first.inner_text(timeout=1500) if h.count() else None
        except Exception:
            return None

    def _login_visible(self):
        try:
            return self.page.locator("input[type=password]:visible").count() > 0
        except Exception:
            return False

    def _links(self):
        try:
            items = self.page.eval_on_selector_all(
                "a[href]", "els => els.map(e => ({href: e.href, text: (e.innerText || '').trim()}))")
        except Exception:
            return []
        out = []
        for it in items:
            href = urljoin(self.page.url, it.get("href") or "")
            if urlparse(href).netloc == self.domain:
                out.append({"href": href.split("#")[0], "text": it.get("text") or ""})
        return out

    def _check_blocked(self, text):
        low = text.lower()
        if any(w in low for w in BLOCK_WORDS):
            raise ScanError(f"{self.domain} is showing a security check, so I stopped - please "
                            "finish it in the browser window yourself, then say scan to carry on.")

    # ----- capture files -----
    def _capture(self, scan, name, body, url):
        out = self.store.dir / "captures" / scan["run_id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(f"URL: {url}\nCaptured: {datetime.now().isoformat(timespec='seconds')}"
                                f"\n\n{body}", encoding="utf-8")
        idx_path = out / "index.json"
        idx = json.loads(idx_path.read_text()) if idx_path.exists() else \
            {"site": self.site_url, "run_id": scan["run_id"], "pages": []}
        idx["pages"].append({"file": name, "url": url})
        idx_path.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        scan["captures"] = str(out)

    # ----- steps -----
    def login(self):
        self.ui.say(f"Opening {self.site_url} in a browser window now.")
        try:
            self._goto(self.site_url)
        except ScanError as exc:
            if "lost the connection" in str(exc):
                raise ScanError(f"I could not reach {self.domain} - please check your internet "
                                "connection and the site name, then say scan again.")
            raise
        self.ui.say("Please log in there yourself - I never see, type or store your password. "
                    "If you are already logged in, there is nothing to do.")
        for attempt in range(3):
            self.ui.enter("Press Enter here when you can see your home page or inbox: ")
            try:
                self.page = self.ctx.pages[-1] if self.ctx.pages else self.page
            except Exception:
                raise ScanError("The browser window was closed, so I stopped - say scan to try again.")
            if not self._login_visible():
                self.home_url = self.page.url
                self.ui.say("Thanks, you are logged in. I will only read - nothing is sent, "
                            "accepted or rejected.")
                return
            if attempt < 2:
                self.ui.say("I still see a login form in the browser. Finish logging in there, "
                            "then press Enter again.")
        raise ScanError("I still see the login page, so I stopped - nothing was read.")

    def discover(self, scan):
        queue_urls = {q["url"] for q in scan["queue"]} | set(scan["done"])
        home = getattr(self, "home_url", self.site_url)
        self._goto(home)
        nav = self._links()
        used = set()
        for source in self.sources:
            if source in scan.get("discovered", []):
                continue
            words = SOURCES[source]
            link = None
            for w in words:  # best word first
                for a in nav:
                    t = a["text"].lower()
                    if a["href"] in used or OWN_PROFILE.search(a["href"]):
                        continue
                    if t == w or (len(t) < 40 and w in t):
                        link = a
                        break
                if link:
                    break
            if not link:
                self.ui.say(f"I could not find your {SOURCE_WORDS[source]} page, so I skipped it.")
                scan.setdefault("discovered", []).append(source)
                continue
            used.add(link["href"])
            url, found = link["href"], 0
            for page_no in range(LIST_PAGES_PER_SOURCE):
                pace("list")
                self._goto(url)
                text = self._text()
                self._check_blocked(text)
                links = self._links()
                names = []
                for a in links:
                    h = a["href"]
                    if OWN_PROFILE.search(h) or h in queue_urls:
                        continue
                    kind = None
                    if source == "chats" and THREAD_HREF.search(h) and h != url:
                        kind = "thread"
                    elif PROFILE_HREF.search(h):
                        kind = "profile"
                    if kind:
                        scan["queue"].append({"url": h, "source": source, "kind": kind})
                        queue_urls.add(h)
                        names.append(f"{a['text'] or '(no name)'} - {h}")
                        found += 1
                if source == "chats":  # never store message previews
                    body = "Inbox page (names and links only - chat text is never saved):\n" + \
                           "\n".join(names)
                else:
                    body = text
                self._capture(scan, f"list_{source}_{page_no + 1}.txt", body, url)
                nxt = next((a["href"] for a in links if a["text"].lower().strip() in
                            ("next", "next page", "next >", ">", "more")), None)
                self.store.save_scan(scan)
                if not nxt or nxt == url:
                    break
                url = nxt
            scan.setdefault("discovered", []).append(source)
            self.store.save_scan(scan)
            self.ui.say(f"Found {found} profile(s) in your {SOURCE_WORDS[source]}.")
        scan["phase"] = "READ"
        self.store.save_scan(scan)

    def read_item(self, scan, item):
        """Visit one queue item -> (record, page_text) or (None, reason)."""
        chat = None
        self._goto(item["url"])
        text = self._text()
        self._check_blocked(text)
        if self._login_visible():
            self.ui.say("The site logged you out. Please log in again in the browser window.")
            self.ui.enter("Press Enter here when you are logged in again: ")
            self._goto(item["url"])
            text = self._text()
            if self._login_visible():
                raise ScanError("Your login expired, so I paused and saved my place - "
                                "log in and say scan to carry on.")
        if item["kind"] == "thread":
            chat = extract.parse_chat(text, my_names=self.my_names, red_flags=self.red_flags)
            prof = next((a["href"] for a in self._links()
                         if PROFILE_HREF.search(a["href"]) and not OWN_PROFILE.search(a["href"])),
                        None)
            text = ""  # the chat page text is dropped here and never written anywhere
            if prof:
                pace("list")
                self._goto(prof)
                text = self._text()
                self._check_blocked(text)
                item = dict(item, profile_url=prof)
        url = item.get("profile_url") or item["url"]
        low = text.lower()
        if any(w in low for w in GONE_WORDS):
            return None, "gone", extract.profile_id_from_url(url)
        rec = extract.extract_profile(text, url=url, heading=self._heading(),
                                      extra_aliases=self.aliases)
        if chat is not None:
            rec["chat"] = chat
        rec["source"], rec["source_detail"] = item["source"], url
        if rec.pop("_unreadable", False):
            return None, "unreadable", None
        return rec, text, None

    def calibrate(self, scan, rec, page_text):
        self.ui.say("Before the full scan, here is exactly what I read from ONE profile:")
        for line in show_record(rec):
            self.ui.say(line)
        while True:
            ans = self.ui.ask("Did I read this correctly? Say 'yes', or correct me like "
                              "'age is 28' or 'city is Pune'. Say 'stop' to pause.")
            if ans is None:
                return False
            low = ans.strip().lower().replace("'", "")
            if low in ("stop", "pause", "cancel", "quit", "exit", "no stop"):
                return False
            if CONFIRM.match(low):
                cal = self.store.state().get("calibration") or {}
                cal[self.domain] = {"confirmed": True, "aliases": self.aliases,
                                    "at": datetime.now().isoformat(timespec="seconds")}
                self.store.update_state(calibration=cal)
                self.calibrated = True
                self.ui.say("Thank you. I will read the rest the same way.")
                return True
            field, value = parse_correction(ans)
            if not field:
                self.ui.say("Tell me which part is wrong, for example: 'education is MBA' or "
                            "'smoking is unknown'.")
                continue
            apply_correction(rec, field, value)
            alias = learn_alias(page_text, field, value)
            if alias and field in extract.ALIASES:
                self.aliases[alias] = field
            shown = rec.get(field) if field in rec else (rec.get("horoscope") or {}).get(field)
            self.ui.say(f"Fixed: {field.replace('_', ' ')} is now {shown if shown is not None else 'unknown'}."
                        + (f" I also learned that '{alias}' on this site means "
                           f"{field.replace('_', ' ')}." if alias else "")
                        + " Anything else? Say 'yes' when it is all right.")

    def save(self, scan, item, rec, page_text=""):
        _, event = self.store.upsert_profile(rec, source=item["source"])
        self.counts[event] += 1
        scan["done"].append(item["url"])
        if rec.get("profile_url") and rec["profile_url"] not in scan["done"]:
            scan["done"].append(rec["profile_url"])  # same person reached via chat and matches
        scan["read"] += 1
        self.store.save_scan(scan)  # checkpoint after EVERY profile
        if rec.get("profile_id"):
            body = page_text or extract_profile_capture(rec)
            self._capture(scan, f"profile_{re.sub(r'[^A-Za-z0-9_-]', '_', rec['profile_id'])}.txt",
                          body, rec.get("profile_url") or item["url"])
        return event

    def run(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ScanError("The browser part needs one install first: run "
                            "'python3 -m pip install playwright' and then "
                            "'python3 -m playwright install chromium'.")
        scan = self.store.scan_state()
        resumed = bool(scan and scan.get("site") == self.site_url)
        if resumed:
            left = len([q for q in scan["queue"] if q["url"] not in scan["done"]])
            self.cap = scan.get("cap", self.cap)
            self.ui.say(f"Picking up the scan that was paused: {scan['read']} of up to "
                        f"{self.cap} profiles read, {left} still listed. Nothing is repeated.")
        else:
            scan = self.store.start_scan(self.site_url, self.cap)
            backlog = self.store.state().get("backlog") or []
            if backlog and backlog[0].get("site") == self.site_url:
                scan["queue"] = [dict(b) for b in backlog[0]["items"]]
        with sync_playwright() as pw:
            try:
                self._open(pw)
            except ScanError:
                self._drop_if_empty(scan)
                raise
            try:
                try:
                    self.login()
                except ScanError:
                    self._drop_if_empty(scan)
                    raise
                if scan["phase"] == "DISCOVER":
                    self.discover(scan)
                pending = [q for q in scan["queue"] if q["url"] not in scan["done"]]
                if not pending:
                    self.store.finish_scan({"read": scan["read"], **self.counts})
                    return {"status": "empty", "read": 0, **self.counts}
                self.ui.say(f"Reading up to {self.cap - scan['read']} profile(s), one at a time, "
                            "a few seconds apart. Press Ctrl+C any time to pause safely.")
                for item in pending:
                    if scan["read"] >= self.cap:
                        break
                    if item["url"] in scan["done"]:
                        continue
                    pace("profile")
                    rec, text, gone_id = self.read_item(scan, item)
                    if rec is None:
                        scan["done"].append(item["url"])
                        self.store.save_scan(scan)
                        if text == "gone":
                            if gone_id:
                                self.store.mark_unavailable(gone_id)
                            self.counts["unavailable"] += 1
                            continue
                        self.unreadable_streak += 1
                        if self.unreadable_streak >= 3:
                            raise ScanError("Three profiles in a row looked different from what I "
                                            "learned, so I stopped - the site may have changed its "
                                            "layout. Your progress is saved.")
                        continue
                    self.unreadable_streak = 0
                    if not self.calibrated:
                        if not self.calibrate(scan, rec, text):
                            self.store.save_scan(scan)
                            return {"status": "paused", "read": scan["read"], **self.counts,
                                    "message": "Paused before the full scan. Say scan when you "
                                               "want to continue - I will show you the profile again."}
                    event = self.save(scan, item, rec, text)
                    self.ui.say(f"Read {scan['read']} of up to {self.cap}: {rec.get('name') or 'a profile'}"
                                f" ({'new' if event == 'new' else 'changed since last time' if event == 'updated' else 'no change'}).")
                left = [q for q in scan["queue"] if q["url"] not in scan["done"]]
                st = self.store.state()
                st["backlog"] = [{"site": self.site_url, "items": left}] if left else []
                self.store._atomic_write_json(self.store.state_path, st)
                summary = {"read": scan["read"], **self.counts, "left": len(left),
                           "captures": scan.get("captures")}
                self.store.finish_scan(summary)
                return {"status": "cap" if left else "done", **summary}
            finally:
                try:
                    self.ctx.close()
                except Exception:
                    pass


def extract_profile_capture(rec):
    """Profile capture file: the extracted fields (no chat text)."""
    lines = [f"{label}: {rec.get(key) if not isinstance(rec.get(key), dict) else json.dumps(rec.get(key))}"
             for key, label in SHOW_FIELDS if rec.get(key) not in (None, "")]
    chat = rec.get("chat") or {}
    if chat.get("exists"):
        lines.append(f"Chat summary: {chat.get('last_message_summary')}")
    return "\n".join(lines)


def run_scan(store, site, ui, cap=DEFAULT_CAP, sources=None):
    url = resolve_url(site)
    if not url:
        raise ScanError("I need the name of your matrimony site first, for example shaadi.com.")
    with store.lock():
        return Scanner(store, url, ui, cap=cap, sources=sources).run()
