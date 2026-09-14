# Freeform Blur Brush and Highlighter Straightening Implementation Notes

Last Updated: 09-14-26 09:34 · Revision 1.7

Implements the remainder of the Blur / Pixelate tool and the whole of the Highlighter's drawing behaviour from the Blur, Highlighter, and Eyedropper Tools PRD (`PRDs/SnapMock-Blur-Highlighter-Eyedropper-Tools-PRD.html`, version 1.6 at the start), with the General UI PRD (version 2.20) and Technical Architecture PRD (version 1.32) rows they own, in the five phases and the close-out defined by `docs/Freeform-Blur-Highlighter-Kickoff-Prompt.md` (revision 1.0). A session pasting that prompt starts at the first phase not marked done in Section 1. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) governs the standards; the General UI implementation notes (`docs/General-UI-Implementation.md`) hold the walk table of Section 17.2.

Starting state, verified at commit 0029bf7 on 09-11-26 (the kickoff names 035fa5e; 0029bf7 adds only the kickoff prompt and the Basic Shape remainder notes 1.4 pointer): the Blur tool draws Gaussian, Pixelate, and Solid Fill regions over rectangles and ellipses with a corner radius, feathering, an inverted mask, the item's opacity, and a border, cached against `SnapScene.content_revision` and captured through `RenderEngine.render_below`; the Freeform and Whole Layer shapes, `brush_size`, `alpha_mask`, `source_mode`, `source_layer_id`, `ModifyBlurMaskCommand`, and `alpha_mask_data` do not exist. The Highlighter draws the raw mouse points with no smoothing, no simplification, and no straightening; `auto_straighten`, `straighten_threshold`, and `snap_to_axis` exist in neither the item nor the bar nor the file; `HighlightItem` stores its points under `points` and has no point-editing session; the tool's cursor is the crosshair. Point editing is a mode of the Select tool with sessions for the line, the arrow, the arc, the polygon, and the freehand item. The suite at the last code commit (437416d) ran 1358 tests with 13 skipped and one environmental deselection: 1344 passed and one failed, the pre-existing timing-sensitive Zoom tool test, which passes alone. Ruff and mypy are clean.

## 1. Phase status

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The mask (Blur PRD 2.4, 2.5, 2.7, 5.1, 7.1): the decisions and these notes, the mask on the item, close-out | Done | f654fd6, f9e78e1, then the shared close-out commit |
| 2 | The brush (2.3, 2.6, 2.11): painting, the Freeform toggle, the Brush Size control, the brush cursor, the hints, close-out | Done | 60ffd5f, then the shared close-out commit |
| 3 | Brush editing (2.8, 6.1): the editing mode beside point editing, `ModifyBlurMaskCommand`, the panel's Brush size row, close-out | Done | 87be2ce, then the shared close-out commit |
| 4 | Whole Layer, the source modes, and the render (2.4, 2.5, 2.7, 2.10) | Done | 98ec5c9, then the shared close-out commit |
| 5 | The Highlighter (3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.9): drawing and straightening, point editing, close-out | Done | bae3963, then the shared close-out commit |
| Close-out | PRD rows, the General UI notes' Section 23 pointer, the Basic Shape remainder notes' Section 10 pointer, the display checks owed | Done | the shared close-out commit |

## 2. Decisions

### 2.1 Taken at the start of Phase 1 (09-11-26)

Presented with the consequential decision template and chosen by Doug on 09-11-26: the recommendation in every case ("use your recommendations for all of them").

