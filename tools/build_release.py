"""Build the Muse skill zip from skills/matrimony_match_scout.

  releases/matrimony_match_scout-muse-v<VERSION>.zip
      Folder matrimony_match_scout/ at the top level, exactly as Muse
      custom-skills expects it. Older zips in releases/ are removed so the
      README link always points at the only one.

The version comes from the VERSION file at the repository root.
Run: python3 tools/build_release.py
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "skills" / "matrimony_match_scout"
OUT = ROOT / "releases"
VERSION = (ROOT / "VERSION").read_text().strip()
SKIP = {"__pycache__", "_test_data"}


def main():
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("matrimony_match_scout-muse-v*.zip"):
        old.unlink()
    target = OUT / f"matrimony_match_scout-muse-v{VERSION}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(SRC.rglob("*")):
            if p.is_file() and not (SKIP & set(p.parts)) and p.suffix != ".pyc":
                z.write(p, Path("matrimony_match_scout") / p.relative_to(SRC))
    with zipfile.ZipFile(target) as z:
        tops = sorted({n.split("/")[0] for n in z.namelist()})
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    link_ok = f"releases/{target.name}" in readme and f"version-v{VERSION}-" in readme
    print(f"{target.relative_to(ROOT)}: top-level {tops}, {target.stat().st_size} bytes; "
          f"README link and badge {'match' if link_ok else 'DO NOT MATCH - update README.md'}")
    return 0 if link_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
