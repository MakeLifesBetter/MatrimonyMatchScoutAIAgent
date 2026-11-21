"""Scripted terminal sessions with realistic, messy typing.

Runs the real program (scripts/scout.py) as a subprocess, feeds it what a
person would type, and checks that every line starts with "Scout:" or
"Response:", that nothing crashes with a traceback, and that each request
is understood.
"""
import json
import os
import re
import subprocess
import sys
import unittest

from helpers import ROOT, tmpdir
from mock_site import MockSite, browser_login

SCOUT = str(ROOT / "scripts" / "scout.py")
INTAKE = ["Shaadi", "my younger sister", "26 - 30", "Seattle, Bay Area and Austin", "no smokers", "yes"]


def run(data_dir, lines, env=None, timeout=240):
    e = dict(os.environ, SCOUT_HEADLESS="1", SCOUT_PACE_SECONDS="0", **(env or {}))
    r = subprocess.run([sys.executable, SCOUT, "--data-dir", str(data_dir)],
                       input="\n".join(lines) + "\n", capture_output=True, text=True,
                       env=e, timeout=timeout)
    return r.stdout, r.stderr


def check_shape(tc, out, err):
    tc.assertNotIn("Traceback", out + err)
    tc.assertEqual(err.strip(), "")
    for line in out.splitlines():
        if line.strip():
            tc.assertRegex(line, r"^(Scout: |Response: )", line)