| Decision | Choice | Effect |
|---|---|---|
| 1 What a painted blur region stores | A, the bitmap mask | `BlurItem` gains `alpha_mask`, a `QImage` in canvas pixels aligned to the region's rectangle, where opaque means obscure and transparent means leave alone; it replaces the region's shape in the clip of `_render`, feathering and inverting as the shape does. The rectangle follows the painted bounds, so the transform handles frame the paint rather than the drag. A resize resamples the mask through `scale_geometry`; a rotation leaves it in the item's own coordinates, where the capture already works. The key is `alpha_mask_data` (5.1, 7.1): a base64 PNG inline in `items.json` under 100 KB, and past that a `file:raster/blur_mask_<item_id>.png` reference to a new `raster/` entry in the `.smk` archive, which holds only `manifest.json`, `layers.json`, `items.json`, and one thumbnail today. Each edit stores the mask before and after (`ModifyBlurMaskCommand`, 6.1). The cost: a 1920 by 1080 mask is about 2 MB in memory and 30 to 100 KB per undo entry, and a resize softens the painted edges. The alternative, option B, a stroke list redrawn on demand, would have kept files small and resizes sharp but could not reproduce an eraser's result over overlapping strokes, and departs from 2.5, 7.1, and 6.1, which all describe an image. |
| 2 Where the Highlighter's smoothing comes from | A, 3.2 as written | A moving average over the last five points while drawing, then Ramer-Douglas-Peucker simplification at 2 px on release, the stroke stored as a point list under `path_points` (5.2). A file saved before this work carries the points under `points` and is read as `path_points`. The straightening of 3.3 then works on that list, and the point editing of 3.6 shows two handles for a straightened stroke and the simplified points for a freeform one. The cost: two smoothing pipelines in the code, the Freehand item's fit and this one, and faint facets on a slow curve at a very wide stroke. The alternative, option B, the Freehand item's simplify-then-fit pipeline with the stroke stored as cubic segments, would have shared one pipeline but departs from 5.2's `path_points` and leaves 3.3's arc-length test and 3.6's two handles without a point list to work on. |
| 3 How far the source modes go | A, all three modes of 2.5 | `source_mode` (`all_below`, `active_layer`, `specific_layer`) and `source_layer_id` filter what `RenderEngine.render_below` paints, with a layer dropdown in the Property Panel that follows renames and deletions; a file naming a layer that is gone falls back to `all_below`. Both join the cache key. The cost: the dropdown's upkeep and the fallback. The alternative, option B, the first two modes only, would have left 2.5's third mode unbuilt for the sake of one control. |
| 4 How the Gaussian meets the 100 ms of 2.10 | A, blur a downscaled capture | The Gaussian path captures at half scale, blurs, and scales the result back, at rest as during a drag, since the cache already keys on the zoom rounded to a power of two. About four times faster, so roughly 50 ms at 1000 by 1000 px against the 200 ms measured at the start. Indistinguishable at radius 10 and slightly softer at radius 50, where the content is already unrecognisable. The cost: a departure from 2.10's background thread, recorded as a PRD row, and the quality difference at the largest radii, with measured timings in Section 9. The alternative, option B, the background thread with the progress indicator past 2000 px, would have been the first thread in the code and would show a stale frame while it ran; it stays available if a region ever grows past what A can carry. |

### 2.2 The kickoff's six silences

Each decided as the kickoff recommended, on 09-11-26.

| Silence | Decision |
|---|---|
| Where the mask lives | Canvas pixels, aligned to the region's rectangle. A resize resamples it; a rotation leaves it in the item's own coordinates, where `render_below` already captures. |
| A freeform region's rectangle | The painted bounds, so the transform handles frame the paint rather than the drag. |
| Brush editing beside point editing | Two modes of the Select tool. A double-click on a freeform region enters brush editing, a double-click on a rectangular or elliptical one does nothing, and neither mode starts while the other lasts. |
| The Snagit writer | Keeps skipping a blur region whatever its shape, with its warning; a highlight keeps its present mapping. |
| Auto-straightening and the snap to axis | While drawing only, never retroactively (3.6). The Property Panel shows them for the tool's defaults, not for a placed stroke. |
| The Whole Layer shape | No region to drag: the tool places it with one click and its rectangle is the canvas. |

### 2.3 Corrections to the kickoff, found in the reading

- Blur PRD 2.8 says freeform editing pushes a `ModifyPropertyCommand` storing the old and new `alpha_mask`, while 6.1 defines `ModifyBlurMaskCommand` for exactly that edit. The kickoff names 6.1's command; 6.1 is built and the 2.8 wording is corrected by a PRD row.
- General UI PRD 6.6 carries no row for the brush cursor and none for the marker-tip cursor: it gives every drawing tool the crosshair. Both are additions to 6.6, not corrections of it.
- `BlurTool.status_hint` documents its hints as "2.10", which is the Performance section; the Blur tool's Status Bar Hints are 2.11. A comment fix in Phase 2.
- `HighlightItem` serializes its points under `points`, where 5.2 names `path_points`. Decision 2 renames the key and reads the old one.

