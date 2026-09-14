# Kickoff Prompt: The Linux AppImage

Last Updated: 09-14-26 17:29 · Revision 1.0

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. Start it only when no other session is committing in this working directory and no CI run of the current commit is in progress, since the workflow this work extends cancels a run in progress when a newer push lands. This is step 3 of the release-engineering list (`docs/Release-Engineering.md`, Section 1): the first package of the application, the Linux AppImage that Technical Architecture PRD 7.3 names as the primary Linux distribution. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) still governs the standards; this one governs the work. Where the two disagree, the general prompt wins and this one is corrected. The work is four phases and a close-out; a session pasting this prompt starts at the first phase not marked done in Section 1 of the notes document this work creates.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root. No other repository is involved in this session.

## Task

Build and publish the Linux AppImage of Snapmockit:

- **A build recipe** that turns the repository at a commit into one runnable file, `Snapmockit-<version>-x86_64.AppImage`, carrying Python, PyQt6 with its Qt libraries and platform plugins, the application's own wheel with its 175 resource files, and the desktop integration an AppImage carries: a `.desktop` entry, an application icon, and AppStream metainfo. Technical Architecture PRD 7.3; Section 10 gains the directory the recipe lives in, in the same version.
- **The AppImage proven on this machine**: it starts from a double-click and from the command line, takes a capture through the X11 backend and through the Wayland portal, opens and saves a project, exports to PNG and PDF, reads a Snagit file, finds the user's existing settings and library, and answers Help > Check for Updates against the real repository.
- **The build in continuous integration**: a job in `.github/workflows/ci.yml` that builds the AppImage on every push and keeps it as an artifact, and a release job that, on a tag of the form `vX.Y.Z`, builds it and attaches it to a GitHub release the update check can see.
- **The first tagged pre-release**, with the migration of the two on-disk names the rename of 09-14-26 left as they were (`docs/Release-Engineering.md`, Section 2), and Check for Updates seen to find it from an AppImage of an earlier version.

The session opens by presenting the five decisions below with the consequential decision template and waits. Nothing is built before they are taken.

## Read first, in this order

1. `docs/Release-Engineering.md` (revision 1.2 or later): Section 1's five steps, Section 2's identity decisions and what they left on disk, Section 3's workflow.
2. `PRDs/SnapMock-Technical-Architecture-PRD.html`: 7.3 (Packaging & Distribution), Section 9 (the technology stack, which names PyInstaller or cx_Freeze for packaging), Section 10 (the binding directory layout), and the 1.48 and 1.49 rows.
3. `PRDs/SnapMock-General-UI-PRD.html`: 3.8 (Check for Updates), 11.6 (About), and the rows that built them (2.9, 2.37, 2.38); `PRDs/SnapMock-Screen-Capture-PRD.html` Sections 3 and 9 for what the capture backends need from the system.
4. `.github/workflows/ci.yml` whole, and `pyproject.toml` whole: the hatchling build, the dynamic version, the dependency groups, the lock.
5. `snapmock/app.py` (`main`, `parse_capture_args`, the single-instance forward), `snapmock/__main__.py`, `snapmock/config/constants.py` (the names, the addresses, `DEFAULT_LIBRARY_DIRECTORY`), `snapmock/config/settings.py` (where QSettings stores), `snapmock/core/tool_themes.py` (the `~/.config/snapmock` store), `snapmock/library/manager.py` (the library directory), `snapmock/core/update_check.py` (the releases query and the tag rule), `snapmock/capture/tray.py` (`make_tray_icon`, the only icon the application draws of itself), and `snapmock/capture/x11.py` and `wayland_portal.py` for the system libraries they load.
6. `tests/test_app.py`, `tests/test_update_check.py`, `tests/test_help_check_updates.py`, `tests/test_capture/test_cli_and_channel.py`, and `tests/test_constants.py`, for what the entry point, the update check, and the constants are held to.

Do not write anything until all six are read.

## Starting state, verified on 09-14-26

Verified by running the code on this machine (an Intel i7-11700K, Linux, Cinnamon on X11, Python 3.12.3, uv), not by reading it:

