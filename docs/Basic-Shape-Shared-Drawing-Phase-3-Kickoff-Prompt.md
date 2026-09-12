# Kickoff Prompt: The Shape Tools' Shared Drawing Behaviour, Phases 3 to 5

Last Updated: 09-12-26 14:14 · Revision 1.0

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. This continues the work `docs/Basic-Shape-Shared-Drawing-Kickoff-Prompt.md` (revision 1.0) began on 09-12-26; Phases 1 and 2 of that prompt are done and this one carries Phases 3, 4, 5, and the close-out. Start it only when no other session is committing in this working directory: two sessions ran in parallel on 09-12-26 and both bumped the General UI PRD, which put two revision numbers on two versions each and needed a correction commit (`fc704a9`) to undo.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root. No other repository is involved in this session.

## Task

Finish the Basic Shape Annotation Tools PRD's Section 2. Phases 1 and 2 built 2.1's press guard, 2.3's modifiers and Escape, and 9.5; **Phases 3, 4, and 5 remain**, and they are the phases of `docs/Basic-Shape-Shared-Drawing-Kickoff-Prompt.md` unchanged. That prompt still governs: its four decisions are taken, its eight silences are decided, and its phase definitions, standards, and close-out are the ones to follow. This prompt records what has changed underneath them since it was written, so nothing is re-derived and nothing already settled is reopened.

**The four decisions are taken** (Doug, 09-12-26, "use your recommendations for all decisions"), and every remaining phase depends on them:

1. **The dimension tooltip is a widget over the canvas view's viewport**, as the Eyedropper's preview loupe is, carrying the constrain icon and the centre marker beside it. The screen-edge arithmetic is factored out of `snapmock/ui/loupe_overlay.py` — `loupe_position` is the function to generalise — so the two overlays share one function rather than two copies.
2. **The not-auto-selected rule reaches every tool that draws**: the seven shape tools, the Blur tool, and the Highlighter. The Text and Callout tools stay excepted.
3. **2.4's guide lines to the rulers are built**, in `SnapView.drawForeground` beside the grid, the guides, and the crosshairs, from the preview's bounding box while a drag lasts and only on the axes whose ruler is visible.
4. **Ctrl is a second route to the centre-draw modifier**, Alt keeping its meaning. Built in Phase 2 and already in `BaseTool.draws_from_centre`; the hint text names it as "Alt or Ctrl: from center".

## Read first, in this order

