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
        self.assertTrue(r["digest"].startswith("Here are your top 3"))
        self.assertEqual(r["digest"].count("Why it fits"), 3)
        self.assertIn("Risky or unknown", r["digest"])
        self.assertIn("left out by your filters", r["digest"])
        md = Path(r["markdown"]).read_text()
        self.assertIn("## Top 3", md)
        self.assertNotIn("Fictional Smoker", md)  # excluded profiles are not shown
        wb = load_workbook(r["excel"])
        self.assertEqual(wb.sheetnames, ["Ranked Matches", "Profile Details", "Updated Since Last Report"])
        self.assertEqual(wb["Ranked Matches"].max_row, 1 + 5)
        self.assertEqual(wb["Ranked Matches"]["C1"].value, "Name")

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
        self.assertIn("profession: Engineer -> Architect", r["digest"])
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