### 2.4 Findings decided with the decisions

- The `.smk` archive has no `raster/` directory: `RasterRegionItem` embeds its PNG as base64 inside `items.json`. A mask past 100 KB creates the archive's first `raster/` entry, so `save_project` and `load_project` gain their first side files (Technical Architecture PRD 6.1 already describes the directory).
- `ResizeImageCommand._restore_geometry` is the one walk of the General UI notes' Section 17.2 kind that names item types one by one, and it already restores a blur region's corner radius and feather. The mask joins it in Phase 1.
- `BlurItem.scale_geometry` scales the rectangle, the blur radius, the corner radius, and the feather; the mask is resampled there in the same call.
- `HighlightItem` today keeps `points` as a list of pairs and rebuilds its `QPainterPath` on every added point. The straightening of 3.3 replaces the whole list on release, so the path is rebuilt from the list rather than appended to.

## 3. What Phase 1 built

Step 1, f654fd6: the decisions of Section 2; Blur PRD 1.7, General UI PRD 2.21, Technical Architecture PRD 1.33. Step 2, f9e78e1: `snapmock/items/mask_utils.py` (a Technical Architecture PRD Section 10 row) with `blank_mask`, `scaled_mask`, `encode_mask_png` and `decode_mask_png`, `mask_entry_name`, `encode_mask_field` and `decode_mask_field` carrying the 100 KB rule of 7.1, and `mask_file_reference`; `BlurRegionShape.FREEFORM` and the brush-size constants of 2.5; `BlurItem.alpha_mask` and `ensure_mask`, `region_path` returning the rectangle for a Freeform region, the mask building of `_render` moved into `_mask_for`, `scale_geometry` resampling the mask, and the cache key taking it; `alpha_mask_data` written and read, with `mask_side_file` and `set_mask_png` for the archive; `save_project` writing each side file and `load_project` resolving each `file:` reference, a group's members included; `ResizeImageCommand._restore_geometry` restoring the mask. Step 3, the shared close-out commit.

Silences found while building, decided as the code says:

- The mask is opaque **white** where the region obscures, not the luminance mask 2.5 describes ("White = blur, Black = no blur"): the render clips with `DestinationIn`, which reads alpha. White keeps both readings true at once, since a saved mask is white where it blurs.
- The inverted mask is punched out with `DestinationOut` rather than `Clear`, so an image's alpha subtracts correctly at its antialiased edges; the two agree for a filled path.
- A Freeform region's `shape()` is its rectangle, as 2.9 says, so a click anywhere in the rectangle selects it even where nothing is painted.

## 4. What Phase 2 built

Step 1, 60ffd5f: the Freeform toggle and the Brush Size control of 2.6, shown only while the shape is Freeform; `brush_cursor` in `ui/cursors.py` and `BlurTool.cursor` returning it at the brush's size times the view's zoom; `paint_stroke`, `restore_region`, and `painted_bounds` in `mask_utils.py`; the tool's painting state machine with the working mask over the canvas, the painted bounds on the item after each segment, Shift holding the stroke straight from the press point, strokes accumulating, Enter and a tool switch finalizing, Escape dropping, and an empty region dropped; the hints of 2.11. Step 2, the shared close-out commit.

Silences found while building:

- `brush_size` is a tool property and not an item key: Section 5.1 gives it none, so it is a creation default that the Property Panel's row and the brush-editing session share.
- The working mask covers the canvas, so a stroke that leaves the canvas is clipped to it; a blur outside the canvas would be invisible in every export anyway.
- Shift's straight strokes are built, which 2.11's hint names and 2.3 does not define: the band the straight line last painted is restored from a snapshot taken at the press, so the path the cursor took on the way is not left behind.
- `BlurTool.cancel` ends a live stroke and leaves the painted region standing, and `is_active_operation` is true only while the mouse is down: the view's focus-out and the first Ctrl+Z both call `cancel` on an active operation, and neither should decide the region's fate.
- A brush cursor is capped at 128 screen pixels; past that the circle stops growing, since a cursor cannot.

## 5. What Phase 3 built

