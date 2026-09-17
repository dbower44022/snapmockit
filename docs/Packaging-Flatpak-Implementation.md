# Packaging: the Linux Flatpak — Implementation Notes

Last Updated: 09-17-26 18:24 · Revision 1.2

Implements the Flatpak that Technical Architecture PRD 7.3 names as the secondary Linux form, the next part of step 3 of the release-engineering list (`docs/Release-Engineering.md`, Sections 1 and 4), which Doug put ahead of the Python Package Index on 09-17-26. The kickoff prompt is `docs/Packaging-Flatpak-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL. The AppImage's notes, `docs/Packaging-AppImage-Implementation.md`, hold the recipe and the release job this work builds beside.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The five decisions, this document, the builder and runtimes installed, the suite under Python 3.13, and the manifest under `packaging/flatpak/` with its tests | Done 09-17-26: the bundle built here, 25.4 MB, and proven headless (Sections 2, 6, 7, 8) | 4d6e2ea, 7b594d1, this commit |
| 2 | The code the sandbox needs (decisions 4 and 5, and the three corrections of Section 5), and the Flatpak proven on this machine through a checklist page | Not started | |
| 3 | The build in continuous integration: the Flatpak on every push as an artifact, and the release job attaching the bundle beside the AppImage | Not started | |
| 4 | The release that first carries both files, `1.1.0` | Not started | |
| Close-out | The PRD rows, the README, the release-engineering notes, the display checks owed, and what of 7.3 remains | Not started | |

## 2. Decisions

All five were presented with the consequential decision template on 09-17-26 at 13:34 and approved by Doug as recommended, decision 1 on the 6.11 runtime branch the presentation recommended as its follow-on detail.

### 2.1 How the Flatpak is built: option A, the KDE runtime and the PyQt base application, branch 6.11

The application is built on `org.kde.Platform//6.11` with `com.riverbankcomputing.PyQt.BaseApp//6.11` as its base application, so PyQt6 comes built against the runtime's Qt and the runtime's Python 3.13 runs the application. Pillow, numpy, psutil, and send2trash are built as modules the manifest lists. Qt is shared with every other KDE Flatpak on the machine, so the bundle carries only the application and its four dependencies, and this is the form Flathub accepts.

The 6.11 branch rather than 6.10: both branches offer the base application (6.11.0 against 6.10.2 on Flathub on 09-17-26), both runtimes are already installed on this machine, and the newer branch is supported longer.

The alternatives: the freedesktop runtime with the PyQt6 wheels from the Python Package Index, which carry their own Qt as the AppImage does, at the cost of a bundle of about the AppImage's size and a form Flathub is unlikely to accept; and the AppImage's relocatable Python 3.12 copied into a freedesktop-runtime Flatpak, the least Flatpak-like form.

**The cost, as presented:** the application runs on Python 3.13 and on Qt 6.11, a combination no one has tested before this work. Phase 1 step 3 answers the interpreter by running the suite under Python 3.13 and adding it to the continuous-integration checks job; Qt 6.11 is answered by Phase 2's proofs on this machine. PyQt6's version is the base application's, not the lock file's.

### 2.2 Where the Flatpak is published: option A, a bundle on the GitHub release

Continuous integration builds `Snapmockit-<version>-x86_64.flatpak` on every push and keeps it as an artifact; the release job attaches it to the GitHub release beside the AppImage; a user installs it with `flatpak install`. A Flathub submission is its own later step, after the bundle has been used, because Flathub's review can force changes to the manifest.

**The cost:** a bundle installed by hand never updates itself, so a user downloads the next bundle as an AppImage user does. Decision 5's message says so.

### 2.3 What the sandbox may reach: option A, the whole home directory

`--filesystem=home`, so the library at `~/Snapmockit/Library`, Open and Save anywhere in the home directory, and the recent files and the session restore work with the paths the user chose, exactly as the AppImage has them. With it: the Wayland socket and the fallback X11 socket, the shared IPC namespace, the GPU device, and the network for Check for Updates.

