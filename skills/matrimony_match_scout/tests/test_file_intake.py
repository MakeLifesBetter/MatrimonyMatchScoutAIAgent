"""File reading: biodata txt/pdf/docx, chat exports, broker sheets, captures, screenshots."""
import csv
import unittest
import zipfile

from helpers import tmpdir
import file_intake
from openpyxl import Workbook
from state_store import ScoutStore


def tiny_pdf(path, lines):
    content = "BT /F1 12 Tf 50 750 Td 14 TL " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF"
    path.write_bytes(out.encode("latin-1"))


def tiny_docx(path, lines):
    body = "".join(f"<w:p><w:r><w:t>{l}</w:t></w:r></w:p>" for l in lines)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document><w:body>{body}</w:body></w:document>")


class FileIntakeTests(unittest.TestCase):
    def setUp(self):
        self.d = tmpdir()
        self.s = ScoutStore(self.d / "data")
        self.f = self.d / "files"
        self.f.mkdir()

    def read(self):
        return file_intake.read_folder(self.s, self.f, {"red_flags": ["asks for money"]})

    def test_biodata_text_docx_and_pdf(self):
        (self.f / "biodata_ravi.txt").write_text("Name: Ravi Test\nAge: 29\nEducation: MBA\nLocation: Pune, India")
        tiny_docx(self.f / "biodata_kiran.docx", ["Name: Kiran Test", "Age: 28", "Profession: Doctor"])
        tiny_pdf(self.f / "biodata_anu.pdf", ["Name: Anu Test", "Age: 27", "City: Hyderabad"])
        got = self.read()
        by = {r["name"]: r for r in got["records"]}
        self.assertEqual(by["Ravi Test"]["city"], "Pune")
        self.assertEqual(by["Kiran Test"]["profession"], "Doctor")
        try:
            import pypdf  # noqa: F401
            self.assertEqual(by["Anu Test"]["city"], "Hyderabad")
        except ImportError:
            pass
        self.assertTrue(all(r["source"] == "file" for r in got["records"]))

    def test_broker_spreadsheets_csv_and_xlsx_contact_never_copied(self):
        with open(self.f / "broker.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Name", "Age", "City", "Education", "Phone", "Notes"])
            w.writerow(["Broker Person One", "27", "Seattle", "MS", "555-0100", "nice family"])
        wb = Workbook()
        wb.active.append(["Name", "Age", "Location"])
        wb.active.append(["Broker Person Two", 30, "Austin, USA"])
        wb.save(self.f / "broker2.xlsx")
        got = self.read()
        names = sorted(r["name"] for r in got["records"])
        self.assertEqual(names, ["Broker Person One", "Broker Person Two"])
        self.assertNotIn("555-0100", str(got["records"]))
        self.assertEqual(got["unmapped"], {"broker.csv": ["Notes"]})
        self.assertIn("row 2", got["records"][0]["source_detail"])

    def test_chat_export_summary_only(self):
        (self.f / "WhatsApp Chat with Meena.txt").write_text(
            "01/11/2026, 10:00 am - Meena: Hello, how are you?\n"
            "01/11/2026, 10:05 am - Vishal: Fine thanks, you?\n"
            "02/11/2026, 09:00 am - Meena: Can you send money for my visa fee?\n")
        rec = self.read()["records"][0]
        self.assertEqual(rec["name"], "Meena")
        self.assertEqual(rec["chat"]["last_message_by"], "them")
        self.assertEqual(rec["chat"]["initiated_by"], "them")
        self.assertTrue(rec["chat"]["red_flags"])
        self.assertNotIn("visa fee", str(rec))

    def test_screenshot_and_unknown_files_skipped_politely(self):
        (self.f / "shot.png").write_bytes(b"\x89PNG")
        (self.f / "weird.bin").write_bytes(b"\x00")
        skipped = dict(self.read()["skipped"])
        self.assertIn("Muse reads these", skipped["shot.png"])
        self.assertIn("weird.bin", skipped)

    def test_terminal_captures_are_readable(self):
        (self.f / "profile_SH9001.txt").write_text(
            "URL: https://site.invalid/profile/SH9001\nCaptured: x\n\nName: Cap Test\nAge: 26")
        rec = self.read()["records"][0]
        self.assertEqual((rec["profile_id"], rec["source"]), ("SH9001", "scan_capture"))


if __name__ == "__main__":
    unittest.main()