Step 1, 87be2ce: `snapmock/commands/blur_commands.py` with `ModifyBlurMaskCommand` and `mask_state`, and `snapmock/tools/blur_edit.py` with `BlurBrushSession` and `brush_editable` (two Section 10 rows); the Select tool's brush-editing mode with its `BRUSH_STROKE` state, the double-click entry, the hidden transform handles, the brush cursor, the 2.11 hint, and the Enter, Escape, tool-switch, and selection-change exits; the main window's Alt momentary eyedropper standing down during the mode; the Property Panel's Brush size row. Step 2, the shared close-out commit.

Silences found while building:

- `ModifyBlurMaskCommand` carries the region's rectangle with the mask, which 6.1 does not name: the rectangle follows the painted bounds, so a stroke past the region moves it and an undo must put it back.
- Painting past the region grows the rectangle in the item's own coordinates and never moves its position, so a rotated region stays where it was placed; erasing never shrinks the rectangle, so the handles do not jump while the brush is working.
- Every press paints wherever it lands, as 2.8 lists only Enter and Escape as the exits; a press away from the region does not leave the mode, which is how a region grows past its own edge.
- Brush editing and point editing never run together: entering one leaves the other, and `handle_escape` asks brush editing first.

## 6. What Phase 4 built

98ec5c9, both steps in one commit (they share `blur_item.py` and `property_panel.py`): `BlurRegionShape.WHOLE_LAYER` and `BlurSourceMode`; `BlurItem.region_rect` giving the canvas for a Whole Layer region, read by `region_path`, `effect_rect`, `boundingRect`, and the mask draw; `source_mode` and `source_layer_id` with their keys and their place in the cache key; `RenderEngine.source_layer_filter` and the two new arguments of `render_below`; the bar's fourth shape toggle and the one-click placement; the Property Panel's Shape list, Source, and Source layer rows; and the half-scale Gaussian of decision 4 with its radius threshold.

Silences found while building:

- Whole Layer joins the bar's Region Shape group as a fourth toggle, which 2.6's three do not list: without it the shape of 2.4 could not be created at all.
- A narrowed capture (`active_layer` or `specific_layer`) leaves the canvas colour out, so a region over a layer with nothing under it obscures nothing rather than painting the canvas colour over the content of other layers.
- `active_layer` follows the scene's active layer, so switching layers changes what such a region obscures; the cache key carries the active layer id for that reason.
- The half-scale Gaussian is used from radius 4 up only. Halving the capture throws away detail finer than two pixels, which 2.10's own acceptance row asks a radius of 1 to keep, so a weak blur still renders at full resolution and still misses the 100 ms target.

## 7. What Phase 5 built

bae3963, both steps in one commit (they share `highlight_item.py` and `point_edit.py`): `moving_average`, `path_length`, `straightness`, and `snap_to_axis` in `core/path_utils.py` with 3.2's and 3.3's numbers in `config/constants.py`; `HighlightItem` rebuilt on `path_points` with `auto_straighten`, `straighten_threshold`, `snap_to_axis`, `set_points`, and `is_straight`, reading the older `points` key; `HighlightTool`'s live smoothing, Shift's straight line and Shift+Alt's 15-degree steps, the release straightening, snapping, simplification, and 4 px minimum, the two bar toggles on the vendored ruler and magnet glyphs, the marker-tip cursor, and the hints of 3.9; the Property Panel's Highlighter section for the tool's defaults; and `HighlightPointSession` in `tools/point_edit.py`.

Silences found while building:

- The straightening reads the smoothed stroke, not the raw points, since 3.2 smooths before 3.3 straightens; a wobble that the moving average flattens is straightened at a tighter threshold than its raw points would allow.
- A stroke that ends where it began has no straight-line distance, so `straightness` gives infinity and it is never straightened.
- With auto-straighten off, a stroke whose wobble is under the 2 px simplification tolerance still comes out as two points. That is simplification, not straightening, and the point editing shows two handles either way.
- `is_straight` is "two points", which is what 3.6 needs to choose between two endpoint handles and the simplified points.
- The Property Panel shows the three straightening properties for the tool's defaults only, in a Highlighter section visible while the tool is active with nothing selected; 3.6 gives them no retroactive effect, so a placed stroke shows no row for them.
- `points` stays on the item as a list of pairs beside `path_points`: the Snagit writer and `ResizeImageCommand` read it, and its Snagit mapping is unchanged.

