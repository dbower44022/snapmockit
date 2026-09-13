# The Freehand Tool's Remaining Rows — Implementation Notes

Last Updated: 09-13-26 10:30 · Revision 1.0

Implements the last open rows of the Basic Shape Annotation Tools PRD (`PRDs/SnapMock-Basic-Shape-Annotation-Tools-PRD.html`, version 1.21 at the start), all of them Section 9's, the Freehand / Pen tool: 9.2's brush-tip cursor and 9.10's two performance rows, with the Section 12 Freehand row they own and the General UI PRD (version 2.32) and Technical Architecture PRD (version 1.42) rows, in the four phases and the close-out defined by `docs/Freehand-Remainder-Kickoff-Prompt.md` (revision 1.0). A session pasting that prompt starts at the first phase not marked done in Section 1. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) governs the standards; the General UI implementation notes (`docs/General-UI-Implementation.md`) hold the walk table of Section 17.2. Finishing this work leaves the Basic Shape Annotation Tools PRD with no open row except what the document itself reserves.

Starting state, verified at commit d88f041 on 09-13-26 (the kickoff names 13d0054; d88f041 adds only the kickoff prompt and the shared drawing notes' pointer). The three probes of the kickoff, re-measured by running the code on this machine, are in Section 3; in one line each: the fit on release takes 85 to 100 ms at 5000 smooth points at every smoothing and 1.9 seconds at 5000 jittery points at 0 percent, against 9.10's 50 ms; the live preview's paint costs 20 ms at 5000 points, against the 16.7 ms a frame allows; and `FreehandTool.cursor` is the crosshair before, during, and after a stroke. The suite at commit 2bce34e ran 1609 passed, 0 failed, 13 skipped, 1 deselected, in 1 hour 34 minutes; ruff and mypy are clean.

## 1. Phase status

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The decisions and the measurements: these notes, the three probes re-measured, the PRD rows the decisions imply | Done | this commit |
| 2 | The brush-tip cursor (9.1, 9.2; General UI PRD 6.6) | Not started | |
| 3 | The fit within 50 ms (9.3, 9.10) | Not started | |
| 4 | The long-stroke preview (9.10) | Not started | |
| Close-out | PRD rows, the notes complete with the measurements before and after, the pointers in the Basic Shape remainder notes (Section 10), the shared drawing notes (Section 12.2), and the General UI notes (Section 26), the display checks owed, what remains of the Basic Shape PRD | Not started | |

## 2. Decisions

### 2.1 Taken at the start of Phase 1 (09-13-26)

Presented with the consequential decision template and chosen by Doug on 09-13-26: the recommendation in every case ("use your recommendations").

| Decision | Choice | Effect |
|---|---|---|
| 1 What the Freehand cursor is, and when it changes | A, the PRD as written in its two rows | Idle, 9.1's "Crosshair, small dot variant": a crosshair with a small centre dot. From the press to the release, 9.2's filled disc: the stroke width times the view's zoom across, in the stroke colour at the stroke opacity, over a white halo ring with a black outline, never under 4 px and never over `BRUSH_CURSOR_MAX` (128 px). The crosshair returns on release, on cancel, on Escape, and on a tool switch. The disc follows a change of stroke width, colour, or opacity and a change of zoom, which Ctrl+wheel can make mid-drag (Section 2.3). The cost: the user does not see the width and colour before the press, which is why a painting program shows a brush outline; two cursors to build instead of one; during the drag the disc sits on the stroke's own end in the same colour. The alternatives: option B, the disc whenever the tool is active as the Blur brush and the marker tip are, which the kickoff recommended before 9.1's cursor row was read and which departs from both 9.1 and General UI PRD 6.6; option C, the crosshair kept and 9.2 recorded as a departure. |
| 2 How the 50 ms fit is met, and what 0 percent means for a jittery stroke | The rule: A first and measured, then B only if A leaves 0 percent over budget | A: the pipeline faster with the same result. `simplify_rdp` vectorised with NumPy over each span (the Python loop dominates every smooth case measured), the fit's per-piece arrays reused, the twenty reparameterisation iterations kept; every existing test stands and a saved stroke re-smooths identically. B, reached only if A leaves 5000 jittery points at 0 percent over 50 ms: a noise floor at 0 percent, the fit error never below the stroke's own median point-to-point deviation, so a jittery stroke at 0 percent gives tens of segments rather than 1388; 9.3's "nearly raw path" read as not a segment per point. The cost of B: a stroke drawn at 0 percent before this work re-fits to different segments when re-smoothed, never on load, since the file carries its segments; a departure from the 0.5 px floor the Basic Shape remainder work recorded; the row names the strokes on which the result differs. Confidence, inferred from the profile's shape and not yet measured: A very likely meets 50 ms at 50 and 100 percent and very likely does not at 0 percent on a jittery stroke. Phase 3 does not stop again for the choice; the row records it either way. The alternatives: option C, the fit on a background thread, the first thread in the code, rejected for the blur for the same reason; option D, A alone with the 0 percent figure recorded as a departure. |
| 3 Whether the beginning of a very long stroke stays on screen while it is drawn | B, nothing vanishes and the cost is bounded | The preview is kept in pieces of 500 points. Each move repaints only the new segment's own patch instead of the whole stroke's bounding rectangle, and only the pieces that touch the patch are stroked, joined as one path so the 70 percent preview shows no seam. On release the full path is painted as today. The cost per move is the current piece plus any older piece the stroke passes near. The cost: more machinery in the item's paint and in what it asks the view to repaint; a scroll, the auto-scroll at the viewport's edge included, or a stroke that grows past its bounding rectangle repaints the whole stroke once, so that frame costs what today's do; a stroke scribbled back and forth over one spot keeps every piece near the pointer and gains little, so B bounds the travelling stroke and not the scribble, and these notes will carry both measurements. A is the fallback if B's scribble case measures over a frame at 5000 points or the targeted repaint proves fragile under the Shift segments. The kickoff's frozen image is not used, for the fourth correction of Section 2.3. The alternatives: option A, 9.10's rule as written, the last 500 points only past 2000, the start of the stroke gone until release; option C, the 20 ms at 5000 points recorded as a departure. |

### 2.2 The kickoff's seven silences

Each decided as the kickoff recommended, on 09-13-26, with the detail the reading added.

| Silence | Decision |
|---|---|
| The cursor's minimum and ceiling | 4 px and `BRUSH_CURSOR_MAX`, the Blur brush's; a stroke width past the ceiling draws at the ceiling. |
| The cursor's fill and hotspot | The stroke colour at the stroke opacity over a white halo ring with a black outline, so a light colour on a light screenshot still reads; the hotspot is the centre. The idle crosshair of decision 1 carries the same halo as every other drawn cursor. |
| A locked or hidden layer | Does not change the cursor: General UI PRD 6.6's forbidden row names a locked item, not a locked layer (shared drawing notes, Section 2.3), and the press guard's message says what is wrong. |
| How the measurements are taken | On the offscreen platform with the scratch script Section 3 describes, on a sine-wave stroke with and without a pixel of jitter, at 500, 2000, and 5000 points, with the machine named. A test holds a loose ceiling, one frame per move for the preview and 50 ms times a factor the notes justify for the fit, never the measured figure. |
| The 2000-point threshold and the 500-point tail | 9.10's values, as module constants in `items/freehand_item.py`, where they are used, rather than beside `MIN_STROKE_EXTENT` in the tool as the kickoff put them: under decision 3 they govern how the item paints, and the tool never reads them. |
| Raw point capture | 9.10's "must not drop events" is met by the existing event route, the view's mouse move handler delegating to the tool on every event, and is not changed. |
| Pressure data | Reserved by 9.2 and 9.4 for a future version, stored as null; not this work's. |

### 2.3 Corrections to the kickoff, found in the reading

- **9.1 gives the Freehand tool an idle cursor of its own.** Its Overview table reads "Default Cursor: Crosshair, small dot variant". The kickoff read General UI PRD 6.6's plain crosshair as the idle cursor and 9.2's disc as the only cursor row, and recommended option B on that reading. Decision 1 follows both rows.
- **The Blur tool's brush cursor does not follow the zoom.** Nothing connects `SnapView.zoom_changed` to `BlurTool._refresh_cursor`; the cursor is re-read on activation and when the bar changes the brush size or the shape. The kickoff said it re-applies on zoom. This work connects the Freehand's cursor to the zoom; the Blur tool's gap belongs to its own PRD and is recorded in the close-out, not fixed here.
- **A zoom during a drag is possible.** `SnapView.wheelEvent` zooms on Ctrl+wheel with no guard for a held mouse button. The kickoff said the drag consumed the mouse. So the disc cursor follows `zoom_changed` mid-drag, and decision 3's preview keeps nothing at the view's scale.
- **A frozen image and a live tail cannot be painted separately under the 70 percent preview.** Qt applies an item's opacity to each primitive it paints, so two paints at 70 percent blend twice where they overlap: a darker disc the stroke's width at every freeze point. One stroked path never does, because Qt fills the stroke's outline once. Decision 3's option B therefore paints pieces joined as one path and repaints only what changed, rather than the cached image the kickoff sketched.
- **The Basic Shape PRD's acceptance criteria are Section 13 by the document's own contents list**, with Serialization as Section 12; every row the document carries and every notes document calls them Section 12, and Open Issues Section 14. The rows this work writes keep "Section 12", as the document's own rows do; the numbering is a record for Doug, beside the three Open Issues.

### 2.4 Findings decided with the decisions

- `FreehandItem._rebuild_path` calls `_geometry_changed` on every added point, which is `prepareGeometryChange` and a whole-item `update`: the view repaints the stroke's entire bounding rectangle on every move, and Qt strokes the whole preview path to do it. Decision 3's targeted repaint replaces that call while a stroke is drawn.
- `VectorItem.pen` folds the stroke opacity into the pen colour, so the disc cursor's fill is the same colour the stroke is painted with, read from the tool's creation defaults.
- `ToolOptionsBar` calls `on_option_changed(key, value)` on the active tool for every shared control, so the Freehand tool learns of a stroke width, colour, or opacity change through the route the Blur tool already uses for its brush size; the same route serves a preset applied while the tool is active.
- The shadow of a stroke being drawn is painted from `paint_shadow`'s blurred image cache, keyed by the path's signature, so it is rebuilt on every added point; under decision 3 the shadow during a long stroke is decided in Phase 4 and recorded there.

## 3. The measurements at the starting commit

Taken on 09-13-26 at commit d88f041 with a scratch script, on the offscreen platform, with no other run sharing the machine (load average 0.8): an Intel Core i7-11700K, sixteen threads, Python 3.12.3, NumPy 2.4.2, PyQt6 6.10.2 on Qt 6.10.0. The stroke is a sine wave 2800 px across with a 150 px amplitude, `y = 200 + 150 sin(x / 60)`, sampled at N points spaced evenly in x; the jittery variant adds a uniform random offset between −0.5 and +0.5 px to both axes of every point (seed 1), a pixel of jitter peak to peak. The fit is `FreehandItem.smooth` on an item built through `add_point`, the median of three; the preview paint is `FreehandItem.paint` of the quadratic preview, antialiased, onto a 2800 by 400 pixel ARGB32 image, the median of five; `add_point` is the whole build divided by the count.

| Stroke, points | Fit at 0 percent | Fit at 50 percent | Fit at 100 percent | Preview paint | `add_point` per point |
|---|---|---|---|---|---|
| smooth, 500 | 19 ms, 93 segments | 14 ms, 46 | 12 ms, 43 | 4.4 ms | 0.005 ms |
| smooth, 2000 | 46 ms, 93 | 40 ms, 48 | 38 ms, 43 | 7.8 ms | 0.005 ms |
| smooth, 5000 | 100 ms, 100 | 87 ms, 49 | 85 ms, 43 | 20.0 ms | 0.009 ms |
| jittery, 500 | 70 ms, 116 | 15 ms, 51 | 14 ms, 45 | | |
| jittery, 2000 | 616 ms, 490 | 38 ms, 50 | 34 ms, 43 | | |
| jittery, 5000 | 1899 ms, 1388 | 93 ms, 52 | 85 ms, 43 | | |

Read from the figures: the smooth cases cost the same at every smoothing and grow with the point count, which is the Python loop of `simplify_rdp` walking every point of every span; the jittery 0 percent case grows faster than the count, which is the fit splitting at nearly every point, since the 0.5 px floor on the fit error sits below the jitter, and running the twenty-iteration reparameterisation on each near miss. The preview paint is over a frame from about 4000 points on this machine. The kickoff's figures on its own stroke (127 to 159 ms smooth at 5000 points, 1304 ms jittery at 0 percent, 26.5 ms to paint) have the same shape; the strokes differ, and these are the figures the close-out compares against.

## 4. Phase 1 close-out

The decisions of Section 2 are taken and the measurements of Section 3 are recorded. Basic Shape PRD 1.22, General UI PRD 2.33, and Technical Architecture PRD 1.43 carry the Decision rows.

**Next required step:** Phase 2, the brush-tip cursor (9.1, 9.2; General UI PRD 6.6), per decision 1: a dot-variant crosshair and a brush-tip disc in `ui/cursors.py`, the disc set through the view's hover cursor at the press and cleared where the preview ends, refreshed on a change of stroke width, colour, or opacity and on `zoom_changed`. Tests: the disc's pixmap size following the stroke width and the zoom, its fill following the stroke colour and opacity, the 4 px minimum and the 128 px ceiling, the cursor changing when the width or the colour changes on the bar and when the zoom changes mid-drag, the crosshair back on release, cancel, and a tool switch, and a locked layer leaving the cursor alone.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-13-26 10:30 | Claude (Claude Code) | Initial notes: the starting state at commit d88f041, the phase table, the three decisions (1 A, 2 the A-then-B rule, 3 B) and the kickoff's seven silences as chosen 09-13-26, five corrections to the kickoff found in the reading, four findings decided with the decisions, the three probes re-measured with the script described, the next required step. Basic Shape PRD 1.22, General UI PRD 2.33, Technical Architecture PRD 1.43. |
