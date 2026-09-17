# Kickoff Prompt: The Flatpak

Last Updated: 09-17-26 13:31 · Revision 1.0

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. Start it only when no other session is committing in this working directory and no CI run of the current commit is in progress, since a push cancels a run in progress on the same branch. This is the next part of step 3 of the release-engineering list (`docs/Release-Engineering.md`, Sections 1 and 4): the Flatpak, which Technical Architecture PRD 7.3 names as the secondary Linux form. Doug chose it on 09-17-26 ahead of PyPI, which the end-to-end pass's decision 4 had put first. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) still governs the standards; this one governs the work. Where the two disagree, the general prompt wins and this one is corrected. The work is four phases and a close-out; a session pasting this prompt starts at the first phase not marked done in Section 1 of the notes document this work creates.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root. No other repository is involved in this session.

## Task

Build and publish the Flatpak of Snapmockit:

- **A build manifest** that turns the repository at a commit into a Flatpak application, `io.github.dbower44022.snapmockit`, the same id the AppImage's desktop entry and metainfo carry, and one bundle file, `Snapmockit-<version>-x86_64.flatpak`, that a user installs with `flatpak install`. Technical Architecture PRD 7.3; Section 10 gains the directory the manifest lives in, in the same version.
- **The Flatpak proven on this machine**: installed from the bundle, started from the main menu and from a shell, a capture through the X11 backend and through the Wayland portal, a project saved and reopened, PNG and PDF exports, a Snagit file read, the library found, `--capture full` from a shell handed to the running instance, and Help > Check for Updates answering as decision 5 says.
- **The build in continuous integration**: the Flatpak built on every push and kept as an artifact, and the release job attaching the bundle to the GitHub release beside the AppImage.
- **A release carrying both files**, per the version silence below.

The session opens by presenting the five decisions below with the consequential decision template and waits. Nothing is built before they are taken.

## Read first, in this order

1. `docs/Release-Engineering.md` (revision 1.12 or later): Section 1's steps and Section 4's order after 1.0.0.
2. `docs/Packaging-AppImage-Implementation.md` whole: the decisions, the recipe, the portal registration finding of Section 8, the release job, and Section 11's paragraph on the Flatpak.
3. `PRDs/SnapMock-Technical-Architecture-PRD.html`: 7.1, 7.3, Section 8 (the startup target), Section 9, Section 10, and the rows 1.50 to 1.60.
4. `PRDs/SnapMock-General-UI-PRD.html`: 3.8 (Check for Updates), 11.6 (About), 16 (first run), and the rows that built them; `PRDs/SnapMock-Library-PRD.html` for where the library lives; `PRDs/SnapMock-Screen-Capture-PRD.html` Sections 3, 6, and 9.
5. `.github/workflows/ci.yml` whole, `pyproject.toml` whole, and `packaging/appimage/` whole (the build script, the desktop entry, the metainfo, the MIME type, the smoke test).
6. `snapmock/app.py` (`main`, `desktop_entry_installed`, the single-instance forward), `snapmock/capture/single_instance.py`, `snapmock/capture/__init__.py`, `snapmock/capture/x11.py`, `snapmock/capture/wayland_portal.py`, `snapmock/config/constants.py`, `snapmock/config/settings.py`, `snapmock/config/migration.py`, `snapmock/library/manager.py`, and `snapmock/core/update_check.py` with the Help menu code that shows its result.
7. `tests/test_app.py`, `tests/test_update_check.py`, `tests/test_help_check_updates.py`, `tests/test_capture/test_cli_and_channel.py`, and the tests of `packaging/appimage/`.

Do not write anything until all seven are read.

## Starting state, verified on 09-17-26 13:30

Verified on this machine (an Intel i7-11700K, Linux Mint 22.2, Cinnamon on X11, with a Cinnamon on Wayland session available), not by reading:

