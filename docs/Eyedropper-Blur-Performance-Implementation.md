# Eyedropper and Blur Performance Implementation Notes

Last Updated: 09-14-26 09:34 · Revision 1.11

Implements the Eyedropper's Section 4 whole and the Blur / Pixelate tool's remaining Performance rows from the Blur, Highlighter, and Eyedropper Tools PRD (`PRDs/SnapMock-Blur-Highlighter-Eyedropper-Tools-PRD.html`, version 1.8 at the start), with the General UI PRD (version 2.22) and Technical Architecture PRD (version 1.34) rows they own, in the five phases and the close-out defined by `docs/Eyedropper-Blur-Performance-Kickoff-Prompt.md` (revision 1.0). A session pasting that prompt starts at the first phase not marked done in Section 1. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) governs the standards; the General UI implementation notes (`docs/General-UI-Implementation.md`) hold the walk table of Section 17.2. Finishing this work closes the Blur, Highlighter, and Eyedropper Tools PRD.

Starting state, verified at commit 1bafbad on 09-11-26 (the kickoff names 314beb9; 1bafbad adds only the kickoff prompt): the Eyedropper samples one pixel on a click by rendering a 1 by 1 scene region through `QGraphicsScene.render`, stores it as `picked_color`, and bumps `pick_serial`; there is no drag, no live preview, no loupe, and no sample size. Its Tool Options Bar is the picked swatch, the hexadecimal text, the red-green-blue text, and the Apply to Stroke and Apply to Fill buttons of General UI PRD 5.3. The Alt momentary eyedropper of General UI PRD 12.2 works and stands down while the Zoom tool is active, while a drag is in progress, and while the Select tool's point-editing or brush-editing mode lasts. The colour picker's eyedropper button delivers one pick to the picker and to the bar and returns to the previous tool. The Blur / Pixelate tool is complete but for 2.10: the Gaussian captures and blurs at half size from radius 4 up and renders at full size below it, and there is no background thread anywhere in the code. The suite at the last code commit (bae3963) ran 1400 tests with 13 skipped and the one environmental deselection: 1385 passed and two failed, both environmental and both passing alone. Ruff and mypy are clean.

## 1. Phase status

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The Blur tool's performance (Blur PRD 2.10, 8.1): the decisions and these notes, the render's remaining rows, close-out | Done | 668d0c1, b218275, then this commit |
| 2 | Sampling (4.2): the four sample sizes, the arithmetic mean, the press-and-drag live sample | Done | this commit |
| 3 | The preview loupe (4.3) | Done | this commit |
| 4 | The properties and the Tool Options Bar (4.4, 4.5) | Done | this commit |
| 5 | Applying the colour, the Alt mode, and the hints (4.6, 4.7, 4.8, 6.2) | Done | this commit |
| Close-out | PRD rows, the General UI notes' Section 24 pointer, the freeform blur notes' Section 10 pointer, the display checks owed | Done | this commit |

## 2. Decisions

### 2.1 Taken at the start of Phase 1 (09-11-26)

Presented with the consequential decision template and chosen by Doug on 09-11-26: the recommendation in every case ("use all of your recommendations"). Decision 4's options are not the kickoff's, because the measurement the kickoff asked for retired its option B; the three options presented are recorded below as they were put.

| Decision | Choice | Effect |
|---|---|---|
| 1 Where the preview loupe is drawn | B, a widget over the viewport | The loupe is a `QWidget` child of the canvas view's viewport, raised above it, positioned in widget coordinates. Every measurement of 4.3 is in screen pixels — a 120 pixel circle, a 20 pixel offset, a 40 by 24 pixel swatch, 8 times magnification, a 2 pixel border — and the repositioning rule is a screen-edge rule, so the arithmetic is the viewport rectangle's and not the scene's. It is never a scene item, so no render can capture it. The cost: a second widget inside the viewport, which the focus frame painted in `SnapView.paintEvent` and the panel-collapse behaviour of General UI PRD 15.2 have to leave alone. The alternative, option A, `SnapView.drawForeground` beside the grid, the guides, the crosshairs, and the layer hover outline, would have added no widget but would have computed every position in scene coordinates, which the zoom changes under you, and drawn the border and the shadow by hand. Technical Architecture PRD 3.9 gains the row either way. |
| 2 What the Eyedropper samples | A, the canvas composite through an item walk | The sample and the loupe read an image built as `RenderEngine.render_below` builds one: the canvas colour where the canvas covers the sampled area, then every visible annotation item in stacking order, walking `SnapGraphicsItem` instances only, as 4.2 asks ("all visible layers composited together, including the canvas background"). The grid, the guides, the crosshairs, the marching ants, the crop dimming, the handles, the pasteboard, and the loupe itself are excluded by construction, because none of them is one of those items. Outside the canvas the sample is transparent. The cost: a new sampling render path beside the four `RenderEngine` methods, and a rule about what counts as canvas content that must stay correct as item kinds arrive. The alternative, option B, the viewport's pixels, costs nothing to produce but includes every overlay. |
| 3 How far the Eyedropper's Tool Options Bar goes | A, Blur PRD 4.5 in full | The sampled swatch, the colour value field with click-to-copy, the Color Format dropdown over hexadecimal, red-green-blue, and hue-saturation-lightness, the four Sample Size toggles, the Apply Target dropdown, the Copy to Clipboard toggle, and the Color History row of eight swatches. The two Apply buttons go, replaced by the Apply Target dropdown and the apply-on-sample rule of 4.6, since each tool's own PRD owns its details. The cost: the widest bar in the application, General UI PRD 5.3's Eyedropper row corrected twice (the controls, and the removal of the buttons the General UI Phase 4 work built), and the Eyedropper joining the preset and theme model that 5.2 says has nothing to capture for it. The alternative, option B, the General UI row plus Sample Size and Color Format only, would have left 4.4, 4.5, and three 8.3 rows open for the sake of three controls. |
| 4 How the Blur tool's Performance rows close | C, a cheaper blur | The blur itself is made faster, so 2.10's 100 ms is met at every radius at full resolution with no thread, no stale frame, and no loss of detail. 2.10's background thread and its progress indicator past 2000 pixels stay a permanent departure, and a progress indicator is unreachable without a thread in any case, since it cannot repaint during a synchronous render. The cost: `blur_image` is shared with every item's drop shadow, so the change touches every shadow render; float32 replaces float64 and must be pinned by test; and a 2000 by 2000 pixel region is four times the work, so very large regions stay slow. The alternative, option A, the background thread of 2.10, covers every region size but is the first thread in the code, needs teardown on document close, shows a stale frame while it runs, and would give Technical Architecture PRD 9.1 its first concurrency row; it stays available on its own kickoff if a display check ever finds a region option C cannot carry. The kickoff's option B, a capture cache with a permanent departure, is retired by the measurement of Section 2.4. |

