# Basic Shape Remainder and Blur Modes Implementation Notes

Last Updated: 09-14-26 09:34 · Revision 1.10

Implements the remainder of the Basic Shape Annotation Tools PRD (`PRDs/SnapMock-Basic-Shape-Annotation-Tools-PRD.html`, version 1.8 at the start) and the Blur / Pixelate tool of the Blur, Highlighter, and Eyedropper Tools PRD (version 1.4), with the General UI PRD (version 2.16) and Technical Architecture PRD (version 1.28) rows they own, in the five phases and the close-out defined by `docs/Basic-Shape-Remainder-Kickoff-Prompt.md` (revision 1.0). A session pasting that prompt starts at the first phase not marked done in Section 1. `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) governs the standards; the General UI implementation notes (`docs/General-UI-Implementation.md`) hold the walk table of Section 17.2.

Starting state, verified at commit 8a9ce6b on 09-11-26 (the kickoff names ab71e15; 8a9ce6b adds only the Vector Item Properties close-out documents and the kickoff prompt): every vector item carries the shared stroke, fill, opacity, shadow, and blend properties; the Arrow draws its heads on a straight shaft and stores `line_style` without drawing it; the Rectangle has the uniform Corner Radius; the Freehand tool simplifies the raw points on release and stores the simplified polyline under `points`; the palette has nineteen tools; `BlurItem` paints a grey placeholder and `BlurTool` has no options. The suite at ab71e15 ran 1272 tests with 13 skipped and one environmental deselection: 1258 passed; ruff and mypy are clean.

## 1. Phase status

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | Point editing and the arrow's lines (Basic Shape PRD 3.5, 4.5, 4.6, 4.7, 11.3): the decisions, the point-editing mode, curved and elbow arrows, close-out | Done | 177f69b, 1f23a37, ba4320e, then this close-out commit |
| 2 | The Rectangle's corners and the Freehand pipeline (5.3, 5.4, 9.3, 9.6 to 9.9): individual corner radii, the Freehand pipeline, Freehand point editing, close-out | Done | 405f637, ad1f6b6, 661371e, then this close-out commit |
| 3 | The Arc tool (Section 7): `ArcItem` and the tool, Arc point editing, close-out | Done | 867a763, 58d40a0, then the shared close-out commit |
| 4 | The Polygon tool (Section 8): `PolygonItem` and the tool, Polygon point editing, close-out | Done | 4c99d0f, c20cf5e, then the shared close-out commit |
| 5 | The Blur tool's modes (Blur PRD Section 2): the capture and the three modes, the freeform region and Whole Layer deferral, close-out | Done | c47bf7e, 437416d, then the shared close-out commit |
| Close-out | PRD rows, the General UI notes' pointer, the Vector Item Properties notes' pointer | Done | the shared close-out commit |

## 2. Decisions

### 2.1 Taken at the start of Phase 1 (09-11-26)

Presented with the consequential decision template and chosen by Doug on 09-11-26: the recommendation in every case ("use your recommendations for all decisions").

| Decision | Choice | Effect |
|---|---|---|
| 1 Where point editing lives | A, a mode of the Select tool | A double-click on a line, an arrow, an arc, a polygon, or a freehand item with the Select tool selects it and enters point-editing mode. The transform handles hide; the item's control points show as scene items above every annotation item, the way `TransformHandles` already are. Each item type has one point-edit session class in the new module `snapmock/tools/point_edit.py` (a Technical Architecture PRD Section 10 row): the session knows its handles in scene coordinates, applies a drag with its modifiers, and builds the command the drag pushes. Escape, a click away from the item and its handles, a tool switch, or a selection change leaves the mode. The status bar shows the item's point-editing hint while the mode lasts. The cost: the Select tool gains a second state machine. The alternative, option B, a hidden `PointEditTool`, would have needed exclusion from the presets, the themes, the palette count, and the tool-switch machinery. |
| 2 What the Freehand item stores | A, both the raw points and the fitted segments | `FreehandItem` stores `path_points` (the raw sampled points), `bezier_segments` (cubic segments of start, cp1, cp2, end), `smoothing` (0.0 to 1.0), `is_closed`, and `pressure_data` (always null) under the 10.7 keys, and paints the segments. The two-stage pipeline of 9.3 runs on release: Ramer-Douglas-Peucker simplification at a tolerance of smoothing times 5 px, then least-squares cubic Bezier fitting at an error of smoothing times 3 px. Moving the Smoothing slider with freehand items selected re-smooths each from its `path_points` as one undoable change; a hand edit of the segments is replaced by a re-smooth, since the re-smooth starts from the raw points. The cost: about twice the data per stroke, and the fitting algorithm to write and test. The alternatives: option B, the raw points only with the fit recomputed on every load, where a hand-edited segment could not survive; option C, the simplified polyline kept, leaving 9.3's second stage and 9.7's handles unmet. |
| 3 The tool count and the shortcuts | A, two tools, Arc on Shift+A | The Arc tool (`arc`, Arc, Shift+A) and the Polygon tool (`polygon`, Polygon, G) are registered as the twentieth and twenty-first tools, after the Line tool in the palette and in the Tools menu's shape group. Shift+A is the Basic Shape PRD's key (7.1); General UI PRD 3.7 lists O, and its Arc row is corrected by a General UI PRD row, since each tool's own PRD owns its details (the marker work's silence 1; the Emoji tool's Shift+E came the same way). The palette count changes from nineteen to twenty-one in the three tests that assert it. The cost: Arc needs two keys, and 3.7 carries a correction. The alternatives: Arc on O with the Basic Shape PRD corrected; one Shapes tool with a mode dropdown, departing from 3.7's table. |
| 4 How far the Blur tool goes | A, three modes over two shapes, on the main thread | `BlurItem` gains the Gaussian, Pixelate, and Solid Fill modes over the Rectangle and Ellipse region shapes, with `corner_radius`, `feather`, `invert_mask`, the item's opacity, `border_color`, and `border_width`, a cached render, and the 2.6 bar. The brush-painted freeform region of 2.3 and 2.8, the Freeform and Whole Layer shapes of 2.4, `brush_size`, `alpha_mask`, the source modes of 2.5, and the background-thread render and progress indicator of the Performance section are recorded as not built; a file carrying `freeform` or `whole_layer` reads as a rectangle. The cost: those rows open, and a region larger than 500 by 500 px may miss the 100 ms render target. The alternative, option B, all of Section 2 with the mask's own editing mode and the first thread in the code. |

### 2.2 The kickoff's six silences

Each decided as the kickoff recommended, on 09-11-26, with the detail the reading added.

| Silence | Decision |
|---|---|
| The arrowhead on a curve | Oriented along the tangent at the endpoint (4.5): toward the end point from the control point for a curve, along the terminal segment for an elbow. `head_paths` takes a direction per end. |
| The geometry commands | `ModifyGeometryCommand` (11.3) in the new module `snapmock/commands/geometry_commands.py` (a Section 10 row), merging drags of the same property on the same item within 300 ms; `InsertVertexCommand` and `RemoveVertexCommand` (11.4, 11.5) beside it. A line's endpoint drag pushes `ModifyGeometryCommand`, not the `ModifyPropertyCommand` that 3.5 names, since 11.3 is the section on point edits. |
| What the blur captures | Every visible item stacked below the blur item, which is every item of the lower layers plus the lower items of its own layer, painted into an image over the region at the canvas scale with the canvas colour first. The items are painted directly with their scene transforms and effective opacity by a new `RenderEngine` method, not through `QGraphicsScene.render` with visibility toggles as the thumbnails are: a scene render from inside the blur item's paint would draw the blur item itself, and a visibility toggle schedules another paint. The cache key is the region, the properties, the item's scene transform, and a revision counter the scene bumps on every command push, undo, and redo and on every layer change. |
| Whole Layer and the source modes | Wait with the freeform brush (decision 4). |
| The Snagit writer | Skips a blur region with its warning, as today. Verified 09-11-26: the 239 sample files carry the tool modes Text, Callout, Image, Highlight, Shape, Arrow, Line, and Stamp, and no blur object. A Snagit notes row at the close-out. |
| The Arc and Polygon glyphs | From the vendored Tabler subset; a glyph added to the subset is recorded in the icons README. |

### 2.3 Corrections to the kickoff, found in the reading

- General UI PRD 3.7 lists Arc under O, not Shift+A; only the Basic Shape PRD (7.1) gives Shift+A. Settled by decision 3.
- The transform handles are scene items (`TransformHandles`, a `QGraphicsItemGroup` at z 999997), not drawn in the view's foreground pass; only the grid, the guides, the crosshairs, and the layer hover outline are. The point-editing handles follow the transform handles.
- No callout tail handle exists in the Select tool: `MoveTailCommand` has no caller, and a callout's tail moves only with a resize. Decision 1's "joins it later" has nothing to join; nothing is built for it here.
- A third test asserts the palette count: `tests/test_tools/test_emoji_tool.py::test_emoji_is_the_nineteenth_tool_after_stamp_with_shift_e`, beside the two the kickoff names.

### 2.4 Findings decided with the decisions

- The Line and Arrow tools show "Shift: constrain angle" and do not read Shift while drawing. Point editing needs the same 15-degree snap, so Phase 1 step 2 builds one helper and both tools use it while drawing (Basic Shape PRD 3.2, a row).
- A closed freehand stroke fills (9.8), and 9.6 adds its controls to the shared set of 2.6, which includes Fill Color and Fill Opacity; the Vector Item Properties work left them off the Freehand bar because the item drew no fill. The Freehand bar gains both with Close Path (Phase 2 step 2).
- Files saved before Phase 2 store the already-simplified polyline under `points`. They load with those points as `path_points` and are fitted on load at their stored smoothing, 0.5 when absent.
- The Freehand tool's Smoothing creation default stays the slider's whole percent, 0 to 100, as presets and themes already store it; the item stores the 0.0 to 1.0 fraction of 10.7. The Ramer-Douglas-Peucker tolerance at 100 percent becomes 9.3's 5 px, where the shipped `MAX_SMOOTHING_EPSILON` was 6 px (a Basic Shape PRD row).
- The PRD's class name `BlurRegionItem` stays `BlurItem` in the code and in `items.json`, as every file saved so far names it.

## 3. What Phase 1 built

In commit order. Step 1, 177f69b: the decisions of Section 2; Basic Shape PRD 1.9, Blur PRD 1.5, General UI PRD 2.17, Technical Architecture PRD 1.29. Step 2, 1f23a37: `snapmock/tools/point_edit.py` (`HandleKind` with the diameters of 3.5, 4.5, and 9.7; `PointHandle`; `PointEditSession` with scene and local coordinates through the item's flips, `handle_at`, `begin_drag`, `cancel_drag`, `end_drag`; `LinePointSession` and `ArrowPointSession`; `session_for`; `PointHandlesItem`, a scene item at z 999998 drawing the handles and dashed guides) and `snapmock/commands/geometry_commands.py` (`ModifyGeometryCommand`, `copy_geometry`, `shape_name`), each with its Technical Architecture PRD Section 10 row; the Select tool's point-editing mode (double-click entry, the handle drag state, the exits, the handles following undo and redo through the command stack's signal); Edit > Deselect's Escape leaving the mode first; `constrain_angle` in `core/path_utils.py`, used by point drags and now by the Line and Arrow tools while Shift is held. Step 3, ba4320e: curved and elbow arrows in `ArrowItem` (`control_point`, `bend_point`, `effective_control_point`, `bend_x`, `bend_handle_point`, `elbow_points`, `end_directions`, `line_path` in the line style, `head_paths` returning the shaft as a path trimmed at a filled head's base along the curve or the segments, the 10.2 keys); the Line Style toggles of 4.7 in the Arrow bar with `line_style_icon` and the `line_style` creation default; `LineStyle` in the preset codec; the Line style row of the Property Panel's Arrow section; the control point and bend point handles in `ArrowPointSession` with the 4.8 hints per style. Step 4, this commit: Basic Shape PRD 1.10, General UI PRD 2.18, Technical Architecture PRD 1.30, Snagit notes 1.4, these notes.

Silences found while building, decided as the code says and recorded as PRD rows:

- The handles are sized in scene pixels, as the transform handles are, so they grow with the zoom; a press within 3 px of a handle's edge grabs it; the topmost handle wins where two overlap.
- A press on the item keeps point-editing mode, so a missed handle does not end it; a press elsewhere leaves the mode and acts as a normal press.
- A point drag snaps to the grid and the guides as a move does, unless Shift is held, when the 15-degree constraint wins.
- A flipped item's handles are mirrored where the item paints them.
- The mode also ends when the item leaves the scene (Delete, or an undo of its creation) and on a tool switch.
- A curved arrow with no `control_point` curves through the midpoint, so switching a straight arrow to Curved changes nothing until the green point moves; switching the style keeps the stored points.
- An elbow is horizontal, vertical, horizontal; its bend point stores the middle y and moves across only; when the bend meets an end's x, the first or last segment vanishes and two remain.
- A curved arrow's shaft ends where the curve meets a filled head's reach measured in a straight line from the tip.
- The new arrow keys use 10.2's `{"x", "y"}` form while `line` keeps its list form.
- The Snagit writer writes a curved or elbow arrow as its straight line (Snagit notes 1.4).

## 4. What Phase 2 built

In commit order, built while the Phase 1 suite ran and committed after the Phase 1 close-out. Step 1, 405f637: the individual corner radii (`CornerRadiusMode` and `CORNER_KEYS` in `config/constants.py`; `RectangleItem`'s four radii stored as set and drawn clamped with one `arcTo` per corner; the Individual toggle and four spin boxes of the Rectangle bar through `ToolOptionsBar.set_control_visible`; the Property Panel's Individual corners check box and four rows; the codec). Step 2, ad1f6b6: the Freehand pipeline (`fit_cubic_beziers` and the iterative `simplify_rdp` in `core/path_utils.py`; `FreehandItem`'s `path_points`, `bezier_segments`, `smoothing`, `smoothing_fit`, and `is_closed` under the 10.7 keys; the Freehand bar with the fill controls, the Stroke Cap toggles, and Close Path; the Property Panel's Freehand section; `ResizeImageCommand`'s restore). Step 3, 661371e: Freehand point editing (`FreehandPointSession` and `split_cubic`; the Select tool's double-click insertion and right-click deletion routes; Alt kept from the momentary eyedropper). Step 4, this commit: Basic Shape PRD 1.11, General UI PRD 2.19, Technical Architecture PRD 1.31, these notes.

Silences found while building, decided as the code says and recorded as PRD rows:

- Switching a rectangle to Individual while its four radii are all zero starts them from the uniform radius, so it keeps its look; radii already set are never overwritten.
- In Individual mode the bar hides the Corner Radius slider with its label, and the Property Panel hides the Corner radius row.
- Both stages of the Freehand pipeline have a 0.5 px floor, and the fit and the simplification are iterative, so no stroke exhausts the recursion limit.
- Re-smoothing a placed stroke is done from the Property Panel's Freehand section, since the bar edits creation defaults only; one command restores the smoothing and the segments together, a hand edit included.
- A stroke is an accidental click when its points span under 2 px both across and down, so a straight underline is kept.
- Dragging an on-curve point carries its two handles; dragging a handle turns the opposite handle in line at its own length; Alt breaks either link; a right-click on a handle never opens the item menu, even where the two-point minimum refuses the deletion.
- Shift's straight segments (9.5) and the brush-tip cursor (9.2) are not built.

Measured for 5000 raw points on this machine: about 65 to 70 ms at 50 and 100 percent smoothing, and up to 630 ms at 0 percent on a stroke with a pixel of jitter, against the 50 ms of 9.10.

## 5. What Phase 3 built

Built while the Phase 2 suite ran. Step 1, 867a763: `items/arc_item.py` and `tools/arc_tool.py` (Section 10 rows); `head_geometry` and `quad_shaft` as module functions of `items/arrow_item.py`, shared by the arrow and the arc; the Arc tool registered as the twentieth tool on Shift+A with the Tabler `vector-bezier-arc` glyph (vendored with `polygon` from the npm package of the same release, as the icons README records); `ArcType` and the enums Phases 4 and 5 use in `config/constants.py`; `BaseTool.handle_escape`, through which Edit > Deselect's Escape reaches the active tool first; `ITEM_REGISTRY`, the Snagit writer's skip, the Property Panel's Arc section; the three palette-count tests and the 17.2 Tools rows. Step 2, 58d40a0: `ArcPointSession`. Step 3, the close-out commit shared with Phases 4 and 5 (Section 1).

Silences found while building, decided as the code says and recorded as PRD rows:

- The pie's lines meet at the centre of the circle through both ends and the curve's peak, since a quadratic Bezier belongs to no ellipse (7.6); a straight arc's pie closes as a chord.
- In step 2 the peak follows the cursor's perpendicular distance from the chord, on either side.
- A chord under 2 px is an accidental click.
- The hit shape is the outline's band of stroke width plus 4 px and the inside of a filled Chord or Pie.
- `head_size_custom` is not an arc key, as 10.5 lists `head_size` alone.
- Escape reaches the tool through Edit > Deselect's shortcut, which now asks the active tool first.

## 6. What Phase 4 built

Step 1, 4c99d0f: `items/polygon_item.py` and `tools/polygon_tool.py` (Section 10 rows); the Polygon tool registered as the twenty-first tool on G with the Tabler `polygon` glyph; `ITEM_REGISTRY`, the codec's `PolygonMode`, the Snagit writer's skip, the Property Panel's Polygon section; the palette count at twenty-one and the 17.2 Tools rows. Step 2, c20cf5e: `InsertVertexCommand` and `RemoveVertexCommand` in `commands/geometry_commands.py` and `PolygonPointSession`. Step 3, the shared close-out commit.

Silences found while building:

- The star's inner radius is the outer radius times 1 minus `star_indent`, 8.3's reading, where 8.6's formula reads the other way (a departure).
- The regular polygon's rotation is written as `polygon_rotation`, since the item's own `rotation` key is taken (a departure).
- The 10 px closing distance is in scene pixels; an open polyline needs two vertices; a click without a drag makes no regular polygon.
- A right-click while vertices are placed removes one and opens no menu.
- A regular polygon's point-editing hint is this work's own, since 8.7 gives none.

## 7. What Phase 5 built

Step 1, c47bf7e: `RenderEngine.render_below`, `SnapScene.content_revision`, `BlurItem` rebuilt with the three modes, the two shapes, feather, invert, opacity, border, and the cache, `pixelate_image`, `BlurTool` with the drag of 2.3 and the bar of 2.6, the codec's `BlurMode` and `BlurRegionShape`, and the Property Panel's Blur section. Step 2, the freeform region and Whole Layer: recorded as not built by decision 4 in the Blur PRD's 1.6 Departure row, with no code. Then 437416d: the arc, the polygon, the individual radii, and the blur region's corner radius and feather join Resize Image's geometry walk, the one walk of the General UI notes' Section 17.2 kind that names item types one by one; every other walk reads every item alike. Step 3, the shared close-out commit.

Silences found while building:

- The capture paints the items below directly with their scene transforms, in the region's own coordinates, so a rotated region obscures what it covers and nothing is hidden or shown during a paint.
- The Gaussian blur reads a margin of twice its radius and crops it away; the feather blurs the mask over its width.
- The cache's zoom is rounded to a power of two, the factor of two of 2.7.
- The region repaints whole on every command, since the content beneath may change anywhere under it.
- A flip does not mirror what lies beneath.
- The colours are written `#AARRGGBB`, as every other item writes them.