- **v1.0.0 is the latest release**, the Linux AppImage alone, tagged on f53c4e5. The head is f2ca494, whose CI run was in progress at 13:30; the run before it that finished, at f53c4e5, passed.
- **Flatpak 1.14.6 is installed** with the `flathub` remote at system level. `appstreamcli` and `desktop-file-validate` are installed. **`flatpak-builder` is not installed.** Flathub offers it as the application `org.flatpak.Builder`; installing it, and any runtime or SDK, installs software on Doug's machine and is asked of him first.
- **The runtimes.** `org.kde.Platform//6.10` is installed; its Qt is 6.10.3 and its Python is **3.13.15**, with no PyQt6. `org.kde.Sdk//6.10` is not installed. Flathub offers `com.riverbankcomputing.PyQt.BaseApp//6.10` (version 6.10.2), a base application that carries PyQt6 built against that runtime. `org.freedesktop.Platform` 25.08 and 26.08 are installed, and `org.freedesktop.Sdk//25.08`.
- **The application has only ever run on Python 3.12** (`requires-python = ">=3.12"`, `.python-version` 3.12, CI on 3.12, the AppImage on a relocatable 3.12). The KDE runtime's 3.13 is untried.
- **The dependencies** are PyQt6, Pillow, numpy, send2trash, and psutil. Pillow, numpy, and psutil are compiled. **send2trash is declared but no module under `snapmock/` imports it.**
- **The desktop files exist** under `packaging/appimage/`: `io.github.dbower44022.snapmockit.desktop`, `.appdata.xml`, and the MIME type `.xml` for `.smk`; the icon is `snapmock/resources/icons/snapmockit.svg`, rendered to PNG sizes by `packaging/appimage/build.py`.
- **What differs inside a Flatpak, from reading, to be proven:** `XDG_CONFIG_HOME` and `XDG_DATA_HOME` point under `~/.var/app/io.github.dbower44022.snapmockit/`, so the settings and presets are not the AppImage's; the home directory is not visible without a `--filesystem` permission, so `~/Snapmockit/Library` is not either; the X11 backend loads `libX11` and friends through ctypes, which the runtime carries; Qt registers the application id with the portal from the sandbox without the desktop entry lookup the AppImage needed; the single-instance channel is a `QLocalServer` whose socket must be reachable from a second `flatpak run`.
- **Check for Updates** tells a user of a newer release and opens its GitHub page, where the download is the AppImage.

## Phases

Four phases and a close-out, each phase one or more commits, each closed out before the next starts: PRD rows, the notes' section, the phase-table row done, the next required step. Every commit is ruff-clean and mypy-strict-clean with the suite passing; the full suite runs from a scratch `git worktree` at the commit under test with the venv's own interpreter, `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font`, in about 6 minutes. A push to `main` cancels the CI run in progress, so push once per phase, after the suite.

### Phase 1, the decisions, Python 3.13, and the manifest

1. **Decisions and the notes document.** Present decisions 1 to 5; create `docs/Packaging-Flatpak-Implementation.md` (revision 1.0) with the phase table, the decisions, the silences decided, and the starting state re-verified. One commit.
2. **The tools.** Ask Doug to install `org.flatpak.Builder` and the SDK, base application, and runtime decision 1 names, with the exact commands through the instruction-discipline skill. Record the versions installed.
3. **Python 3.13.** The suite run once under Python 3.13 (`uv run --python 3.13`), every failure a defect fixed with a test; the CI checks job gains 3.13 beside 3.12, so the Flatpak's interpreter is tested on every push. Technical Architecture PRD Section 9 row.
4. **The manifest.** Per decision 1, a directory `packaging/flatpak/` (a Technical Architecture PRD Section 10 row in the same commit) holding the manifest, the generated dependency modules, and a build script that produces `Snapmockit-<version>-x86_64.flatpak` under `dist/` with one command, the version read from the package. Tests: the manifest's permissions match decision 3, and its id matches the desktop entry and metainfo, held by tests that need no build.
5. **Phase close-out.**

### Phase 2, the code the sandbox needs, and the Flatpak proven here

1. **The code.** Decision 4's settings and decision 5's update message, each tested; anything the proofs of step 2 find, fixed with a test first.
2. **The runs.** The bundle installed with `flatpak install --user`, run as a user would: from the main menu and from a shell, with a fresh configuration, and with `flatpak run io.github.dbower44022.snapmockit --capture full` while it runs. The notes record each of the task's proofs with what was seen. **Display checks are owed to Doug through a checklist page**, a new section of `Snapmockit AppImage Display Checks` (https://claude.ai/artifact/HHCf3xs7L32kcHrtEnBpe2, database collection `appimage1`, ids `f01` onward so the stored marks stay attached). **Doug has marked whole sections at once without running them** (end-to-end pass notes, Section 8); every mark is checked against what the machine shows (the installed ref and commit, the files written, the processes running) before it is recorded, and a mark the machine contradicts is put to Doug.
3. **Phase close-out**, with the bundle's size and the start time measured against Technical Architecture PRD Section 8's two-second target.

### Phase 3, the build in continuous integration

