"""Real browser (Playwright, headless) against the FICTIONAL mock site.

Covers: you log in yourself (Scout waits, never types a password), the login
is remembered, calibration on ONE profile with corrections, human pace,
per-run cap, checkpoint after every profile + resume after a disconnect,
read-only (no clicks on Send/Accept/Shortlist), chat text never saved,
updated profiles, site security check, plain-English failures.
"""
import os
import unittest
from unittest import mock

from helpers import FakeUI, tmpdir
import pipeline
import scan_browser
import mock_site
from mock_site import MockSite, browser_login
from state_store import ScoutStore

try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    HAVE_PW = True
except ImportError:
    HAVE_PW = False

CRIT = {"site": "shaadi.com", "age_min": 25, "age_max": 31, "places": ["Seattle"],
        "dealbreakers": ["smoking"], "red_flags": ["asks for money"]}


@unittest.skipUnless(HAVE_PW, "Playwright not installed")
class BrowserScanTests(unittest.TestCase):
    def setUp(self):
        self.site = MockSite().start()
        os.environ["SCOUT_SITE_URL_OVERRIDE"] = self.site.url
        self.d = tmpdir()
        self.store = ScoutStore(self.d)
        self.store.save_interests(CRIT, "user", "test")

    def tearDown(self):
        os.environ.pop("SCOUT_SITE_URL_OVERRIDE", None)
        self.site.stop()

    def login_as_human(self):
        browser_login(self.d / "browser_profile", self.site.url)

    def scan(self, answers, cap=20):
        ui = FakeUI(answers)
        return scan_browser.run_scan(self.store, "shaadi.com", ui, cap=cap), ui

    def test_waits_for_user_login_and_never_reads_password(self):
        ui = FakeUI(["<enter>", "<enter>", "<enter>"])
        with self.assertRaises(scan_browser.ScanError) as cm:
            scan_browser.run_scan(self.store, "shaadi.com", ui)
        self.assertIn("nothing was read", str(cm.exception))
        self.assertIn("could not see you logged in", str(cm.exception))
        self.assertEqual(ui.enters, 3)
        self.assertIn("log in there yourself", ui.text)
        self.assertEqual(self.site.passwords_seen, 0)  # the Scout never submitted a login
        self.assertEqual(self.store.load_profiles(), {})

    def test_full_scan_calibration_cap_readonly_and_privacy(self):
        self.login_as_human()
        res, ui = self.scan(["<enter>", "age is 28", "yes"], cap=6)
        self.assertEqual(res["status"], "cap")
        self.assertEqual(res["read"], 6)
        self.assertIn("here is exactly what I read from ONE profile", ui.text)
        self.assertIn("Fixed: age is now 28", ui.text)
        self.assertEqual(self.store.load_profiles()["SH101"]["data"]["age"], 28)
        self.assertTrue(self.store.state()["calibration"])
        self.assertEqual(self.site.actions, [])  # read-only: nothing clicked or sent
        # chats: only summaries, never the message text, anywhere in the data folder
        blob = "".join(p.read_text(errors="ignore") for p in self.d.rglob("*")
                       if p.is_file() and "browser_profile" not in str(p))
        for phrase in ("Rainier", "gift card", "difficult situation"):
            self.assertNotIn(phrase, blob)
        asha = self.store.load_profiles()["SH101"]["data"]
        self.assertEqual(asha["chat"]["last_message_by"], "them")
        self.assertEqual(asha["horoscope"]["rashi"], "Mesha")
        self.assertTrue(list((self.d / "captures").rglob("list_matches_1.txt")))
        self.assertGreater(res["left"], 0)  # remaining go first next time

    def test_second_run_remembers_login_and_calibration(self):
        self.login_as_human()
        self.scan(["<enter>", "yes"], cap=3)
        res, ui = self.scan(["<enter>"], cap=3)  # no calibration question again
        self.assertNotIn("ONE profile", ui.text)
        self.assertIn("you are logged in", ui.text)

    def test_disconnect_resumes_instead_of_restarting(self):
        self.login_as_human()
        self.site.fail_after_profiles = 3
        with self.assertRaises(scan_browser.ScanError) as cm:
            self.scan(["<enter>", "yes"], cap=20)
        self.assertIn("saved my place", str(cm.exception))
        paused = self.store.scan_state()
        self.assertIsNotNone(paused)
        read_before = paused["read"]
        self.assertGreaterEqual(read_before, 1)
        self.site.fail_after_profiles = None
        res, ui = self.scan(["<enter>"], cap=20)
        self.assertIn("Picking up the scan that was paused", ui.text)
        self.assertEqual(res["status"], "done")
        self.assertEqual(len(self.store.load_profiles()), 8)
        # list pages were not re-discovered on resume
        self.assertEqual(self.site.visits["/matches"], 1)

    def test_changed_profile_shows_as_updated(self):
        self.login_as_human()
        self.scan(["<enter>", "yes"], cap=20)
        first = pipeline.make_report(self.store)
        self.assertEqual(first["status"], "ok")
        self.site.people["SH101"]["job"] = "Engineering Manager"
        self.scan(["<enter>"], cap=20)
        r = pipeline.make_report(self.store)
        self.assertEqual((r["new"], r["updated"]), (0, 1))
        self.assertIn("profession: Software Engineer -> Engineering Manager", r["digest"])

    def test_security_check_stops_politely(self):
        self.login_as_human()
        self.site.blocked = True
        with self.assertRaises(scan_browser.ScanError) as cm:
            self.scan(["<enter>", "yes"])
        self.assertIn("security check", str(cm.exception))

    def _capture_scanner(self):
        box = []
        real = scan_browser.Scanner.__init__

        def init(this, *a, **k):
            real(this, *a, **k)
            box.append(this)
        return box, mock.patch.object(scan_browser.Scanner, "__init__", init)

    def test_unknown_menu_names_user_opens_the_page_and_it_is_remembered(self):
        self.login_as_human()
        mock_site.ODD_NAV["on"] = True
        box, patch = self._capture_scanner()

        def open_page(path):
            return lambda: box[0].page.goto(self.site.url.rstrip("/") + path)
        with patch:
            res, ui = self.scan(["<enter>", open_page("/inbox"), "skip", open_page("/matches"),
                                 "skip", "yes"], cap=4)
        self.assertIn("could not find your chats page by myself", ui.text)
        self.assertIn("I will remember where your chats page is", ui.text)
        self.assertIn("Skipped your interests received", ui.text)
        self.assertEqual(res["read"], 4)
        urls = self.store.state()["calibration"][box[0].domain]["source_urls"]
        self.assertTrue(urls["chats"].endswith("/inbox") and urls["matches"].endswith("/matches"))
        # next run: no questions about pages, it goes straight there
        res2, ui2 = self.scan(["<enter>", "skip", "skip"], cap=2)
        self.assertNotIn("find your chats page", ui2.text)
        self.assertNotIn("find your matches page", ui2.text)
        self.assertIn("Found", ui2.text)

    def test_login_on_another_site_is_not_accepted(self):
        self.login_as_human()
        box, patch = self._capture_scanner()
        other = self.site.url.replace("127.0.0.1", "localhost")  # a different site, like Google
        with patch:
            with self.assertRaises(scan_browser.ScanError) as cm:
                self.scan([lambda: box[0].page.goto(other)] * 3)
        self.assertIn("could not see you logged in", str(cm.exception))
        self.assertEqual(self.store.load_profiles(), {})

    def test_empty_pages_leave_a_diagnostics_file(self):
        self.login_as_human()
        mock_site.ODD_NAV["on"] = True
        box, patch = self._capture_scanner()
        with patch:
            res, ui = self.scan(["<enter>", lambda: box[0].page.goto(self.site.url + "my-profile"),
                                 "skip", "skip", "skip"])
        self.assertEqual(res["status"], "empty")
        self.assertTrue(list(self.d.rglob("diagnostics_chats.txt")))
        self.assertIn("I closed the browser window", ui.text)

    def test_calibration_stop_pauses_before_full_scan(self):
        self.login_as_human()
        res, _ = self.scan(["<enter>", "stop"])
        self.assertEqual(res["status"], "paused")
        self.assertEqual(self.store.load_profiles(), {})

    def test_unreachable_site_is_one_sentence(self):
        os.environ["SCOUT_SITE_URL_OVERRIDE"] = "http://127.0.0.1:9/"
        with self.assertRaises(scan_browser.ScanError) as cm:
            self.scan(["<enter>"])
        msg = str(cm.exception)
        self.assertIn("could not reach", msg)
        self.assertEqual(msg.count(". "), 0)


