# The Menu Entry — Implementation Notes

Last Updated: 09-20-26 15:08 · Revision 1.0

Snapmockit put into the desktop's main menu from inside the application, and taken out again, so that a user who downloaded the AppImage or installed from the Python Package Index reaches the application the way every other application is reached. This is end-to-end pass finding 1 (`docs/End-to-End-Pass.md`, Section 5.1) and step 2 of what is left on the release-engineering list (`docs/Release-Engineering.md`, Section 4). The kickoff prompt is `docs/Menu-Entry-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The decisions, the module that writes and removes the entry, what the entry says per form, the tests | Decisions taken 09-20-26 (Section 2); the module owed | this commit |
| 2 | The Help menu row, the offer on the first start, what the user is told, the tests through the window | Not started | |
| 3 | Doug's run on his display, and what it finds | Not started | |
| Close-out | The README, the release-engineering notes, the product requirements document rows, the next required step | Not started | |

## 2. Decisions

All four were presented with the consequential decision template on 09-20-26, one at a time, and each was taken as recommended. Two of them were presented with a correction to the kickoff prompt's stated reasoning, recorded under each.

### 2.1 How the user reaches it: option C, both the Help menu row and the offer on the first start

Presented at 14:17, taken by 14:43. The Help menu gains a row after Report a Bug and before the separator, which reads "Add to Menu" and becomes "Remove from Menu" once the entry exists; and the first start of a form that has no entry shows the offer once, as a message that does not block, with the action on it.

**Why C and not A or B:** the discoverability failure that finding 1 actually recorded is not answered by a message a user may never read, and the removal needs a permanent home that a first-start offer cannot give it. **The cost:** two ways in, both tested; a settings key, `desktopEntryOfferShown`, so the offer is made once and not at every start; and a Help menu row that must say something useful on a form that needs nothing, since no control is disabled (General UI PRD 1.3).

**Follow-on detail, settled with the decision:** the row sits directly after Report a Bug, so Check for Updates and About keep their group; the offer is shown after the storage migration's message, never in the same breath as it; on the Flatpak the row reads "Add to Menu" and, when clicked, says that this installation is already in the menu.

### 2.2 What `Exec` names, per form: option B, always an absolute path

Presented at 14:43, taken by 14:44. The entry's `Exec` is a file path in every case — the AppImage's own file, or the full path of the installed command — and never the bare console name. `%F` is kept, so a project file opens by a double-click.

**A correction to the kickoff prompt's reasoning.** The prompt gives as option B's reason that "a desktop session's `PATH` often lacks `~/.local/bin`". **Verified on this machine on 09-20-26: it does not** — the running desktop session's `PATH` carries `/home/doug/.local/bin` at both its front and its end. The reason that stands is the failure mode, not its frequency: an `Exec` the desktop cannot resolve fails with no window and no message, while a session environment is set by the login manager and not by the shell's startup files, so no single machine's reading is a guarantee about anyone else's.

**The cost:** the entry records a path only the installing tool controls, so a later `pipx reinstall` or a move from pipx to `uv tool` can leave it pointing at nothing; the user's repair is to run the action again. **Follow-on detail:** the path is shell-quoted as `launch_command` already quotes it, a path containing a space is tested, and the writing module takes the resolved path from `config/packaging.py` rather than growing its own copy of the form logic.

### 2.3 The AppImage's own file: option C, ask, with the copy as the default

Presented at 14:44, taken by 15:06. On the AppImage alone, the action asks whether to copy the running file to `~/Applications/Snapmockit.AppImage` and point the entry there, or to point the entry at the file where it sits. The copy is the offered default and its size is named in the question.

**The evidence on this machine:** `~/Applications/Snapmockit.AppImage` exists, 128,293,368 bytes, dated 09-17-26 — the copy Doug made by hand for v1.0.0 — and `~/Downloads` holds no Snapmockit AppImage at all. Had the entry pointed at the download, the menu entry would already be dead three days later.

**The cost:** a question in front of an action the user expected to just happen, which is the one modal moment in this work and so must be a short choice with a default rather than a dialog with prose (General UI PRD 1.3 asks for a non-modal workflow wherever possible); and a removal that has to know which of the two was done.

**Follow-on detail, settled with the decision:** the question names the destination and the size in one sentence; a destination that exists and is not a Snapmockit AppImage is refused with a message; a destination that already holds one is overwritten, which is how a user upgrades; removal deletes the entry and the icons always and offers to delete the copy separately, so no 122 MB file disappears without being named; and a session already running from `~/Applications/Snapmockit.AppImage` is asked nothing and copies nothing, since the file is already at the fixed name.

### 2.4 Whether the MIME type is installed too: option B, the entry, the icons, and the MIME type