## 8. Deviations from the PRDs

Each has its PRD row.

- Blur PRD 2.5 and 7.1: the mask is opaque white where the region obscures, read through its alpha; 2.5 describes a luminance mask.
- Blur PRD 2.6: the Region Shape group has four toggles, not three; Whole Layer is one of them, and Brush Size joins the bar.
- Blur PRD 2.8: the mask edit pushes `ModifyBlurMaskCommand` (6.1), not the `ModifyPropertyCommand` 2.8 names, and the command carries the region's rectangle with the mask.
- Blur PRD 2.8: a press away from the region paints rather than leaving the mode; only Enter, Escape, a tool switch, and a selection change leave, as 2.8 lists.
- Blur PRD 2.10: the Gaussian meets the 100 ms target from radius 4 up by rendering at half size; below that it renders at full size and the target is unmet. The background thread, the progress indicator past 2000 px, and the separate half-resolution drag preview are not built.
- Blur PRD 3.4 and 5.2: `straighten_threshold` is clamped to the 1.01 to 1.50 range on the way in, and `brush_size` has no serialization key, so it is a tool setting only.
- Blur PRD 3.6: the Property Panel shows Auto-straighten, Threshold, and Snap to axis for the tool's defaults and not for a placed stroke.
- General UI PRD 5.3 and 6.6: the Blur and Highlighter rows gain the controls above, and 6.6 gains the brush and marker-tip cursor rows it did not carry.
- Blur PRD 5.1: the colours are written `#AARRGGBB`, as the Basic Shape remainder work recorded.

## 9. Tests

New modules: `tests/test_blur_mask.py` (8), `tests/test_blur_brush.py` (8), `tests/test_blur_brush_edit.py` (8), `tests/test_blur_source_modes.py` (5), and `tests/test_highlight_straightening.py` (13). The round-trip tests of `tests/test_blur_modes.py` and `tests/test_blur_mask.py` now read `freeform` and `whole_layer` as themselves, with an unknown shape still reading as a rectangle.

The full suite at the Phase 1 code commit (f9e78e1), run from a scratch worktree while the Phase 2 to 5 work's targeted runs shared the machine, ran 1366 tests with 13 skipped and the one environmental deselection: 1352 passed and one failed, the pre-existing timing-sensitive Zoom tool test (`tests/test_tools/test_zoom_tool.py::test_left_click_zooms_in_and_alt_at_the_release_zooms_out`), which passes alone; the run took 65 minutes. The full suite at the last code commit (bae3963), run alone from a scratch worktree, ran 1400 tests with 13 skipped and the one environmental deselection: 1385 passed and two failed; the run took 69 minutes. Both failures are environmental and both pass alone at that commit: the pre-existing timing-sensitive Zoom tool test, and `tests/test_capture/test_x11.py::test_live_key_press_is_delivered`, which synthesizes a real key event through XTest against the live display and so races with whatever else holds it during a full run. Nothing in `snapmock/capture/` was touched by this work. Ruff and mypy are clean at every commit; the accessibility audit passes over the Blur bar's Brush Size and Whole Layer controls, the Highlighter bar's two toggles, and the new Property Panel rows.

Under load a second Zoom tool test (`test_alt_at_the_press_alone_zooms_out`) also fails and also passes alone; both are the same timing-sensitive pair the Basic Shape remainder notes record.

### 9.1 Measured render times

A 1000 by 1000 px region on this machine, the median of five renders with the cache cleared each time, measured alone:

