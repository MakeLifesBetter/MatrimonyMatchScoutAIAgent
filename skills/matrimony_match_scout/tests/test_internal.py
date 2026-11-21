"""Internal actions used by the AI chat layer (JSON in, JSON out)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import ROOT, person, tmpdir

SCOUT = str(ROOT / "scripts" / "scout.py")


def act(d, *args):
    r = subprocess.run([sys.executable, SCOUT, "--data-dir", str(d), *args],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class InternalActionTests(unittest.TestCase):
    def test_ai_flow(self):
        d = tmpdir()
        self.assertFalse(act(d, "status")["has_interests"])
        (d / "c.json").write_text(json.dumps({"age_min": 25, "age_max": 30, "places": ["Seattle"],
                                              "dealbreakers": ["smoking"]}))
        self.assertEqual(act(d, "save-interests", str(d / "c.json"))["version"], 1)
        recs = [dict(person("A1"), qualitative=17, ai_judgement="Shared values; warm chat."),
                person("A2", smoking="regularly")]
        (d / "p.json").write_text(json.dumps(recs))
        self.assertEqual(act(d, "ingest", str(d / "p.json"))["new"], 2)
        prev = act(d, "report", "--preview")
        self.assertEqual(prev["status"], "ok")
        self.assertEqual([Path(p).suffix for p in prev["attach"]], [".xlsx", ".md"])
        self.assertTrue(all(Path(p).exists() for p in prev["attach"]))
        self.assertIn("do not forward", prev["share_text"])
        self.assertIn("Here is your match", prev["share_text"])
        self.assertIn("Shared values", Path(prev["markdown"]).read_text())
        self.assertEqual(act(d, "report")["status"], "ok")  # preview did not mark as shown
        self.assertEqual(act(d, "report")["status"], "nothing_new")
        self.assertEqual(len(act(d, "history")), 1)
        act(d, "set-status", "A1", "rejected")
        # hand edit is surfaced, and saving over it needs explicit confirmation
        f = d / "interests.json"
        data = json.loads(f.read_text())
        data["criteria"]["age_max"] = 29
        f.write_text(json.dumps(data))
        st = act(d, "status")
        self.assertTrue(st["interests_hand_edited"])
        self.assertEqual(st["hand_edit_diff"][0]["field"], "age_max")
        r = subprocess.run([sys.executable, SCOUT, "--data-dir", str(d), "save-interests",
                            str(d / "c.json")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(json.loads(r.stdout)["error"], "interests_hand_edited")
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertEqual(json.loads(f.read_text())["criteria"]["age_max"], 29)
        act(d, "hand-edit", "accept")
        self.assertFalse(act(d, "status")["interests_hand_edited"])

    def test_scan_timing_through_ingest_and_demo(self):
        d = tmpdir()
        start = act(d, "scan-start", "--cap", "3")
        self.assertIn("will take about", start["say"])
        (d / "p.json").write_text(json.dumps([person("B1")]))
        out = act(d, "ingest", str(d / "p.json"))
        self.assertEqual(out["progress"]["read"], 1)
        self.assertIn("1 of 3 read", out["progress"]["say"])
        self.assertEqual(act(d, "scan-progress")["left"], 2)
        self.assertIn("Done - I read 1", act(d, "scan-end")["say"])
        self.assertNotIn("progress", act(d, "ingest", str(d / "p.json")))  # no scan running
        self.assertIn("Here are your", act(d, "demo")["digest"])
        self.assertEqual(act(d, "scan-start")["cap"], 5)                       # default
        self.assertEqual(act(d, "scan-start", "--cap", "30")["cap"], 10)       # not asked
        self.assertEqual(act(d, "scan-start", "--cap", "30", "--user-asked")["cap"], 30)
        self.assertEqual(act(d, "scan-start", "--cap", "500", "--user-asked")["cap"], 50)
        (d / "c.json").write_text(json.dumps({"max_profiles_per_run": 15}))   # saved by the person
        act(d, "save-interests", str(d / "c.json"))
        self.assertEqual(act(d, "scan-start")["cap"], 15)

    def test_explain_seen_unavailable_forget(self):
        d = tmpdir()
        (d / "c.json").write_text(json.dumps({"age_min": 25, "age_max": 30, "dealbreakers": ["smoking"]}))
        act(d, "save-interests", str(d / "c.json"))
        (d / "p.json").write_text(json.dumps([
            person("E1", name="Esha Test", profile_url="https://x.invalid/profile/E1"),
            person("E2", name="Old Test", age=40)]))
        act(d, "ingest", str(d / "p.json"))
        ex = act(d, "explain", "E1")
        self.assertFalse(ex["excluded"])
        self.assertIn("Age 27 is in your range", ex["why_fit"])
        self.assertTrue(act(d, "explain", "E2")["excluded"])
        seen = act(d, "seen", "https://x.invalid/profile/E1", "https://x.invalid/profile/NEW9")
        self.assertTrue(seen["https://x.invalid/profile/E1"]["seen"])
        self.assertFalse(seen["https://x.invalid/profile/NEW9"]["seen"])
        act(d, "mark-unavailable", "E1")
        self.assertEqual(act(d, "report")["status"], "all_excluded")  # E1 gone, E2 too old
        self.assertTrue(act(d, "forget", "E2")["forgotten"])
        self.assertEqual(act(d, "status")["profiles_seen"], 1)

    def test_delete_all_needs_confirmation_and_scout_data(self):
        d = tmpdir() / "data"
        (d.parent / "c.json").write_text(json.dumps({"age_max": 30}))
        act(d, "save-interests", str(d.parent / "c.json"))
        self.assertFalse(act(d, "delete-all")["deleted"])
        self.assertTrue(d.exists())
        self.assertTrue(act(d, "delete-all", "--confirm")["deleted"])
        self.assertFalse(d.exists())
        other = tmpdir()
        (other / "my_photos.txt").write_text("not scout data")
        self.assertFalse(act(other, "delete-all", "--confirm")["deleted"])
        self.assertTrue((other / "my_photos.txt").exists())

    def test_chat_checkpoint_resume(self):
        d = tmpdir()
        (d / "cp.json").write_text(json.dumps({"phase": "SCAN", "run_id": "chat-1",
                                               "cursors": {"chats": {"next": "SH2", "done": ["SH1"]}}}))
        act(d, "checkpoint", "save", str(d / "cp.json"))
        self.assertEqual(act(d, "status")["chat_checkpoint"]["cursors"]["chats"]["next"], "SH2")
        act(d, "checkpoint", "clear")
        self.assertIsNone(act(d, "status")["chat_checkpoint"]["phase"])

    def test_extract_capture_file(self):
        d = tmpdir()
        (d / "page.txt").write_text("Name: Cap Person\nAge: 30\nLives in: Pune, India")
        out = act(d, "extract", str(d / "page.txt"), "--url", "https://x.invalid/profile/ZX900")
        self.assertEqual((out["name"], out["age"], out["city"], out["profile_id"]),
                         ("Cap Person", 30, "Pune", "ZX900"))


if __name__ == "__main__":
    unittest.main()
