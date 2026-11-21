"""Shared test helpers. All data here is fictional."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))


def tmpdir():
    return Path(tempfile.mkdtemp(prefix="scout-test-"))


def person(pid="T1", **kw):
    base = {"profile_id": pid, "name": f"Test {pid}", "age": 27, "city": "Seattle", "state": "WA",
            "country": "USA", "education": "MS", "profession": "Engineer",
            "mother_tongue": "Telugu", "marital_status": "never_married", "food": "vegetarian",
            "smoking": "never", "drinking": "never", "about_me": "Fictional test person.",
            "chat": {"exists": False, "red_flags": [], "contradictions": []}}
    base.update(kw)
    return base
