"""Scoring: hard filters first, unknown is neutral, red flags cap, deterministic."""
import unittest

from helpers import person
from score import RED_FLAG_CAP, score_profile

C = {"age_min": 25, "age_max": 30, "places": ["Seattle", "Bay Area"], "min_education": "masters",
     "mother_tongue": "Telugu", "marital_statuses": ["never_married"], "food_ok": ["vegetarian"],
     "dealbreakers": ["smoking"], "red_flags": ["asks for money"], "profession_keywords": ["engineer"]}


class ScoreTests(unittest.TestCase):
    def test_good_profile_high_and_deterministic(self):
        a = score_profile(person(), C)
        self.assertFalse(a["excluded"])
        self.assertGreaterEqual(a["score"], 75)
        self.assertEqual(a, score_profile(person(), C))

    def test_hard_filters_exclude_no_exceptions(self):
        for change, word in ((dict(age=34), "age"), (dict(city="Austin", state="TX"), "lives in"),
                             (dict(education="Bachelors"), "education"),
                             (dict(marital_status="divorced"), "marital"),
                             (dict(food="non_vegetarian"), "food")):
            r = score_profile(person(**change), C, qualitative=20)
            self.assertTrue(r["excluded"], change)
            self.assertEqual(r["score"], 0)
            self.assertTrue(any(word in x for x in r["exclude_reasons"]), r["exclude_reasons"])

    def test_dealbreaker_excludes_even_a_perfect_match(self):
        r = score_profile(person(smoking="occasionally"), C, qualitative=20)
        self.assertTrue(r["excluded"])
        self.assertIn("dealbreaker 'smoking'", r["exclude_reasons"][0])

    def test_unknown_never_passes_never_fails(self):
        known = score_profile(person(), C)
        unk = score_profile(person(smoking=None, education=None), C)
        self.assertFalse(unk["excluded"])  # never assumed to fail
        self.assertIn("education", unk["unknowns"])  # never assumed to pass: flagged
        self.assertTrue(any("smoking" in u for u in unk["unknowns"]))
        self.assertTrue(any("Unknown - please check" in r for r in unk["risks"]))
        self.assertNotIn("Clear of your dealbreaker: smoking", unk["why_fit"])
        # unknown is left out of the points, not counted as zero
        no_edu_crit = {k: v for k, v in C.items() if k != "min_education"}
        self.assertEqual(score_profile(person(education=None), C)["weighted_points"],
                         score_profile(person(education=None), no_edu_crit)["weighted_points"])
        self.assertNotEqual(unk["confidence"], "high")
        self.assertEqual(known["confidence"], "high")

    def test_red_flag_caps_score(self):
        r = score_profile(person(chat={"exists": True, "red_flags": ["asks for money (mentions 'loan')"]}),
                          C, qualitative=20)
        self.assertLessEqual(r["score"], RED_FLAG_CAP)
        self.assertTrue(any("Red flag" in x for x in r["risks"]))
        r2 = score_profile(person(about_me="Looking for an investment opportunity partner, send money"), C)
        self.assertLessEqual(r2["score"], RED_FLAG_CAP)

    def test_place_aliases_and_country(self):
        r = score_profile(person(city="Sunnyvale", state="CA"), C)
        self.assertFalse(r["excluded"])
        self.assertIn("Bay Area", " ".join(r["why_fit"]))
        r = score_profile(person(city=None, state=None, country=None), C)
        self.assertIn("location", r["unknowns"])
        self.assertFalse(r["excluded"])

    def test_free_text_dealbreaker(self):
        c = dict(C, dealbreakers=["tattoos"])
        self.assertTrue(score_profile(person(about_me="I have two tattoos"), c)["excluded"])
        r = score_profile(person(), c)
        self.assertFalse(r["excluded"])
        self.assertIn("tattoos", r["needs_check"])

    def test_more_dealbreakers(self):
        hor = person(horoscope={"manglik": "yes"})
        self.assertTrue(score_profile(hor, {"dealbreakers": ["manglik"]})["excluded"])
        self.assertIn("manglik status (for your dealbreaker 'manglik')",
                      score_profile(person(), {"dealbreakers": ["manglik"]})["unknowns"])
        self.assertTrue(score_profile(person(marital_status="widowed"),
                                      {"dealbreakers": ["previously married"]})["excluded"])

    def test_ai_judgement_used_and_bounded(self):
        r = score_profile(person(), C, qualitative=99, judgement="Strong shared values.")
        self.assertEqual((r["qualitative"], r["judgement_by"]), (20, "ai"))
        rule = score_profile(person(), C)
        self.assertEqual(rule["judgement_by"], "rules")
        self.assertTrue(rule["judgement"].startswith("Rule-based"))

    def test_no_photo_or_looks_inputs(self):
        a = score_profile(person(), C)
        b = score_profile(person(photo_count=9, photo_url="x.jpg", looks="anything"), C)
        self.assertEqual(a["score"], b["score"])


if __name__ == "__main__":
    unittest.main()