| Mode | Before this work | After |
|---|---|---|
| Gaussian, radius 1 | about 200 ms | 154 ms (full resolution; 2.10's 100 ms unmet) |
| Gaussian, radius 4 | about 200 ms | 34 ms |
| Gaussian, radius 10 | about 200 ms | 36 ms |
| Gaussian, radius 50 | about 200 ms | 50 ms |
| Pixelate | about 50 ms | 41 ms |
| Solid Fill | about 3 ms | 1 ms |
| Inverted Gaussian over 1920 by 1080 | about 500 ms | 80 ms |

The same measurements while another full-suite run shared the machine were 284, 41, 43, 62, 134, 1, and 95 ms, which is what a loaded machine costs.

## 10. Close-out of the work

Every phase is done. The PRDs stand at Blur PRD 1.8, General UI PRD 2.22, and Technical Architecture PRD 1.34, with the Snagit notes at 1.6 and the General UI notes at 1.35 (Section 23). The Basic Shape remainder notes' Section 10 points here. Phases 2 to 5 were each built and committed in one step rather than the kickoff's several, since each phase's files overlap and the phases were built while the Phase 1 suite ran; the close-outs are written together in this commit after one full-suite run at the last code commit.

Display checks, run by Doug on 09-12-26 over two sessions from a checklist page whose marks and notes were read back. **Every check this work owed is answered and passing:**

| Check | Result |
|---|---|
| The angled marker-tip cursor | Pass, first run: "works perfectly" |
| A straightened highlight: a wobbly stroke flat and horizontal on release | Pass, first run: "worked perfectly" |
| A freeform highlight kept as a curve with its point handles | Pass, second run |
| A painted blur region: the brush cursor at two sizes, strokes accumulating, Enter placing it | Pass, second run |
| A Whole Layer region: the whole canvas from one click | Pass, second run |
| Each source mode: All below, Active layer, Specific layer with its dropdown | Pass, second run |

**The erased region is confirmed as blocked, not failed.** Alt+paint is the eraser's only route (2.8), and on this desktop it cannot reach the canvas: `org.cinnamon.desktop.wm.preferences mouse-button-modifier` reads `<Alt>` (verified 09-12-26), so Cinnamon starts a window move first. The painting and the Enter that place a region both work, so the gap is the modifier alone. The Zoom tool was given right-click as a second route for the same reason and that route is now confirmed working (General UI notes, acceptance row 20); the eraser needs an equivalent. A Blur PRD row and a General UI PRD 12.2 row.

The first run's difficulty finding the Blur tool's Mode and Shape controls was not a fault: a screenshot of 09-12-26 shows every control present with no overflow. On this machine the Tool Options Bar shares one row with the Main Toolbar rather than sitting below it as General UI PRD 5.1 describes; View > Reset Layout puts it back on its own row. Recorded in the General UI notes.

**Next required step:** done. The kickoff this close-out named, `docs/Eyedropper-Blur-Performance-Kickoff-Prompt.md` (revision 1.0), ran on 09-11-26 and 09-12-26 and is complete; its notes are `docs/Eyedropper-Blur-Performance-Implementation.md`. Two things it changed reach back into this work. **2.10 closes at every radius** (its Section 4): the blur itself is cheaper — float32 over all four colour channels in one array, and a direct sum of shifted slices while the box is one or two pixels wide — so a 1000 by 1000 px Gaussian region renders in 55 ms at radius 1 against the 154 ms recorded in Section 9.1 here, and in 11 to 42 ms from radius 4 up against the 34 to 50 ms here. The half-scale capture of decision 4 stays and gains from the same arithmetic. The background thread and the progress indicator past 2000 px are now recorded as a permanent departure rather than a deferral, since the render is fast enough on the main thread at the size 2.10 names and a progress indicator cannot repaint during a synchronous render. Every measured figure in Section 9.1 is therefore superseded by that work's Section 4. **The display checks above are still owed**, and that work adds three of its own: the loupe at each sample size, the loupe near a viewport edge, and the Eyedropper's bar at a narrow window.

## 11. The brush cursor and the zoom

Found by the Freehand remainder work on 09-13-26 and fixed on 09-14-26 (Blur PRD 1.18): the brush cursor of Phase 2 and the brush-editing cursor of Phase 3 are drawn in screen pixels at the brush's size times the zoom, but neither tool listened to the view's `zoom_changed` signal, so a zoom left the circle at its old size until the tool was activated again or its bar changed. The Blur tool now connects to the signal in `activate` and disconnects in `deactivate`, re-drawing the cursor while the region shape is Freeform; the Select tool does the same while a brush-editing session lasts. The pattern is the Freehand tool's (`docs/Freehand-Remainder-Implementation.md`, Section 5). Two tests in `tests/test_blur_brush.py` and `tests/test_blur_brush_edit.py`. The full suite at the fix's commit (cee0740), run alone from a scratch worktree between 01:08 and 02:45 on 09-14-26: **1634 passed, 0 failed, 13 skipped, 1 deselected, in 1 hour 37 minutes.**

## 12. The display run of 09-14-26

Run by Doug between 08:57 and 09:31 from the checklist page `SnapMock Blur and Eyedropper Display Checks`, whose marks were read back, against the working tree at c020337. Of this work's checks: **the painted region passes again** (two strokes adding up, Enter placing them, the Edit menu reading Undo Add BlurItem), **the Whole Layer region and all three source modes pass again**, and **the erased region passes for the first time**, on the only route 2.8 gives it: with Cinnamon's window-move gesture handed to the Super key for the check (`gsettings set org.cinnamon.desktop.wm.preferences mouse-button-modifier '<Super>'`, and back to `'<Alt>'` afterwards), Alt+paint inside brush editing erased the smear along the dragged path and the window stayed put. Section 10's "confirmed as blocked" is therefore a desktop setting, not a fault, and the eraser needs no second route for a user who moves the gesture; whether it should have one anyway is the Blur PRD's question, as before. The Multiply highlight passes again, as the Vector Item Properties notes recorded on 09-12-26.

Two notes Doug left. On the Enter that ends brush editing: "It remains the blur tool." Headlessly, after the same Enter the session is over, the viewport's cursor is the arrow, the active tool is the Select tool, and the status bar reads the Select tool's idle line; not reproduced, and what stayed on the display is asked. On New Layer (Ctrl+Shift+N): "Layer 1 remained active." Reproduced: `AddLayerCommand` adds the layer above the active one and leaves the active layer where it was, and the Layers panel's highlight stays with it; General UI PRD Section 7 says only "create a new empty annotation layer above the active layer" and is silent on activation. Raised with Doug; not this work's row.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.7 | 09-14-26 09:34 | Claude (Claude Code) | Section 12: the display run of 09-14-26. The erased region passes with the desktop gesture handed to Super, the painted region and Whole Layer with its source modes pass again; two notes, one not reproduced and one a New Layer silence raised with Doug. |
| 1.6 | 09-14-26 02:46 | Claude (Claude Code) | Section 11: the full suite at the fix's commit, 1634 passed, whole. |
| 1.5 | 09-14-26 01:08 | Claude (Claude Code) | Section 11: the brush and brush-editing cursors follow the zoom. Blur PRD 1.18. |
| 1.4 | 09-12-26 10:35 | Claude (Claude Code) | Section 10: the second display run of 09-12-26. Every check this work owed now passes — the painted region, Whole Layer, all three source modes, and the freeform highlight's handles joining the marker-tip cursor and the straightened highlight. The erased region is confirmed blocked by Cinnamon's Alt gesture rather than failing, and the Tool Options Bar difficulty is confirmed to have been a layout question, not a missing control |
| 1.3 | 09-12-26 00:23 | Claude (Claude Code) | Section 10: the kickoff this close-out named is complete, and what it changed here — 2.10 now closes at every radius by a cheaper blur, so the measured figures of Section 9.1 are superseded, and the background thread and progress indicator become a permanent departure; the display checks stay owed, with three of that work's added. |
| 1.2 | 09-11-26 22:41 | Claude (Claude Code) | The next required step names the kickoff written at Doug's request: `docs/Eyedropper-Blur-Performance-Kickoff-Prompt.md` (revision 1.0). |
| 1.1 | 09-11-26 22:36 | Claude (Claude Code) | Every phase done and the work closed out: the phase table, Sections 3 to 7 (what each phase built and the silences found while building), Section 8's deviations, Section 9's tests and the two suite runs with the measured render times of 9.1, and Section 10's close-out with the display checks owed and the next required step. Blur PRD 1.8, General UI PRD 2.22, Technical Architecture PRD 1.34, Snagit notes 1.6, General UI notes 1.35 (Section 23), Basic Shape remainder notes 1.5. |
| 1.0 | 09-11-26 20:14 | Claude (Claude Code) | Initial notes: the starting state at commit 0029bf7, the phase table, the four decisions (1 A, 2 A, 3 A, 4 A) and the kickoff's six silences as chosen 09-11-26, four corrections to the kickoff found in the reading, four findings decided with the decisions. Blur PRD 1.7, General UI PRD 2.21, Technical Architecture PRD 1.33. |