### 2.2 The kickoff's six silences

Each decided as the kickoff recommended, on 09-11-26.

| Silence | Decision |
|---|---|
| The loupe over the pasteboard | Beyond the canvas edge the loupe shows the checkerboard and the swatch reads "transparent", as 4.3 and the 8.3 row say for transparent canvas; the pasteboard's own grey is never sampled. |
| `ApplyEyedropperColorCommand` (6.2) | Built, and it replaces the `MacroCommand` of `ModifyPropertyCommand`s the Apply buttons push today, since 6.2 defines exactly that command with its own description. The undo entry's text changes and the behaviour does not. |
| The Eyedropper in the preset and theme model | It joins, so General UI PRD 5.2's line that "Select, Stamp, Blur, Eyedropper, Pan, and Zoom have no options to capture" is corrected by a row. `sample_size`, `color_format`, `apply_target`, and `copy_to_clipboard` are captured; `last_sampled_color` and the colour history are not. |
| The colour history | Session state, written to no settings file, which 7.3 offers and does not require. Eight entries, newest first, de-duplicated by alpha-red-green-blue value, as the colour picker's recent-colour list already does with twelve. |
| Alt during inline text editing | Alt stands down (4.7). Whether it already does is checked in Phase 5 before anything is built for it; if a focused editor already swallows the key, the row is recorded as met and a test pins it. |
| A sample size larger than one pixel | The arithmetic mean of the red, green, and blue channels of every pixel in the area, as 4.2 says, ignoring alpha in the average and reporting the area transparent only when every pixel in it is. |

### 2.3 Corrections to the kickoff, found in the reading

- The kickoff names "Section 7.1's overlay order" in the Technical Architecture PRD. Section 7 is Cross-Platform Considerations and 7.1 is Target Platforms; the overlay order is Section 3.9's Rendering Pipeline, which places a tool's temporary overlays "on a dedicated overlay layer that is always on top". Section 3.9 carries this work's rows. The Check for Updates work recorded the same class of error against the same document.
- The Eyedropper's present sample is wrong over an empty canvas. It renders through `QGraphicsScene.render`, and the canvas colour is painted by nothing in the scene: `RenderEngine.render_below` and `render_to_image` each fill it explicitly, and the view paints the pasteboard and the checkerboard in `SnapView.drawBackground`. A click on empty canvas over a white canvas colour therefore reports transparent black, against 4.2. Decision 2 fixes this in Phase 2.
- `SelectionOverlay` and `CropOverlay` are scene items with z-values near one million, so a sample taken through `QGraphicsScene.render` during the Alt momentary mode from the Crop or Raster Selection tool would read the marching ants or the crop dimming. The item walk of decision 2 excludes both by construction, since neither is a `SnapGraphicsItem`.

### 2.4 The measurement decision 4 asked for

Taken on this machine before the decisions, on a 1000 by 1000 pixel Gaussian blur region over a striped screenshot, the median of five renders with the cache cleared each time. It retires the kickoff's option B and produced option C.

| What | Radius 1 | Radius 2 | Radius 4 | Radius 10 |
|---|---|---|---|---|
| The whole render | 163 ms | 161 ms | 37 ms | 40 ms |
| of which the capture (`render_below`) | 0.6 ms | 0.7 ms | 0.3 ms | 0.2 ms |
| of which the blur (`blur_image`) | 159 ms | 159 ms | 32 ms | 35 ms |
| of which the mask | 0.3 ms | 0.2 ms | 0.2 ms | 0.3 ms |

The capture is under one percent of the time, so the capture cache the kickoff proposed saves nothing: the freeform blur work's expectation that "the capture, not the blur, is most of the time" is wrong. The blur is twelve whole-array passes — four colour channels, three box passes each, every pass a pad, two cumulative sums, and a concatenation over a float64 array — and its cost follows the pixel count, not the radius, which is why halving the capture gave the fourfold gain the freeform blur work measured.

