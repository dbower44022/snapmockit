# Release Engineering Notes

Last Updated: 09-18-26 01:42 · Revision 1.13

The work that turns the finished application into a product: its identity, continuous integration, packaging, and the first release. Every feature row of the nine product requirements documents was built or recorded as a departure by 09-14-26 (`docs/Freehand-Remainder-Implementation.md`, Section 8.1, names the last of them); this document holds what follows, in the order Doug set on 09-14-26: the identity, then continuous integration, then packaging, then an end-to-end pass on real work, then the two platform backends when their machines exist.

## 1. Status

| Step | Scope | Status | Commits |
|---|---|---|---|
| 1 | The identity: the name, the repository, the licence, the version's one source, the README | Done | faf8e1b, then this commit |
| 2 | Continuous integration: lint, format, types, the suite on the offscreen platform, and the wheel and sdist, on every push | Done: green on GitHub 09-14-26 | 632b30b, 74bc47d |
| 3 | Packaging: the Linux AppImage first (Technical Architecture PRD 7.3), then Flatpak, PyPI, the Windows MSI or portable ZIP, and the macOS bundle | Linux AppImage done 09-15-26 (v0.9.0), v1.0.0 on 09-17-26. **Linux Flatpak done 09-18-26** (`docs/Packaging-Flatpak-Implementation.md`): built in continuous integration on every push and published in **v1.1.0** beside the AppImage. Remaining, in order: the Python Package Index, a Flathub submission, the Windows MSI or portable ZIP, the macOS bundle; and the menu entry the AppImage does not install (end-to-end pass finding 1) | 860f370 to 080e2f3 |
| 4 | An end-to-end pass on real work, on the released AppImage `Snapmockit-0.9.0-x86_64.AppImage`, then the 1.0.0 release | Done 09-17-26: two sittings, one on real work, ended by Doug's call; sixteen findings, all closed but one follow-up (the menu install); the Wayland capture passed; **v1.0.0 released 09-17-26** and started from the main menu on Doug's display (`docs/End-to-End-Pass.md`, Section 9) | def7507 to this commit (tag v1.0.0 on f53c4e5) |
| 5 | The Windows and macOS capture backends, when their machines exist | Waiting: both are stubs; no Windows or macOS machine is available; `docs/Windows-Backend-Kickoff-Prompt.md` is ready for the Windows one | |

## 2. The identity (09-14-26)

Doug confirmed four of the five facts as the code held them and changed one: **the product is named Snapmockit**, so its domain can be registered. `APP_NAME` carries the name and everything a user reads takes it from there; the distribution name is `snapmockit`; the import package stays `snapmock`, so every module path and `python -m snapmock` are unchanged; the version has one source, `snapmock/__init__.py`, which `pyproject.toml` reads through hatchling's dynamic version; the settings and the library keep their on-disk names (`~/.config/SnapMock`, `~/SnapMock/Library`) until a release carries a migration, so a user's settings and library are found; the licence is MIT as it was; the README is written. Technical Architecture PRD 1.48, General UI PRD 2.37. The organisation domain constant reads `snapmockit.com`, an assumption until Doug names the registered domain. Doug renamed the repository to `dbower44022/snapmockit` on 09-14-26 at 17:10 (GitHub redirects the old name); the code's address, the project file's links, the remote, the README, and the nine product requirements documents' headers followed in one commit, so Check for Updates queries the final address from its first release.

## 3. Continuous integration (09-14-26)

`.github/workflows/ci.yml`, on every push to `main` and every pull request, with a run in progress cancelled by a newer one on the same branch. Two jobs on `ubuntu-latest`. **Checks:** the Qt runtime libraries and two font packages installed with apt, uv installed with its cache, the pinned Python installed by uv, `uv sync --locked` so the lock file is the one truth, then `ruff check`, `ruff format --check`, `mypy snapmock`, and the suite on the offscreen platform with the one environmental deselection the kickoff prompts carry (`test_font_combo_reflects_text_item_font`, whose font fallback differs by machine), a 90 minute limit against the 16 minutes the suite takes here since the style-sheet guard of 09-14-26. **Build:** `uv build`, so the wheel and sdist, and with them the dynamic version and the packaging metadata, are proven on every change; both are kept as a workflow artifact. Verified here: the workflow parses, and `uv build` produces `snapmockit-0.1.0-py3-none-any.whl` and its sdist. **The first runs on GitHub, 09-14-26.** The repository was renamed to `dbower44022/snapmockit` and `main` pushed at 17:12 with 48 commits. Run 34897493910: the apt list, uv, the lock, ruff, mypy, and the build job all passed at once, and the tests ran 1630 passed, 19 skipped (six more than here, the display-bound capture tests), 1 failed: the first-action capture test's 3 second wait for the manager's completed signal, which the path meets in 0.12 seconds here and a two-core runner does not. Its wait is 20 seconds since 74bc47d, and the workflow prints the fifteen slowest tests. Run 34899448828 on that commit: **1631 passed, 19 skipped, 1 deselected, in 16 minutes 56 seconds, both jobs green.** The slowest tests on the runner are the theme switches, 30 to 116 seconds each: every change of theme sets the application style sheet, which re-polishes the widgets earlier tests leave alive, the same cost the guard of General UI PRD 2.38 removed from window construction. Deleting closed windows at teardown cuts it: an autouse fixture in `tests/conftest.py` now deletes every closed top-level widget after each test, once pytest-qt has closed the test's own, so the widgets no longer accumulate for the run. Locally the theme switch fell from seconds to 0.6 s and the whole suite from 15 minutes 32 seconds to **6 minutes 8 seconds, 1637 passed, whole**; on the runner (run 34902154516 at 287c6ef) the suite ran **1631 passed, 19 skipped, in 3 minutes 40 seconds**, the whole checks job in 4 minutes 10 seconds against 16 minutes 56 before, and the slowest test anywhere is under a second on the runner and 4 seconds here. Every push is now answered in about five minutes.

