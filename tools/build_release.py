"""Build the two release zips from skills/matrimony_match_scout.

  dist/matrimony_match_scout-muse-v<version>.zip
      Folder matrimony_match_scout/ at top level, exactly as Muse
      custom-skills expects it.
  dist/matrimony-match-scout-claude-v<version>.zip
      Folder matrimony-match-scout/ at top level (Claude requires the
      folder name to match the skill name), SKILL.md carrying the
      name/description frontmatter Claude.ai upload accepts, and no
      skill.yaml (a Muse descriptor Claude does not use).

Run: python3 tools/build_release.py
"""
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "skills" / "matrimony_match_scout"
DIST = ROOT / "dist"
VERSION = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
DESCRIPTION = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["description"]
IGNORE = shutil.ignore_patterns("__pycache__", "_test_data", "*.pyc")


def zip_folder(folder, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(folder.parent))
    return zip_path


def main():
    DIST.mkdir(exist_ok=True)
    staging = DIST / "_staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()

    muse_dir = staging / "matrimony_match_scout"
    shutil.copytree(SRC, muse_dir, ignore=IGNORE)
    muse_zip = zip_folder(muse_dir, DIST / f"matrimony_match_scout-muse-v{VERSION}.zip")

    claude_dir = staging / "matrimony-match-scout"
    shutil.copytree(SRC, claude_dir, ignore=IGNORE)
    (claude_dir / "skill.yaml").unlink(missing_ok=True)
    skill_md = claude_dir / "SKILL.md"
    frontmatter = ("---\nname: matrimony-match-scout\n"
                   f'description: "{DESCRIPTION}"\n---\n\n')
    skill_md.write_text(frontmatter + skill_md.read_text(encoding="utf-8"), encoding="utf-8")
    claude_zip = zip_folder(claude_dir, DIST / f"matrimony-match-scout-claude-v{VERSION}.zip")

    shutil.rmtree(staging)
    for z in (muse_zip, claude_zip):
        with zipfile.ZipFile(z) as f:
            tops = sorted({n.split("/")[0] for n in f.namelist()})
        print(f"{z.name}: top-level {tops}, {z.stat().st_size} bytes")


if __name__ == "__main__":
    main()