- **The wheel builds and is small.** `uv build` produces `snapmockit-0.1.0-py3-none-any.whl` and its sdist from hatchling with the version read from `snapmock/__init__.py`: 348 files, 2.6 MB, of which 175 are the resources under `snapmock/resources/` (109 icons, 59 stamps, 2 themes, 3 emoji files, 1 sound). The CI build job proves this on every push.
- **The runtime is large and lives in the environment, not the wheel.** The dependencies are PyQt6, Pillow, numpy, send2trash, and psutil; the virtual environment is 435 MB, of which PyQt6 with its bundled Qt is 256 MB. An AppImage carries all of it plus a Python.
- **The entry point is a module, not a script.** `python -m snapmock` runs `snapmock.app.main`, which parses `--capture` and its options, forwards to a running instance over the single-instance channel, registers hotkeys, and shows the window; `pyproject.toml` declares no console or GUI script, and there is no `--version` flag.
- **There is no application icon.** The system tray icon is drawn in code by `make_tray_icon`; every other icon is a Tabler glyph. A `.desktop` entry and AppStream metainfo need one, and none exists at any size.
- **Two names stay on disk from the rename.** QSettings stores under `~/.config/SnapMock/SnapMock.conf` (`ORG_NAME` and `STORAGE_APP_NAME`), presets and themes under `~/.config/snapmock`, and the default library at `~/SnapMock/Library`; the product is Snapmockit. The release-engineering notes reserve their migration for the first release.
- **Check for Updates queries `dbower44022/snapmockit`** for the latest release and reads its `tag_name` as `vX.Y.Z` or `X.Y.Z` (`parse_version`); the repository has no release and no tag yet. The first CI run on GitHub was in progress when this prompt was written (run 34897493910, the tests step) with the build job green.
- **The suite** at ead205f, the pushed head: 1637 passed at the commit before it in 15 minutes 32 seconds, whole; ruff and mypy clean. It takes about 16 minutes since the style-sheet guard of 09-14-26.
- **The capture backends' system needs.** The X11 backend and the Wayland portal backend are the two live ones; the system libraries they and Qt's xcb platform plugin need on a bare Ubuntu are the apt list in `ci.yml`'s checks job, which the first CI run confirms or corrects.

## Phases

Four phases and a close-out, each phase one or more commits, each closed out before the next starts: PRD rows, the notes' section, the phase-table row done, the next required step. Every commit is ruff-clean and mypy-strict-clean with the suite passing; the full suite runs from a scratch `git worktree` at the commit under test with the venv's own interpreter, `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font`, in about 16 minutes. A push to `main` cancels the CI run in progress, so push once per phase, after the suite. Nothing in this work changes what the application does except the migration of decision 4 and the `--version` flag of silence 6; both are tested.

### Phase 1, the decisions and the recipe

1. **Decisions and the notes document.** Present decisions 1 to 5; create `docs/Packaging-AppImage-Implementation.md` (revision 1.0) with the phase table, the decisions, the silences decided, and the starting state re-verified. One commit.
2. **The recipe.** Per decision 1, a directory `packaging/appimage/` (a Technical Architecture PRD Section 10 row in the same commit) holding the build script, the `.desktop` entry, the AppStream metainfo, and the icon per decision 3, producing `Snapmockit-<version>-x86_64.AppImage` under `dist/` from the repository at a commit with one command; the version read from the package, never typed. Tests: the recipe's inputs (the desktop entry's fields, the metainfo's validity against `appstreamcli validate` where installed, the icon's sizes) held by tests that need no build.
3. **Phase close-out.**

### Phase 2, the AppImage proven here

1. **The runs.** The AppImage built by the recipe, run on this machine as a user would: from a file manager and from a shell, with and without an existing configuration, and with `--capture full` from the shell. The notes record each of the task's proofs with what was seen: the capture through X11 and through the Wayland portal (a Wayland session or the portal's own dialog), a project saved and opened, PNG and PDF exports, a Snagit file read, the existing settings and library found, Help > About reading the version, and Help > Check for Updates reaching GitHub and saying no release exists yet. These are display checks, owed to Doug through a checklist page as every display run has been.
2. **Phase close-out**, with the size and the start time of the AppImage measured and recorded against Technical Architecture PRD Section 8's two-second startup.

### Phase 3, the build in continuous integration

