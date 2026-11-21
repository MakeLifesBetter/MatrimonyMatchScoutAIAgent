"""Memory: survives reopen, never shows a profile twice, hand edits confirmed."""
import json
import unittest

from helpers import person, tmpdir
from state_store import ExternalEditPending, InterestsFileError, ScoutStore


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.d = tmpdir()
        self.s = ScoutStore(self.d)
        self.s.save_interests({"age_max": 30, "places": ["Seattle"]}, "user", "intake")

    def test_interests_survive_close_and_reopen(self):
        s2 = ScoutStore(self.d)
        data, ext = s2.load_interests()
        self.assertEqual(data["criteria"]["age_max"], 30)
        self.assertFalse(ext)

    def test_profile_never_shown_twice(self):
        self.s.upsert_profile(person("A"), "chats")
        self.s.upsert_profile(person("B"), "search")
        self.assertEqual(len(self.s.digest_candidates()["new"]), 2)
        self.s.mark_shared(["A", "B"], "r1")
        s2 = ScoutStore(self.d)  # reopen
        s2.upsert_profile(person("A"), "matches")  # seen again from another page
        self.assertEqual(s2.digest_candidates(), {"new": [], "updated": []})
        recs = s2.load_profiles()
        self.assertEqual(set(recs["A"]["sources"]), {"chats", "matches"})

    def test_volatile_fields_do_not_count_as_change(self):
        self.s.upsert_profile(person("A"), "chats")
        self.s.mark_shared(["A"], "r1")
        _, ev = self.s.upsert_profile(person("A", last_active="today", online_now=True,
                                             source_detail="other page"), "search")
        self.assertEqual(ev, "unchanged")
        self.assertEqual(self.s.digest_candidates()["updated"], [])

    def test_changed_profile_reappears_as_updated_with_what_changed(self):
        self.s.upsert_profile(person("A", profession="Analyst"), "search")
        self.s.mark_shared(["A"], "r1")
        self.s.upsert_profile(person("A", profession="Engineer"), "search")
        self.s.upsert_profile(person("A", profession="Senior Engineer"), "search")
        cand = self.s.digest_candidates()
        self.assertEqual([r["profile_id"] for r in cand["updated"]], ["A"])
        diff = self.s.diff_since_shown("A")  # relative to what the user SAW
        self.assertEqual(diff, [{"field": "profession", "from": "Analyst", "to": "Senior Engineer"}])
        self.s.mark_shared(["A"], "r2")
        self.assertEqual(self.s.digest_candidates(), {"new": [], "updated": []})

    def test_source_without_a_field_never_erases_it(self):
        self.s.upsert_profile(person("A", chat={"exists": True, "last_message_by": "them"}), "chats")
        _, ev = self.s.upsert_profile(person("A", chat={"exists": None}, income_text=None), "search")
        self.assertEqual(ev, "unchanged")
        self.assertTrue(self.s.load_profiles()["A"]["data"]["chat"]["exists"])

    def test_rejected_never_comes_back_even_if_changed(self):
        self.s.upsert_profile(person("A"), "search")
        self.s.set_user_status("A", "rejected")
        self.s.upsert_profile(person("A", city="Bellevue"), "search")
        self.assertEqual(self.s.digest_candidates(), {"new": [], "updated": []})
        self.assertEqual(ScoutStore(self.d).load_profiles()["A"]["user_status"], "rejected")

    def test_unavailable_profile_left_out(self):
        self.s.upsert_profile(person("A"), "search")
        self.s.mark_unavailable("A")
        self.assertEqual(self.s.digest_candidates()["new"], [])

    def test_interest_change_versions_history_and_stale_flag(self):
        self.s.save_interests({"age_max": 28}, "user", "tightened")
        data, _ = self.s.load_interests()
        st = json.loads((self.d / "run_state.json").read_text())
        hist = (self.d / "interests_history.jsonl").read_text().strip().splitlines()
        self.assertEqual(data["version"], 2)
        self.assertTrue(st["scores_stale"])
        self.assertEqual(len(hist), 2)
        self.assertEqual(json.loads(hist[1])["diff"][0]["field"], "age_max")

    def test_hand_edit_detected_and_never_silently_overwritten(self):
        raw = json.loads(self.s.interests_path.read_text())
        raw["criteria"]["age_max"] = 26
        self.s.interests_path.write_text(json.dumps(raw))
        s2 = ScoutStore(self.d)
        _, ext = s2.load_interests()
        self.assertTrue(ext)
        self.assertEqual(s2.external_edit_diff(), [{"field": "age_max", "from": 30, "to": 26}])
        with self.assertRaises(ExternalEditPending):
            s2.save_interests({"age_max": 40}, "agent")
        self.assertEqual(json.loads(self.s.interests_path.read_text())["criteria"]["age_max"], 26)

    def test_hand_edit_accept(self):
        raw = json.loads(self.s.interests_path.read_text())
        raw["criteria"]["age_max"] = 26
        self.s.interests_path.write_text(json.dumps(raw))
        self.s.accept_external_edit()
        data, ext = self.s.load_interests()
        self.assertFalse(ext)
        self.assertEqual(data["criteria"]["age_max"], 26)

    def test_hand_edit_revert_keeps_the_edited_copy(self):
        raw = json.loads(self.s.interests_path.read_text())
        raw["criteria"]["age_max"] = 26
        self.s.interests_path.write_text(json.dumps(raw))
        self.s.revert_external_edit()
        self.assertEqual(self.s.criteria()["age_max"], 30)
        self.assertTrue(list(self.d.glob("interests.hand-edit-*.json")))

    def test_flat_hand_written_file_is_accepted_shape(self):
        self.s.interests_path.write_text(json.dumps({"age_min": 24, "age_max": 29}))
        data, ext = self.s.load_interests()
        self.assertTrue(ext)
        self.assertEqual(data["criteria"]["age_min"], 24)

    def test_broken_hand_edit_is_not_auto_replaced(self):
        self.s.save_interests({"age_max": 31}, "user", "v2")
        self.s.interests_path.write_text('{"criteria": {"age_max": 29,,}')
        with self.assertRaises(InterestsFileError) as cm:
            ScoutStore(self.d).load_interests()
        self.assertIn("line 1", str(cm.exception))
        self.assertIn(",,", self.s.interests_path.read_text())  # untouched
        self.s.restore_interests_backup()
        self.assertEqual(self.s.criteria()["age_max"], 31)  # last confirmed version
        self.assertTrue(list(self.d.glob("interests.broken-*.json")))

    def test_corrupt_data_file_restored_from_backup(self):
        self.s.upsert_profile(person("A"), "search")
        self.s.upsert_profile(person("B"), "search")
        self.s.profiles_path.write_text("{corrupt")
        s2 = ScoutStore(self.d)
        self.assertIn("A", s2.load_profiles())
        self.assertIn("profiles.json", s2.recovered)

    def test_checkpoint_survives_disconnect(self):
        self.s.save_checkpoint("SCAN", {"chats": {"done": ["SH1"], "next": "SH2"}}, "run-1")
        again = ScoutStore(self.d).load_checkpoint()
        self.assertEqual((again["phase"], again["cursors"]["chats"]["next"]), ("SCAN", "SH2"))
        self.s.clear_checkpoint()
        self.assertIsNone(self.s.load_checkpoint()["phase"])

    def test_find_by_id_url_or_name(self):
        self.s.upsert_profile(person("A", name="Asha Test", profile_url="https://x.invalid/profile/A"), "x")
        self.assertEqual(self.s.find("A"), ["A"])
        self.assertEqual(self.s.find("https://x.invalid/profile/A/"), ["A"])
        self.assertEqual(self.s.find("asha"), ["A"])
        self.assertEqual(self.s.find("nobody"), [])

    def test_single_run_lock(self):
        with self.s.lock():
            with self.assertRaises(RuntimeError):
                with ScoutStore(self.d).lock():
                    pass
        with self.s.lock():  # released
            pass

    def test_judgement_never_marks_profile_changed(self):
        self.s.upsert_profile(person("A"), "search")
        self.s.mark_shared(["A"], "r1")
        self.s.save_judgement("A", 15, "Warm, shared values.")
        self.assertEqual(self.s.digest_candidates(), {"new": [], "updated": []})


if __name__ == "__main__":
    unittest.main()