1. **The jobs.** Per decision 2: the Flatpak built on every push on `ubuntu-latest` (the `flatpak/flatpak-github-actions` builder or `flatpak-builder` in a container) and kept as an artifact; the release job attaches `Snapmockit-<version>-x86_64.flatpak` beside the AppImage. Tests: the workflow parses.
2. **Phase close-out.**

### Phase 4, the release

1. **The release.** Per the version silence: the version and build date set, the release notes written for Doug to read before the tag (the tag is never pushed without his word), the release job seen to attach both files, the bundle downloaded, installed, and started.
2. **Phase close-out.**

### Close-out of the work

Technical Architecture PRD rows for 7.3 and for any section a change touched; General UI PRD rows for 3.8 and for any change; the Library PRD if the library's place changed; the README's "Install on Linux" gaining the Flatpak; `docs/Release-Engineering.md` Sections 1 and 4 brought to the state of the work; the next required step. **Say plainly what remains**: PyPI, a Flathub submission if decision 2 left it for later, the menu entry the AppImage lacks, and Windows and macOS.

## Decisions to surface

Apply the two-part test from the global guidance. Five decisions are expected to pass it; present all five with the consequential decision template before Phase 1 step 2 and wait.

- **1. How the Flatpak is built.** Option A, the KDE runtime `org.kde.Platform//6.10` with `com.riverbankcomputing.PyQt.BaseApp//6.10`: PyQt6 comes built against the runtime's Qt, the runtime's Python 3.13 runs the application, and Pillow, numpy, and psutil are built as modules the manifest lists (generated by `flatpak-pip-generator`); the bundle is small because Qt is shared with every other KDE Flatpak, and this is the form Flathub accepts. Option B, the freedesktop runtime with the PyQt6 wheels from PyPI, which carry their own Qt, as the AppImage does: the Qt and PyQt6 versions are the ones the AppImage ships, at the cost of a bundle of about the AppImage's size and a form Flathub is unlikely to accept. Option C, the AppImage's relocatable Python 3.12 AppDir copied into a freedesktop-runtime Flatpak: the same interpreter as the AppImage, and the least Flatpak-like. Why it matters: it decides the interpreter, the Qt the user runs, the download size, and whether Flathub is open later. The cost of A: Python 3.13 and a Qt that the runtime updates on its own schedule, so the application runs on a combination no one tested before this work (Phase 1 step 3 answers the first), and PyQt6's version is the base application's, not the lock file's. Recommendation: A.
- **2. Where the Flatpak is published.** Option A, a bundle attached to the GitHub release, built in continuous integration, installed with `flatpak install Snapmockit-<version>-x86_64.flatpak`; a Flathub submission becomes its own later step. Option B, a Flathub submission in this work: the Flathub review, a pull request to `flathub/flathub`, and its own build infrastructure, after which users install and update from their software manager. Option C, a Flatpak repository of the project's own, served from GitHub Pages, so `flatpak update` works without Flathub. Why it matters: a bundle installed by hand never updates, so the user's route to a new version differs by option. The cost of A: a bundle user updates by downloading the next bundle, as an AppImage user does. The cost of B: a review out of this session's hands and time, with requirements (permissions, metainfo screenshots and release entries) that can change the manifest. Recommendation: A now, with B as the next step once the bundle has been used.
- **3. What the sandbox may reach.** Option A, `--filesystem=home`: the library at `~/Snapmockit/Library` as the AppImage has it, Open and Save anywhere in the home directory, and recent files and session restore working with the paths the user chose. Option B, `--filesystem=~/Snapmockit:create` and `--filesystem=xdg-pictures`, with Open and Save through the document portal elsewhere: a tighter sandbox, at the cost that a file opened outside those folders is reached through a path under `/run/user/<id>/doc/` which may not survive a restart, so recent files and session restore can lose it. Both options take the Wayland and fallback X11 sockets, the IPC share, the GPU device, and the network (Check for Updates). Why it matters: it decides whether the Flatpak behaves like the AppImage for a user's files, and how a Flathub reviewer reads the manifest. The cost of A: the broad permission Flathub asks to be justified, and a sandbox that does not protect the home directory. Recommendation: A, with the justification written in the notes for decision 2's later Flathub step.
- **4. Whether the Flatpak shares the AppImage's settings.** Option A, a store of its own: the Flatpak's settings, presets, and themes live under `~/.var/app/io.github.dbower44022.snapmockit/` as Flatpak's defaults put them, and a user who moves from the AppImage starts with the first-run defaults but the same library. Option B, one store: the manifest grants `xdg-config/Snapmockit` and `xdg-config/snapmockit`, and the application reads and writes `~/.config` as the AppImage does. Option C, a store of its own that is filled once from `~/.config/Snapmockit` on the Flatpak's first start, if that exists, the way the 0.9.0 migration moved the old names. Why it matters: a user who has set up the AppImage expects the Flatpak to look the same, and two versions of the application writing one settings file can undo each other's changes. The cost of C: a copy the user did not ask for, and changes after it no longer shared. Recommendation: C.
- **5. What Check for Updates says inside the Flatpak.** Option A, a message of its own: when the application runs in a Flatpak (the file `/.flatpak-info` exists), a newer release is reported with how to get it for this form (download the new bundle, or `flatpak update` once decision 2's Flathub step exists), and the release page still opens. Option B, unchanged: the message and the page as the AppImage has them, whose download is the AppImage. Option C, the Help menu item removed inside the Flatpak. Why it matters: a Flatpak user told to download an AppImage is sent to the wrong file. The cost of A: a second wording in General UI PRD 3.8 and a branch the tests hold. Recommendation: A. Option C is not recommended: General UI PRD 1.3 keeps controls present.

Everything else follows the PRDs; where they are silent or disagree, decide, note it under the notes' decisions section and the PRD rows, and continue. Silences known now:

- The application id is `io.github.dbower44022.snapmockit`; the desktop entry, metainfo, MIME type, and icon are the files under `packaging/appimage/`, used from where they are. If both forms need to change them, they move to a shared `packaging/linux/` in one commit with its Section 10 row.
- The bundle's file name is `Snapmockit-<version>-x86_64.flatpak`, the version from the package; the manifest builds from the local checkout, never from a download.
- The release that first carries the Flatpak is **1.1.0**: the Flatpak is a new form and decision 5 changes what the application says. The AppImage is attached to it as always.
- send2trash, declared and never imported, is removed from the dependencies in Phase 1, so the manifest does not build it; the lock file follows.
- The Windows and macOS capture backends, and the menu entry the AppImage lacks, are out of scope and named in the close-out.
- The Flatpak's startup is measured from `flatpak run`, which adds the sandbox's own start to the application's.

## Standards that apply

- Terminology Precision, Writing Register, and Reply Format from the global guidance apply to every reply and to the documents.
- Every new top-level directory or module gets a row in Technical Architecture PRD Section 10 in the commit that creates it; `packaging/flatpak/` is one.
- Departures from any product requirements document are recorded in that document's change log with a version bump, not only in code comments. **Check the revision-control table for a duplicate version number before bumping**, and keep the header's "Document version" and "Last Updated" in step with the table.
- No control is disabled (General UI PRD 1.3).
- Every existing test passes unchanged unless a decision's row says the result may differ.
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy snapmock`, and `uv run pytest` must pass before each commit, with `QT_QPA_PLATFORM` set to `offscreen` for pytest.
- Installing software on Doug's machine (the builder, a runtime, an SDK) is asked of him first; a user-level `flatpak install --user` of the bundle this work builds is part of the proofs.
- Document timestamps are read from the machine clock at the time of writing, never estimated.
- Commit messages end with the attribution block the session provides. A push is made once per phase, after the suite; a tag is pushed only on Doug's word.

## When the work is complete

Update the phase table in `docs/Packaging-Flatpak-Implementation.md`, bump its revision, add a change-log row, and state the next required step, which is expected to be PyPI or the Flathub submission, whichever Doug picks. Say what of Technical Architecture PRD 7.3 remains.

**The display checks this work will owe**, none of which a headless test can settle: the Flatpak installed from the bundle and started from the main menu with its icon and name; a capture through the X11 backend and through the Wayland portal; `--capture full` from a shell handed to the running instance; a project saved, closed, and reopened from the library and from a folder the user chose; the exports; the first start's settings as decision 4 says; and Help > Check for Updates answering as decision 5 says.

---

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-17-26 13:31 | Claude (Claude Code) | Initial kickoff prompt, written after Doug chose the Flatpak as the next step on 09-17-26 (option C), ahead of PyPI. Starting state verified on 09-17-26: v1.0.0 released; Flatpak 1.14.6 with Flathub, no `flatpak-builder`; the KDE runtime 6.10 installed with Python 3.13.15 and no PyQt6; the PyQt base application 6.10 on Flathub; the application untried on Python 3.13; send2trash declared and unused. Four phases and a close-out; five decisions; six silences. |