**The cost:** Flathub asks a broad filesystem permission to be justified, and the sandbox does not protect the home directory. **The justification, for decision 2's later Flathub step:** the application is a file editor whose documents are the user's own image and project files in arbitrary locations; its library is a folder of project files the user may put anywhere; and it restores a session of open files across restarts, which the document portal's per-session paths under `/run/user/<id>/doc/` cannot carry.

### 2.4 Whether the Flatpak shares the AppImage's settings: option C, a store of its own, filled once

The Flatpak's settings, presets, themes, tool state, and custom stamps live under `~/.var/app/io.github.dbower44022.snapmockit/` where Flatpak's defaults put them. On the Flatpak's first start, if `~/.config/Snapmockit` or `~/.config/snapmockit` exists on the host and the Flatpak's own store does not, each is copied once, the way `config/migration.py` moved the old names in 0.9.0. The library is not copied: decision 3 gives the Flatpak the same `~/Snapmockit/Library`.

**The cost:** a copy the user did not ask for, and changes made after it are no longer shared between the two forms.

**Follow-on detail:** the copy reads `~/.config` from the home directory by path, not through Qt's configuration location, which inside the sandbox points at the Flatpak's own store. One message on the first start reports the copy, never a dialog that blocks (General UI PRD 1.3), through the same `show_startup_message` the migration uses.

### 2.5 What Check for Updates says inside the Flatpak: option A, a message of its own

When the file `/.flatpak-info` exists, a newer release is reported with how to get it for this form — the new bundle downloaded and installed with `flatpak install`, and `flatpak update` once decision 2's Flathub step exists — and Open Release Page still opens the release. Outside a Flatpak the message is unchanged.

**The cost:** a second wording in General UI PRD 3.8 and a branch the tests hold.

Option C, removing the Help row inside the Flatpak, was not recommended and was not taken: General UI PRD 1.3 keeps controls present.

## 3. Silences decided

The kickoff's six, one of them corrected by what the code says (Section 5.1):

1. The application id is `io.github.dbower44022.snapmockit`. The desktop entry, the AppStream metainfo, the MIME type, and the icon are the files under `packaging/appimage/`, used from where they are. If both forms ever need to change them, they move to a shared `packaging/linux/` in one commit with its Technical Architecture PRD Section 10 row.
2. The bundle's file name is `Snapmockit-<version>-x86_64.flatpak`, the version read from the package, never typed; the manifest builds from the local checkout, never from a download.
3. The release that first carries the Flatpak is `1.1.0`: the Flatpak is a new form and decision 5 changes what the application says.
4. **Corrected: send2trash stays.** The kickoff has it declared and never imported, and that is wrong: `snapmock/library/manager.py` imports it and `send_to_system_trash` uses it when a library delete is finalised (Library PRD 10.2). It is pure Python and the manifest builds it as one more module. Section 5.1 records the correction; Section 5.2 records what it does inside a sandbox.
5. The Windows and macOS capture backends, and the menu entry the AppImage does not install, are out of scope and named in the close-out.
6. The Flatpak's startup is measured from `flatpak run`, which adds the sandbox's own start to the application's, against Technical Architecture PRD Section 8's two-second target.

## 4. Starting state, re-verified 09-17-26 13:35

Verified on this machine (an Intel i7-11700K, Linux Mint 22.2, Cinnamon on X11, with a Cinnamon on Wayland session available) by running the tools, not by reading:

