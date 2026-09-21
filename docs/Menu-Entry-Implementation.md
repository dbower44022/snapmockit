# The Menu Entry — Implementation Notes

Last Updated: 09-20-26 23:14 · Revision 1.5

Snapmockit put into the desktop's main menu from inside the application, and taken out again, so that a user who downloaded the AppImage or installed from the Python Package Index reaches the application the way every other application is reached. This is end-to-end pass finding 1 (`docs/End-to-End-Pass.md`, Section 5.1) and step 2 of what is left on the release-engineering list (`docs/Release-Engineering.md`, Section 4). The kickoff prompt is `docs/Menu-Entry-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The decisions, the module that writes and removes the entry, what the entry says per form, the tests | Done 09-20-26 (Sections 2 and 5); Technical Architecture PRD 1.69 | 8c22e71, this commit |
| 2 | The Help menu row, the offer on the first start, what the user is told, the tests through the window | Done 09-20-26 (Section 6); General UI PRD 2.53 | this commit |
| 3 | Doug's run on his display, and what it finds | Under way 09-20-26 (Sections 7 and 7.1): sections 1 and 2 to step 12 passed; step 13 met the fault fixed in a17fd41 and both files were rebuilt | this commit |
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

## 5. Phase 1: the module (09-20-26)

**`snapmock/config/desktop_entry.py`** (Technical Architecture PRD 1.69, Section 10), beside `packaging.py`, which tells it which form is running, and `migration.py`, which is the other module that writes outside the application's own storage. It knows nothing of widgets or settings: the caller decides, this writes.

**What an install writes**, all of it under `$XDG_DATA_HOME` (default `~/.local/share`) and nowhere else, never as root:

- `applications/io.github.dbower44022.snapmockit.desktop`, the packaged entry with its `Exec` line replaced and `%F` kept. Every other field — the name, the comment, the categories, the keywords, the icon, the window class, the MIME type — is the packaged file's, so a user's entry cannot drift from a package's.
- `icons/hicolor/<size>x<size>/apps/io.github.dbower44022.snapmockit.png` at 16, 24, 32, 48, 64, 128, 256, and 512 pixels, rendered from `resources/icons/snapmockit.svg` through Qt's own SVG renderer into a `QImage` — not a `QPixmap`, so it needs no display and no application object — plus that SVG at `icons/hicolor/scalable/apps/`.
- `mime/packages/io.github.dbower44022.snapmockit.xml` (decision 4).

**The `Exec` line** (decision 2) is an absolute path in every form: the AppImage's own file resolved from the `APPIMAGE` variable, or the installed command found beside the running interpreter or on the path, or, where no command is installed at all, the interpreter's own path with `-m snapmock`, which exists whatever the path holds. **A correction made in the building:** the quoting is the desktop entry specification's, not the shell's. `shlex.quote` wraps a path containing a space in single quotes, which a desktop entry does not read as quoting at all; the specification encloses such an argument in double quotes and escapes a double quote, a backslash, a dollar sign, or a backtick with a backslash, which the entry file format then escapes a second time. `quote_exec` does that and a test holds both a path with a space and a path with a dollar sign.

**What it reports.** `Outcome` carries what was written or deleted and a note for each thing that did not happen, each note a sentence a user can read. An install whose entry cannot be written returns an outcome that says so; nothing raises, so a menu action never ends in a traceback. A read-only `mime` directory still installs the entry and the icons and says the file association was not made.

**The two database tools** are run where they are on the path and, where they are not, produce a note that the desktop reads the change at next login (silence 6). Neither absence is a failure.

**Removal** deletes exactly the files an install writes and nothing else: no directory is pruned, and the AppImage's copy at `~/Applications` is not touched, since decision 3 offers it separately. The Flatpak form writes nothing and removes nothing, and `unsupported_reason` gives the sentence the Help menu row shows instead of greying out (General UI PRD 1.3).

**The copy** (decision 3) is `copy_appimage`, which writes through a `.part` file and replaces the destination, sets the executable bit, and refuses a destination that exists and is not a type 2 AppImage, so nothing of the user's is overwritten.