Three changes were then measured over a 1004 by 1004 pixel capture, the median of five runs each, against today's 160 to 180 ms:

| Variant | Radius 1 | Radius 2 | Radius 3 | Radius 6 | Radius 10 | Radius 50 |
|---|---|---|---|---|---|---|
| Today (float64, one channel at a time, cumulative sums) | 181 ms | 160 ms | 171 ms | — | 173 ms | — |
| float32, all four channels in one array, cumulative sums | 106 ms | 106 ms | 112 ms | 110 ms | 110 ms | — |
| float32, all four channels, a direct sum of shifted slices | 67 ms | 64 ms | 86 ms | 134 ms | 174 ms | 666 ms |
| float32, three channels, cumulative sums | 79 ms | 79 ms | 81 ms | 80 ms | 81 ms | 86 ms |

The direct sum of shifted slices wins while the box is one or two pixels wide, which is radius 3 and under; from a box of four up the cumulative sum wins, and its cost is flat in the radius. So Phase 1 step 2 picks per box size. The float32 result is pixel-identical to today's float64 result at radius 2 along a full row, so the existing pixel tests stand.

## 3. What Phase 1 built

Step 1, 668d0c1: the decisions of Section 2.1, the silences of 2.2, the corrections of 2.3, and the measurement of 2.4; Blur PRD 1.9, General UI PRD 2.23, Technical Architecture PRD 1.35.

Step 2, this commit: decision 4, option C, in `snapmock/items/shadow.py`. `blur_image` converts the capture to float32 rather than float64 and blurs all four colour channels in one three-dimensional array rather than one plane at a time. `_box_blur`, which blurred both axes of one plane, is replaced by `_box_pass(planes, radius, axis)`, which blurs one axis of the stack and chooses between two arithmetics: at a box radius of `_DIRECT_BOX_MAX` (two) or under it sums the shifted slices directly, adding each window in place with no padded copy, and above it keeps the cumulative sum over a padded array. Nothing else changed: the zero padding, the three passes, the `radius / 1.7` box, the `np.rint` rounding, and the under-half-a-pixel copy are all as they were.

Silences found while building:

- The two arithmetics agree exactly while the box is narrow and within one level of 255 where the cumulative sum runs, since float32 puts a few values on the other side of a rounding boundary. A test pins the one-level bound. Every existing pixel test over the blur and the shadow passes unchanged.
- The direct sum is written without `np.pad`. Padding a 1000 by 1000 pixel four-channel float32 array costs more than the sum it feeds: dropping it took radius 1 from 63 ms to 49 ms over a 1004 by 1004 pixel capture.
- The half-scale capture of radius 4 and up stays. It is now the faster of two fast paths rather than the only one, and at radius 4 the halved image takes the narrow-box arithmetic as well, which is why a 1000 by 1000 pixel region at radius 4 fell from 37 ms to 11 ms.
- `blur_image` is shared with every item's drop shadow and with the feather of a blur region's mask, so both are faster by the same arithmetic. Neither changes its appearance.

## 4. Measured render times

A 1000 by 1000 pixel region over a striped screenshot on this machine, the median of five renders with the cache cleared each time. The "before" column is the state the freeform blur work left (its Section 9.1) re-measured in this session; the load average was about 2 of 16 cores throughout, so both columns carry the same overhead.

