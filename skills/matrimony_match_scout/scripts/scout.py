"""
Matrimony Match Scout - the conversational terminal.

  python3 scout.py                      talk to the Scout (data in ~/matrimony-scout-data)
  python3 scout.py --data-dir FOLDER    use another data folder

Every Scout line starts with "Scout:" and every place you type is
"Response:". Say things in your own words, for example:
  lets start / open the app / scan / give me the report / check status
  how can you read the data? / change my age range to 26 to 30
  add Pune to my places / my dealbreaker is smoking / pass on 2
  interested in Asha / why is 1 ranked first / draft a reply to Asha
  what did you show me before / read my files / show me a demo / quit

Internal actions for the AI chat layer (JSON out, never shown to the user):
  scout.py --data-dir D status | interests | history | rescore
  scout.py --data-dir D save-interests FILE.json [--confirm-hand-edit]
  scout.py --data-dir D hand-edit accept|revert
  scout.py --data-dir D ingest FILE.json        (list of schema records)
  scout.py --data-dir D judge FILE.json         ([{profile_id, qualitative, text}])
  scout.py --data-dir D report [--preview]      (top 3 + md + xlsx; marks shown)
  scout.py --data-dir D set-status ID interested|rejected|contacted|new
  scout.py --data-dir D extract FILE.txt [--url URL]
  scout.py --data-dir D read-files FOLDER
  scout.py --data-dir D checkpoint save FILE.json | clear   ({phase, cursors, run_id})
"""
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import extract  # noqa: E402
import file_intake  # noqa: E402
import pipeline  # noqa: E402
from state_store import ExternalEditPending, InterestsFileError, ScoutStore  # noqa: E402

DEFAULT_DATA = Path(os.environ.get("SCOUT_DATA_DIR") or "~/matrimony-scout-data").expanduser()
YES = re.compile(r"^(y|yes|yeah|yep|yup|sure|ok|okay|correct|right|thats right|that is right|"
                 r"looks good|go ahead|do it|please do|fine|perfect|all good)\b")
NO = re.compile(r"^(n|no|nope|nah|not really|wrong|thats wrong|incorrect|dont|do not)\b")
SKIP = {"skip", "pass", "dont care", "do not care", "no preference", "any", "anything",
        "whatever", "na", "n/a", "none", ""}
SITE_NAMES = {"shaadi": "shaadi.com", "shadi": "shaadi.com", "bharat matrimony": "bharatmatrimony.com",
              "bharatmatrimony": "bharatmatrimony.com", "jeevansathi": "jeevansathi.com",
              "jeevan sathi": "jeevansathi.com", "telugu matrimony": "telugumatrimony.com",
              "tamil matrimony": "tamilmatrimony.com", "betterhalf": "betterhalf.ai",
              "dil mil": "dilmil.co", "dilmil": "dilmil.co"}


# ---------------- small helpers ----------------

