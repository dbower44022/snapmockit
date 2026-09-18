# Kickoff Prompt: The Flathub Submission

Last Updated: 09-18-26 01:52 · Revision 1.0

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. Start it only when no other session is committing in this working directory and no CI run of the current commit is in progress, since a push cancels a run in progress on the same branch. This is the next part of step 3 of the release-engineering list (`docs/Release-Engineering.md`, Sections 1 and 4): the Flathub submission, which Flatpak decision 2 left for after the bundle had been used. Doug chose it on 09-18-26 ahead of the Python Package Index. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) still governs the standards; this one governs the work. Where the two disagree, the general prompt wins and this one is corrected. The work is four phases and a close-out; a session pasting this prompt starts at the first phase not marked done in Section 1 of the notes document this work creates.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root. The Flathub submission is a pull request to a repository that is not this one (`flathub/flathub`); it is the one place this work touches another repository, and the global guidance's rule about another repository's own process applies there in full.

## Task

Put Snapmockit on Flathub, so that a user installs it from their software centre and `flatpak update` brings them a new version instead of a download:

- **A Flathub manifest** that builds `io.github.dbower44022.snapmockit` **from published sources with checksums** — never from this checkout, which Flathub forbids — and passes `flatpak-builder-lint` with no error that has not been granted an exception.
- **The metainfo brought to Flathub's standard**: screenshots that exist at public addresses, a release history with dates, the branding, the developer, and the content rating, validated strictly.
- **The submission made**: a pull request to the `new-pr` branch of `flathub/flathub`, a test build asked for with `bot, build`, every reviewer comment answered, and the repository accepted under the Flathub organisation.
- **What follows acceptance**: the update flow for later releases, Check for Updates telling a Flathub user to run `flatpak update`, and the README saying where the application comes from.

The session opens by presenting the decisions below with the consequential decision template and waits. Nothing is submitted before they are taken, and **nothing is pushed to any repository outside this one without Doug's word at that moment**, since a pull request to Flathub is a public act in his name.

## Read first, in this order

1. `docs/Packaging-Flatpak-Implementation.md` whole: the five decisions, the recipe of Section 8, the display findings of Section 11, the continuous-integration job of Section 12, and the close-out of Section 14, which names this work.
2. `docs/Release-Engineering.md` Sections 1 and 4, and `docs/Packaging-AppImage-Implementation.md` Sections 2 and 9 for how the two forms are built and released.
3. `packaging/flatpak/` whole: the manifest, `python3-deps.json`, `snapmockit.sh`, `build.py`, `smoke.sh`.
4. `packaging/appimage/io.github.dbower44022.snapmockit.appdata.xml`, `.desktop`, and `.xml`, which both Linux forms use from where they are (Flatpak silence 1).
5. `PRDs/SnapMock-Technical-Architecture-PRD.html` 7.3, Section 9, and Section 10; `PRDs/SnapMock-General-UI-PRD.html` 3.8 and 11.6.
6. `.github/workflows/ci.yml` whole and `tests/test_packaging_flatpak.py`, `tests/test_ci_workflow.py`.
7. The current Flathub documentation, because it changes and this prompt will age: https://docs.flathub.org/docs/for-app-authors/requirements, `/submission`, `/metainfo-guidelines`, and `/linter`. **Where the documentation and this prompt disagree, the documentation wins and the notes record the difference.**

Do not write anything until all seven are read.

## Starting state, verified on 09-18-26

Verified on this machine by running the tools, not by reading:

