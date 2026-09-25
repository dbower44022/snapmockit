# The Border Tool — Implementation Notes

Last Updated: 09-25-26 10:34 · Revision 1.3

A border around the image, built as the twenty-second tool in the palette, and Snagit's own
Border effect read back as an editable border. The requirement is Section 10 of
`PRDs/SnapMock-Navigation-Raster-Operations-PRD.html` at version 1.8, written in this same
session from the reference file `Example Snag Files/Border Tool Example -
2026-09-21_10-21-47.snagx`; the Technical Architecture PRD is amended at version 1.71.
There is no kickoff prompt: the PRD, the decision, and the build were one session.
Operating mode: ARCHITECTURE.

## 1. What the reference file settled

Snagit's border is not an object. The page JSON of the reference file carries no
`CaptureObjects` at all. The border is painted into the background bitmap and the canvas is
grown to hold it: `{GUID}.backup.png` is 2550 × 3300 with a transparent edge,
`{GUID}.png` is 2566 × 3316 with eight pixels of opaque black on every side, and
`{GUID}.backup.json` carries the pre-effect canvas size. No other file in the sample set of
238 has a `.backup` pair, so that pair is Snagit's record of "a destructive image effect
was applied, and here is the original."

Two consequences shaped the work. Reading a Snagit border already worked before this change
— the flattened pixels arrive as the background raster — so the reader's job was not to
make the file open but to make the border editable. Writing was where the work was, because
Snagit has no border object to write to.

## 2. Decisions

### 2.1 What a border is: a canvas property, not an item and not a destructive edit

Presented with the consequential decision template on 09-21-26 at 10:29, taken at option A.
The border is four values on `SnapScene`, beside `background_color` and `canvas_dpi`, changed
through `SetCanvasBorderCommand`.

**Why not an item:** a `BorderItem` on a layer can be dragged off-centre, deleted, stacked
under an annotation, or duplicated, and the frame around the canvas is none of those things.
It would also contradict the rule that the background raster is the canvas and is not
selectable (`SnapScene.is_fixed_in_place`, General UI PRD 6.2).

**Why not Snagit's own destructive model:** the border would not survive a save and reopen
as something the user can still change, which is the whole of what the feature is for.

**The cost, accepted:** the border gets none of the shared vector machinery for free. Its
line type reuses the existing `BorderStyle` enum and its shadow reuses `blur_image`, but
each had to be wired by hand rather than inherited, and there is one border per document, so
an outer-and-inner double frame is not reachable without widening the property set later.

### 2.2 Where the border rides: outside the canvas rectangle

Decided and announced rather than put to Doug, since the user-facing question — does the
border grow the image or cover its edge? — was already answered by "match Snagit", which
grows. What remained was implementation.

`canvas_size` stays the size of the image and the border is painted in a ring outside
`canvas_rect`. The rendered and exported size becomes `SnapScene.output_rect`: the canvas
grown by the border and, with the shadow on, by the shadow's offset and blur.

**The alternative rejected:** growing `canvas_size` itself. It would fire item repositioning
on every width change, make the Resize Canvas dialog quote the image plus its frame, and —
the reason it fails outright — leave a later crop eating into the ring while the border
property still claimed those pixels.

**The cost:** the output size is no longer the canvas size, so every surface that renders the
whole document asks for `output_rect`. That is eight call sites, all named in Section 4, and
one of them — the default region inside `export_scene` and `estimate_export_size` — was
found only by exporting to all four formats and measuring what came out.

### 2.3 Where the PRD lives: a new section, not a new document

Presented at 10:37, taken at "new section". Section 10 of the Navigation & Raster
Operations PRD, which already owns the Crop Canvas tool and the canvas operations, rather
than a standalone `SnapMock-Border-Tool-PRD.html`. Sections 10 to 13 renumbered to 11 to
14; verified first that no document refers to this one above Section 9.

## 3. Departures from the PRD

**One, and it is in the interface, not the model.**

**10.5 and 10.6, the border shadow's own controls.** The PRD says the shadow's colour,
offset and blur are edited in "the Property Panel's Shadow section", which is the shared
section every item that carries the shadow helper uses. That section is driven by the
current selection and has no document-level mode; giving it one would have meant a second
state machine inside the panel for a single consumer. **Built instead:** five rows in the
Property Panel's Canvas section beside the other border rows — Border shadow, Shadow color,
Shadow X, Shadow Y, Shadow blur — written as one `SetCanvasBorderCommand` per edit. The
Tool Options Bar keeps the Shadow checkbox the PRD gives it. The capability is complete; only
its address in the panel differs. Recorded in the PRD's change log at version 1.9.