**The move of silence 8.** `io.github.dbower44022.snapmockit.desktop` and `io.github.dbower44022.snapmockit.xml` moved from `packaging/appimage/` to `snapmock/resources/desktop/`. The AppImage recipe now reads both from there and takes its icon sizes from the module, so the sizes have one source; the Flatpak recipe reads them through the AppImage recipe and needed no change; the AppStream metainfo stays in `packaging/appimage/`, since only a build reads it. `tests/test_packaging_appimage.py` and `tests/test_packaging_flatpak.py` follow the files.

**Tests:** `tests/test_desktop_entry.py`, 24 cases, every one of them writing to a temporary home. The entry written for each form with the right `Exec` (the AppImage's file, the command beside the interpreter, a path with a space quoted, the interpreter's module line); the packaged fields kept; each icon written at its own size and the scalable file copied byte for byte; the entry read back by `app.desktop_entry_installed`, which is what gives Qt the desktop id at start; a second install over the first leaving one entry with the new `Exec`; removal leaving nothing behind and a removal with nothing installed saying so; a read-only applications directory reported and not raised, and a read-only `mime` directory still installing the entry; the Flatpak form refusing to write or remove at all; a missing database tool as a note rather than a failure, and both tools run with the right argument where they exist; and the copy's overwrite, its executable bit, and its refusal of a destination that is not an AppImage.

**Not proven here:** anything that needs a display or a real installation. The action itself is Phase 2 and the display run is Phase 3.

**The next required step** is Phase 2, step 1: the Help menu row, with its label following the entry's state and a sentence for the form that needs nothing.

## 6. Phase 2: the application (09-20-26)

**The Help menu row** sits between Report a Bug and the separator, so Check for Updates and About keep their group (General UI PRD 2.53, 3.8). It reads "Add to Menu", or "Remove from Menu" once our own entry is in place. **The label is read each time the Help menu opens**, through `aboutToShow`, not once at construction: another installed form can put an entry there while the window is open, and a window left running across an install would otherwise offer to add what is already added.

**A form that needs nothing says so.** The Flatpak's row is present and does nothing when used except explain that this installation is already in the menu because its entry is part of the package. No row is greyed out and none is absent, so the Help menu has the same shape in every form (General UI PRD 1.3).

**What the user is told after adding** is one message: what was written, then each thing that could not be written, then — **this is Phase 2 step 3** — the sentence finding 1 earned. Finding 1 saw the entry appear in the menu at once and its icon only after the desktop shell was restarted, because the running desktop had not rescanned its icon directories. The message therefore ends: "If the icon is missing, the desktop has not rescanned its icon folders yet: it appears after the desktop shell restarts or at your next login." It is added only when something was actually written, so a failed install does not offer an explanation for an icon that was never made.

**The AppImage's question** (decision 3) is asked once, before anything is written, and only when the running file is not already at the fixed name: a short choice, "Copy and Add" as the default, "Add Without Copying", and Cancel, with the destination and the running file's size in the sentence. A copy that fails is reported and nothing is written. On removal the copy is named and deleted only if the user says so, and the file the session is running from is never offered for deletion.

**The offer on the first start** is the toast the Welcome panel's own route already uses, with "Add to Menu" on it (General UI PRD 1.3). It is made once, remembered in `general/desktopEntryOfferShown`, and only where the form has no entry and needs one, so a user who removes a Flatpak and keeps an AppImage is offered it then.

**One thing built differently from the plan.** The kickoff has the offer shown after the storage migration's message. Both use the one toast, so the second would replace the first and the user would lose the message that was owed them. `MainWindow` now records that a startup message has been shown and declines the offer for that start; the entry point calls `offer_desktop_entry_once` unconditionally and the window decides. The decision lives in the window, where a test can reach it, rather than in the entry point's control flow, where it could only be asserted by reading the source.