- **v1.1.0 is the latest release**, published 09-18-26, carrying `Snapmockit-1.1.0-x86_64.AppImage` and `Snapmockit-1.1.0-x86_64.flatpak`. The Flatpak of that release is installed here for the user.
- **`flatpak-builder-lint` already answers on the current manifest.** `flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest packaging/flatpak/io.github.dbower44022.snapmockit.yml` returns two errors: **`finish-args-home-filesystem-access`** (Flatpak decision 3, whose justification is written in the Flatpak notes, Section 2.3) and **`toplevel-unnecessary-branch`** (the `branch: stable` the bundle needs and Flathub sets itself).
- **Flathub forbids what the present recipe does twice over.** Its requirements say a manifest may use git or archive sources with checksums only, never a local directory — the present one stages a locally built wheel — and that submissions are "built entirely from source code", which puts the four binary wheels of `python3-deps.json` (numpy, Pillow, psutil; send2trash is pure Python) in question. **How much of that is enforced in practice is the first thing this work must establish from the documentation and from applications already on Flathub**, since building numpy and Pillow from their source archives inside the KDE SDK is a different order of work from listing wheels.
- **The metainfo has no screenshots and one release row**, filled at build time with the version being built. Flathub lists an application from this file: screenshots at public addresses and a release history are what its page is made of.
- **The application id matches the repository** as Flathub requires: `io.github.dbower44022.snapmockit` against `github.com/dbower44022/snapmockit`.
- **The tools are installed**: Flatpak 1.14.6, `org.flatpak.Builder` (which carries `flatpak-builder-lint`), `org.kde.Platform` and `org.kde.Sdk` 6.11, `com.riverbankcomputing.PyQt.BaseApp` 6.11, `appstreamcli` 1.0.2 on the host and 1.0.6 inside the SDK, `librsvg` on the host.
- **Two display checks are owed by the Flatpak work** and are not this work's: the Wayland capture inside the Flatpak (checklist section 11) and the Check for Updates wording from a 1.0.0 Flatpak (section 13).

## Phases

Four phases and a close-out, each phase one or more commits, each closed out before the next starts: PRD rows, the notes' section, the phase-table row done, the next required step. Every commit is ruff-clean and mypy-strict-clean with the suite passing; the full suite runs from a scratch `git worktree` at the commit under test with `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font`, in about 6 minutes. A push to `main` cancels the CI run in progress, so push once per phase, after the suite.

### Phase 1, what Flathub requires, and the decisions

1. **The requirements pass.** Read the four documentation pages and check every requirement against what this repository has, in a table in the notes: required files, the application id, the sources rule, the metainfo, the permissions, the licence, and the linter's two current errors. Name for each: met, or what it will take.
2. **The decisions**, presented with the consequential decision template, and `docs/Packaging-Flathub-Implementation.md` (revision 1.0) created with the phase table, the decisions, the silences decided, and the requirements table. One commit.
3. **Phase close-out.**

### Phase 2, the metainfo and the screenshots

1. **The screenshots.** Per the decision on them: taken of the running application on this machine, at a size Flathub accepts, showing what the application is for; **taken with Snapmockit itself**, since the application under submission is a screenshot tool and using it is the honest proof. They live in the repository and are served from a public address that does not move.
2. **The metainfo.** Screenshots with captions, a release history with dates (1.0.0 and 1.1.0 at least), the branding colours, the developer, the content rating, the licences, and the summary and description read against Flathub's guidelines for length and wording. `appstreamcli validate --strict` clean, and clean inside the SDK where the version is newer.
3. **Tests** for what a test can hold: the screenshot addresses are the repository's own and end in a picture, every release row has a date, the file validates.
4. **Phase close-out**, with the AppImage's copy of the file kept in step (Flatpak silence 1: one set of desktop files for both forms).

### Phase 3, the Flathub manifest

1. **The manifest**, under `packaging/flathub/` (a Technical Architecture PRD Section 10 row in the same commit) or wherever the decision on its home puts it: the application built from the **git tag** with its commit, the dependencies as the decision on them says, no local directory anywhere, and the permissions the decision on them settles.
2. **Built and installed here from that manifest alone**, with `flatpak-builder` over a clean checkout of the tag, then run: the window opens, a capture works, the library is found. **`flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest <manifest>` and `… repo repo` must both come back clean**, or every remaining error must be one Flathub grants an exception for, with the exception request written.
3. **Phase close-out**, with the built file's size and the build's time recorded against the bundle's 25.4 MiB.