## 4. What was built, and where

**The model.** `core/scene.py` gains `border_width`, `border_color`, `border_style` and
`border_shadow` with their setters, the `border_changed` signal (which bumps the content
revision, so a blur region's cache notices), `has_border`, `border_rect`, `output_rect`, and
`max_border_width()`. `set_canvas_size` re-clamps a border the grown canvas no longer has
room for.

**The command.** `commands/canvas_property_commands.py` gains `SetCanvasBorderCommand` and
`BORDER_PROPERTIES`, with the same merging rule `SetCanvasPropertyCommand` uses, at merge
ids 3100 to 3103.

**The painting.** `core/render_engine.py` gains `paint_canvas_border`, `border_ring_path` and
`_paint_border_shadow` as module-level functions, so the display and every export share one
routine. The order is the shadow, then the ring filled with the canvas background colour,
then the stroke — whose centre line sits half a width outside the canvas, so it fills the
ring exactly and never covers the image.

**The display.** `core/view.py` calls `paint_canvas_border` in `drawBackground`, between the
canvas drop shadow and the canvas background, and casts the canvas's own chrome shadow from
the border's outer edge when there is a border.

**The tool.** `tools/border_tool.py`, registered after `CropTool` as the twenty-second tool,
`Shift+B` (B belongs to Blur), the `border-outer` Tabler glyph vendored from the pinned
v3.46.0 release, a row in the Tools menu's Region group. It consumes no mouse event and has
no preview. Its bar builds Width, Color, Opacity, Style, Shadow and Remove Border by hand
rather than through `options_controls`, because those bind to creation defaults and this bar
edits the document — the Crop tool's aspect presets are the precedent.

**The panel.** `ui/property_panel.py`'s Canvas section gains Border, Border color, Border
opacity, Border style and the five shadow rows of Section 3.

**The exports.** `io/exporter.py`'s `resolve_region` returns `output_rect` for a whole-canvas
export and leaves Selection Only and Visible Area Only clipped to the canvas, so a selection
export never carries the border; `export_scene` and `estimate_export_size` default to
`output_rect` rather than `canvas_rect` when no region is passed, which is the path the quick
exports and the size estimate take; and `_paint_border` paints it for the SVG and PDF paths
beside `_paint_canvas_colour`. `RenderEngine.render_to_image` and `render_region` paint it for
every raster path, which covers PNG, JPEG, the clipboard, the project thumbnail, the Library
render and printing. A 120 × 90 image with a 10 px border comes out at 140 × 110 in PNG,
JPEG, SVG and PDF alike; the test asserts all four.

**The project file.** `io/project_serializer.py` writes a `border` block inside the manifest's
existing `canvas` object, and only when there is a border, so `format_version` stays 1.

**The Snagit writer.** `io/snagit_writer.py` renders the border into the background PNG,
sets `CaptureCanvasWidth` and `CaptureCanvasHeight` to the output size, and moves every
annotation's `PointsArray` and `CalloutTails` by the border offset, since the image no longer
sits at the page origin. No warning is added: nothing is lost in the file Snagit will read.

**The Snagit reader.** `io/snagit_reader.py` gains `_recover_border` and
`_uniform_ring_color`. A border is recovered only when the backup pair is present, the page
canvas exceeds the backup canvas by the same positive even amount in both dimensions, and the
ring between the two is one uniform colour — checked over the four bands with numpy, not a
Python pixel walk. The background then comes from the backup PNG, the canvas from the backup
JSON, and every annotation moves back by the border width.

**Resize Image.** `commands/raster_commands.py` scales `border_width` by the average scale
factor, to a minimum of 1 when it was not 0, as that command already scales stroke widths and
font sizes; undo restores it.

## 5. The display run, and what it found

Doug ran the application on 09-21-26 and activated the Border tool from the palette. It
crashed:

```
File "snapmock/tools/border_tool.py", line 158, in _read_scene
    self._width_spin.setValue(scene.border_width)
RuntimeError: wrapped C/C++ object of type QSpinBox has been deleted
```

**The cause.** The Tool Options Bar retires its widgets with `deleteLater` when it rebuilds
for the next tool, and `ToolManager.activate` calls `tool.activate` **before** the bar has
built the new ones. The Border tool was the only tool that read its own bar widgets from
`activate`, so it was the only one that could reach a widget Qt had already destroyed.
Every other tool that keeps widget references reads them from its own controls' signals,
which a dead widget cannot emit.

**The fix.** `deactivate` drops the references, and every read goes through a `_live`
helper that returns `None` for a widget `sip.isdeleted` reports gone. Both, because the
scene's `border_changed` signal can also reach the tool between a clear and a rebuild.

**The test.** `test_switching_away_and_back_does_not_touch_dead_widgets` activates Border,
switches to Select, waits one event-loop turn — without that wait `deleteLater` has not run
and the crash cannot be reproduced headless — and activates Border again. Verified to fail
with the fix backed out and pass with it in.

## 6. Silences

1. **The canvas background colour is still not written to the project file.** It never was —
   `manifest["canvas"]` carries width, height and dpi only. This now shows through the
   border, because the ring is filled with that colour. Out of scope here: changing what the
   project file carries needs its own requirement. Worth a row in the General UI PRD.
2. **A round-tripped Snagit object's other coordinate fields.** The writer moves
   `PointsArray` and `CalloutTails`, which are the only coordinate fields it emits. A raw
   object carried through from a Snagit file could in principle hold a coordinate under
   another name; the round-trip path already rewrites both of these from the item, so this
   is the pre-existing limit of round-tripping, not a new one.
3. **The border is not a hit target and has no handles**, as 10.9 says. The canvas's own
   eight resize handles stay on `canvas_rect`, beneath the ring.
4. **A written Snagit file keeps the image's transparency where Snagit's own flattens it.**
   The reference file's backup image is fully transparent and Snagit's page image is opaque
   white, because Snagit composited `CaptureBackgroundColor` into the bitmap. Ours writes
   the ring opaque and leaves the image's own alpha alone, with the same
   `CaptureBackgroundColor` beside it, so Snagit composites on open and the user sees the
   same thing. Keeping the alpha is the more faithful of the two.
5. **`CornerRadiusRatio`**, which Snagit carries on the page and sets to 0 in the reference
   file, is untouched. Rounded corners, a second inner frame, and Snagit's other edge
   effects are named out of scope in Section 10.

## 7. Tests

`tests/test_border_tool.py`, 34 tests: one per acceptance row of 13.8, plus the model of
10.2, the merging rule, the export regions and the four exported sizes, the edge cases of
10.9, and the Property Panel rows, the two surfaces staying in step, and the display run's crash. Three suite rows
that count the tools move from twenty-one to twenty-two: `test_acceptance.py`,
`test_main_toolbar.py`, and `test_tools/test_emoji_tool.py`. The reference Snagit file is asserted against directly — 2550 × 3300 canvas, an 8 px
opaque black border, a 2566 × 3316 output rectangle — and a hand-built archive with a
deliberately non-uniform ring asserts the fallback to a flattened load.

**The sample set, run whole after the reader change:** 237 of 238 `.snagx` files load, the
one failure being the archive that was already corrupt (its page JSON is missing), and
exactly one of them — the reference file — comes back with a border.

## 8. Revision control

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 09-25-26 10:34 | Claude (Claude Code) | Released in v1.4.0 on 09-25-26 (`docs/Release-Engineering.md` 1.21); the whole-document copy of General UI PRD 2.55 to 2.57 covers the border, as the export does (Raster PRD 1.11). |
| 1.2 | 09-25-26 10:34 | 8 | Added | **Added** the release: v1.4.0 carries the tool. |
| 09-25-26 01:07 | Claude (Claude Code) | The reference-file test skips when the file is absent: `*.snagx` is git-ignored, so the release run of 1.4.0 failed on the runner where it asserted the file existed. |
| 1.1 | 09-21-26 16:24 | Claude (Claude Code) | Section 5 added: Doug's display run of 09-21-26, the crash on activating the tool a second time, its cause, the fix, and the test that reproduces it. Later sections renumbered; test count 31 to 34. |
| 1.0 | 09-21-26 16:06 | Claude (Claude Code) | First issue: the decisions, the one departure, what was built, the silences, the tests. |

## 9. Change log

| Date | Section | Type | Detail |
|---|---|---|---|
| 09-25-26 01:07 | 7 | Changed | **Changed** the Snagit reference-file test to skip without the file, found by the first continuous integration run of the work. |
| 09-21-26 16:24 | 5 | Added | **Added** the display run and the crash it found, with the cause, the fix, and the reproducing test. |
| 09-21-26 16:06 | all | Added | Written at the close of the build, in the session that also wrote Navigation & Raster Operations PRD Section 10 (version 1.8) and amended the Technical Architecture PRD (version 1.71). |
