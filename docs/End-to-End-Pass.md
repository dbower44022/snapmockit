# The End-to-End Pass on Real Work, and the 1.0.0 Release — Notes

Last Updated: 09-15-26 21:56 · Revision 1.4

Implements step 4 of the release-engineering list (`docs/Release-Engineering.md`, Section 1): the released AppImage, `Snapmockit-0.9.0-x86_64.AppImage`, used by Doug for his real screenshot work over several sittings, every finding recorded and classified, every defect fixed with a test, and then the first release the product stands behind, `1.0.0`. The kickoff prompt is `docs/End-to-End-Pass-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL. The record takes the shape of the General UI acceptance pass (`docs/General-UI-Implementation.md`, Section 16) where it fits: one row per finding, Doug's words quoted, the evidence named.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The four decisions, this document, and the Wayland check (checklist section 7) | In progress from 09-15-26 09:47: decisions taken, this document written; the Wayland check owed to Doug's next log-out | this commit |
| 2 | The sittings: Doug's real work on the 0.9.0 AppImage, each finding recorded, triaged, and fixed | Not started | |
| 3 | The release: version 1.0.0, the tag, the release job, the smoke test, Check for Updates from 0.9.0, the README | Not started; blocked on decision 1's exit criterion and, under decision 3, on the Wayland check | |
| Close-out | The PRD rows, the release-engineering notes, what remains of packaging and the platform backends, the next required step | Not started | |

## 2. Decisions

All four were presented with the consequential decision template on 09-15-26 at 09:47 and approved by Doug as recommended ("use all of your recommendations").

### 2.1 What ends the pass: option A, findings-bound, with C available

The pass ends after the first sitting in which Doug finds nothing new and every earlier finding is closed, with at least three sittings on at least three distinct pieces of real work. "Closed" means fixed and seen on the display in a later sitting, or reclassified by Doug as a departure or a follow-up. "Distinct pieces of work" means different documents or tasks, not repetitions of one. Doug may call the pass ended at any point (option C); when he does, the close-out records it as his call. The cost: the pass runs a sitting longer for every sitting that finds something. The alternatives were a fixed number of days regardless of what is open (B) and Doug's call alone (C).

### 2.2 Where findings live: option B, GitHub issues for the defects

The findings table in Section 5 is the one complete record. Each finding classified as a defect also becomes one issue on `github.com/dbower44022/snapmockit`, opened at triage, titled in Doug's words from the table, carrying the finding number in its body, and closed by the fix commit's message; the table's row points at the issue. Departures and follow-ups stay in the table only. A defect Doug reclassifies as a follow-up keeps its issue open with a `later` label. The cost: two places to keep in step for every defect, and the defects of a pre-1.0.0 product on public view. The alternatives were the table alone (A) and issues for everything (C).

### 2.3 Whether the Wayland check gates 1.0.0: option A, yes

The AppImage's capture through the desktop portal, section 7 of the checklist page `Snapmockit AppImage Display Checks`, must be seen once on this machine's Cinnamon on Wayland session before `v1.0.0` is tagged. Phase 2 proceeds without it. The marks are read back from the page and recorded in `docs/Packaging-AppImage-Implementation.md` (a new Section 8.4) and in Section 7 of this document. If the check fails, the failure is a defect of this pass and the check is rerun after the fix. The cost: one log-out Doug has not been able to make yet. The alternative was to ship on the X11 proof alone (B).

### 2.4 What 1.0.0 ships: option A, the Linux AppImage alone

As 0.9.0 did. The release notes name what changed since 0.9.0 in the user's words and say that the Windows and macOS packages do not exist yet. The wheel on PyPI (B) is the first packaging step after 1.0.0; the Flatpak (C) follows it. The cost: Linux users without AppImage tooling wait for the next packaging step.

## 3. Silences decided

The kickoff's seven, each taken as the kickoff states:

1. A sitting is one continuous stretch of Doug's real work with the AppImage, however long; the session sets neither its length nor its content.
2. The findings table's columns are those of Section 5.
3. A defect in a capture backend this machine cannot exercise (Windows, macOS) is a follow-up, not a defect of this pass.
4. Where a product requirements document's wording and Doug's expectation differ and Doug's is the better one, the finding is a departure recorded in that document, not a defect.
5. Fix commits carry no version change; the version moves once, at Phase 3.
6. The 0.9.0 AppImage stays at `dist/Snapmockit-0.9.0-x86_64.AppImage` through the work; a fix under test runs from source or from a locally built AppImage, and Doug's sittings use the released 0.9.0 until 1.0.0 exists.
7. The 1.0.0 release notes name what changed since 0.9.0 for a user and say that the Windows and macOS packages do not exist yet.

Two more, found at the start:

8. The change log of `docs/Packaging-AppImage-Implementation.md` had stopped at revision 1.2 while its header read 2.0; no commit had written the rows for 1.3 to 2.0. The rows were back-filled from the commits that made each revision, as revision 2.1, in this phase's first commit. Doug approved the back-fill with the decisions.
9. The checklist page's section 7 was written for the 0.1.0 build. It is repointed at the released 0.9.0 file before Doug runs it, so the Wayland proof is of the release.

## 4. Starting state, re-verified 09-15-26 09:47

Verified by running the code and the repository on this machine (Intel i7-11700K, Linux, Cinnamon on X11, Python 3.12.3, uv), not by reading it:

- The repository head is 8c0ac91, two commits after the kickoff's 6577c65 (the brush-editing retest note and the kickoff prompt itself); the working tree is clean; the CI run of 8c0ac91 (34933591806) passed in 4 minutes 15 seconds.
- `v0.9.0` is the latest release: published 2026-09-15 04:43 UTC, `prerelease=false`, one asset, `Snapmockit-0.9.0-x86_64.AppImage`, 128,272,888 bytes; `releases/latest` answers with it. The copy at `dist/Snapmockit-0.9.0-x86_64.AppImage` has the same size and its SHA-256 begins `ebe7c8e0f0b7427c`. The 0.1.0 build of 09-14-26 23:34 sits beside it.
- `snapmock/__init__.py` reads 0.9.0; `APP_BUILD_DATE` reads 2026-09-15.
- The on-disk names are migrated: `~/.config/Snapmockit`, `~/.config/snapmockit`, and `~/Snapmockit/Library` (22 files) exist; `~/.config/SnapMock`, `~/.config/snapmock`, and `~/SnapMock` do not.
- **The pre-migration instance is still running:** process 214565, `uv run python -m snapmock`, up for eight days. It must be quit before the first sitting; its exit rewrites its settings to `~/.config/SnapMock/SnapMock.conf`, which the migration then leaves as stale because the new store exists, and which may be deleted by hand.
- The session is X11 (`XDG_SESSION_TYPE=x11`); the Wayland check needs a log-out.
- The repository's issue tracker is empty; no labels exist beyond GitHub's defaults.
- The nine product requirements documents stand at: Basic Shape 1.28, Blur / Highlighter / Eyedropper 1.19, General UI 2.40, Library 1.2, Navigation and Raster Operations 1.3, Numbered Steps / Stamps / Emoji 1.7, Screen Capture 1.0, Technical Architecture 1.55, Text and Callout 1.9.
- The suite at 080e2f3: 1669 passed, 14 skipped, 1 deselected, in 6 minutes 13 seconds from a scratch worktree; no code has changed since.

## 5. Findings

One row per finding, numbered in the order found. The class is one of defect (against a product requirements document, fixed here with a test), departure (kept by Doug's decision, recorded in the document), or follow-up (listed for a later kickoff). The state is one of open, fixed, kept, or deferred.

| # | Sitting | What happened, in Doug's words | Where | Requirement | Class | Fix commit or issue | State |
|---|---|---|---|---|---|---|---|
| 1 | 0 (before the first sitting, 09-15-26) | "Can I install this version of snapmockit on my linux pc so I can open it from the main menu?" and, once the entry was placed by hand, "I see the snapmockit, but no icon is shown" | The AppImage on the desktop: no menu entry and no icon until the user installs them | None: Technical Architecture PRD 7.3 names the AppImage form; no document asks for desktop integration | Follow-up | none | Deferred |
| 2 | 0 (before the first sitting, 09-15-26) | "our there installation instructions? What is next for other users to install this app?" | The README: its AppImage run lines named `dist/`, the builder's path, and the download route came second | None: the README is not a requirement; a documentation defect | Defect (documentation) | [#1](https://github.com/dbower44022/snapmockit/issues/1), fixed in this commit | Fixed |
| 3 | 1 (09-15-26) | "There is a major problem with selecting objects and dragging them around the canvas. The icon changes from a hand to a small square and the cursor follows the mouse movements, but the object moves irradically and almost never moves smoothly with the mouse movements. This makes it very difficult to acurately position objects. It does not seem to be dependent on a single object type, as all seem to have same issues. It seems to be worse with vertical movements than horizontal." | The Select tool, dragging a selection on the canvas | Technical Architecture PRD 3.4: transforms previewed in real time during a drag | Defect | [#2](https://github.com/dbower44022/snapmockit/issues/2), fixed in 8ff6705 | Fixed; the display retest owed to the next sitting |

### 5.1 Notes on the findings

**Finding 1, 09-15-26 10:04 to 12:33.** The AppImage carries its desktop entry and icons inside but nothing installs them, and no AppImage helper is on this machine. Doug installed them by hand from a runbook page (https://claude.ai/artifact/MBvoDyV1Emp2C9zf7eCB9U): a copy of the released file at `~/Applications/Snapmockit.AppImage`, the 256 pixel PNG and the SVG extracted with `--appimage-extract` into `~/.local/share/icons/hicolor`, the desktop entry written to `~/.local/share/applications/io.github.dbower44022.snapmockit.desktop` with `Exec` naming the copy, and `update-desktop-database`. The entry appeared in the menu at once; its icon did not until Cinnamon was restarted (Ctrl+Alt+Esc), since the running desktop had not rescanned the icon directories, although a freshly started GTK program found the icon at every size. Doug: "That worked." The README gains the same steps (this commit). The follow-up for a later kickoff: an "Add to Menu" action, or a first-start offer, that writes the entry and icons the AppImage already carries, and removes them on request; the 1.0.0 release notes say the menu entry is installed by hand until then. With the entry installed, the application gives its desktop id to Qt (`desktop_entry_installed`), so the portal registration the AppImage notes' Section 8 describes now succeeds here.

**Finding 2, 09-15-26 21:24 to 21:28.** Asked whether installation instructions exist, the session found them in the release notes and the README, but the README's run lines were written from the builder's chair (`dist/Snapmockit-*.AppImage`) and the download route was one clause before the build recipe. Doug approved a documentation fix before his first sitting. The README now opens its Linux part with "Install on Linux" for a downloader: the download, making the file executable from the file manager or from the shell with the Downloads path, running it, the menu steps of finding 1, and an "Other forms" note (Windows and macOS not yet built; PyPI and Flatpak after 1.0.0, decision 4); the build recipe moved to its own "Building the AppImage" section, and the Developing section's suite time was corrected from 1 hour 40 minutes to about 6 minutes. A documentation defect carries no test; under decision 2 it has an issue, #1, closed by the fix commit, the tracker's first entry.

**Finding 3, 09-15-26 21:39, triage.** Reproduced by reading and measuring, not on the display: a simulated drag of a selected rectangle through the view's mouse events on the offscreen platform costs 0.5 ms per move (median and 90th percentile; the profile puts the tool's own work at 0.1 ms and the transform handles' update at 0.04 ms), so the code path is cheap and the fault is in what the display does with it. The one thing the Select tool's drag does that the drawing tools' drags do not is `QToolTip.showText` on every move, a separate top-level window placed just below and right of the cursor. `SnapView.focusOutEvent` already carries a guard written on 09-07-26 (commit 32c78dd) for "transient focus loss (e.g. QToolTip on Linux)" during a drag, so the tooltip's cost on this desktop was met before; and the Basic Shape shared drawing work moved the drawing tools' dimension readout to a widget over the viewport (`ui/dimension_overlay.py`, decision 1 of that work), after which their drags passed on the display on 09-13-26. A tip window under a pointer moving downward matches "worse with vertical movements". The raster selection tool's drag (`tools/raster_select_tool.py`) shows its size the same way. Proposed fix: both readouts move to the dimension overlay, which never leaves the viewport; the proof is Doug's retest from source.

**Finding 3, fix, 09-15-26 21:50 to 09-15-26 21:56 (commit 8ff6705).** Doug: "go". The Select tool's move readout, and with it the three the same tool showed the same way (the rotate angle, the corner resize size, the edge resize size) and the raster selection tool's W / H readout, now draw on the dimension overlay (`dimension_overlay(viewport).show_measurement`, the constrain icon and the centre marker off) and are hidden by the release, by cancel, and by a tool switch through cancel; `QToolTip` is no longer imported by either tool. Four tests, each failing before the fix (the overlay did not exist after a drag move) and passing after: the move readout's text "ΔX: +20  ΔY: +30" with the item moved by the same amount and no tooltip visible, the readout gone at the release and on cancel, the resize and rotate readouts, and the raster selection's size readout. Technical Architecture PRD 1.56 (3.4, 3.9); the PRD header's "Document version" and "Last Updated" had stopped at 1.49 while the revision table went on, and are brought level in the same row. The full suite from a scratch worktree at 8ff6705: 1673 passed, 14 skipped, 1 deselected, in 5 minutes 48 seconds; ruff and mypy clean. What remains is Doug's retest from source on the display, section 1 of the pass's retest page (https://claude.ai/artifact/394jKsqdydbikiQ3QCV8oq): drag an item, resize it, rotate it, and draw a raster selection, each with the readout beside the cursor and the item following the pointer.

## 6. Sittings

One entry per sitting: the date, the work done in Doug's words, the files it touched, and the findings by number. A sitting with no finding is recorded too.

*None yet.*

## 7. The Wayland check (checklist section 7)

Owed. To be run by Doug from the checklist page against the released 0.9.0 file when he can log out of the X11 session into Cinnamon on Wayland; its five marks are recorded here and in `docs/Packaging-AppImage-Implementation.md`, Section 8.4.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.4 | 09-15-26 21:56 | Claude (Claude Code) | Finding 3 fixed (commit 8ff6705, Technical Architecture PRD 1.56); the display retest owed. |
| 1.3 | 09-15-26 21:44 | Claude (Claude Code) | Finding 3 recorded and triaged: erratic item dragging, a defect against Technical Architecture PRD 3.4, issue #2. |
| 1.2 | 09-15-26 21:28 | Claude (Claude Code) | Finding 2 recorded and fixed: the README rewritten for a downloader (issue #1). |
| 1.1 | 09-15-26 12:34 | Claude (Claude Code) | Finding 1 recorded (no menu install route; follow-up) with its resolution by hand; the README's menu steps noted. |
| 1.0 | 09-15-26 09:48 | Claude (Claude Code) | Initial notes: the phase table, the four decisions as approved (1 A with C available, 2 B, 3 A, 4 A), the seven silences and two more, the starting state re-verified at 8c0ac91, the empty findings table, and the Wayland check owed. |
