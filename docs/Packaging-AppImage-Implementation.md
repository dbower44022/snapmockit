# Packaging: the Linux AppImage — Implementation Notes

Last Updated: 09-14-26 18:10 · Revision 1.1

Implements step 3 of the release-engineering list (`docs/Release-Engineering.md`, Section 1) for Linux: the AppImage that Technical Architecture PRD 7.3 names as the primary Linux distribution, built by a recipe in the repository, proven on this machine, built in continuous integration on every push, and published as a GitHub release on a tag, together with the migration of the two on-disk names the rename of 09-14-26 left as they were. The kickoff prompt is `docs/Packaging-AppImage-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The five decisions, this document, and the recipe under `packaging/appimage/` with its tests | Done 09-14-26: the suite at 2d10faa, 1652 passed, 13 skipped, 1 deselected, in 7 minutes 58 seconds from a scratch worktree | 860f370, 2d10faa, then the close-out commit |
| 2 | The AppImage built here and run as a user would; every proof of the task recorded; size and start time measured | Checklist page published 09-14-26 (`Snapmockit AppImage Display Checks`); the run is owed | |
| 3 | The build in continuous integration: the AppImage as an artifact on every push, a smoke test on the runner, the release job on a `vX.Y.Z` tag | Not started | |
| 4 | The migration of the on-disk names, and the first release, `v0.9.0` | Not started | |
| Close-out | The PRD rows, the release-engineering notes, the display checks owed, what of 7.3 remains | Not started | |

## 2. Decisions

All five were presented with the consequential decision template on 09-14-26 and approved by Doug as recommended, with the corrections noted.

### 2.1 How the AppImage is built: option A, a relocatable Python AppImage

The `python-appimage` tool's CPython 3.12 base image, built on the `manylinux_2_28` image, is extracted, the application's wheel and its locked dependencies are installed into it by pip, and `appimagetool` seals the result. Nothing is pruned: every package is installed whole, so every Qt platform plugin the PyQt6 wheel carries, QtDBus for the Wayland portal, QtNetwork for the update check, and the 175 resources are present because they were installed, not because an import analysis found them. The cost is the size, around 150 to 200 MB, and a dependency on the `python-appimage` base image being current for Python 3.12 (verified 09-14-26: the `python3.12` release carries `python3.12.14-cp312-cp312-manylinux_2_28_x86_64.AppImage`).

The alternatives: a PyInstaller one-directory bundle wrapped by `appimagetool`, smaller and the tool Technical Architecture PRD Section 9 names, at the cost of hook work for the platform plugins, QtDBus, and the resources, and of a pruning that can drop a lazily imported module on a machine that is not this one; and a bare `appimagetool` over a copied virtual environment, which is not relocatable without the same work as the chosen option. Section 9's packaging row is amended to name `python-appimage` for Linux.

**A correction to the kickoff's cost statement for decision 2:** with this option the AppImage's glibc floor is set by the wheels installed into it, not by the machine that runs the build, so a build on the continuous-integration runner runs on distributions older than the runner. **Verified 09-14-26 by reading the built file's symbol versions:** the bundled Python needs glibc 2.28 (the `manylinux_2_28` image's), and Qt's `libQt6Core.so.6` needs glibc 2.34, because the `pyqt6-qt6` 6.10.2 wheel on PyPI is tagged `manylinux_2_34_x86_64`. **The floor is therefore glibc 2.34:** Ubuntu 22.04, Debian 12, Fedora 35, RHEL 9, and later. The estimate of 2.28 in the decision as presented was wrong by one wheel and is corrected here.

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

`packaging/appimage/` (Technical Architecture PRD 1.50, Section 10). One command from the repository at a commit:

```
uv run --group packaging python packaging/appimage/build.py
```

produces `dist/Snapmockit-<version>-x86_64.AppImage`. The steps, in `build.py`:

1. `uv build --wheel` into `build/appimage/wheel/`; the version is read from the wheel's file name and cross-checked by nothing else, so it is never typed. `uv export --no-dev --no-emit-project --frozen --no-hashes` gives the seven locked runtime requirement lines (numpy, pillow, psutil, pyqt6, pyqt6-qt6, pyqt6-sip, send2trash), so what ships is what `uv.lock` and the CI build prove.
2. The application icon (`snapmock/resources/icons/snapmockit.svg`) is rendered to 16, 24, 32, 48, 64, 128, 256, and 512 pixel PNGs through Qt's SVG renderer on the offscreen platform.
3. A staging directory gets the desktop entry, the 256 pixel PNG named as the entry's `Icon`, `entrypoint.sh`, and `requirements.txt` (the locked lines, then the wheel's path). `python-appimage build app --base-image <the pinned image> --no-packaging` extracts the base image, installs each requirement with the bundled pip under `-I`, and writes `AppRun` from the entry point: `exec "${APPDIR}/usr/bin/python3.12" -I -m snapmock "$@"`. `-I` keeps the user's `PYTHONPATH` and user site-packages out of the bundled interpreter. `QT_QPA_PLATFORM` is not set, so Qt picks xcb or wayland from the session as it does from source.
4. The AppDir is completed with what `python-appimage` does not carry: `usr/share/metainfo/io.github.dbower44022.snapmockit.appdata.xml` with `@VERSION@` and `@DATE@` filled (the `.appdata.xml` name is the one `appimagetool` looks for and validates; AppStream accepts it beside `.metainfo.xml`), `usr/share/mime/packages/io.github.dbower44022.snapmockit.xml`, the hicolor icon set at the eight sizes plus the scalable SVG, and `usr/bin/snapmockit`, a symlink to `AppRun`, so the desktop entry's `Exec=snapmockit %F` names a file that exists.
5. `appimagetool` (fetched once by `python-appimage` into `~/.cache/python-appimage/bin`) seals the AppDir; it validates the AppStream metainfo and embeds the type 2 runtime.

**The base image is pinned:** `python3.12.14-cp312-cp312-manylinux_2_28_x86_64.AppImage` from the `python3.12` release of `niess/python-appimage`, downloaded once into `build/appimage/` by its direct address. `python-appimage`'s own lookup reads GitHub's API unauthenticated on every build, which a shared runner is rate limited against; the pin avoids the call and makes the Python version part of the recipe.

**The build, measured here 09-14-26:** about one minute with the base image already downloaded (the pip installs from PyPI are most of it); the file is 122.3 MB (128,264,696 bytes), below the decision's 150 to 200 MB estimate because squashfs compresses the 435 MB environment well. `--version` answers in 0.40 s wall from the sealed file, mount included. `--appimage-extract-and-run --version` answers the same without FUSE. The AppDir's bundled Python builds the main window on the offscreen platform (`from snapmock.main_window import MainWindow`, then `MainWindow()`), the smoke test Phase 3 runs on the runner.

**What the host must provide (silence 4).** Verified by `ldd` over the xcb platform plugin in the built AppDir: nothing is unresolved on this machine, and the libraries taken from the host are libc, libstdc++, libgcc, glib, dbus, fontconfig, freetype, expat, png, brotli, bz2, lzma, zstd, lz4, pcre2, systemd, gcrypt, gpg-error, cap, bsd, md, X11, X11-xcb, Xau, Xdmcp, xkbcommon, xkbcommon-x11, GL, GLX, EGL, GLdispatch, and the xcb family (xcb, cursor, icccm, image, keysyms, randr, render, render-util, shape, shm, sync, util, xfixes, xkb). On a bare Ubuntu that is the apt list in `ci.yml`'s checks job (`libegl1 libgl1 libglib2.0-0 libdbus-1-3 libfontconfig1 libfreetype6 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xkb1 libxcb-render-util0 libxcb-image0`), plus `libx11-6` and `libxfixes3` for the X11 capture backend's ctypes loads, `libwayland-client0` for the wayland platform plugin, and `xdg-desktop-portal` with a backend for the Wayland capture. Fonts come from the host (silence 3). The README records the same list in Phase 2, once the display run has confirmed it.

**The entry point and the icon.** `snapmock/app.py`: `--version` prints `Snapmockit <version>` and exits before any Qt object exists; the files named on the command line (`parse_command_line` in `capture/cli.py`, which `parse_capture_args` now wraps) open through `MainWindow.open_paths` after the window shows; the application names itself to Qt (`setApplicationName`, `setApplicationVersion`, `setDesktopFileName(DESKTOP_ENTRY_ID)`, `setWindowIcon`), so the window carries the desktop entry's class and icon under xcb and wayland. `DESKTOP_ENTRY_ID` in `config/constants.py` is the one source of the id; the recipe imports it, and the tests compare the files' names to it. `snapmock/ui/icons.py` gains `render_application_icon` and `application_icon`; the tray (`capture/tray.py`) and the About dialog draw the same SVG.

## 6. Tests

`tests/test_packaging_appimage.py`, twelve tests, none of which builds or reaches the network: the desktop entry's fields (type, name, icon, `Exec` with `%F`, the two categories, the MIME type, the window class) and `desktop-file-validate` where installed; the metainfo's id, name, licence, launchable, provided media type, and placeholder release row, the template fill with the package version, and `appstreamcli validate --no-net` where installed; the MIME file's one type and one glob; the entry point's shebang, `-I -m snapmock "$@"`, and the absence of a forced platform; the icon rendered square with an opaque centre and a transparent corner at 16, 48, and 256 pixels, and every size in the application icon; the build script's `render_icons`, `wheel_version`, `appimage_name`, and `requirement_lines`, and the recipe files' existence. `tests/test_app.py` gains the `--version` test (exit code 0, the text, no Qt) and an `open_paths` test that opens a saved project from a path; `tests/test_capture/test_cli_and_channel.py` gains the `parse_command_line` cases (files alone, files after `--capture` and `--delay`, an option without a program name, an unknown option). `desktop-file-validate` reports one hint, that Graphics and Utility are both main categories so the entry may appear twice in a menu; silence 2 names both and the hint is not an error.

## 7. Follow-ups

- A designed application icon to replace the session's draft (decision 3, option B).
- `APP_BUILD_DATE` in `config/constants.py` is set by hand ("2026-09-08"); the release process of Phase 4 sets it for `v0.9.0`, and a later step could derive it from the build.
- `appimagetool` is fetched at its `continuous` tag by `python-appimage`; a pinned release would make the seal reproducible too.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 09-14-26 18:10 | Claude (Claude Code) | Phase 1 done: Sections 5 and 6 written (the recipe, its measurements, the host libraries, the entry point and icon changes, the tests); the glibc floor corrected to 2.34 from the built file; three follow-ups. |
| 1.0 | 09-14-26 17:59 | Claude (Claude Code) | Initial notes: the phase table, the five decisions as approved (decision 5 corrected: an ordinary release, since `releases/latest` excludes pre-releases), the seven silences with silence 2's consequence for the entry point, and the starting state re-verified. |