Measured while another test run shared the machine: a 1000 by 1000 px region in about 200 ms for Gaussian Blur (2.10's 100 ms unmet), 50 ms for Pixelate, 3 ms for Solid Fill, and about 0.5 s for an inverted Gaussian over the whole 1920 by 1080 canvas.

## 8. Deviations from the PRDs

Each has its PRD row.

- General UI PRD 3.7: Arc on Shift+A, not O (decision 3).
- Basic Shape PRD 3.5: a line's endpoint drag pushes `ModifyGeometryCommand` (11.3), not `ModifyPropertyCommand`.
- Basic Shape PRD 9.3: the Smoothing creation default stays a whole percent; the item stores the fraction.
- Blur PRD Section 2: the freeform region, Whole Layer, the source modes, and the background-thread render are not built (decision 4); the item class keeps the name `BlurItem`.
- Basic Shape PRD 9.3 and 9.10: both stages of the Freehand pipeline floor at 0.5 px; a jittery 5000-point stroke fits in up to 630 ms at 0 percent smoothing.
- Basic Shape PRD 9.7: re-smoothing a placed stroke is done from the Property Panel's Freehand section, not the Tool Options Bar.
- Basic Shape PRD 9.1: a stroke is an accidental click when its points span under 2 px both across and down, not when its bounding box is under 4 square pixels.
- Basic Shape PRD 7.6: the pie's lines meet at the centre of the circle through both ends and the peak.
- Basic Shape PRD 8.6 and 10.6: the star indent reads as 8.3 describes it, and the regular polygon's rotation is written as `polygon_rotation`.
- Blur PRD 2.10: the 100 ms Gaussian target is unmet, there is no background thread or progress indicator, and the drag preview renders at full resolution.
- Blur PRD 5.1: the colours are written `#AARRGGBB`.
- Basic Shape PRD 2.4 and 2.5, open before this work and still open: no dimension tooltip or constrain icon near the cursor for the drag-drawn shapes, and every shape tool selects its new item and returns to the Select tool.

## 9. Tests

Phase 1: `tests/test_point_edit.py` (13: entering by double-click with the handles, the transform handles hidden, and the hint; an item without points not entering; a drag as one undoable geometry edit with the handles following undo; the Shift constraint; the 300 ms merge by point; Escape, a click away, and a new selection leaving; deleting the item leaving; the window's Escape keeping the selection; the arrow's endpoints; a flipped line's handles; `constrain_angle`; both drawing tools under Shift) and `tests/test_arrow_lines.py` (9: the curve through its control point by pixels and hit shape; the heads along the tangent with the shaft ending at the filled base; the elbow's right angles and its two-segment case; the keys' round trip, old files, the list form, and scaling; the control point and bend point drags with undo and hints; the bar's toggles reaching the next arrow; the panel row with undo). The two shaft assertions of `tests/test_arrow_heads.py` read the path. The full suite at the Phase 1 code commit (ba4320e), run from a scratch worktree while the Phase 2 work's targeted runs shared the machine, ran 1293 tests with 13 skipped and the one environmental deselection: 1279 passed and one failed, the pre-existing timing-sensitive Zoom tool test (`tests/test_tools/test_zoom_tool.py::test_left_click_zooms_in_and_alt_at_the_release_zooms_out`), which passes alone at that commit; the run took 48 minutes. Ruff and mypy are clean at every commit; the accessibility audit passes over the Arrow bar's toggles and the new panel row.

Phase 2: `tests/test_corner_radii.py` (8), `tests/test_freehand_pipeline.py` (10), `tests/test_freehand_point_edit.py` (7); the Freehand smoothing test of `tests/test_tool_options_bar.py`, the scale test of `tests/test_transform_resize.py`, and the Freehand bar order of `tests/test_vector_bar_presets.py` moved with the work. The full suite at the Phase 2 code commit (661371e), run from a scratch worktree while the Phase 3 to 5 work's targeted runs shared the machine, ran 1318 tests with 13 skipped and the one environmental deselection: 1304 passed and one failed, the pre-existing timing-sensitive Zoom tool test, which passes alone at that commit; the run took 50 minutes. Ruff and mypy are clean at every commit; the accessibility audit passes over the Rectangle and Freehand bars' new controls and the two new panel sections.

Phases 3 to 5: `tests/test_arc_tool.py` (10), `tests/test_arc_point_edit.py` (4), `tests/test_polygon_tool.py` (11), `tests/test_polygon_point_edit.py` (4), `tests/test_blur_modes.py` (10), and the Resize Image walk test of `tests/test_raster_commands.py`; the three palette-count tests read twenty-one, the 17.2 Tools rows include Arc and Polygon, and the bar test for tools without options no longer lists the Blur tool. The full suite at the last code commit (437416d), run alone from a scratch worktree, ran 1358 tests with 13 skipped and the one environmental deselection: 1344 passed and one failed, the pre-existing timing-sensitive Zoom tool test, which passes alone at that commit; the run took 62 minutes. Ruff and mypy are clean at every commit; the accessibility audit passes over the Arc, Polygon, and Blur bars and the three new panel sections.

## 10. Close-out of the work

Every phase is done. The PRDs stand at Basic Shape PRD 1.12, Blur PRD 1.6, General UI PRD 2.20, and Technical Architecture PRD 1.32, with the Snagit notes at 1.5. The General UI notes' Section 6 bullet on the per-tool bar contents is closed with a Section 22 pointer (General UI notes 1.34); the Vector Item Properties notes' Section 8 points here (1.4). The close-outs of Phases 3, 4, and 5 were written together in one commit after one full-suite run at the last code commit, since Phases 3 to 5 were built while the Phase 2 suite ran; each phase's steps are its own commits.

Display checks, run by Doug on 09-12-26 from a checklist page whose marks and notes were read back. **Answered and passing**, six of the seven this work owed:

| Check | Doug, 09-12-26 |
|---|---|
| A curved arrow and its point editing: the green control point on dashed guides, the bend following it, the head turning along the tangent | "It works perfectly" |
| An elbow arrow and its point editing: three segments at right angles, the bend point moving across only | "Worked Perfectly" |
| A freehand stroke's handles: the on-curve points, the off-curve handles on dashed lines, Alt breaking the continuity | "worked perfectly." |
| An arc of each type: Open, Chord, and Pie | "perfect" |
| A star polygon: five points with even notches, sized and turned by the drag | "perfect" |
| A rectangle with individual radii: two rounded corners diagonally opposite, the uniform slider hidden | "perfect" |

The seventh, a blur region in each mode over a screenshot, was run on 09-12-26 in a second session: **Gaussian Blur passes** (the text under the region completely unreadable and smoothly smeared) and **Pixelate passes** (a clean mosaic of equal tiles with straight edges). **Solid Fill is still blocked**, now by a narrower fault than the first run suggested: "Color would not select. So transparent was only color selectable."

The picker itself is not at fault. The same run took the Rectangle tool's Stroke swatch through the shared picker and it committed a blue correctly, so General UI PRD 11.1 holds. What fails is the Blur tool's own **Fill:** swatch, which `tools/blur_tool.py` builds directly rather than through the Tool Options Bar's shared control path. Checked headlessly on 09-12-26: the wiring is sound — a `color_changed` signal from that picker does set `fill_color` on the tool's creation defaults — so the fault is in the popover interaction, which no headless test can drive and which this work's tests therefore never covered. A Blur PRD row when it is diagnosed; not reproduced in code.

The older checks the Vector Item Properties notes list are answered there.

**Next required step:** the work is complete. The kickoff it named, `docs/Freeform-Blur-Highlighter-Kickoff-Prompt.md` (revision 1.0), was run on 09-11-26 and is complete: its notes are `docs/Freeform-Blur-Highlighter-Implementation.md`, and every row this work left open in the Blur PRD's Section 2 is now built or recorded as a departure there. The display checks above are still owed, and that work adds its own.

**Section 2 of the Basic Shape PRD is closed** by `docs/Basic-Shape-Shared-Drawing-Implementation.md` (09-12-26): the rows the 1.12 row left open in Section 2 — the dimension tooltip and constrain icon of 2.4 and the not-auto-selected rule of 2.5 — are built there, with the Freehand tool's Shift straight segments of 9.5. The shape tools this work built now stay active after a shape is made and draw a 70 percent preview with a tooltip beside the cursor. What remains of the Basic Shape PRD outside Section 2 is named in that work's Section 12.

**Section 9's last rows are closed** by `docs/Freehand-Remainder-Implementation.md` (09-13-26): 9.2's brush-tip cursor, and 9.10's fitting budget and long-stroke preview. Two things there reach back into this work. The Freehand pipeline this work built in Phase 2 is faster with its result unchanged, and its fitting error now has a noise floor below 50 percent smoothing, so the 0.5 px floor of the 1.11 row and the 630 ms figure of Section 4 are superseded (that work's Section 6); and the 9.2 cursor this work's Phase 2 left unbuilt is built (its Section 5). No row of the Basic Shape Annotation Tools PRD is open except the pressure data it reserves and the Open Issues of its Section 14.