**One correction, found while writing Phase 3's checklist.** The offer to delete the AppImage's copy fired for every form, so an installation from the index whose user happened to keep a file at `~/Applications/Snapmockit.AppImage` would have been offered its deletion on removal — a file this action never wrote. The offer is now the AppImage's alone. The running file is still never offered for deletion, since deleting a mounted AppImage takes the running application's own files away; it is named as left in place instead, with the sentence that says so. Two tests cover the two paths.

**Tests:** `tests/test_menu_entry_action.py`, 20 cases through the window on the offscreen platform with the writing module stubbed, so nothing here writes an entry or reads the developer's own data directory. The row's place in the menu and its label following the entry's state; the form that needs nothing explaining itself and writing nothing; adding, with the rescan sentence, and a failed add without it; removing; the AppImage's three answers and its failed copy; an AppImage already at the fixed name asked nothing; the copy offered on removal, kept on no, deleted on yes, and never offered for the running file; the offer made once, with its action, declined where an entry exists or the form needs nothing, and deferred by a start that owes a message; and the copy never offered under another form. `tests/test_menus.py`'s Help menu row reads the new label as either of its two texts, so it does not depend on whether the machine running the suite has the entry.

**The next required step** is Phase 3: Doug's run on his display, written as a checklist page with the `instruction-discipline` skill.

## 7. Phase 3: the display run (09-20-26)

**Decision, taken by Doug at 16:00: option C.** The kickoff has Phase 3 run "from a 1.2.0 installation from the index and from the released AppImage". Neither carries the action: v1.2.0 was released on 09-19-26 and this code was written on 09-20-26, so the published AppImage and the `snapmockit` on pypi.org both have a Help menu with no row to test. The three options put to Doug were local builds now (A), a release first so the published files are what is checked (B), and both in order (C). He took C: the display run now, on builds of this commit, and the released AppImage and the released index form checked at the next release, which the close-out names as the step that follows.

**The two builds, made here at 16:08 from the commit after 4eb25b1.** `dist/Snapmockit-1.2.0-x86_64.AppImage`, 128,330,232 bytes, SHA-256 beginning `22fd1763602e7ff4`, which answers `Snapmockit 1.2.0` to `--version`; and `dist/snapmockit-1.2.0-py3-none-any.whl`, 770,399 bytes, which Doug installs with pipx as the first section of the run. Both report version 1.2.0, the version in `snapmock/__init__.py`, although they are ahead of the release of that number.

**What this machine looked like before the run**, read rather than assumed, because three of its facts change what the run proves:

- **There is no desktop entry of ours.** `~/.local/share/applications/` holds no `io.github.dbower44022.snapmockit.desktop`: the one Doug wrote by hand for finding 1 is gone.
- **Two icon files from finding 1 remain**, the 256 pixel PNG and the scalable SVG, which an install overwrites and a removal deletes. That is the right end state, but it means the removal takes away two files that predate this work.
- **The Flatpak is installed** and exports its own entry and MIME file through `~/.local/share/flatpak/exports/share`, which the session's `XDG_DATA_DIRS` carries. So a Snapmockit already sits in the main menu, and `xdg-mime` already answers this desktop id for a `.smk` file, before anything in this run writes a thing. `$XDG_DATA_HOME` is searched before `$XDG_DATA_DIRS`, so an entry this action writes takes the menu over while it is installed and the Flatpak's returns when it is removed — which the run checks at section 2, step 15.

**The discriminator the run uses.** With the Flatpak installed, "Snapmockit is in the menu" cannot tell one form from another. The Help menu row does: in the Flatpak it reads "Add to Menu" and refuses with its sentence, and in every other form with an entry in place it reads "Remove from Menu". The run reads that row after each start from the menu, which also gives the Flatpak's own row its only display check.

**The checklist page:** https://claude.ai/artifact/Cp2idwFN6PcUmTdoEqswdT — thirty-five steps in five sections, written with the `instruction-discipline` skill, each with the place, the exact thing to type or click, what should be seen, and what to do when it is not. Its ticks and notes are kept in the page's own store, collection `menuentry1`, so the run can be stopped and returned to and the marks read back here. **The run is Doug's; nothing of Phase 3 is done until it has been made.**

