"""Scripted demo: two days of realistic, messy use against the FICTIONAL mock site.

  python3 tests/run_scripted_demo.py

Writes tests/demo_transcript.txt - exactly what the terminal printed, with the
temporary folder shown as ~/matrimony-scout-data. Needs Playwright + Chromium.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mock_site import MockSite, browser_login  # noqa: E402

DAY1 = ["lets start", "Shaadi", "my younger sister", "26 - 30", "Seattle, Bay Area", "no smokers",
        "yes", "how can you read the data?", "give me the report", "open the app then", "8", "",
        "age is 27", "looks good", "yes", "why is 1 ranked first", "pass on 3",
        "draft a reply to Asha", "quit"]
DAY2 = ["check status", "change my age range to 26 to 31", "give me the report", "scan", "", "",
        "yes", "what did you show me before", "quit"]


def main():
    site = MockSite().start()
    d = Path(tempfile.mkdtemp(prefix="scout-demo-"))
    env = dict(os.environ, SCOUT_HEADLESS="1", SCOUT_PACE_SECONDS="0.2",
               SCOUT_SITE_URL_OVERRIDE=site.url)
    browser_login(d / "browser_profile", site.url)  # stands in for the person logging in by hand
    out = []
    try:
        for day, lines in (("DAY 1", DAY1), ("DAY 2 (terminal closed and reopened; one profile "
                                             "changed on the site overnight)", DAY2)):
            if day.startswith("DAY 2"):
                site.people["SH103"]["job"] = "Senior Data Analyst"
            r = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "scout.py"),
                                "--data-dir", str(d)], input="\n".join(lines) + "\n",
                               capture_output=True, text=True, env=env, timeout=600)
            typed = iter(lines)
            shown = []
            for line in r.stdout.splitlines():
                while line.startswith("Response: "):  # show what the person typed
                    shown.append("Response: " + next(typed, ""))
                    line = line[len("Response: "):]
                if line:
                    shown.append(line)
            out += [f"===== {day} =====", *shown, ""]
            if r.stderr.strip():
                out += ["STDERR:", r.stderr]
    finally:
        site.stop()
    text = "\n".join(out).replace(str(d), "~/matrimony-scout-data")
    text = re.sub(r"http://127\.0\.0\.1:\d+", "https://fictional-matrimony.example", text)
    text = text.replace("127.0.0.1", "fictional-matrimony.example")
    (HERE / "demo_transcript.txt").write_text(
        "Scripted demo on a FICTIONAL matrimony site (tests/mock_site.py). Every person is made up.\n"
        "Lines after 'Response:' are what the person typed. Site clicks recorded: "
        f"{len(site.actions)} (read-only).\n\n" + text, encoding="utf-8")
    print(text)
    return 0 if "Traceback" not in text and not site.actions else 1


if __name__ == "__main__":
    sys.exit(main())
