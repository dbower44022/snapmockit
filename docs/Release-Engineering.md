# Release Engineering Notes

Last Updated: 09-14-26 17:52 · Revision 1.3

The work that turns the finished application into a product: its identity, continuous integration, packaging, and the first release. Every feature row of the nine product requirements documents was built or recorded as a departure by 09-14-26 (`docs/Freehand-Remainder-Implementation.md`, Section 8.1, names the last of them); this document holds what follows, in the order Doug set on 09-14-26: the identity, then continuous integration, then packaging, then an end-to-end pass on real work, then the two platform backends when their machines exist.

## 1. Status

| Step | Scope | Status | Commits |
|---|---|---|---|
| 1 | The identity: the name, the repository, the licence, the version's one source, the README | Done | faf8e1b, then this commit |
| 2 | Continuous integration: lint, format, types, the suite on the offscreen platform, and the wheel and sdist, on every push | Done: green on GitHub 09-14-26 | 632b30b, 74bc47d |
| 3 | Packaging: the Linux AppImage first (Technical Architecture PRD 7.3), then Flatpak, PyPI, the Windows MSI or portable ZIP, and the macOS bundle | Kickoff written: `docs/Packaging-AppImage-Kickoff-Prompt.md` (revision 1.0), not yet run | |
| 4 | An end-to-end pass on real work, on the first AppImage | Not started | |
| 5 | The Windows and macOS capture backends, when their machines exist | Waiting | |

## 2. The identity (09-14-26)

Doug confirmed four of the five facts as the code held them and changed one: **the product is named Snapmockit**, so its domain can be registered. `APP_NAME` carries the name and everything a user reads takes it from there; the distribution name is `snapmockit`; the import package stays `snapmock`, so every module path and `python -m snapmock` are unchanged; the version has one source, `snapmock/__init__.py`, which `pyproject.toml` reads through hatchling's dynamic version; the settings and the library keep their on-disk names (`~/.config/SnapMock`, `~/SnapMock/Library`) until a release carries a migration, so a user's settings and library are found; the licence is MIT as it was; the README is written. Technical Architecture PRD 1.48, General UI PRD 2.37. The organisation domain constant reads `snapmockit.com`, an assumption until Doug names the registered domain. Doug renamed the repository to `dbower44022/snapmockit` on 09-14-26 at 17:10 (GitHub redirects the old name); the code's address, the project file's links, the remote, the README, and the nine product requirements documents' headers followed in one commit, so Check for Updates queries the final address from its first release.

## 3. Continuous integration (09-14-26)

`.github/workflows/ci.yml`, on every push to `main` and every pull request, with a run in progress cancelled by a newer one on the same branch. Two jobs on `ubuntu-latest`. **Checks:** the Qt runtime libraries and two font packages installed with apt, uv installed with its cache, the pinned Python installed by uv, `uv sync --locked` so the lock file is the one truth, then `ruff check`, `ruff format --check`, `mypy snapmock`, and the suite on the offscreen platform with the one environmental deselection the kickoff prompts carry (`test_font_combo_reflects_text_item_font`, whose font fallback differs by machine), a 90 minute limit against the 16 minutes the suite takes here since the style-sheet guard of 09-14-26. **Build:** `uv build`, so the wheel and sdist, and with them the dynamic version and the packaging metadata, are proven on every change; both are kept as a workflow artifact. Verified here: the workflow parses, and `uv build` produces `snapmockit-0.1.0-py3-none-any.whl` and its sdist. **The first runs on GitHub, 09-14-26.** The repository was renamed to `dbower44022/snapmockit` and `main` pushed at 17:12 with 48 commits. Run 34897493910: the apt list, uv, the lock, ruff, mypy, and the build job all passed at once, and the tests ran 1630 passed, 19 skipped (six more than here, the display-bound capture tests), 1 failed: the first-action capture test's 3 second wait for the manager's completed signal, which the path meets in 0.12 seconds here and a two-core runner does not. Its wait is 20 seconds since 74bc47d, and the workflow prints the fifteen slowest tests. Run 34899448828 on that commit: **1631 passed, 19 skipped, 1 deselected, in 16 minutes 56 seconds, both jobs green.** The slowest tests on the runner are the theme switches, 30 to 116 seconds each: every change of theme sets the application style sheet, which re-polishes the widgets earlier tests leave alive, the same cost the guard of General UI PRD 2.38 removed from window construction. Deleting closed windows at teardown would cut it and the runner's time with it; a follow-up, not a fault.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 09-14-26 17:52 | Claude (Claude Code) | Step 2 done: the first CI runs on GitHub, the capture test's wait, and the green run at 74bc47d recorded; the theme tests' cost on the runner noted as a follow-up. |
| 1.2 | 09-14-26 17:29 | Claude (Claude Code) | Step 3's kickoff prompt written, `docs/Packaging-AppImage-Kickoff-Prompt.md` (revision 1.0). |
| 1.1 | 09-14-26 17:12 | Claude (Claude Code) | Step 1 done: the repository renamed to dbower44022/snapmockit and every address changed. |
| 1.0 | 09-14-26 17:04 | Claude (Claude Code) | Initial notes: the five steps and their status, the identity decisions of 09-14-26, and the continuous integration workflow as written. Technical Architecture PRD 1.49. |