**What the run covers:** the row's label in each form; the entry's `Exec` naming an absolute path, checked for the index's form and for both of the AppImage's answers; the nine icon files; the entry in the main menu and its icon, with finding 1's rescan behaviour allowed for and noted rather than failing the step; a start from the menu; a `.smk` opened by a double-click; the removal leaving neither entry nor icon; the Flatpak's entry surviving the removal; the AppImage's copy question with both answers; the copy left in place when it is the running file, and deleted on request when it is not; and the Flatpak's row explaining itself and writing nothing.

**The next required step** is Doug's run, and then what it finds, fixed with tests.

### 7.1 The run, 09-20-26 21:10 to 22:15, and the rebuild it forced

**Sections 1 and 2 up to step 12 passed.** The wheel installed with pipx, the command answered `Snapmockit 1.2.0`, the Help menu's row read "Add to Menu", the action wrote the entry and reported it, the row then read "Remove from Menu", the entry's `Exec` and the nine icon files were as this document says, the entry reached the main menu, the application started from it, its row read "Remove from Menu" — which is what tells the form apart from the Flatpak — and a `.smk` project opened on a double-click.

**Step 13 showed a second box**, Doug's words: "The copy at /home/doug/Applications/Snapmockit.AppImage (128 MB) is left in place. Delete it as well". **This is not a new finding.** It is exactly the fault Section 6 records as found while writing this checklist and fixed in `a17fd41`: the offer to delete the copy fired under every form, so an installation from the index was offered a file it never wrote. The builds Doug installed were made at 16:08 and the fix was committed at 16:14, six minutes later; the installed `main_window.py` under `~/.local/share/pipx/venvs/snapmockit/` was read here and carries the old handler, which settles it. **The run found the defect independently, on the display, which is what the display run is for; the fix it confirms was already written and tested.**

**Both files were rebuilt from `a17fd41` at 22:18**, to the same paths: `dist/Snapmockit-1.2.0-x86_64.AppImage`, 128,330,232 bytes, SHA-256 beginning **`c3506c18594d1efc`**, and `dist/snapmockit-1.2.0-py3-none-any.whl`, 770,605 bytes, whose `main_window.py` was read out of the archive here to confirm the fix is in it. The AppImage was rebuilt too, since Section 3 of the run reads the other side of the same handler: under the old build, removing while running the copy showed no second box at all, where the fixed one names the file as left in place.

**The checklist page gains Section 2B** (version 2 of the page): uninstall, check the new fingerprint, reinstall, confirm the copy at `~/Applications` survived, add to the menu again, and run the removal again — which must now show one box and nothing about the copy. Steps 14 and 15 of section 2, which Doug had not reached, moved into it, so the run stays linear. Everything ticked above section 2B still stands: nothing but that one handler changed between the two builds.

**Finding 1 of the run, 09-20-26 23:00: two menu entries.** Doug: "Do you realize there are two icons in the start menu one labled snapmockit and the second snapmockit(Flatpak)?" Read here rather than guessed: two files of the one identifier exist, ours at `~/.local/share/applications/` and the Flatpak's export at `~/.local/share/flatpak/exports/share/applications/`, which the desktop entry specification makes one entry and a conformant menu shows once. Cinnamon lists them separately and marks the Flatpak's. **Decision of 09-20-26, option A:** the action goes on writing the entry and names what it found — "A Flatpak installation of Snapmockit also has a menu entry, so your desktop may list Snapmockit twice." Option B, refusing where another form already has an entry, was rejected: it takes the feature away from the AppImage and the index's form, which are the two this work exists for, on any machine that happens to carry a Flatpak. Changing the identifier was ruled out, since the window class, the portal registration, and the file association all hang on it. `other_entries` searches `$XDG_DATA_DIRS` and both Flatpak export directories whether or not the environment names them, because a process started from a terminal can carry a path from before the Flatpak was installed. Four tests. General UI PRD 2.54, and the README's claim that the desktop shows one entry is corrected in the same commit.

