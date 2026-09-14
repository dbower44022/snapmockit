# Packaging: the Linux AppImage — Implementation Notes

Last Updated: 09-14-26 17:59 · Revision 1.0

Implements step 3 of the release-engineering list (`docs/Release-Engineering.md`, Section 1) for Linux: the AppImage that Technical Architecture PRD 7.3 names as the primary Linux distribution, built by a recipe in the repository, proven on this machine, built in continuous integration on every push, and published as a GitHub release on a tag, together with the migration of the two on-disk names the rename of 09-14-26 left as they were. The kickoff prompt is `docs/Packaging-AppImage-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The five decisions, this document, and the recipe under `packaging/appimage/` with its tests | Step 1 done 09-14-26; step 2 in progress | |
| 2 | The AppImage built here and run as a user would; every proof of the task recorded; size and start time measured | Not started | |
| 3 | The build in continuous integration: the AppImage as an artifact on every push, a smoke test on the runner, the release job on a `vX.Y.Z` tag | Not started | |
| 4 | The migration of the on-disk names, and the first release, `v0.9.0` | Not started | |
| Close-out | The PRD rows, the release-engineering notes, the display checks owed, what of 7.3 remains | Not started | |

## 2. Decisions

All five were presented with the consequential decision template on 09-14-26 and approved by Doug as recommended, with the corrections noted.

### 2.1 How the AppImage is built: option A, a relocatable Python AppImage

The `python-appimage` tool's CPython 3.12 base image, built on the `manylinux_2_28` image, is extracted, the application's wheel and its locked dependencies are installed into it by pip, and `appimagetool` seals the result. Nothing is pruned: every package is installed whole, so every Qt platform plugin the PyQt6 wheel carries, QtDBus for the Wayland portal, QtNetwork for the update check, and the 175 resources are present because they were installed, not because an import analysis found them. The cost is the size, around 150 to 200 MB, and a dependency on the `python-appimage` base image being current for Python 3.12 (verified 09-14-26: the `python3.12` release carries `python3.12.14-cp312-cp312-manylinux_2_28_x86_64.AppImage`).

The alternatives: a PyInstaller one-directory bundle wrapped by `appimagetool`, smaller and the tool Technical Architecture PRD Section 9 names, at the cost of hook work for the platform plugins, QtDBus, and the resources, and of a pruning that can drop a lazily imported module on a machine that is not this one; and a bare `appimagetool` over a copied virtual environment, which is not relocatable without the same work as the chosen option. Section 9's packaging row is amended to name `python-appimage` for Linux.

**A correction to the kickoff's cost statement for decision 2:** with this option the AppImage's glibc floor is set by the manylinux image the Python was built on (`manylinux_2_28`, glibc 2.28), not by the machine that runs the build, so a build on the continuous-integration runner runs on distributions older than the runner. Verified in Phase 1 step 2 by reading the built AppImage's library requirements.

Follow-on detail: `AppRun` passes its arguments to `python -m snapmock`; `QT_QPA_PLATFORM` is not forced, so Qt chooses xcb or wayland as it does from source.

### 2.2 Where the build runs and what publishes: option A, continuous integration

A job in `.github/workflows/ci.yml` builds the AppImage on every push and keeps it as a workflow artifact, with a smoke test that runs it on the runner; a release job on a tag of the form `vX.Y.Z` builds it and attaches it to a GitHub release, so every release is built from a clean runner and never from this machine's environment. The local recipe stays for Phase 2's proofs and for development. The cost: a tag is a publication, so tagging is a deliberate act.

### 2.3 The application icon: option A, drawn by this session

An SVG mark for Snapmockit, simple enough to read at 16 pixels and distinct from the Tabler glyphs, kept under `snapmock/resources/icons/` so the wheel carries it; the tray and the About dialog use it too, so the application has one face. The recipe renders the PNG sizes the desktop integration needs from it through Qt's own SVG renderer, so no new tool is needed. It is a first draft, to be replaced by a designed icon when there is one (option B, the follow-up).

### 2.4 The migration of the on-disk names: option A

On the first start of a version that carries it, `~/.config/SnapMock` is moved to `~/.config/Snapmockit`, `~/.config/snapmock` to `~/.config/snapmockit`, and `~/SnapMock/Library` to `~/Snapmockit/Library`, each only when the old exists and the new does not, and each read from the old location if the move fails, so nothing is ever lost. The library is moved only when it is at the default path, and the library path preference is updated with it. The move is announced once in a message that does not block (General UI PRD 1.3). The cost: a move the user did not ask for, and a file manager bookmark that stops working. Built in Phase 4.

### 2.5 The first release's version and standing: option A as corrected

Version `0.9.0`, tagged `v0.9.0`, published as an ordinary GitHub release, not marked a pre-release. The kickoff's option A marked it a pre-release; verified in `snapmock/core/update_check.py` and the General UI PRD rows of 09-10-26, Check for Updates queries the `releases/latest` endpoint, which GitHub defines as the newest release that is neither a draft nor a pre-release, so a release marked pre-release is invisible to the check and Phase 4's proof would report "no release published yet". The version number alone states the standing; the release-engineering notes reserve `1.0.0` for the first packaged release that passed the end-to-end pass. The cost: GitHub labels `0.9.0` "Latest" with no pre-release badge, so its standing is carried only by the number and the release notes. The alternatives were the pre-release mark with the update check amended to read the releases list and accept pre-releases (a change to a decided row, and every later pre-release shown to every user), and `1.0.0` at once.

## 3. Silences decided

The kickoff's seven, each taken as the kickoff states unless noted:

1. The AppImage's file name is `Snapmockit-<version>-x86_64.AppImage`, the version read from `snapmock/__init__.py` through the built wheel's name, never typed.
2. The desktop entry is `io.github.dbower44022.snapmockit.desktop`, with the same id in the AppStream metainfo; categories Graphics and Utility; a MIME type `application/x-snapmockit-project` for `.smk`, declared in a shared-mime-info file the AppDir carries, so a double-click on a project opens it. The Snagit `.snagx` type is not claimed. **Consequence:** the entry point opens project files named on the command line, which it did not do before; the desktop entry's `Exec` carries `%F`. This is the one addition to what the application does beyond the migration and the `--version` flag, and it is tested.
3. Fonts come from the user's system, the colour emoji font included (the marker tools' decision 4); the AppImage bundles none.
4. The Qt platform plugins bundled are those the PyQt6 wheel carries (xcb, wayland, offscreen, minimal, eglfs, linuxfb, vnc, vkkhrdisplay, minimalegl). The system libraries the AppImage still needs from the host are recorded in Section 5 and in the README.
5. Flatpak, PyPI, Windows, and macOS are out of scope and named in the close-out.
6. A `--version` flag is added to the entry point, printing the product's name and version and exiting before any Qt object is created; General UI PRD 11.6's Copy Version Info stays the in-application route.
7. The recipe runs from `uv run` with its own dependency group, `packaging`, so nothing of the packaging tools lands in the application's runtime dependencies.

## 4. Starting state, re-verified 09-14-26 17:56

Verified by running the code on this machine (Linux, Cinnamon on X11, glibc 2.39, Python 3.12.3, uv 0.10.6), not by reading it:

- `uv build` at d961a9a produces `snapmockit-0.1.0-py3-none-any.whl` (739 KB) and its sdist: 348 files, 2.6 MB uncompressed, of which 175 are resources. The virtual environment is 435 MB, PyQt6 with its bundled Qt 6.10.2 is 256 MB.
- The entry point is a module with no `--version` flag and no file arguments; the single-instance forward carries `--capture` only.
- No application icon exists; the tray icon is drawn in code and the About dialog shows Qt's generic desktop icon.
- QSettings stores under `~/.config/SnapMock/SnapMock.conf`, presets and themes under `~/.config/snapmock`, the default library at `~/SnapMock/Library`.
- Check for Updates queries `dbower44022/snapmockit` through `releases/latest`; the repository has no release and no tag.
- The suite: 1631 passed on GitHub at 74bc47d in 16 minutes 56 seconds; a CI run of d961a9a was in progress when this work started and nothing here pushes before it ends.
- Tools on this machine: `appstreamcli` 1.0.2 and `desktop-file-validate` installed; FUSE 2 and 3 libraries present; `python-appimage` 1.4.6 on PyPI; `appimagetool` continuous downloadable (15 MB). PyQt6's `QtSvg` module imports.
- One uncommitted change not of this work was found in the tree at the start: `tests/conftest.py` gains a fixture that deletes closed top-level widgets after each test, the follow-up the release-engineering notes' Section 3 names. It belongs to another session and is left untouched; no commit of this work includes it.

## 5. The recipe

Written in Phase 1 step 2.

## 6. Tests

Written in Phase 1 step 2.

## 7. Follow-ups

- A designed application icon to replace the session's draft (decision 3, option B).

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-14-26 17:59 | Claude (Claude Code) | Initial notes: the phase table, the five decisions as approved (decision 5 corrected: an ordinary release, since `releases/latest` excludes pre-releases), the seven silences with silence 2's consequence for the entry point, and the starting state re-verified. |
