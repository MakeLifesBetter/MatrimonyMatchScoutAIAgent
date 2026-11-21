"""Reports: top 3 first, Markdown + Excel (3 sheets), never repeat, rescore without browsing."""
import json
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, person, tmpdir
import pipeline
from openpyxl import load_workbook
from state_store import ScoutStore

CRIT = {"age_min": 25, "age_max": 30, "places": ["Seattle"], "dealbreakers": ["smoking"],
        "min_education": "masters"}


def store_with(n=5):
    s = ScoutStore(tmpdir())
    s.save_interests(CRIT, "user", "test")
    for i in range(n):
        s.upsert_profile(person(f"P{i}", name=f"Fictional {i}", age=25 + i), "search")
    return s


class ReportTests(unittest.TestCase):
    def test_empty_before_any_scan(self):
        s = ScoutStore(tmpdir())
        s.save_interests(CRIT, "user", "t")
        self.assertEqual(pipeline.make_report(s)["status"], "no_profiles")
        self.assertFalse((s.dir / "reports").exists())  # no confusing empty files

    def test_top3_markdown_and_excel_sheets(self):
        s = store_with(5)
        s.upsert_profile(person("X", name="Fictional Smoker", smoking="regularly"), "search")
        r = pipeline.make_report(s)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["digest"].startswith("Summary: 5 profile(s) in this report"))
        self.assertEqual(r["digest"].count("Why it fits"), 3)
        self.assertIn("Risky or unknown", r["digest"])
        self.assertIn("1 left out by your must-haves", r["digest"])
        md = Path(r["markdown"]).read_text()
        for sec in ("## Summary", "## Profiles that match your interests",
                    "## Profiles that need your attention", "## Ranked list", "## Every profile in this report"):
            self.assertIn(sec, md)
        self.assertNotIn("Fictional Smoker", md)  # excluded profiles are not shown
        wb = load_workbook(r["excel"])
        self.assertEqual(wb.sheetnames, ["Ranked Matches", "Profile Details", "Updated Since Last Report"])
        self.assertEqual(wb["Ranked Matches"].max_row, 1 + 5)
        self.assertEqual(wb["Ranked Matches"]["C1"].value, "Name")

    def test_excel_and_whatsapp_outputs(self):
        s = store_with(5)
        r = pipeline.make_report(s)
        self.assertTrue(r["excel"].endswith("report.xlsx"))
        self.assertEqual(r["attach"][0], r["excel"])          # Excel always attached first
        w = r["whatsapp_text"]
        self.assertTrue(w.startswith("*Matrimony shortlist - "))
        self.assertEqual(w.count("/100"), 3)                  # only the top 3 in the message
        self.assertIn("attached Excel sheet", w)
        self.assertIn("do not forward", w)
        self.assertLessEqual(len(w), 1500)
        self.assertNotIn("about_me", w)

    def test_summary_matches_and_attention(self):
        s = store_with(0)
        s.upsert_profile(person("G", name="Good Match"), "search")
        s.upsert_profile(person("W", name="Waiting Reply", chat={"exists": True, "last_message_by": "them",
                         "open_questions": ["asked about a phone or video call"]}), "chats")
        s.upsert_profile(person("R", name="Red Flag", chat={"exists": True, "last_message_by": "user",
                         "red_flags": ["asks for money (mentions 'loan')"]}), "chats")
        s.upsert_profile(person("U", name="Unknown Bits", education=None, smoking=None), "search")
        r = pipeline.make_report(s)
        d = r["digest"]
        matches = d.split("MATCH YOUR INTERESTS")[1].split("NEED YOUR ATTENTION")[0]
        attention = d.split("NEED YOUR ATTENTION")[1]
        self.assertIn("Good Match", matches)
        self.assertNotIn("Red Flag", matches)                      # red flags never listed as a match
        self.assertIn("Red Flag: red flag - asks for money", attention)
        self.assertIn("Waiting Reply: waiting for your reply (asked about a phone or video call)", attention)
        self.assertIn("Unknown Bits: not shown, please check - education, smoking", attention)
        self.assertNotIn("Good Match", attention)
        self.assertIn("3 need your attention", d)
        ws = load_workbook(r["excel"])["Ranked Matches"]
        heads = [c.value for c in ws[1]]
        self.assertIn("Needs attention", heads)
        col = heads.index("Needs attention")
        vals = {row[2].value: row[col].value for row in ws.iter_rows(min_row=2)}
        self.assertIn("red flag", vals["Red Flag"])
        self.assertFalse(vals["Good Match"])
        self.assertIn("3 need attention", r["whatsapp_text"])
        self.assertNotIn("Red Flag", r["whatsapp_text"].split("*Match your interests:*")[1])

    def test_second_report_never_repeats(self):
        s = store_with(3)
        pipeline.make_report(s)
        self.assertEqual(pipeline.make_report(s)["status"], "nothing_new")

    def test_updated_profile_marked_with_what_changed(self):
        s = store_with(3)
        pipeline.make_report(s)
        s.upsert_profile(person("P1", name="Fictional 1", age=26, profession="Architect"), "search")
        r = pipeline.make_report(s)
        self.assertEqual((r["new"], r["updated"]), (0, 1))
        self.assertIn("[UPDATED]", r["digest"])
        self.assertIn("changed since you last saw it - profession: Engineer -> Architect", r["digest"])
        ws = load_workbook(r["excel"])["Updated Since Last Report"]
        self.assertEqual([c.value for c in ws[2]], ["Fictional 1", "P1", "profession", "Engineer", "Architect"])

    def test_rejected_not_in_report(self):
        s = store_with(3)
        s.set_user_status("P0", "rejected")
        r = pipeline.make_report(s)
        self.assertNotIn("P0", [row["profile_id"] for row in r["rows"]])

    def test_all_excluded_explains_and_writes_nothing(self):
        s = store_with(2)
        s.save_interests(dict(CRIT, age_max=24, age_min=20), "user", "t")
        r = pipeline.make_report(s)
        self.assertEqual(r["status"], "all_excluded")
        self.assertIn("age outside your range", r["excluded"])

    def test_interest_change_rescores_from_saved_data_without_browsing(self):
        s = store_with(5)  # ages 25..29
        pipeline.make_report(s)
        s.upsert_profile(person("OLD", age=33), "search")  # excluded at first
        self.assertEqual(pipeline.make_report(s)["status"], "all_excluded")
        with mock.patch("socket.socket", side_effect=AssertionError("went online!")):
            s.save_interests(dict(CRIT, age_max=35), "user", "widened")
            res = pipeline.rescore(s)  # saved data only - no network at all
        self.assertEqual(res["ready_to_show"], 1)
        r = pipeline.make_report(s)
        self.assertEqual([row["profile_id"] for row in r["rows"]], ["OLD"])
        self.assertFalse(s.state()["scores_stale"])

    def test_ai_judgement_feeds_score(self):
        s = store_with(1)
        s.save_judgement("P0", 18, "Strong overlap in values, warm chat.")
        r = pipeline.make_report(s)
        self.assertIn("Strong overlap", r["rows"][0]["judgement"])

    def test_demo_examples_are_fictional(self):
        for p in json.loads((ROOT / "examples" / "sample_profiles.json").read_text()):
            self.assertIn("example.invalid", p["profile_url"])
            self.assertTrue(p["name"].startswith("Sample "))


if __name__ == "__main__":
    unittest.main()
