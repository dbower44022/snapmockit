# Release Engineering Notes

Last Updated: 09-21-26 00:39 · Revision 1.20

The work that turns the finished application into a product: its identity, continuous integration, packaging, and the first release. Every feature row of the nine product requirements documents was built or recorded as a departure by 09-14-26 (`docs/Freehand-Remainder-Implementation.md`, Section 8.1, names the last of them); this document holds what follows, in the order Doug set on 09-14-26: the identity, then continuous integration, then packaging, then an end-to-end pass on real work, then the two platform backends when their machines exist.

## 1. Status

| Step | Scope | Status | Commits |
|---|---|---|---|
| 1 | The identity: the name, the repository, the licence, the version's one source, the README | Done | faf8e1b, then this commit |
| 2 | Continuous integration: lint, format, types, the suite on the offscreen platform, and the wheel and sdist, on every push | Done: green on GitHub 09-14-26 | 632b30b, 74bc47d |
| 3 | Packaging: the Linux AppImage first (Technical Architecture PRD 7.3), then Flatpak, PyPI, the Windows MSI or portable ZIP, and the macOS bundle | Linux AppImage done 09-15-26 (v0.9.0), v1.0.0 on 09-17-26. **Linux Flatpak done 09-18-26** (`docs/Packaging-Flatpak-Implementation.md`): built in continuous integration on every push and published in **v1.1.0** beside the AppImage. No Flathub submission (Doug's decision of 09-18-26, `docs/Packaging-Flathub-Implementation.md`). **The Python Package Index done 09-19-26** (`docs/Packaging-PyPI-Implementation.md`): `pipx install snapmockit` installs the application on any platform with Python 3.12 or later, published from the release workflow through trusted publishing on Doug's approval, first as **v1.2.0**. **The menu entry done 09-20-26 and released as v1.3.0 on 09-21-26** (`docs/Menu-Entry-Implementation.md`): Help > Add to Menu writes the desktop entry, the icon set, and the `.smk` file type from inside the application, and Remove from Menu takes them away, which closes end-to-end pass finding 1 for the AppImage and the index's form. Remaining, in order: the Windows MSI or portable ZIP, the macOS bundle | 860f370 to 080e2f3 |
| 4 | An end-to-end pass on real work, on the released AppImage `Snapmockit-0.9.0-x86_64.AppImage`, then the 1.0.0 release | Done 09-17-26: two sittings, one on real work, ended by Doug's call; sixteen findings, all closed but one follow-up (the menu install); the Wayland capture passed; **v1.0.0 released 09-17-26** and started from the main menu on Doug's display (`docs/End-to-End-Pass.md`, Section 9) | def7507 to this commit (tag v1.0.0 on f53c4e5) |
| 5 | The Windows and macOS capture backends, when their machines exist | Waiting: both are stubs; no Windows or macOS machine is available; `docs/Windows-Backend-Kickoff-Prompt.md` is ready for the Windows one | |

## 2. The identity (09-14-26)

Doug confirmed four of the five facts as the code held them and changed one: **the product is named Snapmockit**, so its domain can be registered. `APP_NAME` carries the name and everything a user reads takes it from there; the distribution name is `snapmockit`; the import package stays `snapmock`, so every module path and `python -m snapmock` are unchanged; the version has one source, `snapmock/__init__.py`, which `pyproject.toml` reads through hatchling's dynamic version; the settings and the library keep their on-disk names (`~/.config/SnapMock`, `~/SnapMock/Library`) until a release carries a migration, so a user's settings and library are found; the licence is MIT as it was; the README is written. Technical Architecture PRD 1.48, General UI PRD 2.37. The organisation domain constant reads `snapmockit.com`, an assumption until Doug names the registered domain. Doug renamed the repository to `dbower44022/snapmockit` on 09-14-26 at 17:10 (GitHub redirects the old name); the code's address, the project file's links, the remote, the README, and the nine product requirements documents' headers followed in one commit, so Check for Updates queries the final address from its first release.

## 3. Continuous integration (09-14-26)

`.github/workflows/ci.yml`, on every push to `main` and every pull request, with a run in progress cancelled by a newer one on the same branch. Two jobs on `ubuntu-latest`. **Checks:** the Qt runtime libraries and two font packages installed with apt, uv installed with its cache, the pinned Python installed by uv, `uv sync --locked` so the lock file is the one truth, then `ruff check`, `ruff format --check`, `mypy snapmock`, and the suite on the offscreen platform with the one environmental deselection the kickoff prompts carry (`test_font_combo_reflects_text_item_font`, whose font fallback differs by machine), a 90 minute limit against the 16 minutes the suite takes here since the style-sheet guard of 09-14-26. **Build:** `uv build`, so the wheel and sdist, and with them the dynamic version and the packaging metadata, are proven on every change; both are kept as a workflow artifact. Verified here: the workflow parses, and `uv build` produces `snapmockit-0.1.0-py3-none-any.whl` and its sdist. **The first runs on GitHub, 09-14-26.** The repository was renamed to `dbower44022/snapmockit` and `main` pushed at 17:12 with 48 commits. Run 34897493910: the apt list, uv, the lock, ruff, mypy, and the build job all passed at once, and the tests ran 1630 passed, 19 skipped (six more than here, the display-bound capture tests), 1 failed: the first-action capture test's 3 second wait for the manager's completed signal, which the path meets in 0.12 seconds here and a two-core runner does not. Its wait is 20 seconds since 74bc47d, and the workflow prints the fifteen slowest tests. Run 34899448828 on that commit: **1631 passed, 19 skipped, 1 deselected, in 16 minutes 56 seconds, both jobs green.** The slowest tests on the runner are the theme switches, 30 to 116 seconds each: every change of theme sets the application style sheet, which re-polishes the widgets earlier tests leave alive, the same cost the guard of General UI PRD 2.38 removed from window construction. Deleting closed windows at teardown cuts it: an autouse fixture in `tests/conftest.py` now deletes every closed top-level widget after each test, once pytest-qt has closed the test's own, so the widgets no longer accumulate for the run. Locally the theme switch fell from seconds to 0.6 s and the whole suite from 15 minutes 32 seconds to **6 minutes 8 seconds, 1637 passed, whole**; on the runner (run 34902154516 at 287c6ef) the suite ran **1631 passed, 19 skipped, in 3 minutes 40 seconds**, the whole checks job in 4 minutes 10 seconds against 16 minutes 56 before, and the slowest test anywhere is under a second on the runner and 4 seconds here. Every push is now answered in about five minutes.

## 4. After 1.0.0 (09-17-26)

The product has its first release it stands behind: v1.0.0, the Linux AppImage, after the end-to-end pass on real work. Doug ended that pass after one sitting on real work, where its plan asked for three, so later real use may still turn up defects of the kind the pass found; they go to the issue tracker.

**The Flatpak is done (09-18-26).** Both Linux forms are built and smoke-tested on every push and published together: **v1.1.0** carries `Snapmockit-1.1.0-x86_64.AppImage` and `Snapmockit-1.1.0-x86_64.flatpak`. The work took four phases and found seven things on the display, four of them defects fixed with tests, two in the Library panel that every form had. Its notes are `docs/Packaging-Flatpak-Implementation.md`; two display checks are still owed there (the Wayland capture inside the Flatpak, and Check for Updates from a 1.0.0 Flatpak).

**No Flathub submission (09-18-26).** Doug chose Flathub ahead of the Python Package Index, and then closed that work at its first phase. Flathub's current documentation forbids an AI tool to open or answer a submission pull request, and refuses the home-directory permission to software that shows signs of large language model use; 394 of this repository's 422 commits carry a Claude co-author line. The bundle on the GitHub release stays the Flatpak route, and a Flatpak user updates by downloading the next one. The notes, with Flathub's requirements checked against the repository for a later reopening, are `docs/Packaging-Flathub-Implementation.md`.

**The Python Package Index is done (09-19-26).** **v1.2.0**, published 09-19-26, is the first release there and carries the AppImage and the Flatpak bundle as well. The work took three phases and a close-out, and five decisions; its notes are `docs/Packaging-PyPI-Implementation.md`. The rehearsal on the test index found one defect, which is fixed: Check for Updates could not read a running pre-release. Three display checks are owed there.

**The menu entry is done (09-20-26).** End-to-end pass finding 1, the last one left open by that pass, is closed for the two forms it applied to. The work took three phases and a close-out and four decisions; its notes are `docs/Menu-Entry-Implementation.md`. The display run found one thing the tests could not: with a Flatpak installed, Cinnamon lists its exported entry beside the user's own file of the same application id, so the desktop shows two Snapmockit entries, and the action now says so when it finds another form's entry. **Released as v1.3.0 on 09-21-26**, tag `v1.3.0` on `f2e0d0e`: the GitHub release carries `Snapmockit-1.3.0-x86_64.AppImage` and `Snapmockit-1.3.0-x86_64.flatpak`, and the wheel and source distribution went to the Python Package Index on Doug's approval at 00:27, attested to `dbower44022/snapmockit` and `ci.yml`. Two display checks are owed on the released files: Help > Add to Menu from the released AppImage, and from a `pipx install snapmockit` of 1.3.0.

What is left of this list, in order:

1. **Windows and macOS**: the packages of step 3 and the capture backends of step 5, each waiting for its machine. `docs/Windows-Backend-Kickoff-Prompt.md` is ready for the Windows backend; the Windows package has no kickoff prompt yet.

## 5. The release process

Every release is built and published from a clean runner; nothing is built here for a release. The steps, in order:

1. **The release commit on `main`**: `snapmock/__init__.py` carries the version, and every document a user reads is brought to it. **The README is part of this commit**, since the Python Package Index shows the description uploaded with the files and a later edit reaches that page only with the next release.
2. **The suite at that commit**, run from a scratch `git worktree` with `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font`.
3. **`uv build`, then `uvx twine check --strict dist/*`**, so the index will take the files and render the README.
4. **Push `main`** and wait for the run to be green in all five jobs.
5. **The release notes**, written for Doug to read before the tag.
6. **The annotated tag** `vX.Y.Z` on that commit, with the notes as its message, pushed on Doug's word. The release job refuses a tag that is not `v` followed by the package's version.
7. **The GitHub release** is published by the workflow with the AppImage and the Flatpak bundle attached.
8. **The upload to the Python Package Index** waits for Doug's approval of the `pypi` environment on the run's page (Review deployments, tick `pypi`, Approve and deploy). It uploads the wheel and sdist of the same run through trusted publishing. A version uploaded there can never be reused, so the approval is the last point at which a release can be stopped.
9. **Read back**: the release page, `https://pypi.org/project/snapmockit/`, and the attestation of each uploaded file.

## 6. Waiting, and on what (09-21-26)

Everything below is ready to start and blocked only on the thing named. Nothing here is in progress, and no session should begin one of these without the condition being met.

| What | Waiting on | Ready |
|---|---|---|
| The two display checks v1.3.0 owes: Help > Add to Menu from the **released** AppImage, and from `pipx install snapmockit` of 1.3.0 | Doug, about ten minutes at his display. No new machine needed | The checks are the ones already passed on local builds (`docs/Menu-Entry-Implementation.md`, Sections 7 to 7.2); a short checklist page is written when he says |
| **The Windows package**: the MSI or the portable archive of Technical Architecture PRD 7.3 | **A Windows personal computer Doug has access to.** Doug's decision of 09-21-26: this waits until he has one | No kickoff prompt yet; it is written when the machine is in sight, since what it can assume depends on the machine |
| **The Windows capture backend**: `snapmock/capture/windows.py`, written and never run on Windows | The same machine | `docs/Windows-Backend-Kickoff-Prompt.md` is written and ready |
| **macOS**: the bundle of 7.3 and the backend of step 5 | A Mac, which does not exist here | `docs/Windows-macOS-Backends-Kickoff-Prompt.md` covers the backend |

The Windows package and the Windows capture backend are one sitting's work on one machine and should be taken together.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.20 | 09-21-26 00:39 | Claude (Claude Code) | Section 6 added: what is waiting and on what. The Windows package and the Windows capture backend wait on a Windows personal computer Doug has access to (his decision of 09-21-26); macOS waits on a Mac; and v1.3.0's two display checks wait only on ten minutes of Doug's time. |
| 1.19 | 09-21-26 00:28 | Claude (Claude Code) | **v1.3.0 released 09-21-26**: the menu entry reaches users. Tag `v1.3.0` on `f2e0d0e`; the GitHub release carries both Linux files and the index took the wheel and source distribution on Doug's approval at 00:27, attested to the repository's workflow. Two display checks are owed on the released files. |
| 1.18 | 09-20-26 23:34 | Claude (Claude Code) | Sections 1 and 4: the menu entry is done, which closes the last finding the end-to-end pass left open. Help > Add to Menu writes the desktop entry, the icon set, and the `.smk` file type, and Remove from Menu takes them away; the display run of 09-20-26 passed and found one thing besides, that a machine with the Flatpak installed lists two menu entries. Nothing of it is in a release yet: the run was made on builds of the commit, since v1.2.0 predates the work. What is left of the list is Windows and macOS. |
| 1.17 | 09-20-26 14:05 | Claude (Claude Code) | Section 4: the menu entry is next on Doug's choice of 09-20-26, and its kickoff prompt is written. |
| 1.16 | 09-20-26 13:31 | Claude (Claude Code) | Step 3's Python Package Index done: v1.2.0 published there 09-19-26 through trusted publishing on Doug's approval. Section 4 rewritten, with the menu entry next and Windows and macOS after it; new Section 5, the release process, with the upload to the index as its step 8. |
| 1.15 | 09-18-26 10:22 | Claude (Claude Code) | No Flathub submission, Doug's decision of 09-18-26 against Flathub's Generative AI and exception policies; step 3 and Section 4 bring the Python Package Index next, its kickoff prompt written. The header's revision, left at 1.13 by the 1.14 row, is brought into step. |
| 1.14 | 09-18-26 01:52 | Claude (Claude Code) | Section 4: the Flathub submission moved ahead of the Python Package Index on Doug's choice of 09-18-26; its kickoff prompt written, with what the Flathub linter already says about the manifest. |
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