- **The head is 8103568** and its continuous-integration run, 35253331043, passed at 13:36 in 4 minutes 32 seconds. The working tree is clean. **v1.0.0 is the latest release**, the Linux AppImage alone.
- **Flatpak 1.14.6**, with the `flathub` remote at system level. `appstreamcli` 1.0.2 and `desktop-file-validate` are installed. **`flatpak-builder` is not installed**; Flathub offers it as the application `org.flatpak.Builder` (126.8 MB to download).
- **The runtimes.** `org.kde.Platform` 6.10 **and 6.11** are both installed; the kickoff names only 6.10. Each carries Python 3.13.15 and no PyQt6. Neither `org.kde.Sdk//6.10` (1.1 GB) nor `org.kde.Sdk//6.11` (1.2 GB) is installed. Flathub offers `com.riverbankcomputing.PyQt.BaseApp` at 6.10 (version 6.10.2, 240.7 MB) and at **6.11 (version 6.11.0, 244.1 MB)**; neither is installed. `org.freedesktop.Platform` 25.08 and 26.08 and `org.freedesktop.Sdk//25.08` are installed and are not used by decision 1.
- **The application has only ever run on Python 3.12**: `requires-python = ">=3.12"`, `.python-version` 3.12, the continuous-integration checks job on 3.12, the AppImage on a relocatable 3.12.14. uv 0.10.6 offers `cpython-3.13.12` as a download.
- **The dependencies** are PyQt6, Pillow, numpy, send2trash, and psutil; Pillow, numpy, and psutil are compiled, send2trash is pure Python, and all five are used.
- **The desktop files** under `packaging/appimage/`: `io.github.dbower44022.snapmockit.desktop` (`Exec=snapmockit %F`, `StartupWMClass=Snapmockit`), `.appdata.xml` with `@VERSION@` and `@DATE@` filled at build time, and the MIME type for `.smk`; the icon is `snapmock/resources/icons/snapmockit.svg`, rendered to eight PNG sizes by `packaging/appimage/build.py`.
- **What differs inside a Flatpak, from reading, to be proven in Phase 2:** `XDG_CONFIG_HOME` and `XDG_DATA_HOME` point under `~/.var/app/io.github.dbower44022.snapmockit/`, which is what decision 4 answers; the home directory is reachable because of decision 3; the X11 backend loads `libX11`, `libXfixes` and friends through `ctypes.util.find_library`, which the runtime must carry; Qt registers the application id with the desktop portal from the sandbox, and `desktop_entry_installed` in `snapmock/app.py` must find the entry the Flatpak exports under `/app/share/applications`; the single-instance channel is a `QLocalServer` whose socket, named for the user under the temporary directory, must be reachable from a second `flatpak run` of the same application.

## 5. Corrections to the kickoff prompt

### 5.1 send2trash is used

Found at 13:20 by reading `snapmock/library/manager.py`: line 15 imports `send2trash`, and `send_to_system_trash` (line 537) calls it; `snapmock/library/commands.py` uses that when a delete leaves the session trash for good, which is Library PRD 10.2's model. The kickoff's silence "send2trash, declared and never imported, is removed" is therefore not applied, and the dependency and the lock file are unchanged. Silence 4 above records the correction.

### 5.2 Inside a Flatpak, a deleted library file would go to a trash the user cannot see

Inferred from how send2trash works, **not yet proven**: it writes to the trash directory under `$XDG_DATA_HOME`, which inside the Flatpak is `~/.var/app/io.github.dbower44022.snapmockit/data/Trash`, not the user's own trash, so a file deleted from the library would vanish from the file manager's Trash. Qt's own `QFile.moveToTrash` reads the same variable. The route that works inside a sandbox is the desktop's own trash service, `org.freedesktop.portal.Trash`, over the same QtDBus connection the Wayland capture backend already uses. Phase 2 step 1 proves the behaviour first and, if it is as inferred, fixes it with a test first.

### 5.3 The desktop-shortcut commands shown to the user name a command that does not exist

`snapmock/capture/onboarding.py` (lines 35 to 37) and `snapmock/ui/preferences_dialog.py` (lines 68 to 70) show `snapmock --capture region` and its two siblings for the user to bind to a key. No installed form provides a `snapmock` command: the AppImage's is `snapmockit` and only when it is on the path, and the Flatpak's is `flatpak run io.github.dbower44022.snapmockit --capture region`. Screen Capture PRD 3.5 and 9.2 make this command the Wayland user's only route to a hotkey, so a wrong command is a defect for both forms. Fixed in Phase 2 step 1 with a test: the command shown is the one that starts the running form.

## 6. Python 3.13 (Phase 1 step 3)