| Mode | Before this work | After |
|---|---|---|
| Gaussian, radius 1 | 163 ms (2.10's 100 ms unmet) | **55 ms** |
| Gaussian, radius 2 | 161 ms (unmet) | **57 ms** |
| Gaussian, radius 3 | about 190 ms (unmet) | **72 ms** |
| Gaussian, radius 4 | 37 ms | 11 ms |
| Gaussian, radius 10 | 40 ms | 29 ms |
| Gaussian, radius 50 | 50 ms | 42 ms |
| Pixelate | 41 ms | 37 ms |
| Solid Fill | 1 ms | 1 ms |
| Inverted Gaussian, radius 10, over 1920 by 1080 | 80 ms | 59 ms |

Where the time went at radius 1 before the change: the capture 0.6 ms, the blur 159 ms, the mask 0.3 ms of a 163 ms render. That is the measurement that retired the kickoff's option B.

The blur itself, over a 1004 by 1004 pixel capture, the median of five runs: 151 ms before against 49 ms after at radius 1 and 2, 161 ms against 66 ms at radius 3, and 159 ms against 102 to 109 ms at radius 10 and 50, where the wide-box cumulative sum runs. The blur region never takes the wide-box path at full resolution, since radius 4 and up captures at half size.

Past 2.10's stated 1000 by 1000 pixel region the render is still linear in the pixel count: a 1920 by 1080 pixel region at radius 1 takes 129 ms, and a 2000 by 2000 pixel region 287 ms at radius 1 and 117 ms at radius 10. 2.10's progress indicator past 2000 pixels is a departure and stays one, since it cannot repaint during a synchronous render.

### 4.1 The loupe's cost per mouse move

4.3 asks that the loupe's capture and render happen every frame at sixty frames a second, and the 8.3 row asks the same. Measured on this machine over a 1920 by 1080 pixel screenshot with fifty annotations over it, thirty moves, both the loupe's fifteen by fifteen pixel capture and the sampled colour's own render included: **0.36 ms** per update at a one-pixel sample and **0.45 ms** at an eleven-pixel one, the worst of thirty being 1.8 ms. A frame at sixty frames a second is 16.7 ms, so the loupe has two orders of magnitude of headroom and needs no capture cache.

### 4.2 Phase 1 close-out

Blur PRD 1.10 carries the Built row for 2.10 and 8.1 and the Departure row for what stays: 2.10's background-thread re-render, its progress indicator past 2000 pixels, and its separate half-resolution drag preview are not built, and the first two are now permanent rather than deferred. The render is fast enough on the main thread at the region size 2.10 names; a progress indicator cannot repaint during a synchronous render, so it cannot exist without the thread; and the drag preview needs no separate path, since the Gaussian already captures at half size from radius 4 up and the full-resolution radii render in 55 to 72 milliseconds. Option A, the thread, stays available on its own kickoff if a display check ever finds a region this cannot carry.

The 8.1 performance rows are met, the Gaussian inside 100 ms and Pixelate inside 50 ms, and Section 2 of the Blur PRD has no open row left.

**Next required step:** Phase 2, sampling (Blur PRD 4.2) — what the Eyedropper reads per decision 2, `sample_size` with its four values and the arithmetic mean, and a press-and-drag that samples continuously and applies the colour under the cursor at the release.

## 5. What Phase 2 built

One commit, both steps together, as the freeform blur work's phases were: the sampling and its close-out share the Blur PRD rows.

`RenderEngine.render_sample(rect)` (Technical Architecture PRD 3.9): the composite of 4.2 over the sampled area in scene coordinates at canvas scale — the canvas colour where the canvas covers the area, then every visible `SnapGraphicsItem` in stacking order, each with its own scene transform and effective opacity — clipped to the canvas. `SAMPLE_SIZES` and `DEFAULT_SAMPLE_SIZE` in `config/constants.py`. In `tools/eyedropper_tool.py`: `sample_rect` and `average_color` as module functions, `sample_size` reading `creation_defaults`, `sample_image` and `sample_at`, a preview callback beside the pick callback, and the press, move, release, and cancel of the drag. In `ui/tool_options_bar.py`: the preview callback wired to the colour display, and "transparent" in place of black for a sample with no alpha.

Silences found while building:

- A vector item's edge is antialiased, so a sample straddling one is a blend of the two colours and not either of them. That is correct — 4.2 names antialiased areas as a reason for the wider sample sizes — but it means the tests that check the arithmetic use a raster item, whose pixels land one for one on the canvas.
- The press applies nothing. 4.2 reads as though a click samples at the press and a drag samples at the release; a click is a press and a release at one place, so applying at both would apply twice. The release is the one that applies, and the press and the moves preview.
- `pick_serial` counts applied samples only. The momentary Alt mode compares the serial before and after to tell whether a pick happened, so a preview must not move it.
- The Eyedropper's first creation default puts it into `ToolThemeManager.tool_ids`, which is every tool that has any, so the preset dropdown appears on its bar from this phase rather than from Phase 4. That is the silence the kickoff decided; General UI PRD 5.2's Eyedropper line is corrected in the close-out of the work.
- `render_sample` walks every item rather than the top-level items, as `render_below` does: a group paints nothing itself and each member carries the group's transform in its own `sceneTransform`, so walking all of them paints each once, in the right place.

**Next required step:** Phase 3, the preview loupe (Blur PRD 4.3) — a 120 pixel circular window at 8 times magnification per decision 1, as a widget over the canvas view's viewport.

## 6. What Phase 3 built

One commit, both steps together. `snapmock/ui/loupe_overlay.py` (Technical Architecture PRD Section 10): `LOUPE_DIAMETER`, `LOUPE_MAGNIFICATION`, `LOUPE_CAPTURE_SIDE`, `LOUPE_CURSOR_OFFSET`, `LOUPE_BORDER_WIDTH`, and the swatch's size from 4.3; `circle_rect`, `swatch_rect`, `loupe_size`, and `loupe_position` as module functions, so the geometry can be tested without painting; and `LoupeOverlay`, a widget parented to the canvas view's viewport that paints the shadow, the checkerboard, the magnified capture, the sampled area's outline, the crosshair, the border, the swatch, and the value text. In `tools/eyedropper_tool.py`: `loupe`, `update_loupe`, and `hide_loupe`, called from the press, every move, the release, `cancel`, and `deactivate`.

Silences found while building:

- The loupe hides itself when the pointer leaves the viewport, through an event filter it installs on its own parent. Nothing in the view or in `BaseTool` had to change for it, and a stale loupe cannot be left behind over a viewport the cursor has left.
- The loupe follows a hover, not only a drag: 4.3 says it follows the cursor while the tool is active. A hover move updates the loupe and is still reported unconsumed, so the view's own hover handling is untouched.
- 4.3 asks for a drop shadow and decision 1 offered a graphics effect. It is painted instead, as a radial fade beneath the circle: a graphics effect on a translucent child widget is unpredictable across platforms, and the fade is deterministic and testable.
- The magnification is of canvas pixels, not screen pixels, at every zoom. 4.3 asks that each pixel be an 8 by 8 block and that the pixel grid show, which is only true of the canvas's own pixels.
- The very centre of the circle is the crosshair, so a test that reads the magnified content reads it a little off centre.
- The checkerboard uses the theme's own checkerboard colours, as the canvas does, rather than 4.3's unnamed pattern.

**Next required step:** Phase 4, the properties and the Tool Options Bar (Blur PRD 4.4, 4.5) — the eight-control bar of decision 3, option A.

## 7. What Phase 4 built

One commit, both steps together. In `config/constants.py`: `ColorFormat`, `ApplyTarget`, `DEFAULT_APPLY_TARGET`, and `COLOR_HISTORY_MAX`, with the two enumerations registered in the Tool Theme codec's `_ENUM_TYPES` so a preset and a theme can store them. In `tools/eyedropper_tool.py`: `format_color_value` as a module function, the `color_format`, `apply_target`, `copy_to_clipboard`, and `last_sampled_color` properties of 4.4, the colour history with `push_history`, `set_last_sampled_color`, and `value_text`. In `ui/tool_options_bar.py`: `EYEDROPPER_SWATCH_SIZE`, `HISTORY_SWATCH_SIZE`, `_ValueField`, `_color_pixmap`, `_sample_size_icon`, and `_to_clipboard`; `_build_eyedropper_controls` rewritten as 4.5's row; `_write_eyedropper` and `_refresh_eyedropper`; `_show_sampled_color`, `_on_color_applied`, `show_picked_color`, `_copy_value_to_clipboard`, and `_reapply_history`; and `_apply_picked` now taking the colour rather than reading it back from the tool.

Silences found while building:

- 4.4's own HSL example is inexact. `#4A90D9` has a hue-saturation-lightness saturation of 65 percent, not the 63 percent 4.4 prints: the difference between 217 and 74 over 219. The bar writes the standard value and the PRD row records the difference.
- `apply_target` carries five values and 4.5's dropdown offers three. The other two, the highlight colour and the badge colour, are what 4.7's momentary Alt mode sets on the Highlighter and the Numbered Step tool, which chooses by the active tool rather than from this dropdown.
- An empty Color History slot is hidden, not shown doing nothing: General UI PRD 1.3 forbids a disabled control, and a visible swatch with no colour behind it would be one.
- A pick routed through the colour picker's eyedropper button is a sample, so it sets `last_sampled_color` and joins the history. Without that, any later refresh of the bar would show the tool's older colour instead.
- The clipboard toggle copies the hexadecimal value, as 4.4 says; a click on the colour value field copies the value in whichever format is shown, since that is what the field reads.
- The bar's `_apply_picked` takes the colour as an argument now. It had read `tool.picked_color` back, which only worked because the tool sets that before calling the callback; the history's re-apply route has no such ordering.

**Next required step:** Phase 5, applying the colour, the Alt mode, and the hints (Blur PRD 4.6, 4.7, 4.8, 6.2).

## 8. What Phase 5 built

One commit, both steps together. `snapmock/commands/eyedropper_commands.py` (Technical Architecture PRD Section 10 and 3.7) with `ApplyEyedropperColorCommand`. In `tools/tool_manager.py`: `previous_tool_id` and `last_tool_id`, the latter recorded on every switch to a different tool. In `tools/eyedropper_tool.py`: `_TARGET_LABELS`, `_rgb_text`, `momentary_from` and `set_momentary_from`, the four hints of 4.8 in `status_hint`, and `show_hint`, pushed from the press, each move, and the release. In `ui/tool_options_bar.py`: `_apply_picked` split into the three routes of 4.6, `_apply_to_previous_tool`, `_apply_to_selection` (through the command), and `_apply_to_every_tool`. In `main_window.py`: `MOMENTARY_PICK_KEYS` and `momentary_pick_key`, the Alt press setting the momentary context and showing the loupe under the pointer, the Alt release clearing both, `_apply_momentary_pick` using the per-tool property, and the colour picker's route calling the bar's `show_picked_color` rather than its pick callback, so a picker pick is shown and remembered without being applied to the Eyedropper's own target.

Silences found while building:

- **4.7's mid-drag row cannot be built.** Its second behaviour detail asks that Alt during a drawing operation sample a colour; General UI PRD 12.2 gives Alt "draw from center" while drawing, and that is built and relied on by every drag-drawn shape, by point editing, where Alt breaks a curve's continuity, and by brush editing, where Alt erases. One key cannot carry both meanings, so Alt keeps its drawing meaning while a drag lasts and the momentary eyedropper stands down, as before this work. Both PRDs carry the row. This is the one row of Section 4 that is not built, and it is a permanent departure rather than a deferral.
- Alt already stood down during inline text editing. The Text tool reports an open editor as an active operation and the Alt branch refuses one, so the row of 4.7 was met before this work; a test now pins it, as the kickoff's silence said it would.
- 4.6's three routes are not alternatives. A previous tool and a selection can both exist, and they answer different questions — what the next item will look like, and what the selected items look like now — so the first two routes both run and the third runs only when neither did.
- 4.6's "application's active `stroke_color`" has no single home: the application keeps a stroke colour per tool. Route three writes the property on every tool that carries it, which is what the Apply buttons did.
- The momentary Alt mode ignores `apply_target`. 4.7 names the property per tool, which is why `apply_target` carries five values and 4.5's dropdown offers three.
- A pick routed through the colour picker is shown in the bar and remembered in the history, and it is not applied to the Eyedropper's target: the user opened the picker to set one particular colour, and applying it twice would be a surprise.

**Next required step:** the close-out of the work — the PRD rows for what was built and where it departs, the General UI notes' Section 24 pointer, the freeform blur notes' Section 10 pointer, the display checks carried forward, and a full-suite run.

## 9. Deviations from the PRDs

Each has its PRD row.

- **Blur PRD 2.10**: the background-thread re-render and the progress indicator past 2000 pixels are not built and are now permanent, not deferred. The render is fast enough on the main thread at the 1000 by 1000 pixel region 2.10 names, and a progress indicator cannot repaint during a synchronous render. The separate half-resolution drag preview is unnecessary: the Gaussian already captures at half size from radius 4 up and the full-resolution radii render in 55 to 72 milliseconds. Past 2.10's stated region size the render stays linear in the pixel count — 129 milliseconds for a 1920 by 1080 pixel region at radius 1, 287 for a 2000 by 2000 one.
- **Blur PRD 4.2 and 4.4**: `sample_size` is stored as the side of the square in canvas pixels (1, 3, 5, 11) where 4.4 names an enumeration of "1x1" and the rest; a transparent pixel is left out of the colour mean and the result's alpha is the mean over the whole area, which 4.2 does not specify; and both a click and a drag apply at the release, since a click is a press and a release at one place.
- **Blur PRD 4.4 and 4.5**: 4.4's HSL example for `#4A90D9` reads 63 percent saturation where the standard value is 65 (143 of 219), and the bar writes 65. The Apply Target dropdown offers 4.5's three values of the five 4.4 gives the property; the other two are reached by 4.7's momentary mode. The Copy to Clipboard toggle copies the hexadecimal value, as 4.4 says, while a click on the value field copies the value in whichever format is shown. An empty Color History slot is hidden rather than shown, because General UI PRD 1.3 forbids a control that does nothing.
- **Blur PRD 4.6**: the three routes are applied together rather than as alternatives, since a previous tool and a selection can both exist and they answer different questions; and 4.6's "application's active `stroke_color`" is written as the property on every tool that carries it, the application having no single one.
- **Blur PRD 4.7**: the mid-drag row is not built and is permanent. General UI PRD 12.2 gives Alt "draw from center" while drawing, which is built and relied on by every drag-drawn shape, by point editing, and by brush editing; one key cannot carry both meanings, so Alt keeps its drawing meaning and the momentary eyedropper stands down mid-drag. The momentary mode also ignores `apply_target`, since 4.7 names the property per tool.
- **Blur PRD 4.3**: the drop shadow is painted as a radial fade rather than through a graphics effect, and the checkerboard uses the theme's own colours.
- **General UI PRD 5.2 and 5.3**: the Eyedropper has creation defaults and so a preset dropdown, where 5.2 lists it among the tools with nothing to capture; and its 5.3 row is the Blur PRD's bar of 4.5, the two Apply buttons removed.

## 10. Tests

New modules: `tests/test_blur_performance.py` (3), `tests/test_eyedropper_sampling.py` (13), `tests/test_eyedropper_loupe.py` (10), `tests/test_eyedropper_bar.py` (10), and `tests/test_eyedropper_apply.py` (13). `tests/test_tool_options_bar.py` reads the new bar in place of the Apply buttons, and `tests/test_color_picker.py`'s pick test sends the release the colour now lands on. The accessibility audit passes over the Eyedropper's bar, whose every control carries an accessible name; the loupe carries one too, though it is transparent to mouse events and takes no focus.

A targeted run over the ten modules this work touches — the five new ones, the bar, the colour picker, the navigation keys, the cursors, the freehand point edit, and the blur brush edit — passes 102 tests at the Phase 5 commit.

The full suite at the Phase 1 code commit (b218275), run from a scratch worktree while this work's targeted runs shared the machine, ran 1403 tests with 13 skipped and the one environmental deselection: 1389 passed and one failed, the pre-existing timing-sensitive Zoom tool test (`tests/test_tools/test_zoom_tool.py::test_left_click_zooms_in_and_alt_at_the_release_zooms_out`), which passes alone; the run took 66 minutes. The full suite at the close-out commit (8a017bb), run alone from a scratch worktree, ran 1450 tests with 13 skipped and the one environmental deselection: **1436 passed and one failed**, the pre-existing timing-sensitive Zoom tool test (`tests/test_tools/test_zoom_tool.py::test_left_click_zooms_in_and_alt_at_the_release_zooms_out`), which passes alone at that commit — its five tests pass in 2.6 seconds on their own. The run took 67 minutes. Nothing in the Zoom tool was touched by this work. A run at the Phase 5 commit (9594c8d) was stopped at 9 percent and restarted at the close-out commit, because reviewing the phase's own code found the Color History's hidden swatches leaving their slots in the bar: the swatch was hidden but not its toolbar action, so eight empty slots stayed on the widest bar in the application. The close-out hides the action instead. Ruff and mypy are clean at every commit.

## 11. Close-out of the work

Every phase is done. The PRDs stand at Blur, Highlighter, and Eyedropper Tools PRD 1.14, General UI PRD 2.25, and Technical Architecture PRD 1.37, with the General UI notes at 1.36 (Section 24) and the freeform blur notes at 1.3 (Section 10). Phases 2 to 5 were each built and closed out in one commit rather than the kickoff's two, as the freeform blur work's phases were: each phase's build and its PRD rows touch the same files.

**The Blur, Highlighter, and Eyedropper Tools PRD has no open row left.** Section 2, the Blur / Pixelate tool, closed with the Performance rows of Phase 1; Section 3, the Highlighter, closed with the freeform blur and Highlighter work on 09-11-26; Section 4, the Eyedropper, closes here. Two rows of Section 4 are recorded as permanent departures rather than built: 2.10's background thread with its progress indicator, and 4.7's mid-drag Alt sampling, which General UI PRD 12.2's "draw from center" convention holds against. Every other row of Sections 4, 6.2, 7.3, 8.1, and 8.3 is built and met by tests.

**What remains across the other PRDs.** The Basic Shape Annotation Tools PRD's Section 2 is open, and has been since before the Basic Shape remainder work. Writing the kickoff for it on 09-12-26 found more open than the two rows this section first named, each verified by running the code: no dimension tooltip, constrain icon, centre marker, 70 percent preview, or guide line of 2.4; every shape tool selecting its new item and returning to the Select tool, against 2.1 and 2.5; **a drag on a locked or hidden layer creating the shape**, against 2.1 and the Section 12 acceptance row; **a tool switch during a drag leaving the preview item in the scene**, behind no command and in no layer, since no shape tool overrides `cancel`; **Shift and Alt doing nothing for the Rectangle and the Ellipse**, where 2.3 asks for a square, a circle, and a centre origin and the tools' own hints already promise them; and the Drawing hints of 3.7, 4.8, 5.7, 6.7, and 9.11 unbuilt, where the Arc's and the Polygon's are done. `docs/Basic-Shape-Shared-Drawing-Kickoff-Prompt.md` (revision 1.0, starting state at commit 385c221) owns all of it in five phases with four decisions and eight silences. The Screen Capture PRD's Windows backend waits for a Windows machine (`docs/Windows-Backend-Kickoff-Prompt.md`), and its macOS backend is deferred with no Mac available. The General UI PRD has no open row; the Library, Navigation and Raster Operations, Text and Callout, and Numbered Steps, Stamps, and Emoji PRDs have none from this work.

**Display checks owed**, since every render check in this work is a pixel test on the offscreen platform. This work adds three: the loupe at each of the four sample sizes over a screenshot, the loupe near the right and top edges of the viewport where it flips, and the Eyedropper's bar at a narrow window, which is now the widest bar in the application. All three were attempted on 09-12-26 and **none could be run**: the Eyedropper would not activate. Doug, of pressing `I` on the canvas: "The I key did not work. Nothing changed." `I` is the Eyedropper's only shortcut and nothing else claims it (`config/shortcuts.py`; `Ctrl+I` is File > Import Image, a different sequence), and the same session had pressed `I` successfully a few minutes earlier to confirm the new build was running, so the key reaches the window at least sometimes. Not reproduced; the Tools menu and the palette are the other two routes and neither was tried. Until the tool can be activated on the display, the loupe has never been seen outside a pixel test.

What the other works owed is now settled by the same two runs, each recorded in its own notes: every check the freeform blur work and the Vector Item Properties work owed passes, the Basic Shape remainder work's blur modes pass for Gaussian Blur and Pixelate with Solid Fill blocked by the Blur tool's own Fill swatch, and the General UI notes' acceptance row 20 is answered in full and closed. Two findings from those runs bear on this work: a saved window state can put the Tool Options Bar beside the Main Toolbar instead of below it (General UI notes Section 6), which the Eyedropper's bar, now the widest in the application, will meet sooner; and Cinnamon's window manager takes Alt plus the left button as its window-move gesture (`org.cinnamon.desktop.wm.preferences mouse-button-modifier` reads `<Alt>`, verified 09-12-26), so no Alt+drag reaches the canvas on that desktop — which leaves the blur eraser of Blur PRD 2.8 with no working route, where the Zoom tool's right-click route is now confirmed working.

**Next required step:** the work is complete. Three things are more valuable than any unbuilt PRD row, all three found by Doug's display run of 09-12-26 and none of them this work's: the colour picker does not commit a pick (General UI PRD 11.1, a shared control every colour swatch opens); the widest Tool Options Bars overflow behind Qt's extension button at Doug's window width, which this work's own bar will meet soonest; and Alt plus a mouse button never reaches the canvas on that desktop, which leaves the blur eraser of Blur PRD 2.8 with no route. After those, the kickoff written on 09-12-26 at Doug's request is `docs/Basic-Shape-Shared-Drawing-Kickoff-Prompt.md` (revision 1.0): the Basic Shape Annotation Tools PRD's Section 2, which runs on this machine. The Windows capture backend still waits for a Windows machine.

## 12. The display run of 09-14-26

Run by Doug between 09:27 and 09:31 from the checklist page `SnapMock Blur and Eyedropper Display Checks`, against the working tree at c020337. **The Eyedropper activated from `I`** this time, with no note; the 09-12-26 failure to activate stays unexplained and did not recur. **The loupe is seen for the first time and passes:** a round magnifier following the pointer over text, enlarged, with its crosshair, swatch, and hex value; the sampled square growing through the four sizes; the loupe flipping to the pointer's left at the right edge and below it at the top edge; a click on a black letter sampling a dark value into the bar. Two steps were marked as problems because the checklist named the sample-size buttons by text ("3x3", "5x5", "11x11") where the bar shows them as icons of squares from small to large; Doug: "when I click on the different size squares it expands the outlined square", which is the behaviour the check wanted. An instruction error, not a fault.

**The narrow-window check cannot arise.** Doug: "The window cannot be made small enough to display a more button." Measured headlessly at 1600 by 900: the window's minimum width is 1024 px for every tool, and the Eyedropper's bar wants 801 px, so it never overflows; the Blur tool's bar wants 1469 px and the Rectangle's 1726 px, and both show More… at the minimum width. Section 11's "now the widest bar in the application" was wrong once the unused history swatches took no room (its own 1.7 row): the Eyedropper's bar is among the narrowest. The overflow popover itself was confirmed on the display on 09-12-26 with other bars, so nothing is owed. Every display check this work owed is answered.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.11 | 09-14-26 09:34 | Claude (Claude Code) | Section 12: the display run of 09-14-26. The Eyedropper activated from I; the loupe passes at every size and at both edges; the narrow-window check cannot arise, since the bar fits inside the window's minimum width, and the "widest bar" claim is corrected. |
| 1.10 | 09-12-26 10:14 | Claude (Claude Code) | Section 11: what remains in the Basic Shape PRD's Section 2 rewritten against the three probes taken while writing its kickoff (a locked or hidden layer accepting a drag, a tool switch leaving the preview in the scene, Shift and Alt doing nothing for the Rectangle and the Ellipse), the kickoff named, and a next required step that puts the three findings of Doug's display run ahead of any unbuilt row. |
| 1.10 | 09-12-26 10:35 | Claude (Claude Code) | Section 11: the display run of 09-12-26. None of this work's three checks could be run, because the Eyedropper would not activate from its `I` shortcut; the loupe has still never been seen outside a pixel test. What the other works owed is settled by the same runs, and the Zoom tool's right-click route is confirmed working |
| 1.9 | 09-12-26 09:58 | Claude (Claude Code) | Section 11: the restated list of other works' display checks corrected against the run Doug made on 09-12-26, and the two findings from it that bear on this work — the Tool Options Bar's overflow behind Qt's extension button and Cinnamon's Alt window-move gesture, which leaves the blur eraser of Blur PRD 2.8 without a working route. |
| 1.8 | 09-12-26 02:02 | Claude (Claude Code) | The full-suite run at the close-out commit recorded in Section 10: 1436 passed, one environmental failure that passes alone, 13 skipped, one deselected, 67 minutes. |
| 1.7 | 09-12-26 00:53 | Claude (Claude Code) | Close-out: Section 4.1 with the loupe's measured cost per mouse move, Section 9's deviations, Section 10's tests, and Section 11's close-out with what remains across the other PRDs and the display checks owed; the General UI notes' Section 24 and two corrected Section 6 bullets, and the freeform blur notes' Section 10 pointer. One fix found by reviewing this work's own code: the Color History's unused swatches hide their toolbar action, not only the widget, so they take no room in the bar. |
| 1.6 | 09-12-26 00:16 | Claude (Claude Code) | Phase 5, applying the colour, the Alt mode, and the hints (Blur PRD 4.6, 4.7, 4.8, 6.2, 8.3): Section 8 with what was built and the six silences found while building, including the permanent departure of 4.7's mid-drag row against General UI PRD 12.2's Alt convention; the phase-table row done. Blur PRD 1.14, General UI PRD 2.25, Technical Architecture PRD 1.37. |
| 1.5 | 09-12-26 00:06 | Claude (Claude Code) | Phase 4, the properties and the Tool Options Bar (Blur PRD 4.4, 4.5, 8.3): Section 7 with what was built, the six silences found while building, and the next required step; the phase-table row done. Blur PRD 1.13, General UI PRD 2.24. |
| 1.4 | 09-11-26 23:56 | Claude (Claude Code) | Phase 3, the preview loupe (Blur PRD 4.3, 8.3): Section 6 with what was built, the six silences found while building, and the next required step; the phase-table row done. Blur PRD 1.12, Technical Architecture PRD 1.36 (Section 10 gains `ui/loupe_overlay.py`). |
| 1.3 | 09-11-26 23:50 | Claude (Claude Code) | Phase 2, sampling (Blur PRD 4.2, 4.4, 8.3): Section 5 with what was built, the five silences found while building, and the next required step; the phase-table row done. Blur PRD 1.11. |
| 1.2 | 09-11-26 23:55 | Claude (Claude Code) | Phase 1 close-out: the Blur PRD rows (now Section 4.2), the departures that stay permanent, and the next required step; the phase-table row done. Blur PRD 1.10. |
| 1.1 | 09-11-26 23:47 | Claude (Claude Code) | Phase 1 step 2: decision 4 option C built in `snapmock/items/shadow.py` — float32, all four channels in one array, and a direct sum of shifted slices at a narrow box. Section 3's step 2 with the four silences found while building, and Section 4's measured render times before and after: 2.10's 100 ms is met at every radius for a 1000 by 1000 px region. |
| 1.0 | 09-11-26 22:58 | Claude (Claude Code) | Initial notes: the starting state at commit 1bafbad, the phase table, the four decisions (1 B, 2 A, 3 A, 4 C) and the kickoff's six silences as chosen 09-11-26, three corrections to the kickoff found in the reading, and the measurement that retired decision 4's option B and produced option C. Blur PRD 1.9, General UI PRD 2.23, Technical Architecture PRD 1.35. |