class ScanHelpersTests(unittest.TestCase):
    def test_human_pace_defaults(self):
        os.environ.pop("SCOUT_PACE_SECONDS", None)
        try:
            with mock.patch("time.sleep") as sl:
                scan_browser.pace("profile")
                scan_browser.pace("list")
            waits = [c.args[0] for c in sl.call_args_list]
            self.assertTrue(4 <= waits[0] <= 9 and 3 <= waits[1] <= 6)
        finally:
            os.environ["SCOUT_PACE_SECONDS"] = "0"

    def test_same_site_includes_subdomains(self):
        self.assertTrue(scan_browser.same_site("https://my.shaadi.com/inbox", "shaadi.com"))
        self.assertTrue(scan_browser.same_site("https://www.shaadi.com/x", "shaadi.com"))
        self.assertFalse(scan_browser.same_site("https://accounts.google.com/x", "shaadi.com"))
        self.assertTrue(scan_browser.SITE_ID_HREF.search("https://www.shaadi.com/profile?x=SH12345678"))

    def test_hard_cap_and_url_resolution(self):
        s = scan_browser.Scanner(ScoutStore(tmpdir()), "https://www.shaadi.com", FakeUI(), cap=500)
        self.assertEqual(s.cap, scan_browser.HARD_CAP)
        os.environ.pop("SCOUT_SITE_URL_OVERRIDE", None)
        self.assertEqual(scan_browser.resolve_url("Shaadi.com"), "https://www.shaadi.com")
        self.assertEqual(scan_browser.resolve_url("shaadi"), "https://www.shaadi.com")

    def test_missing_playwright_is_plain_english(self):
        with mock.patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            with self.assertRaises(scan_browser.ScanError) as cm:
                scan_browser.Scanner(ScoutStore(tmpdir()), "https://x.invalid", FakeUI()).run()
        self.assertIn("pip install playwright", str(cm.exception))

    def test_corrections_parse(self):
        self.assertEqual(scan_browser.parse_correction("Age is 28"), ("age", "28"))
        self.assertEqual(scan_browser.parse_correction("her city should be Pune"), ("city", "Pune"))
        self.assertEqual(scan_browser.parse_correction("smoking: unknown"), ("smoking", "unknown"))
        self.assertEqual(scan_browser.parse_correction("looks fine"), (None, None))


if __name__ == "__main__":
    unittest.main()