**Solid Fill passes**, on Doug's display run of 09-14-26 (checklist page `SnapMock Blur and Eyedropper Display Checks`): with Solid Fill chosen under Mode:, a green typed into the Hex field of the Blur tool's own Fill swatch committed, the swatch turned green, and a dragged rectangle covered the text under it with a solid green box. The seventh check of Section 10 is closed, and with it every display check this work owed. Blur PRD 1.19.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.10 | 09-14-26 09:34 | Claude (Claude Code) | Section 10: Solid Fill passes on the display run of 09-14-26; every display check of this work is answered. Blur PRD 1.19. |
| 1.9 | 09-13-26 14:36 | Claude (Claude Code) | Section 10: the pointer to the Freehand remainder work, which closes Section 9's last rows and supersedes this work's 0.5 px fitting floor and 630 ms figure. |
| 1.8 | 09-12-26 16:01 | Claude (Claude Code) | Section 10: the pointer to the shared drawing work, which closes the Basic Shape PRD's Section 2 and 9.5. |
| 1.7 | 09-12-26 10:35 | Claude (Claude Code) | Section 10: the second display run of 09-12-26. Gaussian Blur and Pixelate pass; Solid Fill stays blocked, narrowed from the shared colour picker (which the same run proved works) to the Blur tool's own Fill swatch, whose signal wiring is sound headlessly, leaving the popover interaction as the fault |
| 1.6 | 09-12-26 09:58 | Claude (Claude Code) | Section 10: the display checks Doug ran on 09-12-26, quoted. Six of the seven pass — the curved and elbow arrows, the freehand handles, the three arc types, the star polygon, and the individual corner radii. The blur modes stay owed, Solid Fill blocked by a colour picker that does not commit a pick. |
| 1.5 | 09-11-26 22:36 | Claude (Claude Code) | Section 10: the kickoff this work named is complete, with its notes in `docs/Freeform-Blur-Highlighter-Implementation.md`; the display checks stay owed. |
| 1.4 | 09-11-26 20:07 | Claude (Claude Code) | The next required step names the kickoff written at Doug's request: `docs/Freeform-Blur-Highlighter-Kickoff-Prompt.md` (revision 1.0). |
| 1.3 | 09-11-26 18:44 | Claude (Claude Code) | Phases 3 to 5 done and the work complete: the phase table, the Phase 3, 4, and 5 sections (what each built, the silences found while building, the blur timings), five deviations added, the tests and the suite run, the close-out of the work with the display checks owed and the next required step. Basic Shape PRD 1.12, Blur PRD 1.6, General UI PRD 2.20, Technical Architecture PRD 1.32, Snagit notes 1.5, General UI notes 1.34, Vector Item Properties notes 1.4. |
| 1.2 | 09-11-26 17:41 | Claude (Claude Code) | Phase 2 done: the phase table, the Phase 2 section (what it built, the silences found while building, the Freehand timings), three deviations added, the Phase 2 tests and the suite run, the next required step. Basic Shape PRD 1.11, General UI PRD 2.19, Technical Architecture PRD 1.31. |
| 1.1 | 09-11-26 16:45 | Claude (Claude Code) | Phase 1 done: the phase table, Section 3 (what Phase 1 built, the silences found while building), Sections 4 and 5 renumbered, Section 5 with the Phase 1 tests and the suite run, the next required step. Basic Shape PRD 1.10, General UI PRD 2.18, Technical Architecture PRD 1.30, Snagit notes 1.4. |
| 1.0 | 09-11-26 15:38 | Claude (Claude Code) | Initial notes: the starting state, the phase table, the four decisions (1 A, 2 A, 3 A with Arc on Shift+A, 4 A) and the kickoff's six silences as chosen 09-11-26, four corrections to the kickoff, five findings decided with the decisions, the deviations they imply, the next required step. Basic Shape PRD 1.9, Blur PRD 1.5, General UI PRD 2.17, Technical Architecture PRD 1.29. |
