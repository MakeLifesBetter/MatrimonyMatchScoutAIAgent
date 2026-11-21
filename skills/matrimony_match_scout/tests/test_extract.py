"""Extraction: page text -> schema; chats -> summaries only (never copies)."""
import unittest
from datetime import date

from helpers import ROOT  # noqa: F401
import extract

TABLE = """Home | Inbox | Matches
Asha Rao
27 yrs, 5' 4", Seattle
Basic Details
Profile ID\tSH101
Height\t5 ft 4 in
Lives in\tSeattle, Washington, USA
Marital Status\tNever Married
Mother Tongue\tTelugu
Religion\tHindu
Community\tNot specified
Education & Career
Highest Education\tMS Computer Science
Profession\tSoftware Engineer
Annual Income\tINR 20 - 25 Lakh
Lifestyle
Diet\tVeg
Smoking\tNo
Drinking\tOccasionally
About Me
I love hiking and cooking.
Family is important to me.
Horoscope
Rashi
Mesha
Nakshatra
Ashwini
Manglik
No
Send Interest
"""


class ExtractTests(unittest.TestCase):
    def test_table_layout_all_fields(self):
        r = extract.extract_profile(TABLE, url="https://site.invalid/profile/SH101", heading="Asha Rao")
        self.assertEqual(r["profile_id"], "SH101")
        self.assertEqual((r["name"], r["age"], r["height_cm"]), ("Asha Rao", 27, 163))
        self.assertEqual((r["city"], r["state"], r["country"]), ("Seattle", "Washington", "USA"))
        self.assertEqual(r["marital_status"], "never_married")
        self.assertEqual(r["education"], "MS Computer Science")
        self.assertEqual(r["income_text"], "INR 20 - 25 Lakh")
        self.assertEqual((r["food"], r["smoking"], r["drinking"]), ("vegetarian", "never", "occasionally"))
        self.assertIsNone(r["community"])  # "Not specified" is unknown, never guessed
        self.assertEqual(r["about_me"], "I love hiking and cooking. Family is important to me.")
        self.assertEqual(r["horoscope"], {"rashi": "Mesha", "nakshatra": "Ashwini", "manglik": "no"})

    def test_colon_layout_and_dob(self):
        text = ("Name: Ravi Kumar\nDate of Birth: 12 Mar 1997\nHeight: 175 cm\nLocation: Pune, India\n"
                "Marital status: Divorced\nDiet: Non-Veg\nOccupation: Doctor\nIncome: not shown")
        r = extract.extract_profile(text, today=date(2026, 11, 20))
        self.assertEqual((r["name"], r["age"], r["height_cm"]), ("Ravi Kumar", 29, 175))
        self.assertEqual((r["city"], r["country"]), ("Pune", "India"))
        self.assertEqual((r["marital_status"], r["food"]), ("divorced", "non_vegetarian"))
        self.assertIsNone(r["income_text"])

    def test_missing_fields_stay_unknown(self):
        r = extract.extract_profile("Name: Only A Name")
        self.assertEqual(r["name"], "Only A Name")
        for f in ("age", "city", "education", "religion", "smoking"):
            self.assertIsNone(r[f])

    def test_learned_alias_from_calibration(self):
        r = extract.extract_profile("Name: X\nHometown: Nagpur", extra_aliases={"hometown": "city"})
        self.assertEqual(r["city"], "Nagpur")

    def test_profile_id_from_url_shapes(self):
        self.assertIsNone(extract.profile_id_from_url("https://a.invalid/search?page=2"))
        self.assertEqual(extract.profile_id_from_url("https://a.invalid/profile/SH900"), "SH900")
        self.assertEqual(extract.profile_id_from_url("https://a.invalid/view?profileid=AB12"), "AB12")

    def test_chat_summary_never_copies_messages(self):
        text = ("Asha: Hi! I saw you like the Rainier trails.\nYou: Yes, love them.\n"
                "Asha: Would you like a video call this weekend?")
        c = extract.parse_chat(text)
        self.assertEqual((c["exists"], c["message_count"], c["initiated_by"], c["last_message_by"]),
                         (True, 3, "them", "them"))
        self.assertIn("asks you something", c["last_message_summary"])
        blob = str(c)
        self.assertNotIn("Rainier", blob)
        self.assertNotIn("love them", blob)

    def test_whatsapp_export_and_red_flag_evidence_is_short(self):
        text = ("12/03/2026, 9:15 pm - Kiran: Hello\n12/03/2026, 9:20 pm - Me Myself: Hi Kiran\n"
                "13/03/2026, 8:00 am - Kiran: Please send money via gift card, it is urgent")
        c = extract.parse_chat(text, my_names=["Me Myself"], red_flags=["asks for money"])
        self.assertEqual(c["message_count"], 3)
        self.assertEqual(c["last_message_by"], "them")
        self.assertEqual(c["red_flags"], ["asks for money (mentions 'send money')"])

    def test_no_chat(self):
        self.assertFalse(extract.parse_chat("Inbox is empty")["exists"])


if __name__ == "__main__":
    unittest.main()
