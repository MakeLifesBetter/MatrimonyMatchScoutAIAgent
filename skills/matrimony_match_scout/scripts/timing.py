"""
Matrimony Match Scout - how long will this take? (for the Muse browser scan)

An AI browsing a site is slower than a person clicking: each profile means
opening the page, reading it, extracting it and saving it. These are the
STARTING estimates; once a few profiles are done, the real measured pace is
used instead, so "time left" gets more accurate as the scan goes.

  estimate(profiles, list_pages)  -> minutes (low, high) before starting
  start(store, cap, list_pages)   -> saves the start time, returns the estimate
  tick(store, n)                  -> after each saved profile: read, left, time left
  finish(store)                   -> total time taken
"""
import math
import time

SECONDS_PER_PROFILE = (30, 60)    # open + read + extract + save, at a human pace
SECONDS_PER_LIST_PAGE = (20, 40)  # inbox, interests received, matches, search
SECONDS_CALIBRATION = (60, 120)   # the one-profile check with the user
MEASURE_AFTER = 3                 # switch to the real pace after this many profiles
QUICK_BATCH = 5


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


def start(store, cap, list_pages=4, calibration=True):
    lo, hi = estimate(cap, list_pages, calibration)
    qlo, qhi = estimate(min(QUICK_BATCH, cap), list_pages, calibration)
    store.update_state(progress={"started": time.time(), "cap": cap, "read": 0,
                                 "first_profile_at": None, "estimate": [lo, hi]})
    msg = (f"Reading up to {cap} profiles will take {fmt(lo, hi)}. You do not need to watch - "
           "I will tell you the time left as I go, and you can say stop at any time.")
    if cap > QUICK_BATCH:
        msg += (f" Want a quick first batch of {QUICK_BATCH} instead ({fmt(qlo, qhi)})?")
    return {"cap": cap, "estimate_minutes": [lo, hi], "quick_batch": QUICK_BATCH,
            "quick_batch_minutes": [qlo, qhi], "say": msg}


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