1. `docs/Basic-Shape-Shared-Drawing-Implementation.md` (revision 1.2 or later), whole. It is this work's own notes: Section 1's phase table says where to start, Section 2 carries the four decisions and eight silences and three corrections to the first kickoff, Sections 3 to 5 are Phase 1, Section 6 is Phase 2 with its five silences and its measured cost per Shift move.
2. `docs/Basic-Shape-Shared-Drawing-Kickoff-Prompt.md` (revision 1.0): the Phases section from "Phase 3" to the end, the decisions as they were put, the silences, and the standards. Its "Starting state" section is now history — Phases 1 and 2 closed three of its findings — and the section below replaces it.
3. `docs/Eyedropper-Blur-Performance-Implementation.md` (revision 1.10 or later): Section 2.1's decision 1 and Section 6, the preview loupe built as a widget over the viewport, which decision 1 of this work follows; and Section 4.1's measured 0.36 to 0.45 ms per mouse move, the budget a second overlay shares.
4. `PRDs/SnapMock-Basic-Shape-Annotation-Tools-PRD.html` (version 1.15): Section 2 whole, then the Status Bar Hints tables 3.7, 4.8, 5.7, 6.7, 7.7, 8.7, and 9.11, the Shared Behavior rows of Section 12, and the 1.13 to 1.15 revision rows, which are this work's own.
5. `PRDs/SnapMock-General-UI-PRD.html` (version 2.30): 1.3, 5.2, 6.6, Section 9, 12.2, and 15.1, whose overflow behaviour changed on 09-12-26 in another session. `PRDs/SnapMock-Technical-Architecture-PRD.html` (version 1.39): 3.3, 3.9, 8, and 10.
6. `snapmock/tools/base_tool.py` whole — it is where the shared drawing lifecycle now lives — then `snapmock/tools/rectangle_tool.py` and `ellipse_tool.py` (the pattern every drag-drawn tool now follows), `line_tool.py`, `arrow_tool.py`, `freehand_tool.py`, `arc_tool.py`, and `polygon_tool.py`.
7. `snapmock/ui/loupe_overlay.py` (`loupe_position`, `loupe_size`, the event filter that hides on Leave, the painted shadow), `snapmock/core/view.py` (`drawForeground`, `_draw_grid`, `_draw_guides`, `_draw_crosshairs`, `set_rulers_visible` and `_rulers_visible`, `paintEvent`'s focus frame), and `snapmock/ui/tool_options_bar.py`'s `overflow_popover` and `overflowing`, which are new.
8. `tests/test_shape_drawing_lifecycle.py` and `tests/test_shape_modifiers.py`, this work's own; then `tests/test_eyedropper_loupe.py` for how an overlay widget is tested, and `tests/test_acceptance.py` and `tests/test_inter_tool.py` for what a tool switch is asserted to do.
9. Every test that draws through a shape tool and then expects the Select tool to be active or the new item to be selected — Phase 5 rewrites each of them. `BaseTool._switch_to_select` reaches the tool manager through the view's window, so a test with a bare `SnapView` never sees the switch and a test with the `main_window` fixture does.

Do not write anything until all nine are read.

## Starting state, verified at commit fc704a9 on 09-12-26

This replaces the first kickoff's "Starting state" section. Its three probes are closed: a locked or hidden layer now refuses the drag, a tool switch during a drag leaves nothing in the scene, and Shift and the centre-draw modifier both work on the Rectangle and the Ellipse.

**What Phases 1 and 2 built**, all of it in `BaseTool` and the nine tools that draw:

- `layer_allows_drawing`, the press guard of 2.1, refused through `check_requirements` so the message reads as General UI PRD 1.3 asks. Called by the seven shape tools, the Blur tool, and the Highlighter; the Numbered Step tool's own copy is gone.
- `_start_preview` and `_end_preview` hold the drawing preview, so `cancel` drops it, `is_active_operation` is true while a drag lasts, and `handle_escape` cancels a drawing operation. The five drag-drawn shape tools read the preview back through a typed `_item` property; the Arc, Polygon, Blur, and Highlighter tools keep their own overrides.
- `constrains` and `draws_from_centre` read Shift and the centre-draw modifier, the second on Alt and Ctrl alike; `constrained_rect` in `snapmock/core/path_utils.py` is the geometry for the Rectangle and the Ellipse.
- The Freehand's Shift straight segments of 9.5, through `FreehandItem.preview_snapshot` and `restore_preview`.
- The Idle hints of 5.7, 6.7, and 9.11 now read as their tables word them. **The Line's and the Arrow's do not**: they still read "Click and drag to draw line | Shift: constrain angle" where 3.7 and 4.8 word them differently. Phase 4 corrects those two Idle rows along with the five Drawing rows.

**What is still open in Section 2**, and is this session's work:

- **2.4 whole.** No preview at 70 percent opacity, no dimension tooltip, no constrain icon, no centre marker, no guide lines. The Arc and the Polygon put their measurements in the status bar hint, which is a different place from the one 2.4 names.
- **2.1's last mouse-release step and 2.5.** Every shape tool still selects its new item and switches to the Select tool, and so do the Blur tool — from three separate release paths — and the Highlighter.
- **The Drawing rows of 3.7, 4.8, 5.7, 6.7, and 9.11**, and the Idle rows of 3.7 and 4.8.

**Other things that changed underneath the first kickoff:**

- **The Tool Options Bar's overflow was rebuilt on 09-12-26** in another session (commit `923d8d7`, General UI PRD 2.30, Sections 5, 14, 15.1): every control now sits in one strip the bar lays out itself, and the tail that does not fit moves into a popover under a "More…" button. The first kickoff's "When the work is complete" section lists the bar's overflow as one of three things waiting; it is no longer waiting.
- **The colour picker's Saved row was rebuilt the same day** (commit `0832db3`, General UI PRD 2.29, Section 11.1), which was the first of those three things. Whether it closes Doug's finding is a display check, not a code question.
- **The Alt gesture on this desktop** is the third and is unchanged: Cinnamon's window manager takes Alt plus a mouse button, so no Alt+drag reaches the canvas. Decision 4's second route is why the centre-draw modifier works anyway; the Zoom tool's Alt+click and the blur brush's Alt+paint eraser still have no route and belong to other product requirements documents.
- **The suite at the Phase 1 close-out commit** (`c4bba0c`) ran 1475 passed, 2 failed, 13 skipped, 1 deselected, in 1 hour 20 minutes. One failure was the pre-existing timing-sensitive Zoom tool test. The other was this work's own `test_a_focus_loss_during_a_drag_leaves_nothing`, which passed alone and failed in the suite because it read the application's ambient mouse-button and focus state; commit `b32659e` pins both with monkeypatch and adds the companion test for the other half of the rule. **Which module leaves that state was never identified** — the failure did not reproduce under `tests/test_tools` plus this work's own module — so a full-suite run in this session should be watched for it.

## Phases

Three phases and the close-out, exactly as `docs/Basic-Shape-Shared-Drawing-Kickoff-Prompt.md` defines them. Each phase is one or more commits and is closed out before the next starts: PRD rows, the notes' section, the phase-table row done, the next required step. Every commit is ruff-clean and mypy-strict-clean with the suite passing.

Run the full suite as `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font` to a log file in the background from a scratch `git worktree` at the commit under test, with the venv's own interpreter from the worktree's root. It took 1 hour 20 minutes on 09-12-26 and slows when other test runs share the machine, so run one at a time and keep foreground runs small. A test that measures a frame time keeps a loose ceiling and puts the measured figure in the notes, as Section 6.1 of the notes does. No test opens a real popover or dialog unpatched; the `unmet_messages` fixture captures the never-disabled message. **A test must not read the application's ambient input state without pinning it** — that is what the Phase 1 failure above was.

### Phase 3, the dimension tooltip (2.4)

1. **The tooltip, the constrain icon, and the centre marker.** Per decision 1: a tooltip following the cursor at a 15 by 15 pixel offset, repositioned when it would leave the viewport, showing each tool's own measurements — the Line's and the Arrow's length and angle, the Rectangle's and the Ellipse's width and height, the Ellipse's diameter while Shift is held, the Arc's chord length and angle then its bulge, the Polygon's vertex count or its sides and radius, and the Freehand's state; the constrain icon beside it while Shift is held; and the centre marker at the origin point while the centre-draw modifier is held. One function per tool computes the measurements, the tooltip shows them, and Phase 4's hint text is built from the same values, so the two can never disagree — that is the first kickoff's sixth silence and it shapes this phase's design.
2. **Phase close-out.**

Tests: the tooltip's text per tool, its offset and its repositioning at each viewport edge, the icon appearing with the modifier, the marker's position, the tooltip never reaching a render of the scene, and its cost per mouse move under a loose ceiling.

### Phase 4, the preview and the hints (2.4, 3.7, 4.8, 5.7, 6.7, 9.11)

1. **The 70 percent preview, the guide lines, and the drawing hints.** The preview drawn at 70 percent opacity and restored to full when the item is committed; the guide lines of 2.4 per decision 3; the Drawing rows of 3.7, 4.8, 5.7, 6.7, and 9.11 in the PRD's own wording, from the same measurements the tooltip shows; and the Idle rows of 3.7 and 4.8, which are still the shipped tools' shorter wording.
2. **Phase close-out.**

Tests: the preview's opacity during the drag and the committed item's, each tool's drawing hint text, the Ellipse's Shift-held diameter row, and the guide lines against decision 3.

### Phase 5, the post-creation rule (2.1, 2.5)

1. **No auto-selection, no tool switch.** Per decision 2: the seven shape tools, the Blur tool, and the Highlighter stop selecting the new item and stop switching to the Select tool, so the tool stays active for the next shape and each shape is its own undo step. The Blur tool reaches the Select tool from three release paths — the drag-drawn region, the Whole Layer region, and the brush-painted region — and all three are covered. Every test that assumed the switch is rewritten to activate the Select tool itself rather than deleted.
2. **Phase close-out.**

Tests: drawing three shapes in succession with one tool without touching anything between them, each its own undo entry; the selection empty after a draw; the tool still active; and the Text and Callout tools keeping their present behaviour.

### Close-out of the work

Basic Shape PRD, General UI PRD, and Technical Architecture PRD rows for what was built and where it departs; the notes complete; the General UI notes' Section 25 pointer; the Basic Shape remainder notes' Section 10 pointer updated; the display checks owed carried forward with this work's own added; the next required step stated. **Say plainly which rows of the Basic Shape Annotation Tools PRD remain, if any.**

## Decisions to surface

None is expected. The four the work needed are taken and recorded in Section 2.1 of the notes. Apply the two-part test from the global guidance to anything new: real downstream impact, and at least two viable options producing meaningfully different outcomes. Where a product requirements document is silent or self-contradictory, decide as the notes' existing silences decide — record it in the notes' decisions section and in the PRD row, and continue.

Two silences are known to be waiting in Phase 3, neither of them expected to pass the two-part test:

- **What the Freehand's tooltip shows.** 9.11's Drawing row reads "Drawing…", which is a state and not a measurement. The tooltip shows the same, or the stroke's point count; decide and record.
- **What "to the rulers" means when a ruler is hidden on one axis or the shape is off screen.** The first kickoff's eighth silence says the lines are drawn only on the axes whose ruler is visible, which settles the first half; the second half is this phase's.

## Standards that apply

- Terminology Precision, Writing Register, and Reply Format from the global guidance apply to every reply and to the documents.
- Every new module gets a row in Technical Architecture PRD Section 10 in the commit that creates it; one is expected for the tooltip overlay, `snapmock/ui/dimension_overlay.py`, which Technical Architecture PRD 1.38 already names.
- Departures from any product requirements document are recorded in that document's change log with a version bump, not only in code comments. **Check the revision-control table for a duplicate version number before bumping**, since a parallel session caused two on 09-12-26.
- No control is disabled (General UI PRD 1.3); a control whose requirement is unmet says which, through `check_requirements`.
- Every new control gets an accessible name as it is created, and `tests/test_accessibility.py`'s audit passes over every new surface.
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy snapmock`, and `uv run pytest` must pass before each commit, with `QT_QPA_PLATFORM` set to `offscreen` for pytest.
- Document timestamps are read from the machine clock at the time of writing, never estimated.
- Commit messages end with the attribution block the session provides.

## When the work is complete

Update the phase table in `docs/Basic-Shape-Shared-Drawing-Implementation.md`, bump its revision, add a change-log row, and state the next required step. Say which rows of the Basic Shape Annotation Tools PRD remain open, if any, and name what remains elsewhere. Known to be waiting, none of it this work's: the Zoom tool's Alt+click and the blur brush's Alt+paint eraser, which Cinnamon's window-move gesture holds against and which belong to other product requirements documents; the Windows capture backend (`docs/Windows-Backend-Kickoff-Prompt.md`), which waits for a Windows machine; and the macOS backend, deferred with no Mac available.

**The display checks owed** are the ones the notes documents carry on 09-12-26 — a blur region in Solid Fill, a highlight in Multiply over dark text, the painted and erased blur regions, the Whole Layer region and its source modes, and the three the Eyedropper and Blur performance work added — plus **this work's own, of which Phases 1 and 2 have already earned four**: a square drawn with Shift and a circle drawn with Shift; a rectangle drawn from its centre with Ctrl; a drag refused on a locked layer, with its message; and a Freehand stroke that mixes a curve and a Shift-held straight run. Phases 3 to 5 add: the dimension tooltip at each of the seven tools, the tooltip near a viewport edge, the guide lines to the rulers, the preview at 70 percent opacity, and three shapes drawn in succession without touching anything between them. Two more are owed by the other session's work of 09-12-26 and are worth running in the same sitting: the colour picker's Saved row, and the Tool Options Bar's "More…" popover at Doug's window width.

---

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-12-26 14:14 | Claude (Claude Code) | Initial continuation prompt, written at Doug's request after the Phase 2 close-out. Carries Phases 3, 4, 5, and the close-out of `docs/Basic-Shape-Shared-Drawing-Kickoff-Prompt.md` (revision 1.0) unchanged, and replaces its starting state with what is verified at commit fc704a9: the four decisions taken, Phases 1 and 2 built, the Line's and Arrow's Idle hints still uncorrected, the Tool Options Bar's overflow and the colour picker's Saved row rebuilt in a parallel session, the General UI PRD renumbered after a version collision, and the Phase 1 suite failure whose cause was fixed but never traced to the module that caused it. Four display checks are already earned. |