**The suite passes under Python 3.13 unchanged: 1707 passed, 14 skipped, 1 deselected, in 5 minutes 48 seconds**, run on 09-17-26 at 13:39 from a scratch `git worktree` at 4d6e2ea with `uv sync --locked --python 3.13` and `QT_QPA_PLATFORM=offscreen uv run --python 3.13 pytest -q`, the one environmental deselection as always. The interpreter was uv's `cpython-3.13.12`; the KDE runtime carries 3.13.15, a patch release ahead. No defect was found, so no fix and no new test belong to this step. The lock file already resolves under 3.13, since `requires-python` is `>=3.12`, and nothing in it was changed.

**Continuous integration now runs both interpreters.** `.github/workflows/ci.yml`'s checks job gains a matrix of `3.12` and `3.13` with `fail-fast: false`, and sets `UV_PYTHON` to the matrix value, so `uv python install`, `uv sync --locked`, and every `uv run` in the job use it. The other three jobs are unchanged and stay on 3.12: the AppImage bundles 3.12 and the wheel is version-independent. `tests/test_ci_workflow.py` gains `test_checks_job_runs_on_both_interpreters`, which holds the two versions, the fail-fast setting, and the environment variable. Technical Architecture PRD 1.61 records the change and Section 9's language row now reads 3.12+ with both tested versions named.

## 7. The tools installed (Phase 1 step 2)

Doug ran the three installs at about 18:00 on 09-17-26 into the system-wide installation, and the listing afterwards reads: `com.riverbankcomputing.PyQt.BaseApp` branch 6.11, version **6.11.0**; `org.flatpak.Builder` branch stable, version **v0-Flathub**; `org.kde.Sdk` branch **6.11**. `org.kde.Sdk.Locale` 6.11 and an NVIDIA graphics extension came with them as dependencies. `flatpak-builder` is therefore reached as `flatpak run org.flatpak.Builder`, which is what the build script falls back to when no `flatpak-builder` is on the path.

## 8. The recipe (Phase 1 step 4)

`packaging/flatpak/` (Technical Architecture PRD 1.62, Section 10). One command from the repository at a commit:

```
uv run python packaging/flatpak/build.py
```

produces `dist/Snapmockit-<version>-x86_64.flatpak`. The four files:

- **`io.github.dbower44022.snapmockit.yml`**, the manifest. `org.kde.Platform` 6.11 with `org.kde.Sdk` 6.11 and the base application `com.riverbankcomputing.PyQt.BaseApp` 6.11 (decision 1); the command is `snapmockit`; the permissions are decision 3's six and nothing else. Two modules: the generated dependency module, then the application, whose sources are the staging directory the build script fills and the launcher beside the manifest. `cleanup-commands` runs the base application's own `/app/cleanup-BaseApp.sh`, and `build-options.env` sets `BASEAPP_REMOVE_WEBENGINE` and `BASEAPP_REMOVE_PYWEBENGINE`, which that script reads: nothing under `snapmock/` imports QtWebEngine, and removing it with the runtime's locale extension took the bundle from **150.3 MB to 25.4 MB** and the installed application from 718 MB to 137 MB.
- **`python3-deps.json`**, generated by `build.py --update-deps` from the versions `uv.lock` pins, never written by hand: numpy 2.4.2, Pillow 12.1.1, psutil 7.2.2, and send2trash 2.1.0, each as the Python Package Index address of its CPython 3.13 wheel and that wheel's SHA-256, installed by one `pip3 install --no-index --no-deps`. `flatpak-builder` downloads the four itself, so the build sandbox never reaches the network. PyQt6 is not among them: the base application carries 6.11.0, which is the one departure from the lock file (decision 1's stated cost). A wheel is chosen only when the runtime's interpreter can load it: a pure-Python wheel, a `cp313-cp313` build, or a stable-ABI `cp3N-abi3` build with N at most 13, on glibc and x86-64, never a free-threaded, musl, or other-architecture wheel.
- **`snapmockit.sh`**, the command the manifest names, since the wheel installs no console script: `exec python3 -m snapmock "$@"`, so the desktop entry's `%F` files and `--capture` reach the entry point as they do from `AppRun`.
- **`build.py`**. It loads `packaging/appimage/build.py` by path, so the wheel build, the icon rendering, the metainfo template fill, and the desktop files are the AppImage's own and the two forms cannot drift. It builds the wheel, stages it with the desktop entry, the filled metainfo (named `.metainfo.xml`, which is what a Flatpak's AppStream data is called), the MIME type, the scalable icon and the eight PNG sizes; runs `flatpak-builder` into a local OSTree repository; and runs `flatpak build-bundle` over that repository into `dist/`. It prints the bundle's size and SHA-256.

