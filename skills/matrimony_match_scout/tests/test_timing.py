"""Muse scan timing: an estimate up front, then time left after every profile."""
import unittest
from unittest import mock

from helpers import tmpdir
import timing
from state_store import ScoutStore


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.s = ScoutStore(tmpdir())

    def test_estimate_up_front_and_quick_batch_offer(self):
        r = timing.start(self.s, 20)
        lo, hi = r["estimate_minutes"]
        self.assertTrue(10 <= lo < hi <= 30, (lo, hi))
        self.assertIn("will take about", r["say"])
        self.assertIn("quick first batch of 5", r["say"])
        self.assertLess(r["quick_batch_minutes"][1], hi)
        self.assertNotIn("quick first batch", timing.start(self.s, 5)["say"])

    def test_time_left_switches_to_measured_pace(self):
        t = [1000.0]
        with mock.patch("time.time", lambda: t[0]):
            timing.start(self.s, 10)
            t[0] += 180                          # list pages + calibration
            first = timing.tick(self.s)
            self.assertEqual((first["read"], first["basis"]), (1, "estimated"))
            self.assertTrue(first["tell_user_now"])
            for _ in range(3):                   # then 20 s per profile
                t[0] += 20
                p = timing.tick(self.s)
            self.assertEqual(p["basis"], "measured")
            self.assertEqual(p["left"], 6)
            self.assertEqual(p["minutes_left"], [2, 2])   # 6 x 20 s
            self.assertIn("4 of 10 read - about 2 minutes left", p["say"])
            for _ in range(6):
                t[0] += 20
                p = timing.tick(self.s)
            self.assertEqual(p["left"], 0)
            self.assertIn("All 10 profiles read", p["say"])
            done = timing.finish(self.s)
            self.assertIn("in about 6 minute", done["say"])
        self.assertIsNone(self.s.state().get("progress"))

    def test_user_told_every_five_profiles(self):
        timing.start(self.s, 12)
        told = [timing.tick(self.s)["tell_user_now"] for _ in range(12)]
        self.assertEqual([i + 1 for i, x in enumerate(told) if x], [1, 5, 10, 12])

    def test_no_scan_running(self):
        self.assertIsNone(timing.tick(self.s))
        self.assertIn("No scan", timing.finish(self.s)["say"])


if __name__ == "__main__":
    unittest.main()
