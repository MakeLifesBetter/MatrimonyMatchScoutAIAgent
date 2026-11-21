"""
Matrimony Match Scout - persistence / memory layer (stdlib only).

Everything the Scout knows lives in ONE user-owned data folder
(never inside the skill folder):

  interests.json          your criteria. Human-editable. Source of truth.
  interests_history.jsonl every change to your interests (who, when, what, why)
  profiles.json           every profile ever seen, deduped, with content hash
  judgements.json         AI / rule-based judgement per profile (kept apart so
                          a new judgement never makes a profile look "changed")
  shared_log.jsonl        every profile ever SHOWN to you, with hash at that time
  run_state.json          checkpoint: scan queue + cursor, calibration, flags
  scout.lock              single-run lock (stale after 2 hours)
  captures/<date>/        page text of matches / search / profile pages
                          (chat pages are never saved - only short summaries)
  reports/<date>/         digest.txt, report.md, report.xlsx

Rules baked in:
  - Atomic writes (tmp + fsync + rename) with a .bak of the previous copy.
  - A corrupt DATA file is restored from .bak and the recovery is reported.
  - interests.json is YOURS: a hand edit is detected by hash and must be
    confirmed (accept or undo) before anything else is saved over it.
    A broken hand edit is never auto-replaced either.
  - A profile is shown again ONLY if its content changed since it was last
    shown, with a field-level diff against what you saw.
  - Rejected profiles never come back, even if they change.
"""
import hashlib
import json
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

# Fields that never make a profile count as "changed".
VOLATILE_FIELDS = {"last_active", "views", "online_now", "source", "source_detail",
                   "captured_at", "qualitative", "ai_judgement", "photo_count"}
LOCK_STALE_SECONDS = 2 * 3600
USER_STATUSES = ("new", "interested", "rejected", "contacted")


class InterestsFileError(Exception):
    """interests.json exists but cannot be read (usually a hand-edit typo)."""