**A note on how the run was conducted.** Part-way through, the session asked Doug to remember which window he had clicked a button in, to tell two readings of the machine's state apart. That was the session's work, not his: the question was settled in one command by running the installed package's own `running_appimage()`, which answers `None` for the index's form and so cannot reach the offer at all. A display run asks the user what the display shows, and reads everything else itself.

**Also found:** starting the application from the desktop's menu after a removal starts the Flatpak, whose 1.1.0 build has no such row, which read as a missing feature until the running processes were listed. The checklist's start steps now say to use the terminal and name the Flatpak as what the menu holds.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.5 | 09-20-26 23:14 | Claude (Claude Code) | The run's first finding (Section 7.1): a machine with the Flatpak installed shows two menu entries, since Cinnamon lists the Flatpak's export beside the user's own file of the same identifier. Option A taken: the action writes the entry and names what it found, with the README's one-entry claim corrected and four tests. General UI PRD 2.54. Also recorded: the session wrongly asked Doug to reconstruct state it could read itself, and the checklist's start steps now name the terminal, since the menu starts the Flatpak after a removal. |
| 1.4 | 09-20-26 22:20 | Claude (Claude Code) | Doug's run of 09-20-26 21:10 to 22:15 recorded (Section 7.1): sections 1 and 2 to step 12 passed on the display; step 13 showed the copy-deletion box under the index's form, which is the fault already fixed in a17fd41 six minutes after the build he had installed, confirmed by reading the installed module. Both files rebuilt from a17fd41 at 22:18, SHA-256 beginning c3506c18594d1efc, the fix read back out of the wheel; the checklist page gains section 2B for the reinstall and the removal again. |
| 1.3 | 09-20-26 16:13 | Claude (Claude Code) | Phase 3's checklist written (Section 7) and one Phase 2 correction (Section 6). Doug took option C on 09-20-26 at 16:00: the display run on local builds of this commit now, since neither the released v1.2.0 AppImage nor the published index form carries the action, and the released files checked at the next release. The two builds, the machine's starting state (no entry of ours, two icon files left from finding 1, the Flatpak installed and exporting its own entry), and the discriminator the run uses. The correction: the offer to delete the AppImage's copy is the AppImage's alone, and the running file is named as left in place rather than offered. |
| 1.2 | 09-20-26 15:49 | Claude (Claude Code) | Phase 2 done (Section 6): the Help menu row with its label read each time the menu opens, the sentence about the desktop's icon rescan that finding 1 earned, the AppImage's copy question and the offer to delete the copy on removal, and the first-start offer remembered in `general/desktopEntryOfferShown`. Built differently from the kickoff in one place: the window, not the entry point, declines the offer on a start that already owes a message, since both use the one toast. 19 tests through the window with the writing module stubbed. General UI PRD 2.53. |
| 1.1 | 09-20-26 15:14 | Claude (Claude Code) | Phase 1 done (Section 5): `config/desktop_entry.py` writes and removes the entry, the eight-size icon set and the scalable file, and the `.smk` MIME type, all under `$XDG_DATA_HOME`; the `Exec` is an absolute path quoted by the desktop entry specification's rules, a correction made in the building, since `shlex.quote`'s single quotes are not quoting to a desktop entry; the entry and the MIME file moved into `snapmock/resources/desktop/` under silence 8, with both recipes and their tests following them; 24 tests, every one against a temporary home. Technical Architecture PRD 1.69. |
| 1.0 | 09-20-26 15:08 | Claude (Claude Code) | Initial notes: the four decisions taken on 09-20-26, each as recommended (1 C, 2 B, 3 C, 4 B); the kickoff's seven silences and an eighth decided here (the desktop entry and the MIME file move into the package's resources, so every form carries them); the starting state verified here, which found two of the kickoff prompt's statements wrong (no installation from the index on this machine; this desktop session's `PATH` does carry `~/.local/bin`). |
