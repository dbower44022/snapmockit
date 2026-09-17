# Packaging: the Linux AppImage — Implementation Notes

Last Updated: 09-17-26 11:56 · Revision 2.3

Implements step 3 of the release-engineering list (`docs/Release-Engineering.md`, Section 1) for Linux: the AppImage that Technical Architecture PRD 7.3 names as the primary Linux distribution, built by a recipe in the repository, proven on this machine, built in continuous integration on every push, and published as a GitHub release on a tag, together with the migration of the two on-disk names the rename of 09-14-26 left as they were. The kickoff prompt is `docs/Packaging-AppImage-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The five decisions, this document, and the recipe under `packaging/appimage/` with its tests | Done 09-14-26: the suite at 2d10faa, 1652 passed, 13 skipped, 1 deselected, in 7 minutes 58 seconds from a scratch worktree | 860f370, 2d10faa, then the close-out commit |
| 2 | The AppImage built here and run as a user would; every proof of the task recorded; size and start time measured | Done 09-14-26; the Wayland portal capture, deferred then, passed 09-17-26 (Section 8.4); the icon note closed 09-15-26 as an instruction error | eb4e4ac, d3b100f, then the close-out commit |
| 3 | The build in continuous integration: the AppImage as an artifact on every push, a smoke test on the runner, the release job on a `vX.Y.Z` tag | Done 09-15-26: run 34928224677 green, the AppImage job in 51 seconds | b683422, then the close-out commit |
| 4 | The migration of the on-disk names, and the first release, `v0.9.0` | Done 09-15-26: v0.9.0 published by the release job at 00:43, found by Check for Updates from 0.1.0; the migration\'s first start and the menu check owed as display checks | b29ac86, 080e2f3 |
| Close-out | The PRD rows, the release-engineering notes, the display checks owed, what of 7.3 remains | Done 09-15-26 (Section 11) | the close-out commit |

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

## 8. The Phase 2 display run

**Steps 1.1 and 1.2, run by Doug on 09-14-26 at about 23:25 against the first build (2d10faa):** `--version` printed `Snapmockit 0.1.0`; the start printed one line, `qt.qpa.services: Failed to register with host portal QDBusError("org.freedesktop.portal.Error.Failed", "Could not register app ID: Connection already associated with an application ID")`. Reproduced here with a minimized window from the AppDir's Python: Qt 6.10 registers the desktop entry's id with the desktop portal's registry (`org.freedesktop.host.portal.Registry`) when the first window shows, once, from the name it holds at that moment; the entry point set the name after the application object existed, so Qt registered a second time on the same connection and the portal refused it. **Fixed:** `app.py` sets the application name, version, and desktop file name through the static setters before `QApplication` is constructed, and Qt registers once. Doug ran step 1.2 again against the rebuild of 23:28 and saw the portal's own answer, `Could not register app ID: App info not found for 'io.github.dbower44022.snapmockit'`, and called it another error, which it is from a user's chair: a line at every start. The portal looks the registered id up among the installed desktop entries, and a bare AppImage has none. **Fixed again, 23:35:** `app.py` gains `desktop_entry_installed`, which looks for `<id>.desktop` under the `applications` directory of `$XDG_DATA_HOME` and each of `$XDG_DATA_DIRS` as the desktop does, and the id is given to Qt only where that is true: from a package or an integrated AppImage the registration succeeds and the desktop matches the window to its entry; from source or a bare AppImage nothing is registered and nothing is printed. Verified with a minimized window from the rebuilt AppDir: no line. The application name is set in every case, and Qt's window class on X11 is that name, `Snapmockit`, with or without the desktop file name (read with `xprop`), so the desktop entry's `StartupWMClass` is `Snapmockit`, not the id as first written. Under Wayland the app id is the desktop file name when set, which is exactly the integrated case. Tested in `tests/test_app.py` against a temporary data path.

### 8.1 The run, 09-14-26 23:41 to 23:53

Run by Doug from the checklist page `Snapmockit AppImage Display Checks` (https://claude.ai/artifact/HHCf3xs7L32kcHrtEnBpe2), whose marks were read back, against the build of 23:35 from d3b100f. **25 steps: 19 marked, 18 as described, 1 problem; steps 1.1 and 1.2 run from the terminal and reported in the conversation instead of marked (the two findings above); the four Wayland steps of section 7 not run, since the machine could not be logged out at the time.**

Passing, as described and with no note: the window found the existing settings (theme and panel layout) and the existing library; Help > About showed the icon and version 0.1.0; Copy Version Info's Executable line named the AppImage file; Help > Check for Updates reached GitHub from inside the AppImage, reported "No release has been published yet. You are running 0.1.0.", and Open Repository Page opened the repository; Capture Full Screen and Capture Region through the X11 backend each landed a new tab; `--capture full` from the shell was forwarded to the running instance, which took the capture with no second window; a project was saved, closed, and reopened with its rectangle; PNG and PDF exports were written and the PDF opened in the document viewer; a Snagit file opened with its annotations; the file manager listed the AppImage and a double-click started it; Quit closed it. Every proof the task named is met except the Wayland portal capture.

**The problem, step 2.1 (the icon), closed 09-15-26 00:08 as an instruction error:** Doug's note reads "The icon in the linux titlebar is correct, but there is not icon in the application titlebar." Asked to look at the four places an icon can appear, he answered: the left end of the main window's title bar shows no icon; the panel's button for the window, the Alt+Tab switcher, and the About dialog all show the mark. The title bar is the desktop's: Cinnamon's window manager draws a title bar icon only when its button layout includes the `menu` button, and this machine's layout (`org.cinnamon.desktop.wm.preferences button-layout`) is `:minimize,maximize,close`, so no window on this desktop has a title bar icon, Snapmockit's included. The checklist expected one where the desktop never draws one. The application's icon is set and the three places that read it show it; nothing to fix.

### 8.2 Measurements against Technical Architecture PRD Section 8

**Startup:** from process start to the main window mapped on the X11 display, measured three times with `wmctrl` polling at 50 ms, the sealed file with the FUSE mount, session restore on, on this machine (Intel i7-11700K): **1.70 s, 1.70 s, 1.63 s.** Section 8's target is under 2 seconds to interactive; the window is responsive when mapped. From the extracted AppDir on the offscreen platform the same path takes 1.0 s, so the mount and the display account for about 0.7 s. **Size:** 122.3 MB (128,264,696 bytes). Both recorded in the Technical Architecture PRD's 1.51 row.

**Owed:** the Wayland portal capture (checklist section 7: log into Cinnamon on Wayland, start the AppImage, Capture Full Screen through the portal's consent dialog, Capture Active Window degrading to Region), when the machine can be logged out. It stays a display check of this work until then.

### 8.3 The release found and the first start of 0.9.0, 09-15-26 01:24 to 01:29

Run by Doug from section 8 of the same checklist page, marks read back. **Six steps, six as described, no note.** The 0.1.0 build's Help > About read 0.1.0; its Help > Check for Updates said "Snapmockit v0.9.0 is available. You are running Snapmockit 0.1.0." with Open Release Page, which opened the v0.9.0 release page listing the AppImage. The released 0.9.0 build's first start opened the window as it was, with the message along its bottom edge naming the three moves, and the Library panel listing the same captures; the file manager showed `Snapmockit` in the home folder and `Snapmockit` and `snapmockit` under `.config`, none of the SnapMock names; a second start showed no message and About read 0.9.0. Verified here on the disk afterwards: `~/.config/Snapmockit/Snapmockit.conf`, `~/.config/snapmockit/tool_state.json`, and `~/Snapmockit/Library` with its 22 files exist; `~/.config/SnapMock`, `~/.config/snapmock`, and `~/SnapMock` do not; the settings name the library only under the new path. The two display checks of Section 11 that this section covers are closed; the Wayland portal capture of section 7 is the one that remains.

### 8.4 The Wayland portal capture, 09-17-26 11:44 to 11:52

Run by Doug from section 7 of the same page, rewritten 09-17-26 as 21 steps (w01 to w21), against the released 0.9.0 file in the `Cinnamon on Wayland (Experimental)` session. The full record is `docs/End-to-End-Pass.md`, Section 7. In short: one mark on the page (step 15, an instruction error: a capture is a library file and saves in place without a dialog; Save As worked); the library holds a full-screen capture and two active-window captures turned into regions, each naming the `wayland_portal` backend and version 0.9.0. No capture records a Capture Region request; Doug confirmed at 11:56 that the step worked ("step 12 = yes"). **The Wayland portal capture has passed; this work owes no display check.**

## 9. The build in continuous integration (Phase 3)

`.github/workflows/ci.yml` gains two jobs beside the checks and the wheel build, and runs on tags of the form `vX.Y.Z` as well as on pushes to `main` and pull requests.

**`appimage`, on every run:** `ubuntu-latest` (the `ubuntu-24.04` image on 09-14-26), the same Qt host libraries the checks job installs (the smoke test builds a window offscreen), uv with its cache, `uv sync --locked --group packaging`, the recipe (`python packaging/appimage/build.py`), the smoke test, and `dist/*.AppImage` kept as the `snapmockit-appimage` artifact, missing files an error. The recipe reads nothing from GitHub's API: the base image and `appimagetool` come from release download addresses and the AppImage runtime from `appimagetool`'s own download, none of them rate limited the way the API is on a shared runner.

**`packaging/appimage/smoke.sh`, the smoke test:** the file answers `--appimage-extract-and-run --version` with `Snapmockit <version>`, the version taken from the file's own name; then the file is extracted (`--appimage-extract`, no FUSE), the metainfo, the MIME file, and the 256 pixel icon are checked for, and the extracted image's bundled Python builds the main window on the offscreen platform with `APPDIR` set, as the smoke of Phase 1 did by hand. It runs here in 1.9 seconds against `dist/`, and `tests/test_ci_workflow.py` runs it whenever a built AppImage is in `dist/` (skipped otherwise).

**`release`, on a tag only:** after `checks`, `build`, and `appimage` pass, with `contents: write`. The tag must be `v` followed by the version in `snapmock/__init__.py`, or the job fails before it publishes anything, since Check for Updates compares the release's tag with the running version and a mismatch would tell every user the wrong thing. The AppImage is downloaded from the artifact of the same run, the tag's annotation becomes the release notes (a bare tag gets a one-line note), and `gh release create --verify-tag` publishes an ordinary release (decision 5) titled `Snapmockit <version>` with the AppImage attached. Nothing is built on this machine for a release.

**Tests:** `tests/test_ci_workflow.py` parses the workflow with PyYAML (added to the dev group with its stubs) and holds the triggers, the four jobs, the release job's needs, condition, and permission, the appimage job's three commands and its artifact, the release job's version check, download, and `gh release create` without `--prerelease`, and the smoke script's shape; and it runs the smoke script against a built AppImage when one is present.

**The first run on GitHub, 09-15-26 (run 34928224677, on b683422 and the notes commit after it):** all four jobs as expected. The `appimage` job took 51 seconds from start to finish (04:17:00 to 04:17:51 UTC), the apt install, uv, the base image, the pip installs, the seal, and the smoke test included; the runner built the same 122.3 MB file this machine builds and the smoke test passed on it; the artifact `snapmockit-appimage` holds it (127,536,751 bytes as GitHub stores it). The checks job took 4 minutes 16 seconds and the wheel build 13 seconds; the release job was skipped, as it is on every push that is not a tag. The first release is Phase 4's.

## 10. The migration of the on-disk names (Phase 4, step 1)

`snapmock/config/migration.py` (Technical Architecture PRD 1.53, Section 10). On every start, before the window is built, `migrate_storage` looks at three places and moves each to the product's name only when the old exists and the new does not:

| What | From | To |
|---|---|---|
| The settings store | `~/.config/SnapMock/SnapMock.conf` | `~/.config/Snapmockit/Snapmockit.conf` |
| Presets, themes, tool state, custom stamps | `~/.config/snapmock` | `~/.config/snapmockit` |
| The default library | `~/SnapMock/Library` | `~/Snapmockit/Library` |

The library moves only when the library preference is unset or names the old default; a library the user put elsewhere is left where it is, and the report says so. After a library move every settings value that named a file under the old path (the recent files, the open files, the remembered zooms, the preference itself) is rewritten to the new path, so nothing dangles, and the emptied `~/SnapMock` directory is removed. Nothing is deleted or overwritten: a new location that already exists, or a move the file system refuses, leaves the old in place with the reason in the report. The three lookups the application reads through, `storage_names` (used by `AppSettings`), `data_directory` (used by `application_data_directory`), and `default_library_directory` (used by `AppSettings.library_directory`), answer with the old location while only it exists, so a machine where the move could not happen keeps working from the old names. The constants carry the product's names, with `LEGACY_` constants beside them. The entry point calls the migration once the application object exists and, after the window shows, reports the moves made in one toast and one log line, never a dialog that blocks (General UI PRD 1.3), through `MainWindow.show_startup_message`. Running from source migrates too, since the source and the AppImage share the same stores; on this machine the first start of any build from this commit moves Doug's settings, the theme store, and the library at `~/SnapMock/Library`, which the preference does not override (verified: `library/directory` is unset in the store).

**Tests:** `tests/test_storage_migration.py`, ten tests against a temporary home and configuration root: the lookups on a fresh machine, with only the old store, and with both; the full move with the rewritten paths and the message; idempotence and the empty run; a new location never overwritten; a library the preference puts elsewhere left alone; a preference naming the old default moved with the library; a refused move leaving everything readable through the old names; `rewrite_paths` touching only the strings that name the old library; the message's shape. The suite's isolated-settings fixture keeps the migration out of every other test.

### 10.1 The first release, v0.9.0 (Phase 4, step 2)

Version `0.9.0` and build date `2026-09-15` in commit 080e2f3, its suite green from a scratch worktree (1669 passed, 14 skipped, 1 deselected, 6 minutes 13 seconds); the annotated tag `v0.9.0`, whose message is the release's notes, pushed with `main` at 00:39. **Run 34929663044 on the tag:** the checks in 3 minutes 34 seconds, the wheel in 12 seconds, the AppImage job in 72 seconds, and the release job in 19 seconds after them; **the release `Snapmockit 0.9.0` was published at 00:43 with `Snapmockit-0.9.0-x86_64.AppImage` attached, 128,272,888 bytes, an ordinary release** (`prerelease=false`, decision 5 as corrected), and `releases/latest` answers with it. The file was downloaded here (SHA-256 begins `ebe7c8e0f0b7427c`), answers `--version` with `Snapmockit 0.9.0`, and passes the smoke script against a scratch home.

**Check for Updates from the version before, proven headless:** the 0.1.0 AppImage of 23:35, extracted, running `UpdateChecker` from its own bundled Python against the real endpoint (`https://api.github.com/repos/dbower44022/snapmockit/releases/latest`): outcome `NEWER`, tag `v0.9.0`, release page `https://github.com/dbower44022/snapmockit/releases/tag/v0.9.0`. The same check through the Help menu, and the migration's first start of 0.9.0 on this machine, are display checks owed to Doug (Section 11).

## 11. Close-out

**Done.** Technical Architecture PRD 7.3's primary Linux form exists: a recipe (Section 5), proven here (Section 8), built and smoke-tested in continuous integration on every push (Section 9), and published as the GitHub release `v0.9.0` that Check for Updates finds (Section 10.1); the on-disk names migrate to the product's on first start (Section 10). PRD rows: Technical Architecture 1.50 to 1.54 (7.3, 8, 9, 10, and 4.4); General UI 2.39 (3.8's first real target, and the application data directory's new name). `docs/Release-Engineering.md`: step 3 done for Linux, step 4 pointed at the released AppImage.

**What of 7.3 remains, and what this machine can build:** Flatpak (secondary Linux; this machine can build it, with `flatpak-builder` and the KDE or freedesktop runtime, a manifest, and the same desktop integration files; a Flathub submission is a separate step); PyPI (`uv publish` of the wheel and sdist the CI build already makes, from this machine or a workflow, once a PyPI account and token exist; the console entry point Section 3 of the kickoff noted is missing would be added then); the Windows MSI and portable ZIP (need a Windows machine, and the Windows capture backend's own display checks first; `docs/Windows-Backend-Kickoff-Prompt.md`); the macOS bundle (needs a Mac, and the macOS backend, deferred). This machine can build the Flatpak and publish to PyPI; it cannot build the Windows or macOS packages.

**Display checks this work owes:** none since 09-17-26, when the Wayland portal capture of the checklist page's section 7 passed (Section 8.4). The others, Help > Check for Updates from the 0.1.0 AppImage finding v0.9.0, and the first start of 0.9.0 with the migration's message and the new names on disk, passed on 09-15-26 (Section 8.3).

**The next required step** is step 4 of the release-engineering list: an end-to-end pass on real work on the released AppImage, `Snapmockit-0.9.0-x86_64.AppImage`, before `1.0.0` is claimed. Its kickoff prompt is not yet written.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 2.3 | 09-17-26 11:56 | Claude (Claude Code) | Section 8.4: Capture Region confirmed by Doug; the Wayland capture passed and no display check is owed; Phase 2's row and Section 11 say so; the 2.2 row's time corrected to 11:54. |
| 2.2 | 09-17-26 11:54 | Claude (Claude Code) | Section 8.4: the Wayland portal capture run by Doug, recorded from the files it left; Capture Region's evidence put to Doug. |
| 2.1 | 09-15-26 09:50 | Claude (Claude Code) | Change log back-filled: the rows for revisions 1.3 to 2.0 were never written when those revisions were made (found at the start of the end-to-end pass, `docs/End-to-End-Pass.md`); each row below is taken from the commit that made the revision. No other content changed. |
| 2.0 | 09-15-26 01:30 | Claude (Claude Code) | Section 8.3: Doug's section 8 run, Check for Updates from 0.1.0 finding v0.9.0 and the migration's first start of 0.9.0, six steps as described; the Wayland capture the one display check left owed. |
| 1.9 | 09-15-26 00:45 | Claude (Claude Code) | Phase 4 and the close-out done: Section 10.1 (v0.9.0 released and found by Check for Updates headless) and Section 11 (the PRD rows, what of 7.3 remains, the display checks owed). |
| 1.8 | 09-15-26 00:26 | Claude (Claude Code) | Section 10: the migration of the on-disk names (packaging decision 4) and its tests. |
| 1.7 | 09-15-26 00:22 | Claude (Claude Code) | Phase 3 closed: the first CI run with the AppImage job green in 51 seconds recorded in Section 9. |
| 1.6 | 09-15-26 00:11 | Claude (Claude Code) | Section 9: the CI jobs, the smoke script, and the workflow tests of Phase 3. |
| 1.5 | 09-15-26 00:08 | Claude (Claude Code) | Section 8.1: the step 2.1 icon note closed as an instruction error (Cinnamon's button layout draws no title bar icon). |
| 1.4 | 09-14-26 23:56 | Claude (Claude Code) | Phase 2 closed: Sections 8.1 and 8.2, the display run of 18 steps as described and the startup and size measurements. |
| 1.3 | 09-14-26 23:35 | Claude (Claude Code) | Section 8: the second portal line and its fix, the desktop entry's id given to Qt only where the entry is installed. |
| 1.2 | 09-14-26 23:29 | Claude (Claude Code) | Section 8 opened with the first two steps of Doug's run: the portal registration line from the first build, its cause, and the fix in `app.py`. |
| 1.1 | 09-14-26 18:10 | Claude (Claude Code) | Phase 1 done: Sections 5 and 6 written (the recipe, its measurements, the host libraries, the entry point and icon changes, the tests); the glibc floor corrected to 2.34 from the built file; three follow-ups. |
| 1.0 | 09-14-26 17:59 | Claude (Claude Code) | Initial notes: the phase table, the five decisions as approved (decision 5 corrected: an ordinary release, since `releases/latest` excludes pre-releases), the seven silences with silence 2's consequence for the entry point, and the starting state re-verified. |