### Phase 4, the submission

1. **The pull request.** A fork of `flathub/flathub`, a branch named for the application id, the manifest and its files at the top level, the pull request opened **against the `new-pr` branch**, and `bot, build` asked for in a comment. **Doug's word is taken at the moment the fork is pushed and again before the pull request is opened**; his GitHub account is the one that appears.
2. **The review.** Every comment answered in the pull request, never by closing it; each change made here first, tested, and pushed to the branch. The notes record each comment and what was done.
3. **Acceptance.** The repository created under the Flathub organisation with Doug's write access, accepted within the week Flathub allows; two-factor authentication on his GitHub account confirmed beforehand, since Flathub requires it.
4. **Phase close-out.**

### Close-out of the work

Check for Updates tells a Flathub user to run `flatpak update` (General UI PRD 3.8 gains a third wording; Flatpak decision 5 said this would come); the README's "Install on Linux" names Flathub first for the Flatpak; `docs/Release-Engineering.md` Sections 1 and 4 brought to the state of the work; the Technical Architecture PRD's 7.3 row; how a later release reaches Flathub, written down as a step of the release process, whether by Flathub's own update bot or by a pull request per release; and the next required step, which is expected to be the Python Package Index. **Say plainly what remains**: the Python Package Index, the menu entry the AppImage lacks, and Windows and macOS.

## Decisions to surface

Apply the two-part test from the global guidance. Five decisions are expected to pass it; present all five with the consequential decision template before Phase 1 step 3 and wait.

- **1. How the dependencies are built.** Option A, from source archives: numpy, Pillow, and psutil built inside the KDE SDK from their `.tar.gz` sources with checksums, send2trash from its pure-Python wheel, which is what "built entirely from source code" asks for; the cost is a long build on Flathub's builders, a manifest that must carry each build dependency, and a numpy build that can fail on its own terms. Option B, the wheels as they are now, with an exception asked for: the manifest stays the one this machine already builds, at the cost of a review that may refuse it and a submission that then has to be redone. Option C, drop a dependency to shorten the list: psutil is optional under Technical Architecture PRD 9.1 (the memory readout blanks without it), but numpy and Pillow are not. Why it matters: it decides how long a Flathub build takes, how likely the review is to stall, and whether the application on Flathub is built from the same inputs as the bundle here. Recommendation: A for the three compiled dependencies, keeping send2trash's pure-Python wheel, and B held in reserve if a source build proves unreasonable — with the reviewer asked early rather than after the work.
- **2. What the sandbox asks for on Flathub.** Option A, `--filesystem=home` with the justification of Flatpak decision 3, which the linter already flags and which Flathub grants only with a reason it accepts. Option B, the tighter set: `--filesystem=xdg-pictures`, `~/Snapmockit:create`, and everything else through the document portal, at the cost that a file opened elsewhere is reached through a path that may not survive a restart, so the recent files and the session restore lose it — the cost Flatpak decision 3 weighed and declined. Option C, A now and B if the reviewer refuses. Why it matters: it decides what a Flathub user's Open and Save can reach and how long the review takes. Recommendation: C, with the justification written into the pull request from the first comment, so the reviewer answers it before anything is rebuilt.
- **3. Where the Flathub manifest lives.** Option A, in this repository under `packaging/flathub/`, copied into the Flathub repository on each change: one place to read and test, at the cost of two copies that can drift. Option B, only in the Flathub repository once it exists: no drift, at the cost that this repository no longer holds the recipe for the form most users will install. Option C, in this repository as the source of truth with a workflow that opens the Flathub pull request, which is more machinery than one application needs at this size. Why it matters: it decides where a later release's change is made and reviewed. Recommendation: A, with the copy made by a script and a test that the two agree.
- **4. The screenshots.** How many, of what, and where they are served from: the decision names the number, the subjects (the editor with an annotated capture, the library, the capture overlay, the Snagit file read), the size and aspect, and the address — a tag's `raw.githubusercontent.com` path, which never moves, against a branch's, which does. Why it matters: they are the application's page on Flathub and the first thing a user sees; a moving address breaks the page later. Recommendation: four screenshots taken with Snapmockit on this machine at 1920 by 1080, in the repository under `packaging/screenshots/`, served from the `v1.1.0` tag's raw address.
- **5. How a later release reaches Flathub.** Option A, Flathub's own update bot watching the GitHub releases and opening a pull request on each: nothing to do per release, at the cost of trusting the bot's pattern matching. Option B, a pull request made here for each release, which is one more step in the release process and never surprises. Option C, a workflow in this repository that opens that pull request on a tag. Why it matters: a Flathub user's updates arrive only when the Flathub repository is updated. Recommendation: A, with B as the fallback the notes describe, because the release job already publishes the artefacts the bot reads.

