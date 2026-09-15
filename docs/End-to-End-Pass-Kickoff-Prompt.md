# Kickoff Prompt: The End-to-End Pass on Real Work

Last Updated: 09-15-26 01:33 · Revision 1.0

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. Start it only when no other session is committing in this working directory and no CI run of the current commit is in progress, since a push cancels a run in progress on the same branch. This is step 4 of the release-engineering list (`docs/Release-Engineering.md`, Section 1): the released AppImage, `Snapmockit-0.9.0-x86_64.AppImage`, used for real work by Doug over several sittings, every finding recorded and every defect fixed, and then the first release the product stands behind, `1.0.0`. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) still governs the standards; this one governs the work. Where the two disagree, the general prompt wins and this one is corrected. The work is three phases and a close-out; a session pasting this prompt starts at the first phase not marked done in Section 1 of the notes document this work creates, and Phase 2 is expected to span more than one session.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root. No other repository is involved in this session.

## Task

Take Snapmockit from its first packaged release to the release it stands behind:

- **The pass.** Doug does his real screenshot work with the released AppImage and nothing else for the length of the pass: captures for real documents, annotation with the tools he reaches for, exports to the formats the documents need, projects saved and returned to, Snagit files from his archive opened and, where he needs it, written back. Every sitting is recorded: what was done, what got in the way, what broke, what was missed. The session never invents the work; Doug names it.
- **The findings, triaged and closed.** Each finding is one of three things: a defect against a product requirements document, fixed in this work with a test and recorded in that document's change log; a departure from a product requirements document that Doug decides to keep, recorded as such; or a follow-up, listed for a later kickoff and not built here. Nothing is left unclassified.
- **The release, `1.0.0`**, when the exit criterion of decision 1 is met: the version set, the tag pushed, the release job seen to publish, Check for Updates seen from the 0.9.0 AppImage to find it, and the README's status line saying the product is released.

The session opens by presenting the four decisions below with the consequential decision template and waits. Nothing is built before they are taken.

## Read first, in this order

1. `docs/Release-Engineering.md` (revision 1.7 or later): Section 1's five steps, and Sections 2 and 3 for what the identity and continuous integration settled.
2. `docs/Packaging-AppImage-Implementation.md` (revision 2.0 or later), whole: how the AppImage is built and released, what its display run showed, the migration of the on-disk names, and Section 11 for what remains of packaging and the one display check still owed.
3. `docs/General-UI-Acceptance-Pass-Kickoff-Prompt.md` and `docs/General-UI-Implementation.md`, Section 16: how an acceptance pass was run and recorded before, one row per check, so this pass's record takes the same shape where it fits.
4. The nine product requirements documents under `PRDs/`, each one's revision-control table and change log only, so a finding can be placed against the requirement it touches; the body of a document is read when a finding lands on it.
5. `.github/workflows/ci.yml` and `packaging/appimage/build.py`, for how a fix reaches a release.
6. `snapmock/config/migration.py` and `snapmock/core/update_check.py`, for what a second release must not break: the on-disk names, and the tag rule the update check compares against.

Do not write anything until all six are read.

## Starting state, verified on 09-15-26

Verified by running the code and the repository on this machine (Intel i7-11700K, Linux, Cinnamon on X11, Python 3.12.3, uv), not by reading it:

- **The release exists.** `v0.9.0`, published 09-15-26 at 00:43 by the release job from commit 080e2f3, an ordinary release with `Snapmockit-0.9.0-x86_64.AppImage` attached (128,272,888 bytes; SHA-256 begins `ebe7c8e0f0b7427c`), and `releases/latest` answers with it. A copy is at `dist/Snapmockit-0.9.0-x86_64.AppImage`. The repository head is 6577c65.
- **The AppImage passed its display run.** Sections 1 to 6 and 8 of the checklist page `Snapmockit AppImage Display Checks`: 24 steps as described, one note closed as an instruction error. Check for Updates from the 0.1.0 build found `v0.9.0`; the first start of 0.9.0 moved the settings, presets, and library to the product's names and said so once. **Section 7, the capture through the Wayland portal, has not been run**: it needs a log-out into the Cinnamon on Wayland session.
- **The on-disk names are migrated on this machine**: `~/.config/Snapmockit/Snapmockit.conf`, `~/.config/snapmockit/`, and `~/Snapmockit/Library` with 22 files exist; the SnapMock-named directories do not. **One instance started from source before the migration was still running at 01:33 (`uv run python -m snapmock`, process 214565).** When it quits it writes its settings back to `~/.config/SnapMock/SnapMock.conf`, the path it opened, and its library manager points at the old library path. Quit it before the pass starts; if `~/.config/SnapMock` reappears afterwards it is stale, the migration leaves it because the new store exists, and it may be deleted by hand.
- **The suite** at 080e2f3: 1669 passed, 14 skipped, 1 deselected, in 6 minutes 13 seconds from a scratch worktree; ruff and mypy clean; on GitHub the checks job takes about 4 minutes and the AppImage job about 70 seconds.
- **The application's on-disk footprint the pass exercises:** projects (`.smk`, ZIP archives), exports (PNG, JPEG, SVG, PDF), Snagit files (`.snagx`, read and written), the library under `~/Snapmockit/Library` written back on every command, presets and themes under `~/.config/snapmockit`, and the settings.
- **What a fix costs to release:** a commit on `main` with the suite green, then a version, a tag, and the release job; a tag that is not `v` followed by the package's version fails the job before it publishes.

