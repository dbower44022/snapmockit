# Release Engineering Notes

Last Updated: 09-14-26 17:04 · Revision 1.0

The work that turns the finished application into a product: its identity, continuous integration, packaging, and the first release. Every feature row of the nine product requirements documents was built or recorded as a departure by 09-14-26 (`docs/Freehand-Remainder-Implementation.md`, Section 8.1, names the last of them); this document holds what follows, in the order Doug set on 09-14-26: the identity, then continuous integration, then packaging, then an end-to-end pass on real work, then the two platform backends when their machines exist.

## 1. Status

| Step | Scope | Status | Commits |
|---|---|---|---|
| 1 | The identity: the name, the repository, the licence, the version's one source, the README | Done but for the repository's rename on GitHub, which is Doug's | faf8e1b |
| 2 | Continuous integration: lint, format, types, the suite on the offscreen platform, and the wheel and sdist, on every push | Written; its first run waits for a push | this commit |
| 3 | Packaging: the Linux AppImage first (Technical Architecture PRD Section 9), then Flatpak, PyPI, the Windows MSI or portable ZIP, and the macOS bundle | Not started | |
| 4 | An end-to-end pass on real work, on the first AppImage | Not started | |
| 5 | The Windows and macOS capture backends, when their machines exist | Waiting | |

## 2. The identity (09-14-26)

Doug confirmed four of the five facts as the code held them and changed one: **the product is named Snapmockit**, so its domain can be registered. `APP_NAME` carries the name and everything a user reads takes it from there; the distribution name is `snapmockit`; the import package stays `snapmock`, so every module path and `python -m snapmock` are unchanged; the version has one source, `snapmock/__init__.py`, which `pyproject.toml` reads through hatchling's dynamic version; the settings and the library keep their on-disk names (`~/.config/SnapMock`, `~/SnapMock/Library`) until a release carries a migration, so a user's settings and library are found; the licence is MIT as it was; the README is written. Technical Architecture PRD 1.48, General UI PRD 2.37. The organisation domain constant reads `snapmockit.com`, an assumption until Doug names the registered domain. The repository stays `dbower44022/Snagit_FOSS` in the code until Doug renames it on GitHub; the address, the project file's links, the remote, and the README then follow in one commit, and Check for Updates, which queries that address, must see the rename before any release.

## 3. Continuous integration (09-14-26)

`.github/workflows/ci.yml`, on every push to `main` and every pull request, with a run in progress cancelled by a newer one on the same branch. Two jobs on `ubuntu-latest`. **Checks:** the Qt runtime libraries and two font packages installed with apt, uv installed with its cache, the pinned Python installed by uv, `uv sync --locked` so the lock file is the one truth, then `ruff check`, `ruff format --check`, `mypy snapmock`, and the suite on the offscreen platform with the one environmental deselection the kickoff prompts carry (`test_font_combo_reflects_text_item_font`, whose font fallback differs by machine), a 90 minute limit against the 16 minutes the suite takes here since the style-sheet guard of 09-14-26. **Build:** `uv build`, so the wheel and sdist, and with them the dynamic version and the packaging metadata, are proven on every change; both are kept as a workflow artifact. Verified here: the workflow parses, and `uv build` produces `snapmockit-0.1.0-py3-none-any.whl` and its sdist. Not yet verified: the first run on GitHub, which needs a push; the apt package list is the usual set for PyQt6 on a headless Ubuntu runner and may need a library added when that run shows one missing.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-14-26 17:04 | Claude (Claude Code) | Initial notes: the five steps and their status, the identity decisions of 09-14-26, and the continuous integration workflow as written. Technical Architecture PRD 1.49. |
