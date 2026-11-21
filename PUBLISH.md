# Publishing a new version (for the author)

1. Make the change and run the tests:
   `python3 -m unittest discover -s skills/matrimony_match_scout/tests`
2. Bump the number in `VERSION`, and in `README.md` update the version badge,
   the test-count badge and the skill zip link to match. Add a CHANGELOG entry.
3. Build the Muse zip: `python3 tools/build_release.py`
   (it replaces the zip in `releases/` and checks that the README matches).
4. Commit and push to `main`.
5. Optional: on GitHub, create a Release tagged `v<VERSION>` and attach the zip
   from `releases/`.

Licence is settled: all rights reserved (see LICENSING.md). Do not add a
LICENSE file. Never commit a data folder (`matrimony-scout-data/`), reports,
or real profiles.