def norm(text):
    t = (text or "").lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    t = t.replace("'", "")
    t = re.sub(r"[?!,;:\"“”()]", " ", t)
    t = re.sub(r"(?<!\d)\.(?!\d)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def split_list(text):
    parts = re.split(r",|/|;|\band\b|\bor\b|\balso\b|&", text or "", flags=re.I)
    out = []
    for p in parts:
        p = re.sub(r"^\s*(in|anywhere in|somewhere in|around|near|only|just|the)\s+", "", p.strip(),
                   flags=re.I).strip(" .")
        if p and p.lower() not in SKIP:
            out.append(p if any(ch.isupper() for ch in p) else p.title() if len(p) > 3 else p.upper())
    return out


def parse_age_range(text):
    t = norm(text)
    m = re.search(r"(\d{2})\s*(?:to|-|and|till|until|through|–)\s*(\d{2})", t) or \
        re.search(r"^(\d{2})\s+(\d{2})$", t)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return a, b
    m = re.search(r"(under|below|less than|upto|up to|max|maximum|at most|younger than)\s*(\d{2})", t)
    if m:
        return None, int(m.group(2))
    m = re.search(r"(over|above|more than|at least|min|minimum|older than|from)\s*(\d{2})", t)
    if m:
        return int(m.group(2)), None
    return "bad", None


def clean_dealbreaker(text):
    t = norm(text)
    t = re.sub(r"^(no|not|never|must not|dont want|do not want|nobody who|anyone who|someone who)\s+",
                "", t)
    t = {"smokers": "smoking", "smoker": "smoking", "smokes": "smoking", "drinkers": "drinking",
         "drinks": "drinking", "drinker": "drinking", "alcohol": "drinking",
         "divorcees": "divorced", "divorcee": "divorced", "non veg": "non-veg",
         "non vegetarian": "non-veg", "meat eaters": "non-veg"}.get(t, t)
    return t


class Console:
    def say(self, msg=""):
        for line in str(msg).split("\n"):
            print("Scout: " + line, flush=True)

    def ask(self, question=None):
        if question:
            self.say(question)
        try:
            return input("Response: ").strip()
        except EOFError:
            return None

    def enter(self, prompt):
        self.say(prompt.strip())
        try:
            input("Response: ")
        except EOFError:
            pass


# ---------------- the conversation ----------------

class Scout:
    def __init__(self, store, ui=None):
        self.store = store
        self.ui = ui or Console()
        self.undo_criteria = None

    say = property(lambda self: self.ui.say)

    def ask(self, q=None):
        return self.ui.ask(q)

    # ----- interests file guard (hand edits are confirmed, never overwritten) -----
    def interests_ok(self):
        try:
            data, ext = self.store.load_interests()
        except InterestsFileError as exc:
            self.say(f"{exc} I have not changed your file.")
            ans = self.ask("Should I put back your last good copy? Your edited file is kept as a "
                           "separate copy. (yes / no - I will fix it myself)")
            if ans and YES.match(norm(ans)):
                self.store.restore_interests_backup()
                self.say("Done - your last good interests are back. "
                         + pipeline.criteria_summary(self.store.criteria()) + ".")
                return True
            self.say("Okay, I will wait. Fix the file and talk to me again - until then I will not "
                     "score anything.")
            return False
        if ext:
            diff = self.store.external_edit_diff()
            self.say("I noticed your interests file was edited by hand since I last saved it:")
            for d in diff or [{"field": "(formatting only)", "from": "", "to": ""}]:
                label = pipeline.PRETTY.get(d["field"], d["field"])
                self.say(f"  {label}: {pipeline._val(d['from'])} -> {pipeline._val(d['to'])}")
            ans = self.ask("Should I use your edited version? (yes / no - put back what was there before)")
            if ans and YES.match(norm(ans)):
                self.store.accept_external_edit()
                self.say("Great, I am using your edited interests now: "
                         + pipeline.criteria_summary(self.store.criteria()) + ".")
                self.rescore_and_tell()
                return True
            if ans and NO.match(norm(ans)):
                self.store.revert_external_edit()
                self.say("Okay, I put back the previous version. Your edited copy is saved next to it "
                         "in your data folder, in case you want it later.")
                return True
            self.say("No problem - I will leave the file exactly as it is and ask again next time.")
            return False
        return data is not None or True

    def save_criteria(self, criteria, reason):
        before = self.store.criteria()
        try:
            saved = self.store.save_interests(criteria, changed_by="user", reason=reason)
        except (ExternalEditPending, InterestsFileError):
            if not self.interests_ok():
                return None
            saved = self.store.save_interests(criteria, changed_by="user", reason=reason,
                                              allow_over_external=True)
        self.undo_criteria = before
        return saved

    # ----- intake -----
    def intake(self):
        self.say("Great - 5 quick questions. Say 'skip' for anything you do not mind about.")
        c = dict(self.store.criteria())
        site = self.ask("1 of 5: Which matrimony site is this for? (for example Shaadi.com)")
        if site is None:
            return
        if norm(site) not in SKIP:
            key = norm(site).replace(" com", "").replace(".com", "")
            c["site"] = SITE_NAMES.get(key, SITE_NAMES.get(norm(site), site.strip()))
        who = self.ask("2 of 5: Who is the search for - you, or someone in your family?")
        if who is None:
            return
        if norm(who) not in SKIP:
            w = norm(who)
            c["search_for"] = "me" if w in ("me", "myself", "self", "for me", "i am", "mine") else who.strip()
        while True:
            age = self.ask("3 of 5: What age range is okay? (for example 26 to 30)")
            if age is None:
                return
            if norm(age) in SKIP:
                c.pop("age_min", None), c.pop("age_max", None)
                break
            lo, hi = parse_age_range(age)
            if lo == "bad":
                self.say("Sorry, I could not read that as ages. Try something like '26 to 30'.")
                continue
            c["age_min"], c["age_max"] = lo, hi
            break
        places = self.ask("4 of 5: Which places are okay - cities, states or countries? "
                          "(for example Seattle, Bay Area, or 'anywhere')")
        if places is None:
            return
        p = norm(places)
        c["places"] = [] if (p in SKIP or p in ("anywhere", "any where", "anyplace", "any place")
                             or p.startswith("anywhere is")) else split_list(places)
        deal = self.ask("5 of 5: One dealbreaker I must never let through? (for example smoking, "
                        "or say 'none')")
        if deal is None:
            return
        if norm(deal) not in SKIP and norm(deal) not in ("no", "nothing", "none really"):
            c["dealbreakers"] = [clean_dealbreaker(deal)]
        else:
            c["dealbreakers"] = []
        c.setdefault("red_flags", ["asks for money", "pressure to move off-platform"])
        c.setdefault("max_profiles_per_run", 20)
        saved = self.save_criteria(c, "quick start intake")
        if saved is None:
            return
        self.say(f"Saved. Here is what I heard: {pipeline.criteria_summary(c)}.")
        ans = self.ask("Is that right? Say 'yes', or tell me a change like 'change my age range to "
                       "27 to 31'.")
        if ans and not YES.match(norm(ans)) and not NO.match(norm(ans)):
            if not self.apply_change(ans):
                self.say("I did not catch a change there, so I kept it as is.")
        elif ans and NO.match(norm(ans)):
            self.say("No problem - tell me what to change any time, for example "
                     "'add Pune to my places' or 'my dealbreaker is divorced'.")
        self.say(f"Your interests live in {self.store.interests_path} - you can edit that file "
                 "yourself too; I will notice and check with you.")
        self.say("Next: say 'scan' (or 'open the app') and I will open your site so you can log in. "
                 "Education, religion, food, habits and the rest we can fine-tune later, from real "
                 "profiles - just say 'refine my criteria'.")

    def refine(self):
        """Fuller criteria, asked with real stored profiles as examples."""
        c = dict(self.store.criteria())
        examples = [r for r, s in pipeline.score_all(self.store, c) if not s["excluded"]][:2]
        ex = examples[0]["data"] if examples else {}

        def eg(field, word):
            v = ex.get(field)
            return f" (for example, {ex.get('name')} shows {word} '{str(v).replace('_', ' ')}')" \
                if v and ex.get("name") else ""

        self.say("Let's fine-tune. Every question can be skipped.")
        qs = [
            ("min_education", "Lowest education that is okay?" + eg("education", "education"), "edu"),
            ("religion", "Religion - must match, preferred, or don't care? Say e.g. 'must Hindu', "
                         "'preferred Christian' or 'skip'.", "rel"),
            ("community", "Community or caste - must, preferred, or don't care?", "com"),
            ("mother_tongue", "Mother tongue that matters? Add 'must' if it has to match."
             + eg("mother_tongue", "mother tongue"), "tongue"),
            ("food_ok", "Which food habits are okay? (vegetarian, eggetarian, non-veg)"
             + eg("food", "food"), "list_food"),
            ("smoking_ok", "Smoking: okay, occasionally okay, or never?", "habit"),
            ("drinking_ok", "Drinking: okay, occasionally okay, or never?", "habit"),
            ("relocation_needed", "Must they be open to relocating? (yes / no)", "bool"),
            ("timeline", "Your marriage timeline? (for example within a year)", "text"),
            ("red_flags", "Red flags to watch for in chats? (I already watch for: "
             + ", ".join(c.get("red_flags") or ["none"]) + ")", "list_add"),
            ("green_flags", "Green flags that should boost someone? (for example 'loves travel')",
             "list"),
            ("good_match_words", "In a few words, what does a very good match care about? "
                                 "(for example family, travel, kindness)", "list"),
        ]
        for key, q, kind in qs:
            ans = self.ask(q)
            if ans is None:
                break
            a = norm(ans)
            if a in SKIP:
                continue
            if kind == "edu":
                c["min_education"] = ans.strip()
            elif kind in ("rel", "com"):
                field = "religion" if kind == "rel" else "community"
                must = bool(re.search(r"\bmust\b|\bonly\b|\bhas to\b", a))
                val = split_list(re.sub(r"\b(must|preferred|prefer|only|has to|be|match)\b", "", ans,
                                        flags=re.I))
                c.pop(f"{field}_must", None), c.pop(f"{field}_preferred", None)
                if val:
                    c[f"{field}_{'must' if must else 'preferred'}"] = val
            elif kind == "tongue":
                c["must_match_tongue"] = "must" in a
                c["mother_tongue"] = split_list(re.sub(r"\bmust\b", "", ans, flags=re.I))[0] \
                    if split_list(re.sub(r"\bmust\b", "", ans, flags=re.I)) else None
            elif kind == "list_food":
                c["food_ok"] = [extract.norm_food(x) for x in split_list(ans)]
            elif kind == "habit":
                c[key] = ["never", "occasionally", "regularly"] if a in ("okay", "ok", "fine", "yes") \
                    else ["never", "occasionally"] if "occasion" in a else ["never"]
            elif kind == "bool":
                c[key] = bool(YES.match(a))
            elif kind == "text":
                c[key] = ans.strip()
            elif kind == "list_add":
                c[key] = list(dict.fromkeys((c.get(key) or []) + [x.lower() for x in split_list(ans)]))
            elif kind == "list":
                c[key] = [x.lower() for x in split_list(ans)]
        if self.save_criteria(c, "refined from examples") is None:
            return
        self.say("Saved. Your interests now: " + pipeline.criteria_summary(c) + ".")
        self.rescore_and_tell()

    # ----- plain-English changes -----
    def apply_change(self, text):
        t = norm(text)
        c = dict(self.store.criteria())
        msg = None
        m = re.search(r"\bage\b.*?(\d{2})\s*(?:to|-|and|till|until)\s*(\d{2})", t)
        if m:
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            c["age_min"], c["age_max"] = a, b
            msg = f"age range is now {a} to {b}"
        lists = {"places": "places", "locations": "places", "location": "places", "cities": "places",
                 "city": "places", "countries": "places", "dealbreakers": "dealbreakers",
                 "dealbreaker": "dealbreakers", "deal breakers": "dealbreakers",
                 "red flags": "red_flags", "red flag": "red_flags", "green flags": "green_flags",
                 "green flag": "green_flags"}
        lw = "|".join(sorted(lists, key=len, reverse=True))
        if not msg:
            m = re.search(rf"\b(?:add|include|also)\s+(.+?)\s+(?:to|in|as)\s+(?:a\s+|my\s+|the\s+)*({lw})\b", t)
            if m:
                key = lists[m.group(2)]
                vals = [clean_dealbreaker(v) for v in split_list(m.group(1))] if key == "dealbreakers" \
                    else split_list(m.group(1)) if key == "places" else [v.lower() for v in split_list(m.group(1))]
                c[key] = list(dict.fromkeys((c.get(key) or []) + vals))
                msg = f"added {', '.join(vals)} to your {pipeline.PRETTY.get(key, key)}"
        if not msg:
            m = re.search(rf"\b(?:remove|drop|delete|take out|take off)\s+(.+?)\s+from\s+(?:my\s+|the\s+)*({lw})\b", t)
            if m:
                key = lists[m.group(2)]
                gone = {v.lower() for v in split_list(m.group(1))} | {clean_dealbreaker(m.group(1))}
                before = c.get(key) or []
                c[key] = [v for v in before if v.lower() not in gone]
                msg = (f"removed {m.group(1)} from your {pipeline.PRETTY.get(key, key)}"
                       if len(c[key]) < len(before) else None)
                if msg is None:
                    self.say(f"{m.group(1)} was not in your {pipeline.PRETTY.get(key, key)}, so nothing changed.")
                    return True
        if not msg:
            m = re.search(rf"\b(?:change|set|make|update)\s+(?:my\s+|the\s+)?({lw})\s+(?:to|as)\s+(.+)$", t)
            if m:
                key = lists[m.group(1)]
                raw = text[text.lower().rfind(" to ") + 4:] if " to " in text.lower() else m.group(2)
                vals = [clean_dealbreaker(v) for v in split_list(raw)] if key == "dealbreakers" \
                    else ([] if norm(raw) in ("anywhere", "any") else split_list(raw))
                c[key] = vals
                msg = f"your {pipeline.PRETTY.get(key, key)} are now: {', '.join(vals) or 'anywhere'}"
        if not msg:
            m = re.search(r"\b(?:my\s+)?(?:new\s+)?deal ?breaker (?:is|=)\s+(.+)$", t) or \
                re.search(r"^(.+?) is (?:a|my|also a) deal ?breaker$", t)
            if m:
                v = clean_dealbreaker(m.group(1))
                c["dealbreakers"] = list(dict.fromkeys((c.get("dealbreakers") or []) + [v]))
                msg = f"added '{v}' as a dealbreaker"
        if not msg:
            m = re.search(r"\b(?:min(?:imum)?|lowest)\s+education\s+(?:to\s+|is\s+|should be\s+|of\s+)?(.+)$", t) \
                or re.search(r"\beducation\s+(?:at least|minimum)\s+(.+)$", t)
            if m:
                c["min_education"] = m.group(1).strip()
                msg = f"minimum education is now {c['min_education']}"
        if not msg:
            m = re.search(r"\b(?:cap|limit|profiles per (?:run|scan)|read up to|at most)\D{0,12}(\d{1,3})\b", t)
            if m:
                n = max(1, min(50, int(m.group(1))))
                c["max_profiles_per_run"] = n
                msg = f"I will read up to {n} profiles per scan" + (" (50 is the most)" if int(m.group(1)) > 50 else "")
        if not msg:
            m = re.search(r"\b(?:change|set|switch)\s+(?:my\s+|the\s+)?site\s+to\s+(.+)$", t)
            if m:
                c["site"] = SITE_NAMES.get(m.group(1).replace(" com", ""), m.group(1).strip())
                msg = f"site is now {c['site']}"
        if not msg:
            m = re.search(r"\bmother tongue\s+(?:to|is|should be|must be)\s+(.+)$", t)
            if m:
                c["mother_tongue"] = m.group(1).strip().title()
                c["must_match_tongue"] = "must" in t
                msg = f"mother tongue is now {c['mother_tongue']}" + (" (must match)" if c["must_match_tongue"] else "")
        if not msg:
            m = re.search(r"\b(religion|community|caste)\s+(must be|should be|to|is|preferred)\s+(.+)$", t)
            if m:
                field = "religion" if m.group(1) == "religion" else "community"
                kind = "must" if "must" in m.group(2) else "preferred"
                c.pop(f"{field}_must", None), c.pop(f"{field}_preferred", None)
                c[f"{field}_{kind}"] = split_list(m.group(3))
                msg = f"{field} ({kind}) is now {', '.join(c[f'{field}_{kind}'])}"
        if not msg:
            m = re.search(r"\b(?:only\s+)?(vegetarian|veg|eggetarian|non ?veg)\s+only\b|\bonly\s+(vegetarian|veg|eggetarian)\b", t)
            if m:
                c["food_ok"] = [extract.norm_food(m.group(1) or m.group(2))]
                msg = f"only {c['food_ok'][0].replace('_', ' ')} profiles pass now"
        if not msg:
            return False
        if self.save_criteria(c, "changed in conversation: " + text.strip()) is None:
            return True
        self.say(f"Done - {msg}. Saved as version {self.store.state().get('interests_version')}. "
                 "If that is not right, say 'undo'.")
        self.rescore_and_tell()
        return True

    def rescore_and_tell(self):
        if not self.store.load_profiles():
            return
        r = pipeline.rescore(self.store)
        self.say(f"I re-scored your {r['stored']} saved profile(s) from my notes - no browsing "
                 f"needed: {r['passing']} pass your must-haves, {r['excluded']} do not."
                 + (f" {r['ready_to_show']} you have not seen yet - say 'give me the report'."
                    if r["ready_to_show"] else " Nobody new to show you."))

    # ----- profile lookup -----
    def resolve(self, ref):
        ref = norm(ref)
        ref = re.sub(r"^(the|on|to|for|with|in|number|no|profile|#)\s*", "", ref).strip()
        ref = re.sub(r"\s+(please|thanks|thank you|now|then)$", "", ref).strip()
        words = {"first": "1", "1st": "1", "top": "1", "top one": "1", "first one": "1",
                 "second": "2", "2nd": "2", "second one": "2", "third": "3", "3rd": "3",
                 "third one": "3"}
        ref = words.get(ref, ref)
        profiles = self.store.load_profiles()
        ranks = (self.store.state().get("last_report") or {}).get("ranks") or {}
        if ref.isdigit() and ref in ranks:
            return [ranks[ref]]
        for pid in profiles:
            if pid.lower() == ref:
                return [pid]
        hits = [pid for pid, rec in profiles.items()
                if ref and (rec["data"].get("name") or "").lower().startswith(ref)]
        if not hits:
            hits = [pid for pid, rec in profiles.items()
                    if ref and len(ref) > 2 and ref in (rec["data"].get("name") or "").lower()]
        return hits

    def pick(self, ref):
        hits = self.resolve(ref)
        if not hits:
            self.say(f"I could not find anyone called '{ref.strip()}' in my notes. Try a name, a "
                     "number from your last report (like 2), or a profile ID.")
            return None
        if len(hits) > 1:
            names = [f"{self.store.load_profiles()[h]['data'].get('name')} ({h})" for h in hits]
            ans = self.ask("I found more than one: " + "; ".join(names) + ". Which one? (type the ID)")
            if not ans:
                return None
            hits = [h for h in hits if h.lower() == norm(ans)]
            if not hits:
                self.say("Okay, I left everything as it was.")
                return None
        return hits[0]

    def set_status(self, ref, status):
        pid = self.pick(ref)
        if not pid:
            return
        name = self.store.load_profiles()[pid]["data"].get("name") or pid
        self.store.set_user_status(pid, status)
        if status == "rejected":
            self.say(f"Done - {name} is marked 'pass' and will never be shown to you again. "
                     "This is only in your Scout notes; nothing was sent to the site.")
        else:
            self.say(f"Noted - {name} is marked as interesting. Nothing was sent to the site; if you "
                     "want to send an interest, I can draft a message for you to send yourself.")

    def explain(self, ref):
        pid = self.pick(ref)
        if not pid:
            return
        rec = self.store.load_profiles()[pid]
        j = self.store.load_judgements().get(pid)
        from score import score_profile
        c = self.store.criteria()
        if j and j.get("for_hash") == rec["hash"]:
            res = score_profile(rec["data"], c, qualitative=j["qualitative"], judgement=j["text"])
        else:
            res = score_profile(rec["data"], c)
        name = rec["data"].get("name") or pid
        if res["excluded"]:
            self.say(f"{name} is left out because: " + "; ".join(res["exclude_reasons"]) + ".")
            return
        self.say(f"{name} scores {res['score']}/100: {res['weighted_points']} of 80 points for "
                 f"matching what you set, plus {res['qualitative']} of 20 for the judgement.")
        self.say("Why it fits: " + ("; ".join(res["why_fit"]) or "passes your must-haves") + ".")
        self.say("Judgement: " + res["judgement"])
        if res["risks"]:
            self.say("Risky or unknown: " + "; ".join(res["risks"]) + ".")

    def draft(self, ref):
        pid = self.pick(ref)
        if not pid:
            return
        d = self.store.load_profiles()[pid]["data"]
        first = (d.get("name") or "there").split()[0]
        chat = d.get("chat") or {}
        hook = ""
        if d.get("profession"):
            hook = f" I see you work as a {d['profession'].lower()} - how do you like it?"
        elif d.get("city"):
            hook = f" How do you like living in {d['city']}?"
        if chat.get("exists") and chat.get("open_questions"):
            body = (f"Hi {first}, thank you for your message, and sorry for the slow reply. "
                    f"You {chat['open_questions'][0]} - happy to talk about that.{hook} "
                    "Would you be open to a short call this week?")
        else:
            body = (f"Hi {first}, I came across your profile and liked what you wrote.{hook} "
                    "I would be glad to get to know you a little - would you like to chat?")
        self.say("Here is a draft. It is only a draft - I never send anything myself:")
        self.say("  " + body)
        self.say("If you like it, copy it into the site and send it yourself, or tell me what to change.")

    # ----- report -----
    def report(self):
        if self.store.state().get("scores_stale") and self.store.load_profiles():
            pipeline.rescore(self.store)
        r = pipeline.make_report(self.store)
        if r["status"] == "no_profiles":
            self.say("Your report is empty for now, because I have not read any profiles yet.")
            self.say("Next step: say 'scan' and I will open your matrimony site so you can log in, "
                     f"or put biodata files in {self.store.dir / 'files_to_read'} and say 'read my files'.")
            return
        if r["status"] == "all_excluded":
            reasons = "; ".join(f"{k} ({v})" for k, v in r["excluded"].items())
            self.say("Nothing new to show you. The profiles you have not seen yet still do not pass "
                     f"your must-haves - {reasons}.")
            self.say("If that is too strict, loosen one thing, for example 'change my age range to 25 to 32'.")
            return
        if r["status"] == "nothing_new":
            self.say("Nothing new since your last report - I never repeat profiles you have already "
                     "seen unless they change. Say 'scan' to look for new ones.")
            return
        self.say(r["digest"])
        self.say(f"The full report is saved for sharing with family: {r['markdown']} and {r['excel']} "
                 "(sheets: Ranked Matches, Profile Details, Updated Since Last Report).")
        self.say("You can say 'interested in 1', 'pass on 2', 'why is 1 ranked first', or "
                 "'draft a reply to 1'.")

    # ----- scan -----
    def scan(self, said=""):
        import scan_browser
        if "chrome" in norm(said):
            self.say("I open my own browser window (Chromium, the same engine as Chrome) so your "
                     "everyday Chrome is never touched. You log in there once and it remembers you.")
        c = dict(self.store.criteria())
        if not c:
            self.say("Before I open anything, I need to know what you are looking for.")
            self.intake()
            c = dict(self.store.criteria())
            if not c:
                return
        site = c.get("site")
        if not site:
            ans = self.ask("Which matrimony site should I open? (for example shaadi.com)")
            if not ans or norm(ans) in SKIP:
                self.say("I need the site name to open it, so nothing was opened.")
                return
            key = norm(ans).replace(" com", "")
            c["site"] = site = SITE_NAMES.get(key, ans.strip())
            self.save_criteria(c, "site added before scan")
        paused = self.store.scan_state()
        cap = int(c.get("max_profiles_per_run") or 20)
        if not paused:
            ans = self.ask(f"I will read up to {cap} profiles this time, slowly, like a person would. "
                           "Press Enter to keep that, or type another number (50 at most).")
            if ans is None:
                return
            m = re.search(r"\d+", ans or "")
            if m:
                cap = max(1, min(50, int(m.group())))
                if int(m.group()) > 50:
                    self.say("50 is the most per run, to stay gentle on the site - I will use 50.")
        try:
            result = scan_browser.run_scan(self.store, site, self.ui, cap=cap)
        except scan_browser.ScanError as exc:
            self.say(str(exc))
            return
        except KeyboardInterrupt:
            self.say("Paused. Everything read so far is saved - say 'scan' to carry on from here.")
            return
        except RuntimeError as exc:  # lock held by another run
            self.say(str(exc))
            return
        except Exception as exc:
            self.log_error(exc)
            self.say(f"The browser or the site stopped working ({exc.__class__.__name__}), so I "
                     "paused - your progress is saved; say 'scan' to try again.")
            return
        if result["status"] == "paused":
            self.say(result["message"])
            return
        if result["status"] == "empty":
            self.say("I looked at your pages but could not recognise any profiles on them.")
            if result.get("captures"):
                self.say(f"I saved a short list of the links I saw in {result['captures']} "
                         "(files named diagnostics_...). If you share that with whoever helps you set "
                         "up the Scout, the page layout can be taught - or try 'scan' again and open "
                         "your Matches page yourself when I ask.")
            return
        self.say(f"Done. I read {result['read']} profile(s): {result['new']} new, "
                 f"{result['updated']} changed since last time, {result['unchanged']} unchanged"
                 + (f", {result['unavailable']} no longer on the site" if result.get("unavailable") else "")
                 + ".")
        if result.get("left"):
            self.say(f"I stopped at your cap. {result['left']} more are listed - I will start with "
                     "those next time.")
        if result.get("captures"):
            self.say(f"The page text I read is saved in {result['captures']}.")
        ans = self.ask("Want your top 3 now? (yes / no)")
        if ans and YES.match(norm(ans)):
            self.report()

    # ----- other answers -----
    def status(self):
        c = self.store.criteria()
        profiles = self.store.load_profiles()
        shown = {r["profile_id"] for r in self.store.shown_log()}
        rejected = sum(1 for r in profiles.values() if r.get("user_status") == "rejected")
        liked = sum(1 for r in profiles.values() if r.get("user_status") == "interested")
        st = self.store.state()
        if not c:
            self.say("I do not have your interests yet - say 'lets start' for 5 quick questions.")
        else:
            self.say(f"Your interests (version {st.get('interests_version')}): "
                     + pipeline.criteria_summary(c) + ".")
        self.say(f"I have notes on {len(profiles)} profile(s); you have seen {len(shown)} of them in "
                 f"reports; {liked} marked interesting, {rejected} marked pass.")
        scan = st.get("scan")
        if scan:
            left = len([q for q in scan["queue"] if q["url"] not in scan["done"]])
            self.say(f"A scan is paused at {scan['read']} of up to {scan['cap']} profiles "
                     f"({left} still listed). Say 'scan' to carry on.")
        elif st.get("last_scan"):
            ls = st["last_scan"]
            self.say(f"Last scan finished {ls.get('finished_at', '')[:16].replace('T', ' ')} UTC and "
                     f"read {ls.get('read', 0)} profile(s).")
        else:
            self.say("No scan yet - say 'scan' when you are ready.")
        cal = st.get("calibration") or {}
        if cal:
            self.say("Calibration done for: " + ", ".join(cal) + ".")
        self.say(f"Your data folder: {self.store.dir}")

    def history(self):
        rows = self.store.shown_log()
        if not rows:
            self.say("I have not shown you any profiles yet.")
            return
        by_report = {}
        for r in rows:
            by_report.setdefault(r.get("report_id"), []).append(r.get("name") or r["profile_id"])
        self.say(f"I have shown you {len({r['profile_id'] for r in rows})} different profile(s) so far:")
        for rid, names in list(by_report.items())[-5:]:
            when = (rid or "").replace("report-", "")[:10]
            self.say(f"  {when}: " + ", ".join(names))
        self.say("None of them will be shown again unless their profile or chat changes.")

    def how_read(self):
        self.say("Here is how I read your data, in plain words:")
        self.say("1. When you say 'scan', I open your matrimony site in a separate browser window on "
                 "this laptop. You log in there yourself - I never see or store your password.")
        self.say("2. That window remembers your login (in your data folder), so next time you usually "
                 "just press Enter.")
        self.say("3. I visit your inbox, interests received, matches and search pages slowly, like a "
                 "person, and read the text that is on the screen. I only read - I never click send, "
                 "accept, decline or block.")
        self.say("4. From each profile I note name, age, height, city, education, job, religion, "
                 "community, mother tongue, food and habits, about-me and horoscope if shown. From "
                 "chats I keep only a short summary - who wrote last and what it was about - never a copy.")
        self.say(f"5. Everything is saved in {self.store.dir} on this laptop. You can also give me "
                 f"files: put biodata PDFs, Word or text files, chat exports or broker spreadsheets in "
                 f"{self.store.dir / 'files_to_read'} and say 'read my files'. Screenshots need the AI "
                 "chat version of the Scout.")

    def privacy(self):
        self.say(f"Everything stays on this laptop, in {self.store.dir}. Nothing is uploaded anywhere.")
        self.say("I never ask for, see, or store your password - you log in yourself in the browser "
                 "window. Chats are kept only as short summaries, never full copies.")
        self.say("To delete everything, delete that folder. Nothing is sent on the site without your OK.")

    def read_files(self):
        folder = self.store.dir / "files_to_read"
        folder.mkdir(exist_ok=True)
        got = file_intake.read_folder(self.store, folder, self.store.criteria())
        caps = self.store.dir / "captures"
        if caps.exists():
            cap_got = file_intake.read_folder(self.store, caps, self.store.criteria())
            got["records"] += [r for r in cap_got["records"]
                               if r.get("profile_id") not in self.store.load_profiles()]
        if not got["records"] and not got["skipped"]:
            self.say(f"There are no files to read yet. Put biodata files, chat exports or broker "
                     f"spreadsheets in {folder} and say 'read my files' again.")
            return
        counts = {"new": 0, "updated": 0, "unchanged": 0}
        for rec in got["records"]:
            _, ev = self.store.upsert_profile(rec, source=rec.get("source", "file"))
            counts[ev] += 1
        self.say(f"I read {len(got['records'])} profile(s) from your files: {counts['new']} new, "
                 f"{counts['updated']} updated, {counts['unchanged']} already known.")
        for name, why in got["skipped"]:
            self.say(f"Skipped {name}: {why}.")
        for name, cols in got["unmapped"].items():
            self.say(f"In {name} I did not recognise these columns, so I ignored them: {', '.join(cols)}.")
        if got["records"]:
            self.say("Say 'give me the report' to see how they rank.")

    def demo(self):
        tmp = Path(tempfile.mkdtemp(prefix="scout-demo-"))
        try:
            demo_store = ScoutStore(tmp)
            ex = HERE.parent / "examples"
            demo_store.save_interests(json.loads((ex / "sample_criteria.json").read_text()),
                                      changed_by="demo", reason="demo")
            for p in json.loads((ex / "sample_profiles.json").read_text()):
                demo_store.upsert_profile(p, source=p.get("source", "demo"))
            r = pipeline.make_report(demo_store)
            self.say("Here is a demo on made-up profiles (your real data is not touched):")
            self.say("Demo interests: " + pipeline.criteria_summary(demo_store.criteria()) + ".")
            self.say(r.get("digest") or "The demo had nothing to show.")
            self.say("That is exactly the format you will get. Say 'lets start' to set up your own search.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def help(self):
        self.say("Just talk to me. For example:")
        self.say("  'lets start' - 5 quick questions about what you want")
        self.say("  'scan' or 'open the app' - open your site, you log in, I read your profiles")
        self.say("  'give me the report' - your top 3, plus a report and Excel sheet for family")
        self.say("  'change my age range to 26 to 30', 'add Pune to my places', 'my dealbreaker is smoking'")
        self.say("  'interested in 1', 'pass on Divya', 'why is 1 ranked first', 'draft a reply to 1'")
        self.say("  'what did you show me before', 'check status', 'read my files', 'refine my criteria'")
        self.say("  'how can you read the data?', 'show me a demo', 'quit'")

    def log_error(self, exc):
        try:
            with open(self.store.dir / "scout_errors.log", "a", encoding="utf-8") as f:
                f.write(f"--- {datetime.now().isoformat()}\n{traceback.format_exc()}\n")
        except Exception:
            pass

    # ----- intent routing -----
    INTENTS = [
        ("quit", r"^(quit|exit|bye|bye bye|goodbye|good bye|close|close the app|thats all|that is all|"
                 r"done|done for today|see you|stop|q)$"),
        ("undo", r"^(undo|undo that|put it back|go back)$"),
        ("help", r"^(help|menu|options|commands|what now|now what|what next|what can i say)$"
                 r"|\bwhat can you do\b|\bhow do i use\b"),
        ("how_read", r"\bhow\b.*\b(read|get|access|see|collect|fetch|pull|look at)\b.*"
                     r"\b(data|profiles?|account|site|chats?|matches|info|information|inbox)\b"
                     r"|\bhow does (this|it|the scout) work\b"),
        ("privacy", r"\b(privacy|private|password|is my data|safe|secure|security|where is my data|"
                    r"where do you (keep|store)|delete my data)\b"),
        ("demo", r"\bdemo\b|\bshow me an example\b|\bsample run\b"),
        ("change", r"\bage\b.*\d{2}.*\d{2}|^(change|set|update|make|add|include|remove|drop|delete|"
                   r"take out|switch)\b|\bdeal ?breaker\b|\bmin(imum)? education\b|\bmother tongue\b"
                   r"|\b(veg|vegetarian|eggetarian) only\b|\bonly (veg|vegetarian)\b|\bprofiles per\b"),
        ("refine", r"\b(refine|fine ?tune|more questions|full intake|detailed questions|ask me more)\b"),
        ("mark", r"\bmark\s+(.*?)\s*(?:as\s+)?(interested|interesting|liked|a like|rejected|reject|"
                 r"pass|passed|not interested|no)$"),
        ("scan", r"\b(scan|scanning|run (the |my )?(matrimony )?scout|start (the )?(scout|scan|search)|"
                 r"(open|launch|start|use)\s+(up\s+)?(the |my |a )?(app|site|website|web site|browser|"
                 r"chrome|chromium|account|shaadi|shaadi com|matrimony( site| app)?)|"
                 r"(check|visit|go to|look at|browse|read|search)\s+(the |my )?(website|web site|site|shaadi|"
                 r"shaadi com|account|matrimony( site| app)?|profiles|chats|inbox|matches|interests)|"
                 r"log ?in|sign ?in|find (new |more |me )?matches|carry on|resume|continue( the scan)?)\b"),
        ("start", r"^(start again|restart|redo|start over)\b|\b(lets|let us)\s+(start|begin|go|get started)\b"
                  r"|^(start|begin|get started|set up|setup|ok start|yes start)\b"
                  r"|^(hi|hello|hey|namaste|hii|good (morning|evening|afternoon))\b"),
        ("why", r"\bwhy (is|was|did|does)\s+(.+?)\s+(ranked|rank|first|top|score|scored|at)\b"),
        ("draft", r"\b(draft|write|compose)\b.*\b(reply|message|note|intro)\b.*\b(to|for)\s+(.+)$"
                  r"|\breply to\s+(.+)$"),
        ("report", r"\b(report|excel|sheet|spreadsheet|shortlist|top ?3|top three|results|"
                   r"(show|see|give)( me)?( my)? (best |top )?matches|best matches|ranked|ranking)\b"),
        ("history", r"\b(what did you show|shown me|show(ed)? me before|history|already seen|seen before|"
                    r"previous report|last report)\b"),
        ("status", r"\b(status|progress|how many|where are we|whats happening|how far)\b"),
        ("reject", r"\b(reject|pass on|not interested in|no to|skip|hide|never show)\s+(.+)$"),
        ("interested", r"\b(interested in|i like|i liked|keep|pin|yes to|like)\s+(.+)$"),
        ("forget", r"\bforget\s+(.+)$"),
        ("show_interests", r"\b(interests|preferences|criteria|settings|filters|what i want)\b"),
        ("read_files", r"\b(read|import|load|add|check)\b.*\b(files?|biodata|pdfs?|spreadsheets?|"
                       r"captures?|folder|documents?)\b"),
        ("rescore", r"\b(re ?score|recalculate|score again)\b"),
        ("thanks", r"^(thanks|thank you|ok|okay|cool|great|nice|fine|good|got it|alright)\b"),
    ]

    def route(self, text):
        t = norm(text)
        for name, pat in self.INTENTS:
            m = re.search(pat, t)
            if m:
                return name, m, t
        return None, None, t

    def handle(self, text):
        name, m, t = self.route(text)
        if name == "quit":
            return False
        if name not in ("help", "how_read", "privacy", "demo", "thanks", None) and not self.interests_ok():
            return True
        if name == "undo":
            if self.undo_criteria is None:
                self.say("There is nothing to undo right now.")
            else:
                prev, self.undo_criteria = self.undo_criteria, None
                self.store.save_interests(prev, changed_by="user", reason="undo")
                self.say("Undone. " + pipeline.criteria_summary(prev) + ".")
                self.rescore_and_tell()
        elif name == "help":
            self.help()
        elif name == "how_read":
            self.how_read()
        elif name == "privacy":
            self.privacy()
        elif name == "demo":
            self.demo()
        elif name == "change":
            if not self.apply_change(text):
                self.say("I did not quite get that change. Try 'change my age range to 26 to 30', "
                         "'add Pune to my places', or 'my dealbreaker is smoking'.")
        elif name == "refine":
            self.refine()
        elif name == "scan":
            self.scan(text)
        elif name == "start":
            restart = bool(re.match(r"^(start again|restart|redo|start over)", t))
            if self.store.criteria() and not restart:
                self.say("You are already set up: " + pipeline.criteria_summary(self.store.criteria()) + ".")
                self.say("Say 'scan' to read your profiles, 'give me the report', or 'start again' to "
                         "redo the 5 questions.")
            else:
                self.intake()
        elif name == "report":
            self.report()
        elif name == "history":
            self.history()
        elif name == "status":
            self.status()
        elif name == "why":
            self.explain(m.group(2))
        elif name == "draft":
            self.draft(m.group(4) or m.group(5) or "")
        elif name == "mark":
            who, verdict = m.group(1).strip(), m.group(2)
            status = "interested" if verdict in ("interested", "interesting", "liked", "a like") else "rejected"
            if not self.store.load_profiles():
                self.say("I have not read any profiles yet, so there is nobody to mark. Say 'scan' first.")
            elif not who or re.fullmatch(r"(someone|somebody|a profile|one|them|her|him|a person|"
                                         r"profile|person|anyone)", who):
                ans = self.ask("Who should I mark? Say a name, or a number from your last report "
                               "(like 1).")
                if ans and norm(ans) not in SKIP:
                    self.set_status(ans, status)
            else:
                self.set_status(who, status)
        elif name == "reject":
            self.set_status(m.group(2), "rejected")
        elif name == "interested":
            self.set_status(m.group(2), "interested")
        elif name == "forget":
            pid = self.pick(m.group(1))
            if pid and YES.match(norm(self.ask(f"Delete everything I noted about {pid}? (yes / no)") or "")):
                self.store.forget_profile(pid)
                self.say("Deleted from my notes.")
        elif name == "show_interests":
            c = self.store.criteria()
            self.say(("Your interests: " + pipeline.criteria_summary(c) + ".") if c else
                     "I do not have your interests yet - say 'lets start'.")
        elif name == "read_files":
            self.read_files()
        elif name == "rescore":
            if self.store.load_profiles():
                self.rescore_and_tell()
            else:
                self.say("There is nothing to re-score yet - I have not read any profiles.")
        elif name == "thanks":
            self.say("You are welcome. What next - 'scan', 'give me the report', or 'quit'?")
        elif re.search(r"\b(website|site|browser|chrome|shaadi|online|account|profiles?)\b", t):
            ans = self.ask("Do you want me to open your matrimony site and read your profiles? (yes / no)")
            if ans and YES.match(norm(ans)):
                self.scan(text)
            else:
                self.say("Okay. Say 'help' to see what I can do.")
        else:
            self.say("Sorry, I did not catch that. You can say things like 'scan', 'give me the report', "
                     "'check status', 'change my age range to 26 to 30', or 'help'.")
        return True

    def greet(self):
        self.say("Hi, I am your Matrimony Match Scout. Talk to me in plain English - no commands to learn.")
        if not self.interests_ok():
            return
        c = self.store.criteria()
        if not c:
            self.say(f"Your data will stay in {self.store.dir} on this laptop.")
            self.say("Say 'lets start' and I will ask 5 quick questions, or 'show me a demo' to see "
                     "what you will get first.")
            return
        self.say("Welcome back. " + "Your interests: " + pipeline.criteria_summary(c) + ".")
        if self.store.scan_state():
            self.say("Your last scan was paused - say 'scan' and I will carry on from where it stopped.")
        self.say("Say 'scan', 'give me the report', 'check status', or 'help'.")

    def loop(self):
        self.greet()
        while True:
            text = self.ask()
            if text is None:
                break
            if not text.strip():
                continue
            try:
                if not self.handle(text):
                    break
            except KeyboardInterrupt:
                self.say("Stopped that. Your data is saved.")
            except Exception as exc:
                self.log_error(exc)
                self.say(f"Sorry, something went wrong while doing that ({exc.__class__.__name__}). "
                         "Your saved data is safe - try again, or say 'help'.")
        self.say("Saved everything. Next time I will pick up exactly where we stopped. Bye!")


# ---------------- internal actions (AI layer) ----------------

def internal(store, args):
    cmd, rest = args[0], args[1:]
    out = None
    if cmd == "status":
        try:
            data, ext = store.load_interests()
            err = None
        except InterestsFileError as exc:
            data, ext, err = None, False, str(exc)
        st = store.state()
        out = {"has_interests": bool(data), "interests_version": (data or {}).get("version"),
               "interests_hand_edited": ext, "interests_file_error": err,
               "hand_edit_diff": store.external_edit_diff() if ext else [],
               "profiles_seen": len(store.load_profiles()), "shown": len(store.shown_log()),
               "paused_scan": st.get("scan"), "last_scan": st.get("last_scan"),
               "chat_checkpoint": store.load_checkpoint(),
               "calibration": st.get("calibration"), "scores_stale": st.get("scores_stale"),
               "recovered_files": store.recovered, "data_dir": str(store.dir)}
    elif cmd == "interests":
        c = store.criteria()
        out = {"criteria": c, "summary": pipeline.criteria_summary(c)}
    elif cmd == "save-interests":
        crit = json.loads(Path(rest[0]).read_text(encoding="utf-8"))
        saved = store.save_interests(crit.get("criteria", crit), changed_by="user (via AI chat)",
                                     reason="saved in chat", allow_over_external="--confirm-hand-edit" in rest)
        out = {"version": saved["version"], "rescore": pipeline.rescore(store)}
    elif cmd == "hand-edit":
        out = {"accepted": bool(store.accept_external_edit())} if rest[0] == "accept" \
            else {"reverted": bool(store.revert_external_edit())}
    elif cmd == "ingest":
        items = json.loads(Path(rest[0]).read_text(encoding="utf-8"))
        counts = {"new": 0, "updated": 0, "unchanged": 0}
        for item in items if isinstance(items, list) else [items]:
            q = item.pop("qualitative", None)
            j = item.pop("ai_judgement", None)
            rec, ev = store.upsert_profile(item, source=item.get("source", "scan"))
            counts[ev] += 1
            if q is not None:
                store.save_judgement(rec["profile_id"], q, j or "", by="ai")
        out = counts
    elif cmd == "judge":
        for j in json.loads(Path(rest[0]).read_text(encoding="utf-8")):
            store.save_judgement(j["profile_id"], j.get("qualitative", 0), j.get("text", ""), by="ai")
        out = {"saved": True}
    elif cmd in ("report", "build-report"):
        if store.state().get("scores_stale"):
            pipeline.rescore(store)
        r = pipeline.make_report(store, mark_shown="--preview" not in rest)
        r.pop("rows", None)
        out = r
    elif cmd == "rescore":
        out = pipeline.rescore(store)
    elif cmd == "checkpoint":
        if rest[0] == "save":
            cp = json.loads(Path(rest[1]).read_text(encoding="utf-8"))
            store.save_checkpoint(cp.get("phase"), cp.get("cursors"), cp.get("run_id"))
        elif rest[0] == "clear":
            store.clear_checkpoint()
        out = store.load_checkpoint()
    elif cmd == "history":
        out = store.shown_log()
    elif cmd == "set-status":
        store.set_user_status(rest[0], rest[1])
        out = {"profile_id": rest[0], "status": rest[1]}
    elif cmd == "extract":
        url = rest[rest.index("--url") + 1] if "--url" in rest else None
        out = extract.extract_profile(Path(rest[0]).read_text(encoding="utf-8"), url=url)
    elif cmd == "read-files":
        got = file_intake.read_folder(store, rest[0], store.criteria())
        out = {"records": got["records"], "skipped": got["skipped"], "unmapped": got["unmapped"]}
    else:
        print(f"Unknown internal action: {cmd}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0


def main(argv):
    raw = argv[1:]
    data_dir = DEFAULT_DATA
    if "--data-dir" in raw:
        i = raw.index("--data-dir")
        data_dir = Path(raw[i + 1]).expanduser()
        raw = raw[:i] + raw[i + 2:]
    try:
        store = ScoutStore(data_dir)
    except OSError:
        print(f"Scout: I cannot use the folder {data_dir} - please choose another with --data-dir.")
        return 1
    if raw:
        try:
            return internal(store, raw)
        except (ExternalEditPending, InterestsFileError) as exc:
            print(json.dumps({"error": "interests_hand_edited" if isinstance(exc, ExternalEditPending)
                              else "interests_file_broken", "message": str(exc),
                              "next": "show the user the change and run 'hand-edit accept' or "
                                      "'hand-edit revert' after they decide"}, indent=2))
            return 3
        except (KeyError, IndexError, FileNotFoundError, json.JSONDecodeError) as exc:
            print(json.dumps({"error": exc.__class__.__name__, "message": str(exc)}, indent=2))
            return 4
    try:
        Scout(store).loop()
    except KeyboardInterrupt:
        print("\nScout: Saved everything. Bye!")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