**The first build, 09-17-26, from 4d6e2ea's tree with the Phase 1 changes:** `Snapmockit-1.0.0-x86_64.flatpak`, **25.4 MB** (SHA-256 begins `1625dcb85d0e4e7b`), the application 137 MB installed beside the shared runtime. Two defects of the first attempt were fixed in the recipe: pip refuses a wheel whose file name is not a wheel's, so the staged wheel keeps its own name and the manifest installs `snapmockit-*.whl`; and the first bundle carried QtWebEngine and 296 MB of locales, which the cleanup environment above removes.

**Proven headless here, before Phase 2's display runs:** the bundle installed with `flatpak install --user`; `flatpak run io.github.dbower44022.snapmockit --version` answers `Snapmockit 1.0.0`; inside the sandbox the main window builds on the offscreen platform on **Python 3.13.15 and Qt 6.11.1**, with numpy 2.4.2, Pillow 12.1.1, and psutil 7.2.2 imported and the window titled `Untitled - Snapmockit`; `XDG_DATA_DIRS` inside the sandbox begins `/app/share`, where the manifest installs the desktop entry, so `desktop_entry_installed` is true and Qt registers the id with the portal, which is what the AppImage could not do unintegrated; the configuration location is `~/.var/app/io.github.dbower44022.snapmockit/config`, which is what decision 4 answers; and **the single-instance channel crosses two `flatpak run` invocations** — a listening instance received `['snapmockit', '--capture', 'full']` forwarded from a second one, so `/tmp` is shared between instances of the application and the Wayland user's hotkey route works in this form.

**The suite at a0d528f:** 1730 passed, 14 skipped, 1 deselected, in 5 minutes 59 seconds from a scratch `git worktree`, the one environmental deselection as always.

**Tests:** `tests/test_packaging_flatpak.py`, twenty-two tests, none of which builds or reaches the network: the manifest's runtime, base application, and branch; its id against the desktop entry, the metainfo, and the MIME file; **its permissions as exactly decision 3's set**; the two modules, the application module's install commands and its two sources; the QtWebEngine removal; the launcher's shape; the generated module's addresses, digests, and the four distributions it carries with no PyQt6 among them; and the recipe's own functions (the bundle's name, the pins with PyQt6 dropped, the wheel choice over nine file names, the preference for the newest glibc floor, the refusal when no wheel fits, and the module's shape).

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.2 | 09-17-26 18:24 | Claude (Claude Code) | Phase 1 done. Section 7: the three tools Doug installed, with their versions. Section 8: the recipe under `packaging/flatpak/`, the first bundle (25.4 MB after QtWebEngine and the locales were removed), the two defects fixed in it, what is proven headless inside the sandbox, and the twenty-two tests. Technical Architecture PRD 1.62 (Section 10 gains the directory; Section 9's packaging row names flatpak-builder). |
| 1.1 | 09-17-26 13:47 | Claude (Claude Code) | Section 6: Phase 1 step 3 done. The whole suite passes under Python 3.13 unchanged (1707 passed, 5 minutes 48 seconds), so no defect was found; the continuous-integration checks job now runs 3.12 and 3.13 on every push, held by a test. Technical Architecture PRD 1.61. |
| 1.0 | 09-17-26 13:38 | Claude (Claude Code) | Initial notes: the phase table; the five decisions as approved on 09-17-26 at 13:34, decision 1 on the 6.11 runtime branch; the six silences with silence 4 corrected (send2trash is used); the starting state re-verified, adding the 6.11 runtime and base application the kickoff does not name; and three corrections to the kickoff prompt, two of them defects for Phase 2. |
