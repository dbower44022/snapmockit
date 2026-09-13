# The Freehand Tool's Remaining Rows — Implementation Notes

Last Updated: 09-13-26 14:22 · Revision 1.2

Implements the last open rows of the Basic Shape Annotation Tools PRD (`PRDs/SnapMock-Basic-Shape-Annotation-Tools-PRD.html`, version 1.21 at the start), all of them Section 9's, the Freehand / Pen tool: 9.2's brush-tip cursor and 9.10's two performance rows, with the Section 12 Freehand row they own and the General UI PRD (version 2.32) and Technical Architecture PRD (version 1.42) rows, in the four phases and the close-out defined by `docs/Freehand-Remainder-Kickoff-Prompt.md` (revision 1.0). A session pasting that prompt starts at the first phase not marked done in Section 1. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) governs the standards; the General UI implementation notes (`docs/General-UI-Implementation.md`) hold the walk table of Section 17.2. Finishing this work leaves the Basic Shape Annotation Tools PRD with no open row except what the document itself reserves.

Starting state, verified at commit d88f041 on 09-13-26 (the kickoff names 13d0054; d88f041 adds only the kickoff prompt and the shared drawing notes' pointer). The three probes of the kickoff, re-measured by running the code on this machine, are in Section 3; in one line each: the fit on release takes 85 to 100 ms at 5000 smooth points at every smoothing and 1.9 seconds at 5000 jittery points at 0 percent, against 9.10's 50 ms; the live preview's paint costs 20 ms at 5000 points, against the 16.7 ms a frame allows; and `FreehandTool.cursor` is the crosshair before, during, and after a stroke. The suite at commit 2bce34e ran 1609 passed, 0 failed, 13 skipped, 1 deselected, in 1 hour 34 minutes; ruff and mypy are clean.

## 1. Phase status

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The decisions and the measurements: these notes, the three probes re-measured, the PRD rows the decisions imply | Done | this commit |
| 2 | The brush-tip cursor (9.1, 9.2; General UI PRD 6.6) | Done | 6d6a789, then this close-out commit |
| 3 | The fit within 50 ms (9.3, 9.10) | Done | 483e387, 54e62da, then this close-out commit |
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

### 2.5 Decision 2's option B, refined on the measurement (09-13-26)

Presented to Doug after step 1 of Phase 3 and chosen ("b"). Option A left 5000 jittery points at 0 percent at 1.2 to 1.5 s, so the rule reached B, and measuring B as approved found three things. The median point-to-point deviation alone changes nothing: on the jittery stroke it is 0.26 px, under the 0.5 px floor already there, and the floor that meets the budget is about 1.2 px, or 1.5 px on a stroke of whole-pixel mouse coordinates, which every stroke at 100 percent zoom is. A floor at 0 percent only puts a cliff at 1 percent, since every level from 0 to 16 percent already resolves to the 0.5 px error, so the floor applies at every smoothing: the error is the larger of the slider's value and the floor. The lower half of the slider then becomes one level on the noisiest strokes, with the floor capped at 1.5 px so the upper half keeps its meaning; on a smooth stroke the floor is near zero and nothing changes. The measure is the median jump between consecutive points' deviations from their neighbours' chord, times three (Section 6). The alternative, option D, A alone with 0 percent recorded as a departure, would have left every mouse stroke at 30 percent or below paying about 50 ms per 200 points on release. The cost taken: the pipeline test's strict ordering between 0 and 30 percent on its 0.8 px alternating wave becomes non-strict, and a stroke saved at low smoothing before this work re-fits to fewer segments when re-smoothed, never on load.

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

## 5. What Phase 2 built

Step 1, 6d6a789. `dot_crosshair_cursor` and `brush_tip_cursor` in `ui/cursors.py`, drawn beside the brush and marker-tip cursors because no glyph matches: the first is the gapped crosshair every drawn crosshair in the module uses with a black dot on a white halo at its centre, 24 px with the hotspot on the dot; the second is a filled circle of the given diameter in the given colour, with a black outline over a 3 px white halo ring, the diameter clamped to 4 px and `BRUSH_CURSOR_MAX`, the hotspot at the centre, cached by size and colour. `FreehandTool.cursor` returns the dot crosshair while no stroke is drawn and the brush tip from the press to the release, at `stroke_width` times the view's zoom, in `stroke_color` at `stroke_opacity` through the same `with_alpha` the pen uses, so the tip and the stroke are one colour. `_refresh_cursor` puts the cursor on the viewport through `SnapView.set_hover_cursor` at the press, when the preview ends (`_end_preview`, which a release, a cancel, Escape, and a tool switch all reach), when the bar changes the width, colour, or opacity (`on_option_changed`), and when the view's zoom changes (`zoom_changed`, connected in `activate` and disconnected in `deactivate`). A locked or hidden layer refuses the press before the cursor changes, so the crosshair stays.

Silences found while building, decided as the code says:

- The dot crosshair's arms stop 4 px short of the centre where the other drawn crosshairs stop 3 px short, so the dot sits clear of the arms.
- A bar change or a zoom change refreshes the cursor only while a stroke is drawn; at idle the crosshair does not depend on either, and a refresh would only repeat it.
- The tool's `cursor` is now a `QCursor` in both states, where it was the `Qt.CursorShape` crosshair; the view sets whatever it is given, and nothing else read the shape.
- At a high zoom the tip reaches the 128 px ceiling early: a 10 px stroke at 1600 percent is 160 screen pixels and draws at 128, as the Blur brush does.

### 5.1 Tests

`tests/test_freehand_cursor.py` (7): the idle cursor's pixmap, hotspot, dot, arm, gap, and cache, and the tool returning it; the brush tip's size and hotspot following the diameter, its fill following the colour and the alpha, the cache keyed by both, the 4 px minimum, the 128 px ceiling, the outline, and the halo; the viewport showing the tip from the press to the release at the stroke's width and colour and the crosshair after; the tip following the zoom mid-drag through the view's own `set_zoom`, to the ceiling at 3200 percent; the bar's width, colour, and opacity changes reaching the tip while the stroke is drawn; a cancel and a tool switch putting the crosshair back, with the zoom connection following a re-activation; and a locked layer leaving the crosshair alone with the press refused. Targeted runs at 6d6a789: the cursor, pipeline, modifier, and blur brush modules, 57 passed; the lifecycle, post-creation, feedback, tooltip, Freehand point-edit, and accessibility modules, 158 passed; `tests/test_tools` with the options bar, presets, and status bar modules, 117 passed. Ruff and mypy are clean. The full suite at the Phase 2 close-out commit (c1ee66c), run alone from a scratch worktree between 10:42 and 12:16 while the Phase 3 work's targeted runs and measurements shared the machine: **1616 passed, 0 failed, 13 skipped, 1 deselected, in 1 hour 34 minutes.**

### 5.2 Phase 2 close-out

9.1's cursor row and 9.2's brush-tip step are built. Basic Shape PRD 1.23, General UI PRD 2.34 (6.6), and Technical Architecture PRD 1.44 (3.3) carry the rows. The display checks this phase owes: the brush tip at a thin and a thick stroke, in two colours, at 100 and 400 percent zoom, and the dot crosshair between strokes.

**Next required step:** Phase 3, the fit within 50 ms (9.3, 9.10), per decision 2's rule: profile first, then `simplify_rdp` vectorised with NumPy over each span, then the fit's per-piece work, measured at 5000 smooth and 5000 jittery points at 0, 50, and 100 percent; the 0 percent noise floor only if the jittery case is still over 50 ms, with the strokes on which the result differs named in the row. Tests: the fit's cost under a loose ceiling with the measured figure in these notes, and the fitted segments before and after the change agreeing on the strokes the existing tests use.

## 6. What Phase 3 built

Step 1, 483e387, decision 2's option A: the pipeline faster with its result unchanged. `simplify_rdp` in `core/path_utils.py` reads the points into two NumPy arrays once and, for each span on its stack, measures every interior point's distance to the chord in one NumPy pass when the span has 24 interior points or more (`_RDP_NUMPY_SPAN`) and in a plain loop over Python floats below that, where NumPy's per-call cost outweighs the loop; the profile had shown the old loop, a `QPointF` method call and a `math.hypot` per point per span, at 82 to 115 ms of a 5000-point stroke's 90 to 1900 ms. The fit builds each piece's four Bernstein rows once (`_bernstein`) and shares them between the least-squares solve, the error, and the Newton reparameterization, which takes the points it has already evaluated rather than evaluating them again. The arithmetic is written as before, expression for expression, so the segments are the ones the old fit gave: a first version that folded the outer products into dot products moved a control point by 1.2 px on the 5000-point sawtooth stroke the pipeline test uses, through an ill-conditioned piece's Newton steps, and was taken out.

Step 2, 54e62da, decision 2's option B as refined on 09-13-26 (Section 2.5). `stroke_noise` in `core/path_utils.py` measures how much of a stroke's wobble is noise: each interior point's signed distance from the chord through its two neighbours is a deviation, a curve's deviations change slowly, noise makes them jump, and the measure is the median jump between consecutive deviations. `FreehandItem.noise_floor` is that noise times `NOISE_FLOOR_FACTOR` (3), never past `NOISE_FLOOR_MAX_PX` (1.5 px, the error of 50 percent smoothing); `FreehandItem.fit_error` is the slider's error, never below `MIN_FIT_ERROR_PX` and never below the noise floor, at every smoothing; `fit_segments` uses it. Stage 1's tolerance is untouched.

Silences found while building, decided as the code says:

- **The floor is measured on the raw points**, `path_points`, not the simplified ones, so a re-smooth from the Property Panel reads the same floor the release did.
- **The measure ignores a zero-length chord**, two neighbours at the same point, by taking the deviation as the cross product over a length of one; such a point contributes its offset and no division by zero.
- **A fast, tightly wiggled stroke sampled sparsely reads as noisy** (about 0.7 px on a wave of 30 px amplitude sampled every 5 px), since its deviations change from point to point as the curvature does; its floor rises to the cap and the wiggles are fitted within 1.5 px rather than 0.5. Recorded, not corrected: the fit cannot tell undersampling from noise, and 1.5 px on a 30 px wiggle keeps its shape.
- **Fewer than four points have no noise**: the measure needs two deviations to see a jump.

### 6.1 The measurements after

Taken on 09-13-26 at commit 54e62da with the script of Section 3 extended by a third stroke, the sine rounded to whole pixels as a mouse at 100 percent zoom gives it, on the idle machine (load average 0.6 to 1.2), the median of three. The floor column is the item's `noise_floor`.

| Stroke, points | Floor | Fit at 0 percent | Fit at 50 percent | Fit at 100 percent |
|---|---|---|---|---|
| smooth, 500 | 0.10 | 11 ms, 93 segments | 6 ms, 46 | 6 ms, 43 |
| smooth, 2000 | 0.00 | 13 ms, 93 | 8 ms, 48 | 8 ms, 43 |
| smooth, 5000 | 0.00 | 16 ms, 100 | 12 ms, 49 | 12 ms, 43 |
| jittery, 500 | 1.43 | 9 ms, 60 | 7 ms, 51 | 7 ms, 45 |
| jittery, 2000 | 1.33 | 21 ms, 57 | 9 ms, 50 | 7 ms, 43 |
| jittery, 5000 | 1.36 | 28 ms, 56 | 15 ms, 52 | 12 ms, 43 |
| whole-pixel, 500 | 1.50 | 10 ms, 56 | 8 ms, 50 | 8 ms, 44 |
| whole-pixel, 2000 | 1.50 | 17 ms, 60 | 12 ms, 51 | 11 ms, 42 |
| whole-pixel, 5000 | 1.50 | 40 ms, 59 | 14 ms, 52 | 15 ms, 44 |

Against Section 3: 5000 smooth points fell from 85 to 100 ms to 12 to 16 ms at every smoothing, and 5000 jittery points at 0 percent from 1899 ms and 1388 segments to 28 ms and 56. The whole-pixel stroke, which Section 3 did not measure, is the slowest case left, 40 ms at 5000 points at 0 percent, inside 9.10's 50 ms with the least margin; the segments and the time at 50 and 100 percent are unchanged on every stroke, since those errors are above every floor. Between step 1 and step 2, with only option A, the same stroke at 0 percent took 1.2 to 1.5 s while the Phase 2 suite shared the machine, which is what sent decision 2's rule to B. The Section 3 sine gives a floor of 0.10 at 500 points and 0.00 at 2000 and 5000: at 500 points the samples are 5.6 px apart and the wave's curvature changes visibly between them.

### 6.2 Tests

`tests/test_freehand_fit.py` (7). The reference pipeline, the `simplify_rdp` and `fit_cubic_beziers` of commit c1ee66c with their helpers, is kept in the module: the faster simplification keeps the same points on the pipeline's wave, circle, and line, on the jittery and whole-pixel sines, on twelve random walks, and on a zero-length chord, at four tolerances; the faster fit gives the same segments, within a millionth of a pixel, on the wave at three smoothings, the circle, the line, the 5000-point sawtooth, the three sines, and six random walks. The cost: 5000 smooth points at 0, 50, and 100 percent, and 5000 jittery and 5000 whole-pixel points at the same three, each under a ceiling of 200 ms, four times 9.10's 50 ms for a machine shared with a full-suite run, against 12 to 40 ms measured alone. The noise measure reads near zero on the smooth sine, the circle, and a line, zero on three points, 0.3 to 0.6 px on the jittery sine, 0.6 to 0.9 on the whole-pixel one, and over 1 px on the pipeline test's alternating wave; the floor is zero on a smooth stroke, three times the measure on a jittery one and shared by every level below it, capped at 1.5 px on a whole-pixel stroke with 51 percent above it, and gives tens of segments where there were a thousand.

`tests/test_freehand_pipeline.py`: the segment-count ordering on the 0.8 px alternating wave is `>=` between 0 and 30 percent, both at the 1.5 px floor, and strict on a circle at the 0.5 px floor. Targeted runs at 54e62da: the fit, pipeline, point-edit, modifier, property panel, resize, presets, and options bar modules, 110 passed with the environmental deselection failing as it always does on this machine. Ruff and mypy are clean.

### 6.3 Phase 3 close-out

9.10's fitting budget is met on every stroke measured, 9.3's pipeline is unchanged at 50 percent and above and departs below it by the noise floor, and Section 12's "Path smoothing completes within 50 milliseconds on release" is met by tests. Basic Shape PRD 1.24 and Technical Architecture PRD 1.45 carry the rows. The display check this phase owes: the snap on release of a long slow stroke at 0, 50, and 100 percent smoothing feeling immediate, and the 0 percent result reading as the stroke drawn rather than as its jitter.

**Next required step:** Phase 4, the long-stroke preview (9.10), per decision 3's option B: the preview kept in 500-point pieces past 2000 points, each move repainting only the new segment's patch, only the pieces that touch the patch stroked and joined as one path, the full path on release. Tests: the paint cost per move at 2000 and 5000 points under a loose ceiling, the stroke looking the same on screen before and after the change at a fixed point count, the full path painted on release, and the Shift segments, `preview_snapshot`, and `restore_preview` over a stroke longer than 2000 points.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.2 | 09-13-26 14:22 | Claude (Claude Code) | Phase 3 done: Section 2.5 with option B refined on the measurement and chosen; Section 6 with the vectorised simplification, the shared Bernstein rows, the noise measure and the floor at every smoothing, the four silences found while building, 6.1's measurements after against Section 3, 6.2's tests, and 6.3's close-out; Section 5.1 with the Phase 2 full-suite run (1616 passed); the phase-table row done. Basic Shape PRD 1.24, Technical Architecture PRD 1.45. |
| 1.1 | 09-13-26 10:42 | Claude (Claude Code) | Phase 2 done: Section 5 with the two cursors, the four silences found while building, 5.1's tests and targeted runs, and 5.2's close-out; the phase-table row done. Basic Shape PRD 1.23, General UI PRD 2.34, Technical Architecture PRD 1.44. |
| 1.0 | 09-13-26 10:30 | Claude (Claude Code) | Initial notes: the starting state at commit d88f041, the phase table, the three decisions (1 A, 2 the A-then-B rule, 3 B) and the kickoff's seven silences as chosen 09-13-26, five corrections to the kickoff found in the reading, four findings decided with the decisions, the three probes re-measured with the script described, the next required step. Basic Shape PRD 1.22, General UI PRD 2.33, Technical Architecture PRD 1.43. |
