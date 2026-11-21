"""
Matrimony Match Scout - how long will this take? (for the Muse browser scan)

An AI browsing a site is slower than a person clicking: each profile means
opening the page, reading it, extracting it and saving it. These are the
STARTING estimates; once a few profiles are done, the real measured pace is
used instead, so "time left" gets more accurate as the scan goes.

  resolve_cap(requested, user_asked) -> how many profiles this run may read
  estimate(profiles, list_pages)  -> minutes (low, high) before starting
  start(store, cap, list_pages)   -> saves the start time, returns the estimate

How many profiles per run:
  - default 5 (a short run, about 5-10 minutes)
  - at most 10 per run, unless the PERSON asks for more in this conversation
    (or saved a bigger number themselves as max_profiles_per_run)
  - never more than 50, even when asked
  tick(store, n)                  -> after each saved profile: read, left, time left
  finish(store)                   -> total time taken
"""
import math
import time

SECONDS_PER_PROFILE = (30, 60)    # open + read + extract + save, at a human pace
SECONDS_PER_LIST_PAGE = (20, 40)  # inbox, interests received, matches, search
SECONDS_CALIBRATION = (60, 120)   # the one-profile check with the user
MEASURE_AFTER = 3                 # switch to the real pace after this many profiles
DEFAULT_CAP = 5     # every run, unless the person picks another number
RUN_MAX = 10        # the most per run without the person asking for more
HARD_CAP = 50       # the most per run, ever


def _mins(seconds):
    return max(1, math.ceil(seconds / 60))


def fmt(lo, hi=None):
    if hi is None or hi == lo:
        return f"about {lo} minute{'s' if lo != 1 else ''}"
    return f"about {lo}-{hi} minutes"


def estimate(profiles, list_pages=4, calibration=True):
    lo = profiles * SECONDS_PER_PROFILE[0] + list_pages * SECONDS_PER_LIST_PAGE[0]
    hi = profiles * SECONDS_PER_PROFILE[1] + list_pages * SECONDS_PER_LIST_PAGE[1]
    if calibration:
        lo, hi = lo + SECONDS_CALIBRATION[0], hi + SECONDS_CALIBRATION[1]
    return _mins(lo), _mins(hi)


def resolve_cap(requested=None, user_asked=False):
    """-> (cap, note). Only the person can lift the run above 10, never above 50."""
    if requested is None:
        return DEFAULT_CAP, ""
    requested = max(1, int(requested))
    if requested <= RUN_MAX:
        return requested, ""
    if not user_asked:
        return RUN_MAX, (f"I will read {RUN_MAX} this run - that is the most per run unless you "
                         "ask me for more.")
    if requested > HARD_CAP:
        return HARD_CAP, f"{HARD_CAP} is the most I read in one run, to stay gentle on the site."
    return requested, ""


def start(store, cap=None, list_pages=4, calibration=True, user_asked=False):
    cap, note = resolve_cap(cap, user_asked)
    lo, hi = estimate(cap, list_pages, calibration)
    store.update_state(progress={"started": time.time(), "cap": cap, "read": 0,
                                 "first_profile_at": None, "estimate": [lo, hi]})
    msg = (note + " " if note else "") + (
        f"Reading {cap} profile{'s' if cap != 1 else ''} will take {fmt(lo, hi)}. You do not "
        "need to watch - I will tell you the time left as I go, and you can say stop at any time.")
    if cap < RUN_MAX and not note:
        msg += (f" Want more? I can do up to {RUN_MAX} in one run "
                f"({fmt(*estimate(RUN_MAX, list_pages, calibration))}), or more if you ask.")
    return {"cap": cap, "default_cap": DEFAULT_CAP, "run_max": RUN_MAX, "hard_cap": HARD_CAP,
            "limited": bool(note), "estimate_minutes": [lo, hi], "say": msg.strip()}


def tick(store, n=1):
    st = store.state()
    p = st.get("progress")
    if not p:
        return None
    now = time.time()
    if p.get("first_profile_at") is None:
        p["first_profile_at"] = now  # time to the first profile includes list pages + calibration
    p["read"] = min(p["cap"], p["read"] + n)
    p["last_at"] = now
    left = p["cap"] - p["read"]
    elapsed = now - p["started"]
    measured = p["read"] - 1
    if measured >= MEASURE_AFTER - 1 and now > p["first_profile_at"]:
        pace = (now - p["first_profile_at"]) / measured
        eta_lo = eta_hi = _mins(pace * left) if left else 0
        basis = "measured"
    else:
        eta_lo, eta_hi = (_mins(left * SECONDS_PER_PROFILE[0]), _mins(left * SECONDS_PER_PROFILE[1])) \
            if left else (0, 0)
        basis = "estimated"
    store.update_state(progress=p)
    if left == 0:
        say = f"All {p['read']} profiles read in {_mins(elapsed)} minute(s). Building your shortlist now."
    else:
        say = f"{p['read']} of {p['cap']} read - {fmt(eta_lo, eta_hi)} left."
    return {"read": p["read"], "cap": p["cap"], "left": left,
            "elapsed_minutes": round(elapsed / 60, 1), "minutes_left": [eta_lo, eta_hi],
            "basis": basis, "say": say,
            "tell_user_now": p["read"] in (1,) or p["read"] % 5 == 0 or left == 0}


def finish(store):
    st = store.state()
    p = st.pop("progress", None)
    store._atomic_write_json(store.state_path, st)
    if not p:
        return {"say": "No scan was running."}
    took = _mins(time.time() - p["started"])
    return {"read": p["read"], "minutes": took,
            "say": f"Done - I read {p['read']} profile(s) in about {took} minute(s)."}