class ExternalEditPending(Exception):
    """interests.json was edited by hand and the user has not confirmed it yet."""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_obj(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def profile_fingerprint(profile):
    """Stable ID when a site shows no profile ID."""
    keys = ("name", "age", "city", "education")
    return "fp_" + hash_obj({k: str(profile.get(k, "")).lower().strip() for k in keys})[:16]


def _clean(profile):
    return {k: v for k, v in profile.items()
            if k not in VOLATILE_FIELDS and not k.startswith("_")}


def profile_content_hash(profile):
    return hash_obj(_clean(profile))


def _flatten(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def field_diff(old, new):
    """Field-level diff, nested dicts flattened (chat.last_message_by ...)."""
    a, b = _flatten(_clean(old or {})), _flatten(_clean(new or {}))
    diff = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            diff.append({"field": k, "from": a.get(k), "to": b.get(k)})
    return diff


def _empty(v):
    return v is None or v == "" or v == [] or v == {}


def merge_profile(old, new):
    """New sighting merged over the stored record. A source that does not
    show a field (None) never erases a value another source showed."""
    merged = deepcopy(old)
    for k, v in new.items():
        if k == "chat":
            if isinstance(v, dict) and v.get("exists") is not None:
                merged["chat"] = v
            continue
        if not _empty(v):
            merged[k] = v
    return merged


class ScoutStore:
    def __init__(self, data_dir):
        self.dir = Path(data_dir).expanduser()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.interests_path = self.dir / "interests.json"
        self.profiles_path = self.dir / "profiles.json"
        self.judgements_path = self.dir / "judgements.json"
        self.shared_path = self.dir / "shared_log.jsonl"
        self.history_path = self.dir / "interests_history.jsonl"
        self.state_path = self.dir / "run_state.json"
        self.recovered = []

    # ---------- low-level atomic IO ----------
    def _atomic_write_json(self, path, data, backup=True):
        tmp = path.with_suffix(path.suffix + ".tmp")
        if backup and path.exists():
            try:
                json.loads(path.read_text(encoding="utf-8"))
                path.with_suffix(path.suffix + ".bak").write_bytes(path.read_bytes())
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # never back up a broken file over a good backup
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _read_json(self, path, default):
        if not path.exists():
            return deepcopy(default)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            backup = path.with_suffix(path.suffix + ".bak")
            if backup.exists():
                data = json.loads(backup.read_text(encoding="utf-8"))
                self.recovered.append(path.name)
                self._atomic_write_json(path, data, backup=False)
                return data
            raise

    def _append_jsonl(self, path, row):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _read_jsonl(self, path):
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a half-written last line after a crash
        return rows

    def state(self):
        return self._read_json(self.state_path, {})

    def update_state(self, **kv):
        st = self.state()
        st.update(kv)
        self._atomic_write_json(self.state_path, st)
        return st

    @contextmanager
    def lock(self):
        lock_path = self.dir / "scout.lock"
        fd = None
        try:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                age = time.time() - lock_path.stat().st_mtime
                if age < LOCK_STALE_SECONDS:
                    raise RuntimeError("Another Scout run is already working in this data folder. "
                                       "If none is running, delete the file scout.lock in it.")
                lock_path.unlink()
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, now_iso().encode())
            yield
        finally:
            if fd is not None:
                os.close(fd)
                lock_path.unlink(missing_ok=True)

    # ---------- interests (criteria) ----------
    def _raw_interests(self):
        if not self.interests_path.exists():
            return None
        text = self.interests_path.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InterestsFileError(
                f"Your interests file has a typo near line {exc.lineno}, column {exc.colno} "
                f"({exc.msg}).") from None
        if not isinstance(data, dict):
            raise InterestsFileError("Your interests file is not in the expected shape.")
        if "criteria" not in data:  # user rewrote it as a flat dict - accept that shape
            data = {"version": None, "criteria": data}
        return data

    def load_interests(self):
        """Returns (interests, externally_edited). Raises InterestsFileError."""
        data = self._raw_interests()
        if data is None:
            return None, False
        known = self.state().get("interests_hash")
        externally_edited = known is not None and known != hash_obj(data.get("criteria") or {})
        return data, externally_edited

    def criteria(self):
        data, _ = self.load_interests()
        return dict((data or {}).get("criteria") or {})

    def external_edit_diff(self):
        data, ext = self.load_interests()
        if not ext:
            return []
        return field_diff(self.state().get("interests_snapshot") or {}, data.get("criteria") or {})

    def save_interests(self, criteria, changed_by, reason="", allow_over_external=False):
        old = None
        try:
            old, ext = self.load_interests()
        except InterestsFileError:
            if not allow_over_external:
                raise
            ext = False
        if ext and not allow_over_external:
            raise ExternalEditPending("interests.json was edited by hand; confirm it first.")
        prev_criteria = (old or {}).get("criteria") or self.state().get("interests_snapshot") or {}
        version = int((old or {}).get("version") or self.state().get("interests_version") or 0) + 1
        data = {"_comment": "Your Scout interests. You may edit this file by hand; "
                            "the Scout will notice and ask you to confirm the change.",
                "version": version, "updated_at": now_iso(),
                "updated_by": changed_by, "criteria": criteria}
        self._atomic_write_json(self.interests_path, data)
        self.update_state(interests_hash=hash_obj(criteria), interests_version=version,
                          interests_snapshot=deepcopy(criteria),
                          scores_stale=bool(old or prev_criteria))
        self._append_jsonl(self.history_path, {
            "at": now_iso(), "version": version, "changed_by": changed_by,
            "reason": reason, "diff": field_diff(prev_criteria, criteria)})
        return data

    def accept_external_edit(self):
        data, ext = self.load_interests()
        if not ext:
            return data
        return self.save_interests(data.get("criteria") or {}, changed_by="user (edited the file)",
                                   reason="hand edit confirmed", allow_over_external=True)

    def revert_external_edit(self):
        """User said no to the hand edit: put back the last confirmed version.
        The hand-edited file is kept next to it, never thrown away."""
        snap = self.state().get("interests_snapshot")
        if snap is None:
            return None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if self.interests_path.exists():
            self.interests_path.rename(self.dir / f"interests.hand-edit-{stamp}.json")
        return self.save_interests(snap, changed_by="user", reason="hand edit undone",
                                   allow_over_external=True)

    def restore_interests_backup(self):
        """Broken hand edit: keep the broken file aside and put back the LAST
        CONFIRMED interests (the snapshot), falling back to the .bak copy."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = self.interests_path.with_suffix(".json.bak")
        if self.interests_path.exists():
            self.interests_path.rename(self.dir / f"interests.broken-{stamp}.json")
        snap = self.state().get("interests_snapshot")
        if snap is not None:
            return self.save_interests(snap, "user", "restored after a broken hand edit",
                                       allow_over_external=True)
        if bak.exists():
            os.replace(bak, self.interests_path)
            data = json.loads(self.interests_path.read_text(encoding="utf-8"))
            self.update_state(interests_hash=hash_obj(data.get("criteria") or {}),
                              interests_snapshot=data.get("criteria") or {})
            return data
        return None

    # ---------- profiles / dedupe ----------
    def load_profiles(self):
        return self._read_json(self.profiles_path, {})

    _load_profiles = load_profiles  # backwards compatible name

    def upsert_profile(self, profile, source):
        """Returns (record, event) where event is new | updated | unchanged."""
        profiles = self.load_profiles()
        profile = deepcopy(profile)
        pid = profile.get("profile_id") or profile_fingerprint(profile)
        profile["profile_id"] = pid
        if pid not in profiles:
            rec = {"profile_id": pid, "data": profile, "hash": profile_content_hash(profile),
                   "first_seen": now_iso(), "last_seen": now_iso(),
                   "sources": [source], "user_status": "new", "available": True}
            profiles[pid] = rec
            self._atomic_write_json(self.profiles_path, profiles)
            return rec, "new"
        rec = profiles[pid]
        rec["last_seen"] = now_iso()
        if source not in rec["sources"]:
            rec["sources"].append(source)
        merged = merge_profile(rec["data"], profile)
        new_hash = profile_content_hash(merged)
        if rec["hash"] != new_hash:
            rec["diff_from_last"] = field_diff(rec["data"], merged)
            rec["data"] = merged
            rec["hash"] = new_hash
            event = "updated"
        else:
            event = "unchanged"
        rec["available"] = True
        profiles[pid] = rec
        self._atomic_write_json(self.profiles_path, profiles)
        return rec, event

    def mark_unavailable(self, profile_id):
        profiles = self.load_profiles()
        if profile_id in profiles:
            profiles[profile_id]["available"] = False
            self._atomic_write_json(self.profiles_path, profiles)

    def set_user_status(self, profile_id, status):
        if status not in USER_STATUSES:
            raise ValueError(f"unknown status {status}")
        profiles = self.load_profiles()
        profiles[profile_id]["user_status"] = status  # KeyError if unknown id
        profiles[profile_id]["status_at"] = now_iso()
        self._atomic_write_json(self.profiles_path, profiles)

    def forget_profile(self, profile_id):
        profiles = self.load_profiles()
        if profiles.pop(profile_id, None) is not None:
            self._atomic_write_json(self.profiles_path, profiles)
            self._append_jsonl(self.shared_path, {"at": now_iso(), "profile_id": profile_id,
                                                  "forgotten": True, "hash": None})
            return True
        return False

    # ---------- judgements (AI or rule-based, never part of the hash) ----------
    def load_judgements(self):
        return self._read_json(self.judgements_path, {})

    def save_judgement(self, profile_id, qualitative, text, by="ai"):
        j = self.load_judgements()
        prof = self.load_profiles().get(profile_id) or {}
        j[profile_id] = {"qualitative": max(0, min(20, int(qualitative or 0))),
                         "text": (text or "")[:400], "by": by,
                         "for_hash": prof.get("hash"), "at": now_iso()}
        self._atomic_write_json(self.judgements_path, j)

    # ---------- shown log / no-repeat ----------
    def shown_log(self):
        return [r for r in self._read_jsonl(self.shared_path) if not r.get("forgotten")]

    def _last_shared_hashes(self):
        last = {}
        for row in self._read_jsonl(self.shared_path):
            last[row["profile_id"]] = row.get("hash")
        return last

    def digest_candidates(self):
        """Only these may appear in a new report: never shown, or changed since
        last shown. Rejected and unavailable are always left out."""
        shared = self._last_shared_hashes()
        out = {"new": [], "updated": []}
        for pid, rec in self.load_profiles().items():
            if not rec.get("available", True) or rec.get("user_status") == "rejected":
                continue
            if pid not in shared or shared[pid] is None:
                out["new"].append(rec)
            elif shared[pid] != rec["hash"]:
                out["updated"].append(rec)
        return out

    def diff_since_shown(self, profile_id):
        rec = self.load_profiles().get(profile_id) or {}
        return field_diff(rec.get("data_when_shown") or {}, rec.get("data") or {})

    def mark_shared(self, profile_ids, report_id):
        profiles = self.load_profiles()
        for pid in profile_ids:
            if pid in profiles:
                self._append_jsonl(self.shared_path, {
                    "at": now_iso(), "report_id": report_id, "profile_id": pid,
                    "name": profiles[pid]["data"].get("name"), "hash": profiles[pid]["hash"]})
                profiles[pid]["data_when_shown"] = deepcopy(profiles[pid]["data"])
        self._atomic_write_json(self.profiles_path, profiles)

    # ---------- scan checkpoint (resume, never restart) ----------
    def scan_state(self):
        return self.state().get("scan")

    def start_scan(self, site, cap, run_id=None):
        scan = {"run_id": run_id or datetime.now().strftime("run-%Y%m%d-%H%M%S"),
                "site": site, "cap": cap, "queue": [], "done": [], "read": 0,
                "phase": "DISCOVER", "started_at": now_iso(), "checkpoint_at": now_iso()}
        self.update_state(scan=scan)
        return scan

    def save_scan(self, scan):
        scan["checkpoint_at"] = now_iso()
        self.update_state(scan=scan)

    def finish_scan(self, summary):
        st = self.state()
        st.pop("scan", None)
        st["last_scan"] = dict(summary, finished_at=now_iso())
        self._atomic_write_json(self.state_path, st)

    # Legacy simple checkpoint API (kept for older callers / the AI layer)
    def save_checkpoint(self, phase, cursors=None, run_id=None):
        self.update_state(phase=phase, cursors=cursors or {}, run_id=run_id,
                          checkpoint_at=now_iso())

    def load_checkpoint(self):
        st = self.state()
        return {k: st.get(k) for k in ("phase", "cursors", "run_id", "checkpoint_at")}

    def clear_checkpoint(self):
        st = self.state()
        for k in ("phase", "cursors", "run_id", "checkpoint_at"):
            st.pop(k, None)
        self._atomic_write_json(self.state_path, st)
