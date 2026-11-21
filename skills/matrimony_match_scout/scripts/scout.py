"""
Matrimony Match Scout - actions for the Muse skill (JSON out).

Muse drives the browser and the conversation; these actions keep the memory,
scoring and reports deterministic. Never show the JSON to the user.

  scout.py --data-dir D status | interests | history | rescore | demo
  scout.py --data-dir D save-interests FILE.json [--confirm-hand-edit]
  scout.py --data-dir D hand-edit accept|revert
  scout.py --data-dir D scan-start [--cap N] [--user-asked] [--list-pages K] [--no-calibration]
                 (default 5; max 10 per run; above 10 only with --user-asked, max 50)
  scout.py --data-dir D ingest FILE.json        (schema records; returns progress + time left)
  scout.py --data-dir D scan-progress | scan-end
  scout.py --data-dir D judge FILE.json         ([{profile_id, qualitative, text}])
  scout.py --data-dir D report [--preview]      (top 3 + md + xlsx; marks shown)
  scout.py --data-dir D set-status ID interested|rejected|contacted|new
  scout.py --data-dir D explain ID              (why a profile scores what it does)
  scout.py --data-dir D seen URL_OR_ID ...      (already read? when? - pick "the next 5")
  scout.py --data-dir D mark-unavailable ID     (deleted / hidden on the site)
  scout.py --data-dir D forget ID               (delete that record)
  scout.py --data-dir D extract FILE.txt [--url URL]
  scout.py --data-dir D read-files FOLDER
  scout.py --data-dir D checkpoint save FILE.json | clear   ({phase, cursors, run_id})
Data folder default: $SCOUT_DATA_DIR or ~/matrimony-scout-data
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import extract  # noqa: E402
import file_intake  # noqa: E402
import pipeline  # noqa: E402
import timing  # noqa: E402
from state_store import ExternalEditPending, InterestsFileError, ScoutStore  # noqa: E402

DEFAULT_DATA = Path(os.environ.get("SCOUT_DATA_DIR") or "~/matrimony-scout-data").expanduser()


def _opt(rest, name, default=None, cast=str):
    return cast(rest[rest.index(name) + 1]) if name in rest else default


def demo():
    tmp = Path(tempfile.mkdtemp(prefix="scout-demo-"))
    try:
        s = ScoutStore(tmp)
        ex = HERE.parent / "examples"
        s.save_interests(json.loads((ex / "sample_criteria.json").read_text()), "demo", "demo")
        for p in json.loads((ex / "sample_profiles.json").read_text()):
            s.upsert_profile(p, source=p.get("source", "demo"))
        r = pipeline.make_report(s)
        return {"interests": pipeline.criteria_summary(s.criteria()), "digest": r.get("digest")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
               "scan_in_progress": st.get("progress"),
               "chat_checkpoint": store.load_checkpoint(),
               "scores_stale": st.get("scores_stale"),
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
        prog = timing.tick(store, sum(counts.values()))
        if prog:
            out["progress"] = prog
    elif cmd == "scan-start":
        saved = store.criteria().get("max_profiles_per_run")
        cap = _opt(rest, "--cap", None, int)
        user_asked = "--user-asked" in rest
        if cap is None and saved:
            cap, user_asked = int(saved), True  # a number the person saved themselves
        out = timing.start(store, cap, _opt(rest, "--list-pages", 4, int),
                           "--no-calibration" not in rest, user_asked=user_asked)
    elif cmd == "scan-progress":
        p = store.state().get("progress")
        out = timing.tick(store, 0) if p else {"say": "No scan is running."}
    elif cmd == "scan-end":
        out = timing.finish(store)
    elif cmd == "demo":
        out = demo()
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
    elif cmd == "explain":
        from score import score_profile
        rec = store.load_profiles()[rest[0]]
        j = store.load_judgements().get(rest[0])
        if j and j.get("for_hash") == rec["hash"]:
            res = score_profile(rec["data"], store.criteria(), j["qualitative"], j["text"])
        else:
            res = score_profile(rec["data"], store.criteria())
        out = {"name": rec["data"].get("name"), "user_status": rec.get("user_status"), **res}
    elif cmd == "seen":
        profiles = store.load_profiles()
        out = {}
        for ref in rest:
            hits = store.find(ref)
            rec = profiles[hits[0]] if len(hits) == 1 else None
            out[ref] = {"seen": bool(rec), "profile_id": rec and rec["profile_id"],
                        "last_seen": rec and rec.get("last_seen"),
                        "user_status": rec and rec.get("user_status"),
                        "ambiguous": len(hits) > 1}
    elif cmd == "mark-unavailable":
        store.mark_unavailable(rest[0])
        out = {"profile_id": rest[0], "available": False}
    elif cmd == "forget":
        out = {"profile_id": rest[0], "forgotten": store.forget_profile(rest[0])}
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
    if not raw:
        print(__doc__)
        return 0
    try:
        store = ScoutStore(data_dir)
    except OSError:
        print(json.dumps({"error": "data_dir", "message": f"Cannot use folder {data_dir}"}))
        return 1
    try:
        return internal(store, raw)
    except (ExternalEditPending, InterestsFileError) as exc:
        print(json.dumps({"error": "interests_hand_edited" if isinstance(exc, ExternalEditPending)
                          else "interests_file_broken", "message": str(exc),
                          "next": "show the user the change and run 'hand-edit accept' or "
                                  "'hand-edit revert' after they decide"}, indent=2))
        return 3
    except (KeyError, IndexError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": exc.__class__.__name__, "message": str(exc)}, indent=2))
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
