# Kickoff Prompt: The Menu Entry

Last Updated: 09-21-26 10:21 · Revision 1.1

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. Start it only when no other session is committing in this working directory and no continuous-integration run of the current commit is in progress, since a push cancels a run in progress on the same branch. This is end-to-end pass finding 1 (`docs/End-to-End-Pass.md`, Section 5.1) and step 2 of what is left on the release-engineering list (`docs/Release-Engineering.md`, Section 4). It comes after the Python Package Index work closed on 09-19-26 with v1.2.0 (`docs/Packaging-PyPI-Implementation.md`). `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) still governs the standards, and this prompt governs the work. Where the two disagree, the general prompt wins and this one is corrected. The work is three phases and a close-out. A session pasting this prompt starts at the first phase not marked done in Section 1 of the notes document this work creates.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root.

## Task

Put Snapmockit in the desktop's main menu from inside the application, so that a user who installed the AppImage or installed from the Python Package Index can start it the way every other application starts, and can take it out again:

- **An action in the application** that writes the desktop entry and the icons, and an action that removes them.
- **The entry written for the form that is running**, so its `Exec` starts that installation and no other.
- **The icons installed at the sizes the desktop reads**, rendered from the application's own SVG through Qt, as the AppImage recipe already does at build time.
- **Nothing installed for a form that has an entry already** (the Flatpak installs its own), and nothing written outside the user's own `~/.local/share`.

The session opens by presenting the decisions below with the consequential decision template, and then waits.

## Read first, in this order

1. `docs/End-to-End-Pass.md` Section 5.1, finding 1 whole: what Doug did by hand, what the desktop did with the icon, and what the follow-up asks for.
2. `docs/Release-Engineering.md` Sections 1, 4, and 5.
3. `docs/Packaging-AppImage-Implementation.md` Sections 2, 3, and 5; `docs/Packaging-PyPI-Implementation.md` Sections 2 and 6, for the four installed forms and what each one's command is.
4. `snapmock/config/packaging.py` whole (the form, the installer, `launch_command`), and `snapmock/app.py`'s `desktop_entry_installed` and `main`.
5. `packaging/appimage/build.py`: `render_icons`, `complete_appdir`, `fill_template`, and the three files beside it — `io.github.dbower44022.snapmockit.desktop`, the AppStream metainfo, and `io.github.dbower44022.snapmockit.xml` (the MIME type for `.smk`).
6. `snapmock/ui/icons.py` (`application_icon`, `render_application_icon`), and `snapmock/main_window.py`'s Help menu (about line 1760) and `show_startup_message`.
7. `PRDs/SnapMock-Technical-Architecture-PRD.html` 7.3 and 10; `PRDs/SnapMock-General-UI-PRD.html` 1.3, 3.8, and 11 (the Help menu), and the README's "Putting it in the menu" section, which this work replaces.

Do not write anything until all seven are read.

## Starting state, verified on 09-20-26

Verified on this machine by running the tools, not by reading:

- **The AppImage carries the entry, the icons, and the MIME file inside it, and installs none of them.** The user's route is the README's "Putting it in the menu": nine shell lines, a copy of the AppImage to `~/Applications`, `--appimage-extract` for two icon files, a heredoc for the entry, and `update-desktop-database`.
- **An installation from the index installs no entry and no icon either** (PyPI silence 3), and its command is `snapmockit`, linked by pipx into `~/.local/bin`.
- **The Flatpak installs its own entry and icon**, so it needs none of this.
- **`snapmock/config/packaging.py` knows the four forms** and gives each one's launch command; `app.py`'s `desktop_entry_installed` already reads `$XDG_DATA_HOME` and `$XDG_DATA_DIRS` for `io.github.dbower44022.snapmockit.desktop`, and the entry point gives Qt the desktop id only when that file exists.
- **The entry template** (`packaging/appimage/io.github.dbower44022.snapmockit.desktop`) carries `Exec=snapmockit %F`, `Icon=io.github.dbower44022.snapmockit`, `Categories=Graphics;Utility;`, `MimeType=application/x-snapmockit-project;`, and `StartupWMClass=Snapmockit`.
- **The icons can be rendered at run time:** `snapmock/ui/icons.py` already renders the application's SVG through Qt at several sizes for the window icon, and `packaging/appimage/build.py`'s `render_icons` does the same to PNG files at build time.
- **The Help menu** holds Welcome / Getting Started, Documentation, Keyboard Shortcuts, Report a Bug, a separator, and then Check for Updates and About.
- **A message that does not block** already exists for the entry point: `MainWindow.show_startup_message`, used by the storage migration, a toast and a log line (General UI PRD 1.3).

## Phases

Three phases and a close-out. Each phase is one or more commits and is closed out before the next starts: the PRD rows, the notes' section, the phase-table row marked done, and the next required step. Every commit is ruff-clean and mypy-strict-clean with the suite passing. The full suite runs from a scratch `git worktree` at the commit under test with `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font`, in about 6 minutes. A push to `main` cancels the continuous-integration run in progress, so push once per phase, after the suite.

### Phase 1, the decisions and the installer

1. **The decisions**, presented with the consequential decision template, and `docs/Menu-Entry-Implementation.md` (revision 1.0) created with the phase table, the decisions, and the silences decided. One commit.
2. **The module that writes and removes the entry**, in the package (its name and place get a Technical Architecture PRD Section 10 row in the same commit). It writes the entry, the icons, and, per decision 4, the MIME file; it removes exactly what it wrote and nothing else; it reports what it did and what it could not do. It writes only under `$XDG_DATA_HOME` (default `~/.local/share`), never as root, and never outside the user's home.
3. **What the entry says per form** (decision 2), taken from `config/packaging.py`, with the AppImage's copy question (decision 3) settled.
4. **Tests** against a temporary home: the entry written for each form with the right `Exec`, the icons at each size, the entry read back by `desktop_entry_installed`, removal leaving nothing behind, a second install over the first, a read-only directory reported and not raised, and the Flatpak form refusing to write at all.

### Phase 2, the application

1. **The action** (decision 1), with its label changing to the removal when the entry is installed, and the row absent or inert where it cannot apply — remembering that no control is disabled (General UI PRD 1.3), so a form that needs nothing says so instead.
2. **The offer on first start** if decision 1 takes it, as a toast that does not block, with the action on it.
3. **What the user is told** when the desktop has not rescanned its icon directories: finding 1 saw the entry appear at once and the icon only after the desktop shell restarted.
4. **Tests** through the window, on the offscreen platform, with the writing module stubbed.

### Phase 3, the display run

1. **Doug's run on his display**, written as a checklist page with the `instruction-discipline` skill: the action from a 1.2.0 installation from the index and from the released AppImage, the entry in the menu, the icon, starting from the menu, a `.smk` file opened by a double-click if decision 4 takes the MIME type, and the removal.
2. **What the run finds**, fixed with tests.

### Close-out of the work

The README's "Putting it in the menu" replaced by the action, with the shell recipe kept only as the manual route for anyone who wants it. `docs/Release-Engineering.md` Sections 1 and 4 brought to the state of the work. The Technical Architecture PRD 7.3 and Section 10 rows, and the General UI PRD row for the Help menu. The next required step, which is expected to be the Windows package and its capture backend. **Say plainly what remains**: Windows and macOS.

## Decisions to surface

Apply the two-part test from the global guidance. Four decisions are expected to pass it. Present them with the consequential decision template, **one at a time, as DETAIL mode asks**, before Phase 1 step 2, and wait for each.

- **1. How the user reaches it.** Option A: a Help menu row, "Add to Menu", which becomes "Remove from Menu" once the entry exists. Option B: an offer on the first start of a form that has no entry, as a toast that does not block, with nothing in the menus afterwards. Option C: both — the offer once, and the row always. Why it matters: a user who never opens the Help menu never learns that the application can install itself, and a user who dismisses a toast must be able to find it again. Cost of C: two ways in, both tested, and a first-start decision remembered in the settings. Recommendation: C.
- **2. What `Exec` names, per form.** Option A: the running form's launch command from `config/packaging.py` — the AppImage's own path, or `snapmockit` for an installation from the index. Option B: always an absolute path, the AppImage's file or the full path of the installed command, so the entry works whatever the desktop's `PATH` is. Why it matters: a desktop session's `PATH` often lacks `~/.local/bin`, and an entry whose `Exec` cannot be found fails with no message. Cost of B: the entry names a path that a later pipx upgrade could move. Recommendation: B, with `%F` kept so a project file opens by a double-click.
- **3. The AppImage's own file.** Option A: the entry points at the file where it sits, in Downloads or wherever the user left it; if the file is moved or deleted, the menu entry breaks. Option B: the file is copied to `~/Applications/Snapmockit.AppImage` and the entry points there, which is what Doug did by hand and what the README says, at the cost of a second 128 MB copy. Option C: ask the user which, at the moment they add it. Why it matters: it decides whether the menu entry survives a tidy-up of the Downloads folder. Recommendation: C, since the copy is large enough that it should not happen silently, with option B's path as the offered default.
- **4. Whether the MIME type is installed too.** Option A: the entry alone, so Snapmockit is in the menu and opens from it. Option B: the entry, plus `io.github.dbower44022.snapmockit.xml` into `~/.local/share/mime` with `update-mime-database` run when it exists, so a double-click on a `.smk` project opens it. Why it matters: a project file that opens by a double-click is the difference between a menu entry and an installed application. Cost of B: a second thing to write and remove, a second tool that may be missing, and a file association that a user did not explicitly ask for. Recommendation: B, named plainly in the action's message.

Everything else follows the PRDs. Where they are silent or disagree, decide, note it under the notes' decisions section and the PRD rows, and continue. Silences known now:

- The identifiers stay as they are: `io.github.dbower44022.snapmockit` for the entry, the icon, and the AppStream metainfo.
- The icon sizes are those the AppImage recipe already renders, plus the scalable SVG.
- Nothing is written outside `$XDG_DATA_HOME`, nothing needs a password, and no system directory is touched.
- The Flatpak form installs nothing: its entry is part of the package.
- A checkout installs nothing by default; a developer who wants it can still use the action if decision 2's command can be written.
- `update-desktop-database` and `update-mime-database` are run when they are on the path and skipped, without an error, when they are not.
- Windows and macOS are out of scope: neither has a package yet, and their menu integration belongs to those packages.

## Standards that apply

- Terminology Precision, Writing Register, and Reply Format from the global guidance apply to every reply and to the documents.
- Every new top-level directory or module gets a row in Technical Architecture PRD Section 10 in the commit that creates it.
- Departures from any product requirements document are recorded in that document's revision-control table with a version bump, not only in code comments. **Check the table for a duplicate version number before bumping**, and keep the header's "Document version" and "Last Updated" in step with the table.
- No control is disabled (General UI PRD 1.3).
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy snapmock`, and `uv run pytest` must pass before each commit, with `QT_QPA_PLATFORM` set to `offscreen` for pytest.
- Installing software on Doug's machine is asked of him first. **Anything that leaves this machine in Doug's name, whether an upload, a tag, or a release, is asked of him at the moment it happens, not once at the start.**
- Writing into Doug's `~/.local/share` from a test is not allowed: every test writes to a temporary home.
- Document timestamps are read from the machine clock at the time of writing, never estimated.
- Commit messages end with the attribution block the session provides.