1. **The jobs.** Per decision 2: the AppImage built on every push and kept as an artifact, with a smoke test that runs it on the runner (`--appimage-extract-and-run`, the offscreen platform, `--version`); and the release job on a `vX.Y.Z` tag that builds and attaches the AppImage to a GitHub release with the tag's notes. Tests: the workflow parses; the smoke test's own script runs here.
2. **Phase close-out.**

### Phase 4, the migration and the first pre-release

1. **The migration.** Per decision 4: the two on-disk names moved to the product's on the first start of a version that carries the migration, the old locations read where the new do not exist, never destructive, tested with both layouts.
2. **The pre-release.** Per decision 5: the version set, the tag pushed, the release job seen to attach the AppImage, and Check for Updates seen from an AppImage of the version before to find it.
3. **Phase close-out.**

### Close-out of the work

Technical Architecture PRD rows for 7.3, Section 8's startup figure, Section 9's packaging tool, and Section 10; General UI PRD rows for 3.8 and for the settings' new home; `docs/Release-Engineering.md` step 3 done and step 4 pointed at the AppImage; the display checks this work owes; the next required step stated. **Say plainly what of Technical Architecture PRD 7.3 remains**: Flatpak, PyPI, the Windows MSI and portable ZIP, and the macOS bundle, and which of them this machine can build.

## Decisions to surface

Apply the two-part test from the global guidance. Five decisions are expected to pass it; present all five with the consequential decision template before Phase 1 step 2 and wait.

- **1. How the AppImage is built.** Option A, a relocatable Python AppImage: the `python-appimage` tool's manylinux CPython 3.12 image with the wheel and its dependencies installed into it by pip, `appimagetool` sealing it; no import analysis, every resource and plugin present because the packages are installed whole, a size around 150 to 200 MB. Option B, a PyInstaller one-directory bundle wrapped by `appimagetool` or `linuxdeploy`: smaller by what the import analysis prunes, and the tool Technical Architecture PRD Section 9 names, at the cost of PyQt6 hooks that need care for the platform plugins, the D-Bus support the Wayland portal uses, and the resources, and of a pruning that can drop a module the application imports lazily. Option C, a bare `appimagetool` over a copied virtual environment, which is not relocatable without the same work as A. Why it matters: it decides what can go wrong on a user's machine that did not go wrong here, and the size of every download. The cost of A: the larger file, and a build that depends on the manylinux image being current for Python 3.12. Recommendation: A, since correctness on a stranger's machine is worth the size, and Section 9's row is amended to say so. Follow-on detail: the AppImage's `AppRun` passes its arguments to `python -m snapmock`; `QT_QPA_PLATFORM` is not forced, so Qt chooses xcb or wayland as it does from source.
- **2. Where the build runs and what publishes.** Option A, in continuous integration: a job on every push that builds the AppImage on `ubuntu-latest` and keeps it as an artifact, and a release job on a `vX.Y.Z` tag that attaches it to a GitHub release, so every release is built from a clean runner and never from this machine's environment; the local recipe stays for Phase 2's proofs and for development. Option B, built here by hand and uploaded to a release by hand. Why it matters: reproducibility, and the update check, which reads the GitHub release the job creates. The cost of A: the runner's Ubuntu is older than this machine and the AppImage's glibc floor is the runner's, which is what makes it run on more machines; and a tag is a publication, so tagging becomes a deliberate act. Recommendation: A.
- **3. The application icon.** Option A, the session draws one: an SVG mark for Snapmockit, simple enough to read at 16 px and distinct from the Tabler glyphs, exported to the PNG sizes the desktop entry and the metainfo need, and used by the tray and the About dialog as well so the application has one face. Option B, Doug supplies an icon and the session integrates it. Option C, the tray icon's drawing exported at the needed sizes. Why it matters: it is the first thing a user sees of the product, in a file manager, a dock, and a task switcher, and the AppImage cannot integrate with the desktop without one. The cost of A: a first draft by the session, to be replaced by a designed one when there is one; the cost of B: the work waits on it. Recommendation: A now with B as the follow-up, unless Doug has one ready.
- **4. The migration of the on-disk names.** Option A, on the first start of a version that carries it: `~/.config/SnapMock` moved to `~/.config/Snapmockit`, `~/.config/snapmock` to `~/.config/snapmockit`, and `~/SnapMock/Library` to `~/Snapmockit/Library`, each only when the old exists and the new does not, and each read from the old location if the move fails, so nothing is ever lost; the library's path preference updated with it. Option B, the old names kept forever, with the product's name nowhere on disk. Option C, the settings moved and the library left, since a library directory is the user's own to name. Why it matters: a user who looks for the product's files finds them, and a move of a library is a move of every capture the user has taken. The cost of A: a move at first start that a user did not ask for, and a file manager bookmark that stops working; the cost of C: two names on disk. Recommendation: A, done once and announced in the first-run message, with the library moved only when it is at the default path.
- **5. The first release's version and standing.** Option A, a pre-release: version `0.9.0`, tagged `v0.9.0`, marked a pre-release on GitHub, so the update check's first real target exists and the end-to-end pass of step 4 runs on it before `1.0.0` is claimed. Option B, `1.0.0` at once. Why it matters: Check for Updates shows the version to every user, and the release-engineering notes reserve `1.0.0` for the first packaged release that passed the end-to-end pass. The cost of A: a second release soon after. Recommendation: A.