class TerminalSessionTests(unittest.TestCase):
    def test_messy_first_session_without_scan(self):
        d = tmpdir()
        out, err = run(d, ["lets start", *INTAKE,
                           "how can you read the data?",
                           "give me the report",
                           "change my age range to 26 to 30",
                           "Change my age range to 27-31 please",
                           "check status",
                           "what is the weather",
                           "show me a demo",
                           "quit"])
        check_shape(self, out, err)
        self.assertIn("1 of 5", out)
        self.assertIn("5 of 5", out)
        self.assertIn("age 26 to 30; places: Seattle, Bay Area, Austin; dealbreakers: smoking", out)
        self.assertIn("never see or store your password", out)          # how can you read the data
        self.assertIn("Your report is empty for now", out)               # report before any scan
        self.assertIn("say 'scan'", out)
        self.assertNotIn("Here are your top", out[:out.find("demo on made-up")])  # no fake report
        self.assertIn("age range is now 27 to 31", out)
        self.assertIn("Your interests (version 3)", out)                 # check status
        self.assertIn("did not catch that", out)                         # unknown request, friendly
        self.assertIn("demo on made-up profiles", out)
        crit = json.loads((d / "interests.json").read_text())["criteria"]
        self.assertEqual((crit["age_min"], crit["age_max"], crit["site"]), (27, 31, "shaadi.com"))
        self.assertEqual(crit["dealbreakers"], ["smoking"])

    def test_apostrophe_variants_all_start(self):
        for phrase in ("let's start", "Let’s start!", "LETS START", "ok lets begin"):
            out, err = run(tmpdir(), [phrase, "skip", "skip", "skip", "anywhere", "none", "yes", "quit"])
            check_shape(self, out, err)
            self.assertIn("1 of 5", out, phrase)

    def test_open_the_app_then_scans_and_reports(self):
        site = MockSite().start()
        try:
            d = tmpdir()
            browser_login(d / "browser_profile", site.url)  # the human logs in by hand
            env = {"SCOUT_SITE_URL_OVERRIDE": site.url}
            out, err = run(d, ["lets start", *INTAKE, "open the app then", "6", "", "looks good",
                               "yes", "pass on 2", "interested in Asha", "why is 1 ranked first",
                               "draft a reply to Asha", "what did you show me before",
                               "give me the report", "bye"], env=env)
            check_shape(self, out, err)
            self.assertIn("Press Enter here when you can see your home page", out)
            self.assertIn("here is exactly what I read from ONE profile", out)
            self.assertIn("Read 6 of up to 6", out)
            self.assertIn("Here are your top 3", out)
            self.assertIn("report.xlsx", out)
            self.assertIn("will never be shown to you again", out)
            self.assertIn("Asha Rao is marked as interesting", out)
            self.assertIn("scores", out)
            self.assertIn("only a draft - I never send anything", out)
            self.assertIn("I have shown you", out)
            self.assertIn("Nothing new since your last report", out)
            self.assertEqual(site.actions, [])
            # Day 2: reopen - nothing shown twice; remaining queue read first
            out2, err2 = run(d, ["scan", "", "", "no", "give me the report", "check status", "quit"],
                             env=env)
            check_shape(self, out2, err2)
            self.assertIn("Welcome back", out2)
            self.assertNotIn("ONE profile", out2)  # calibration remembered
            reported_1 = set(re.findall(r"^Scout: \d\. ([A-Za-z]+ [A-Za-z]+)", out, re.M))
            reported_2 = set(re.findall(r"^Scout: \d\. ([A-Za-z]+ [A-Za-z]+)", out2, re.M))
            self.assertFalse(reported_1 & reported_2, (reported_1, reported_2))
        finally:
            site.stop()

    def test_hand_edited_interests_are_confirmed_on_open(self):
        d = tmpdir()
        run(d, ["lets start", *INTAKE, "quit"])
        f = d / "interests.json"
        data = json.loads(f.read_text())
        data["criteria"]["age_max"] = 29
        f.write_text(json.dumps(data, indent=2))
        out, err = run(d, ["no", "quit"])
        check_shape(self, out, err)
        self.assertIn("edited by hand", out)
        self.assertIn("oldest age: 30 -> 29", out)
        self.assertEqual(json.loads(f.read_text())["criteria"]["age_max"], 30)  # put back, on request
        f.write_text(json.dumps(dict(data, criteria=dict(data["criteria"], age_max=28))))
        out, err = run(d, ["yes", "quit"])
        self.assertIn("using your edited interests", out)
        self.assertEqual(json.loads(f.read_text())["criteria"]["age_max"], 28)

    def test_broken_interests_file_is_explained_not_overwritten(self):
        d = tmpdir()
        run(d, ["lets start", *INTAKE, "quit"])
        (d / "interests.json").write_text('{"criteria": {"age_max": 29,}')
        out, err = run(d, ["no", "give me the report", "no", "quit"])
        check_shape(self, out, err)
        self.assertIn("typo near line 1", out)
        self.assertEqual((d / "interests.json").read_text(), '{"criteria": {"age_max": 29,}')

    def test_browser_failure_is_one_plain_sentence(self):
        d = tmpdir()
        out, err = run(d, ["lets start", *INTAKE, "scan", "", "", "quit"],
                       env={"SCOUT_SITE_URL_OVERRIDE": "http://127.0.0.1:9/"})
        check_shape(self, out, err)
        self.assertIn("I could not reach 127.0.0.1:9", out)

    def test_read_my_files_then_refine_from_examples(self):
        d = tmpdir()
        (d / "files_to_read").mkdir(parents=True)
        (d / "files_to_read" / "biodata_one.txt").write_text(
            "Name: File Person\nAge: 28\nCity: Seattle\nEducation: MBA\nDiet: Veg\nSmoking: No")
        (d / "files_to_read" / "photo.jpg").write_bytes(b"\xff\xd8")
        out, err = run(d, ["lets start", *INTAKE, "please read my files", "refine my criteria",
                           "masters", "skip", "skip", "Telugu", "veg, eggetarian", "never", "skip",
                           "no", "within a year", "rude", "loves travel", "family, travel",
                           "give me the report", "quit"])
        check_shape(self, out, err)
        self.assertIn("I read 1 profile(s) from your files", out)
        self.assertIn("Skipped photo.jpg", out)
        self.assertIn("File Person shows education 'MBA'", out)  # refined from a real example
        self.assertIn("minimum education: masters", out)
        self.assertIn("1. File Person", out)

    def test_real_user_session_phrases(self):
        """Exact phrases a real user typed on 2026-11-20 that were not understood."""
        d = tmpdir()
        out, err = run(d, ["lets start", "shaadi", "for me ", "23-28", "anywhere in US", "none", "yes",
                           "mark someone interested", "run matrimony scout", "", "", "quit"],
                       env={"SCOUT_SITE_URL_OVERRIDE": "http://127.0.0.1:9/"})
        check_shape(self, out, err)
        self.assertIn("age 23 to 28; places: US; dealbreakers: none", out)
        self.assertIn("nobody to mark", out)
        self.assertIn("Opening http://127.0.0.1:9/", out)  # "run matrimony scout" starts a scan
        self.assertNotIn("did not catch that", out)
        for phrase in ("check the website", "can you open chrome", "open shaadi",
                       "go to the site", "launch the browser", "start the scout"):
            out, err = run(d, [phrase, "", "", "quit"],
                           env={"SCOUT_SITE_URL_OVERRIDE": "http://127.0.0.1:9/"})
            check_shape(self, out, err)
            self.assertIn("browser window now", out, phrase)
        self.assertNotIn("Picking up the scan that was paused: 0", out)
        self.assertIn("Chromium", run(d, ["can you open chrome", "", "", "quit"],
                                      env={"SCOUT_SITE_URL_OVERRIDE": "http://127.0.0.1:9/"})[0])

    def test_mark_named_profile(self):
        d = tmpdir()
        run(d, ["lets start", *INTAKE, "quit"])
        (d / "files_to_read").mkdir()
        (d / "files_to_read" / "b.txt").write_text("Name: Riya Test\nAge: 27\nCity: Seattle")
        out, err = run(d, ["read my files", "mark Riya as interested", "mark riya rejected", "quit"])
        check_shape(self, out, err)
        self.assertIn("Riya Test is marked as interesting", out)
        self.assertIn("Riya Test is marked 'pass'", out)

    def test_end_of_input_exits_cleanly(self):
        out, err = run(tmpdir(), ["lets start", "Shaadi"])  # user closes the terminal mid-intake
        check_shape(self, out, err)
        self.assertIn("Saved everything", out)


if __name__ == "__main__":
    unittest.main()
