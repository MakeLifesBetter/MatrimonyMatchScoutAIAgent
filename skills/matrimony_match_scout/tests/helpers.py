"""Shared test helpers. All data here is fictional."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("SCOUT_PACE_SECONDS", "0")
os.environ.setdefault("SCOUT_HEADLESS", "1")


class FakeUI:
    """Plays the user: answers come from a list; everything said is recorded."""

    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.lines = []
        self.enters = 0

    def say(self, msg=""):
        for line in str(msg).split("\n"):
            self.lines.append("Scout: " + line)

    def ask(self, question=None):
        if question:
            self.say(question)
        if not self.answers:
            return None
        a = self.answers.pop(0)
        if callable(a):  # the "person" does something in the browser, then presses Enter
            a()
            a = ""
        self.lines.append("Response: " + str(a))
        return a

    def enter(self, prompt):
        self.say(prompt)
        self.enters += 1
        if self.answers and callable(self.answers[0]):
            self.answers.pop(0)()
        elif self.answers and self.answers[0] == "<enter>":
            self.answers.pop(0)
        self.lines.append("Response: ")

    @property
    def text(self):
        return "\n".join(self.lines)


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