## 4. After 1.0.0 (09-17-26)

The product has its first release it stands behind: v1.0.0, the Linux AppImage, after the end-to-end pass on real work. Doug ended that pass after one sitting on real work, where its plan asked for three, so later real use may still turn up defects of the kind the pass found; they go to the issue tracker.

**The Flatpak is done (09-18-26).** Both Linux forms are built and smoke-tested on every push and published together: **v1.1.0** carries `Snapmockit-1.1.0-x86_64.AppImage` and `Snapmockit-1.1.0-x86_64.flatpak`. The work took four phases and found seven things on the display, four of them defects fixed with tests, two in the Library panel that every form had. Its notes are `docs/Packaging-Flatpak-Implementation.md`; two display checks are still owed there (the Wayland capture inside the Flatpak, and Check for Updates from a 1.0.0 Flatpak).

What is left of this list, in order:

1. **The Python Package Index.** The build job already makes the wheel and sdist. What is missing is an account, a trusted publisher (or token) for `dbower44022/snapmockit`, and a publish step in the release job. Only Doug can create the account. A kickoff prompt is not yet written.
2. **A Flathub submission**, which Flatpak decision 2 left for after the bundle had been used. It is a pull request to `flathub/flathub` and a review out of this project's hands; the justification for the home-directory permission it will ask about is written in the Flatpak notes, Section 2.3. After it, `flatpak update` brings users a new version instead of a download.
3. **The menu entry**, end-to-end pass finding 1: an "Add to Menu" action or a first-start offer that installs the desktop entry and icons the AppImage carries. The Flatpak installs its own, so this is the AppImage's gap alone.
4. **Windows and macOS**: the packages of step 3 and the capture backends of step 5, each waiting for its machine.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.13 | 09-18-26 01:42 | Claude (Claude Code) | Step 3's Flatpak done: both Linux forms built on every push and published together in v1.1.0; Section 4 rewritten, with the Python Package Index and a Flathub submission as what follows. |
| 1.12 | 09-17-26 13:31 | Claude (Claude Code) | Section 4: Flatpak moved ahead of PyPI on Doug's choice; its kickoff prompt written. |
| 1.11 | 09-17-26 13:25 | Claude (Claude Code) | Step 4 done: v1.0.0 released and started from the menu; step 5 stated as it stands; Section 4 names what is left, PyPI next. |
| 1.10 | 09-16-26 09:00 | Claude (Claude Code) | Step 4's first sitting recorded: eight findings, the Wayland check owed, two sittings to go at least. |
| 1.9 | 09-15-26 09:48 | Claude (Claude Code) | Step 4 started: the four decisions taken as recommended and the notes document written. |
| 1.8 | 09-15-26 01:34 | Claude (Claude Code) | Step 4's kickoff prompt written, `docs/End-to-End-Pass-Kickoff-Prompt.md` (revision 1.0). |
| 1.7 | 09-15-26 00:45 | Claude (Claude Code) | Step 3 done for Linux: the AppImage released as v0.9.0 with the on-disk names migrated; step 4 pointed at the released file. |
| 1.6 | 09-14-26 18:15 | Claude (Claude Code) | Step 3: Phase 1 of the AppImage work done, the recipe and the first build recorded in its own notes. |
| 1.5 | 09-14-26 18:09 | Claude (Claude Code) | Section 3: the runner's time with the teardown, 3 minutes 40 seconds for the suite, the checks job 4 minutes 10 seconds. |
| 1.4 | 09-14-26 18:03 | Claude (Claude Code) | Section 3: closed windows deleted at each test's teardown; the suite 6 minutes 8 seconds here, whole. |
| 1.3 | 09-14-26 17:52 | Claude (Claude Code) | Step 2 done: the first CI runs on GitHub, the capture test's wait, and the green run at 74bc47d recorded; the theme tests' cost on the runner noted as a follow-up. |
| 1.2 | 09-14-26 17:29 | Claude (Claude Code) | Step 3's kickoff prompt written, `docs/Packaging-AppImage-Kickoff-Prompt.md` (revision 1.0). |
| 1.1 | 09-14-26 17:12 | Claude (Claude Code) | Step 1 done: the repository renamed to dbower44022/snapmockit and every address changed. |
| 1.0 | 09-14-26 17:04 | Claude (Claude Code) | Initial notes: the five steps and their status, the identity decisions of 09-14-26, and the continuous integration workflow as written. Technical Architecture PRD 1.49. |