Everything else follows the PRDs; where they are silent or disagree, decide, note it under the notes' decisions section and the PRD rows, and continue. Silences known now:

- The application id, the desktop entry, the MIME type, and the icon are the files under `packaging/appimage/`, used from where they are (Flatpak silence 1). If Flathub's requirements move them, they move to a shared `packaging/linux/` in one commit with its Section 10 row.
- The `branch: stable` the bundle needs is removed from the Flathub manifest, which is what `toplevel-unnecessary-branch` asks; the bundle recipe keeps it.
- The bundle on the GitHub release stays after Flathub accepts the application: a user who does not use Flathub keeps the file, and Check for Updates keeps naming it for a bundle installation.
- No release is tagged by this work. If a change made for Flathub belongs in the product, it ships in the next ordinary release, whose number is Doug's to pick.
- The Python Package Index, the menu entry, Windows, and macOS are out of scope and named in the close-out.

## Standards that apply

- Terminology Precision, Writing Register, and Reply Format from the global guidance apply to every reply and to the documents.
- Every new top-level directory or module gets a row in Technical Architecture PRD Section 10 in the commit that creates it.
- Departures from any product requirements document are recorded in that document's change log with a version bump, not only in code comments. **Check the revision-control table for a duplicate version number before bumping**, and keep the header's "Document version" and "Last Updated" in step with the table.
- No control is disabled (General UI PRD 1.3).
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy snapmock`, and `uv run pytest` must pass before each commit, with `QT_QPA_PLATFORM` set to `offscreen` for pytest.
- Installing software on Doug's machine is asked of him first. **Anything that leaves this machine in Doug's name — a fork, a branch on it, a pull request, a comment on a Flathub review — is asked of him at the moment it happens, not once at the start.**
- Document timestamps are read from the machine clock at the time of writing, never estimated.
- Commit messages end with the attribution block the session provides.

## When the work is complete

Update the phase table in `docs/Packaging-Flathub-Implementation.md`, bump its revision, add a change-log row, and state the next required step, which is expected to be the Python Package Index. Say what of Technical Architecture PRD 7.3 remains, and what a Flathub user's update path now is.

**The display checks this work will owe**, none of which a headless test can settle: the application installed from Flathub through the desktop's software centre and started from the main menu; a capture, a save, and an export from that installation; Check for Updates showing the `flatpak update` wording; and the application's page on flathub.org read as a user reads it, with the screenshots and the description as intended.

---

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-18-26 01:52 | Claude (Claude Code) | Initial kickoff prompt, written after Doug chose the Flathub submission on 09-18-26 ahead of the Python Package Index. Starting state verified on 09-18-26: v1.1.0 released with both Linux forms; `flatpak-builder-lint` already returns `finish-args-home-filesystem-access` and `toplevel-unnecessary-branch` on the current manifest; Flathub forbids a local-directory source and asks for a build from source, which puts the four dependency wheels in question; the metainfo has no screenshots and one release row. Four phases and a close-out; five decisions; five silences. |