Presented at 15:06, taken by 15:08. The action also writes `io.github.dbower44022.snapmockit.xml` into `$XDG_DATA_HOME/mime/packages/` and runs `update-mime-database` when it is on the path, so a `.smk` project carries the application's icon in the file manager and opens on a double-click. What the action reports afterwards names the file association plainly.

**Why B:** `%F` on the `Exec` line and `MainWindow.open_paths` behind it already exist and are already tested; without the MIME type they are reachable only from a command line, and the work of AppImage silence 2 — which added command-line file opening so that a double-click would work — stops one step short of what it was for.

**The cost:** a second thing to write and to remove correctly; a second external tool that may be missing, which is skipped without an error; and a file association the user did not explicitly ask for. **The trap on Doug's machine, verified 09-20-26:** the Flatpak already exports the same MIME file into `~/.local/share/flatpak/exports/share/mime/packages/`, so `xdg-mime query filetype` on a `.smk` file already answers `application/x-snapmockit-project` and its default application is already this desktop entry. Installing the user's own copy gives one type two sources, which agree; removal must delete only the file it wrote, so the Flatpak's association survives it.

**Follow-on detail:** `update-mime-database` and `update-desktop-database` are each run when present and skipped silently when not, with the skip named in what the action reports; the tests run against a temporary home with both tools stubbed, since neither is guaranteed on a continuous-integration runner.

## 3. Silences decided

The kickoff's seven, each taken as the kickoff states:

1. The identifiers stay as they are: `io.github.dbower44022.snapmockit` for the desktop entry, the icon, and the AppStream metainfo.
2. The icon sizes are those the AppImage recipe already renders — 16, 24, 32, 48, 64, 128, 256, and 512 pixels — plus the scalable SVG.
3. Nothing is written outside `$XDG_DATA_HOME` (default `~/.local/share`), nothing needs a password, and no system directory is touched.
4. The Flatpak form installs nothing: its entry is part of the package.
5. A checkout installs nothing by default; a developer who wants it can still use the action where decision 2.2's path can be written.
6. `update-desktop-database` and `update-mime-database` are run when they are on the path and skipped, without an error, when they are not.
7. Windows and macOS are out of scope: neither has a package yet, and their menu integration belongs to those packages.

One more, found in the reading and decided here:

8. **Where the desktop entry and the MIME file live at run time.** Both are in `packaging/appimage/` today, which the wheel does not carry, so an installation from the Python Package Index has neither file to copy. They move to `snapmock/resources/desktop/`, which every form carries, and the AppImage and Flatpak recipes read them from there; the AppStream metainfo stays in `packaging/appimage/`, since only a build reads it. The run-time module substitutes the `Exec` line of decision 2.2 into the entry and writes the MIME file unchanged, so one file is the source for every form and the entry a user installs cannot drift from the entry a package installs. Technical Architecture PRD Section 10 gains the rows in the commit that moves them. The alternative, carrying the entry's fields in code with a test asserting they match the packaged file, was rejected: it is drift prevented by a test rather than drift made impossible.

## 4. Starting state, verified 09-20-26

Read and run here before anything was written, and two of the kickoff prompt's statements were found wrong:

- **Snapmockit is not installed on this machine from the Python Package Index.** The kickoff prompt says v1.2.0 is installed with pipx at `~/.local/bin/snapmockit`; there is no such file, `command -v snapmockit` finds nothing, and pipx lists only `evernote-backup`. It was removed again on Doug's word after the index work closed (`docs/Packaging-PyPI-Implementation.md`, revision 1.7, records the removal, which the kickoff prompt was written without). Nothing in Phase 1 or Phase 2 needs it; Phase 3's display run does, so an installation is made then, on Doug's word.
- **This desktop session's `PATH` carries `~/.local/bin`**, contrary to the prompt's reasoning for decision 2 (recorded in 2.2 above).
- The Flatpak is installed here and its exports already claim the `.smk` MIME type (recorded in 2.4 above).
- `update-mime-database`, `update-desktop-database`, and `xdg-mime` are all present at `/usr/bin`.
- `~/Applications/Snapmockit.AppImage` is the v1.0.0 copy of 09-17-26, 128,293,368 bytes; `~/Downloads` holds no Snapmockit AppImage.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-20-26 15:08 | Claude (Claude Code) | Initial notes: the four decisions taken on 09-20-26, each as recommended (1 C, 2 B, 3 C, 4 B); the kickoff's seven silences and an eighth decided here (the desktop entry and the MIME file move into the package's resources, so every form carries them); the starting state verified here, which found two of the kickoff prompt's statements wrong (no installation from the index on this machine; this desktop session's `PATH` does carry `~/.local/bin`). |