## When the work is complete

Update the phase table in `docs/Menu-Entry-Implementation.md`, bump its revision, add a change-log row, and state the next required step. Say what of end-to-end pass finding 1 remains, and what a user of each form now does to put Snapmockit in the menu.

**The display checks this work will owe**, none of which a headless test can settle: the action run from an installation from the index and from the AppImage; the entry in the main menu with its icon; the application started from that entry; a `.smk` file opened by a double-click if decision 4 takes it; and the removal leaving no entry and no icon behind.

---

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 09-21-26 10:21 | Claude (Claude Code) | **Done.** The work was carried out on 09-20-26 and closed; the menu entry is released as v1.3.0. Its notes are `docs/Menu-Entry-Implementation.md` (revision 1.7), which record five corrections to this prompt: its starting state said Snapmockit 1.2.0 was installed here with pipx, which it was not; its reasoning for decision 2 said a desktop session's `PATH` often lacks `~/.local/bin`, which this machine's does carry, so the failure mode and not its frequency is the reason option B stands; Phase 3's run could not go on the released AppImage or the published index form, since neither carried the action, so it went on builds of the commit by Doug's choice of option C and the released files are checked after v1.3.0; the first-start offer cannot follow the storage migration's message, since both use the one toast, so the window defers it to the next start; and an eighth silence was needed, the desktop entry and the shared-mime-info file moving into `snapmock/resources/desktop/` so every installed form carries them. |
| 1.0 | 09-20-26 14:05 | Claude (Claude Code) | Initial kickoff prompt, written when Doug chose the menu entry as the next step after the Python Package Index closed on 09-19-26. Starting state verified on 09-20-26: the AppImage and the index's form install no entry or icon; the Flatpak installs its own; the entry template, the icon rendering, and `desktop_entry_installed` already exist. Three phases and a close-out; four decisions, presented one at a time; seven silences. |