## Phases

Three phases and a close-out, each phase one or more commits, each closed out before the next starts: PRD rows, the notes' section, the phase-table row done, the next required step. Every commit is ruff-clean and mypy-strict-clean with the suite passing; the full suite runs from a scratch `git worktree` at the commit under test with the venv's own interpreter, `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font`, in about 6 minutes. A push to `main` cancels the CI run in progress, so push once per batch of fixes, after the suite.

### Phase 1, the decisions and the record

1. **Decisions and the notes document.** Present decisions 1 to 4; create `docs/End-to-End-Pass.md` (revision 1.0) with the phase table, the decisions, the silences decided, the starting state re-verified, and an empty findings table with the columns of silence 2. One commit.
2. **The Wayland check.** Section 7 of the checklist page, run by Doug when he can log out; its marks read back and recorded in `docs/Packaging-AppImage-Implementation.md` (a new revision, Section 8.4) and in this work's notes. If it cannot be run in this phase it is carried as owed and does not block Phase 2, but it blocks Phase 3 under decision 3.
3. **Phase close-out.**

### Phase 2, the pass

1. **The sittings.** Doug works; the session records. Each sitting gets one row per finding in the findings table, and one sitting entry (date, the work done in Doug's words, the files it touched, the findings by number). A sitting with no finding is recorded too: it is evidence. Where a finding needs to be seen to be understood, the session asks for a screenshot or a saved project, which the AppImage can produce.
2. **Triage and fixes.** After each sitting the session classifies every new finding (silence 2), fixes the defects in the order Doug sets, each with a test that fails before the fix, and records each in the product requirements document it belongs to. Fixes are pushed in one batch per sitting. A fix that changes what the application does for every user is a decision under the two-part test before it is made.
3. **Phase close-out**, when decision 1's exit criterion is met: every finding classified, every defect fixed or reclassified by Doug as a follow-up, and the count of sittings and findings stated.

### Phase 3, the release

1. **The release.** Version `1.0.0` and the build date set; the release notes written from the findings table (what changed since 0.9.0, in the user's words, without finding numbers); the tag pushed; the release job seen to publish; the released file downloaded and smoke-tested here; Check for Updates seen headless and on the display from the 0.9.0 AppImage to find `1.0.0`; the README's status line updated.
2. **Phase close-out.**

### Close-out of the work

Technical Architecture PRD rows for Section 7.3 (the release the product stands behind) and any section a fix touched; General UI PRD rows for 3.8 and for any fix; every other product requirements document a fix touched; `docs/Release-Engineering.md` step 4 done and step 5 stated as it stands; the next required step. **Say plainly what remains of packaging** (Flatpak, PyPI, the Windows MSI and portable ZIP, the macOS bundle) and of the platform backends (Windows and macOS, waiting for their machines).

## Decisions to surface

Apply the two-part test from the global guidance. Four decisions are expected to pass it; present all four with the consequential decision template before Phase 1 step 1 and wait.

- **1. What ends the pass.** Option A, a findings-bound end: the pass ends after the first sitting in which Doug finds nothing new and every earlier finding is closed, with at least three sittings on at least three distinct pieces of real work. Option B, a time-bound end: a fixed number of days of use, whatever is found. Option C, Doug's call alone, at any point. Why it matters: it is the difference between `1.0.0` meaning "a pass was run" and meaning "the pass stopped finding things"; and a bound that never closes stalls every later step. The cost of A: it can run long if each sitting finds something; the cost of B: a release with known open defects. Recommendation: A, with Doug able to call it under C at any point, recorded as such.
- **2. Where findings live.** Option A, the notes document alone: one table, one row per finding, private to the repository's documents. Option B, GitHub issues for the defects, one issue per defect with the notes' table pointing at them, so the public repository's tracker is real from the first release and Report a Bug in the application leads somewhere populated. Option C, issues for everything, follow-ups included. Why it matters: a public tracker is a commitment to answer it, and the notes are the record every earlier work used. The cost of B: two places to keep in step, and the defects of a pre-1.0.0 product on public view; the cost of A: an empty public tracker beside a released product. Recommendation: B.
- **3. Whether the Wayland check gates `1.0.0`.** Option A, yes: the portal capture must have been seen once on this machine's Wayland session before `1.0.0` is tagged, since it is one of the two Linux capture paths and has never been run from the package. Option B, no: `1.0.0` ships on the X11 proof alone and the Wayland check stays owed. Why it matters: a Wayland user's first capture is the product's first impression on the desktops that are moving to Wayland, and a failure there after `1.0.0` is a `1.0.1`. The cost of A: a log-out Doug has not been able to make yet; the cost of B: the risk named. Recommendation: A.
- **4. What `1.0.0` ships.** Option A, the Linux AppImage alone, as 0.9.0 did. Option B, the AppImage and the wheel on PyPI, which this machine can publish once an account and token exist, so `pip install snapmockit` works from `1.0.0`. Option C, A plus the Flatpak. Why it matters: every form shipped at `1.0.0` is a form every later release must ship too, and the update check reads only the GitHub release. The cost of A: Linux users without AppImage tooling wait; the cost of B: a PyPI account, a token in the repository's secrets, a console entry point the package does not yet declare, and a publish job; the cost of C: a Flatpak manifest, a runtime choice, and a Flathub submission process of its own. Recommendation: A, with B as the first packaging step after `1.0.0`.

Everything else follows the PRDs; where they are silent or disagree, decide, note it under the notes' decisions section and the PRD rows, and continue. Silences known now:

- A sitting is one continuous stretch of Doug's real work with the AppImage, however long; the session does not set its length or its content.
- The findings table's columns: number, sitting, what happened in Doug's words, where (the tool, dialog, or file), the requirement it touches (document and section) or "none", the class (defect, departure, follow-up), the fix commit or the issue, and its state (open, fixed, kept, deferred).
- A defect found in the capture backends that this machine cannot exercise (Windows, macOS) is a follow-up, not a defect of this pass.
- A finding against a product requirements document's own wording, where the document and Doug's expectation differ and Doug's is the better one, is a departure recorded in that document, not a defect.
- Fix commits carry no version change; the version moves once, at Phase 3.
- The 0.9.0 AppImage is kept at `dist/Snapmockit-0.9.0-x86_64.AppImage` through the work, for the Check for Updates proof of Phase 3 and for comparison; a fix under test is run from source or from a locally built AppImage, and Doug's sittings use the released 0.9.0 until `1.0.0` exists.
- The release notes of `1.0.0` name what changed since 0.9.0 for a user and say that the Windows and macOS packages do not exist yet.

## Standards that apply

- Terminology Precision, Writing Register, and Reply Format from the global guidance apply to every reply and to the documents.
- Departures from any product requirements document are recorded in that document's change log with a version bump, not only in code comments. **Check the revision-control table for a duplicate version number before bumping.**
- No control is disabled (General UI PRD 1.3); a fix never adds a dialog that blocks where a message would do.
- Every existing test passes unchanged unless a decision's row says the result may differ.
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy snapmock`, and `uv run pytest` must pass before each commit, with `QT_QPA_PLATFORM` set to `offscreen` for pytest.
- Document timestamps are read from the machine clock at the time of writing, never estimated.
- Commit messages end with the attribution block the session provides. A push is made once per batch, after the suite, and never while a CI run of the commit before is still wanted.
- A tag is a publication; `v1.0.0` is pushed once, deliberately, after Doug has read the release notes.

## When the work is complete

Update the phase table in `docs/End-to-End-Pass.md`, bump its revision, add a change-log row, and state the next required step, which is expected to be step 5 of the release-engineering list, the Windows and macOS capture backends when their machines exist, or the first packaging step after `1.0.0` under decision 4. Say what remains of Technical Architecture PRD 7.3 and which of it this machine can build.

**The display checks this work will owe**, none of which a headless test can settle: the Wayland portal capture of the AppImage checklist's section 7; each fix seen on the display in the sitting that follows it; and Help > Check for Updates from the 0.9.0 AppImage finding `1.0.0`.

---

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-15-26 01:33 | Claude (Claude Code) | Initial kickoff prompt, written at Doug's request after the AppImage work of 09-14-26 and 09-15-26: the end-to-end pass on real work with the released 0.9.0 AppImage, its findings triaged and fixed, and the 1.0.0 release. Starting state verified on 09-15-26: v0.9.0 published, the display run passed but for the Wayland check, the on-disk names migrated, one pre-migration instance still running, the suite at 1669 passed. Three phases and a close-out; four decisions; seven silences. |