Everything else follows the PRDs; where they are silent or disagree, decide, note it under the notes' decisions section and the PRD rows, and continue. Silences known now:

- The AppImage's file name is `Snapmockit-<version>-x86_64.AppImage`, the version from the package.
- The desktop entry is `io.github.dbower44022.snapmockit.desktop` with the same id in the metainfo, categories Graphics and Utility, and a MIME type for the project file, `application/x-snapmockit-project` for `.smk`, so a double-click on a project opens it; the Snagit `.snagx` type is not claimed.
- Fonts come from the user's system, the colour emoji font included, as the marker tools' decision 4 already settled; the AppImage bundles none.
- The Qt platform plugins bundled are those the PyQt6 wheel carries; the system libraries an AppImage still needs from the host are recorded in the notes and in the README.
- Flatpak, PyPI, Windows, and macOS are out of scope and named in the close-out.
- A `--version` flag is added to the entry point, printing the product's name and version and exiting, so a smoke test and a bug report have it; General UI PRD 11.6's Copy Version Info stays the in-application route.
- The recipe is run from `uv run` with its own dependency group, `packaging`, so nothing of the packaging tools lands in the application's runtime dependencies.

## Standards that apply

- Terminology Precision, Writing Register, and Reply Format from the global guidance apply to every reply and to the documents.
- Every new top-level directory or module gets a row in Technical Architecture PRD Section 10 in the commit that creates it; `packaging/` is one.
- Departures from any product requirements document are recorded in that document's change log with a version bump, not only in code comments. **Check the revision-control table for a duplicate version number before bumping.**
- No control is disabled (General UI PRD 1.3); the migration's message, where one is shown, is a message and not a dialog that blocks.
- Every existing test passes unchanged unless a decision's row says the result may differ.
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy snapmock`, and `uv run pytest` must pass before each commit, with `QT_QPA_PLATFORM` set to `offscreen` for pytest.
- Document timestamps are read from the machine clock at the time of writing, never estimated.
- Commit messages end with the attribution block the session provides. A push is made once per phase, after the suite, and never while a CI run of the commit before is still wanted.

## When the work is complete

Update the phase table in `docs/Packaging-AppImage-Implementation.md`, bump its revision, add a change-log row, and state the next required step, which is expected to be step 4 of the release-engineering list, the end-to-end pass on the pre-release AppImage. Say what of Technical Architecture PRD 7.3 remains and which of it this machine can build.

**The display checks this work will owe**, none of which a headless test can settle: the AppImage started from a file manager and from a shell, with the desktop's icon and name; a capture through each backend from the AppImage; a project saved, closed, and reopened; the exports; the settings and the library found after the migration, and the first-run message; and Help > Check for Updates finding the pre-release from the version before it.

---

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-14-26 17:29 | Claude (Claude Code) | Initial kickoff prompt, written at Doug's request after the identity and continuous-integration steps of 09-14-26: the Linux AppImage of Technical Architecture PRD 7.3, built, proven here, built in CI, and released as a pre-release with the migration of the on-disk names. Starting state verified on 09-14-26: the wheel builds at 2.6 MB with 175 resources, the runtime is 435 MB, the entry point is a module with no version flag, there is no application icon, two on-disk names remain from the rename, and the repository has no release. Four phases and a close-out; five decisions; seven silences. |
