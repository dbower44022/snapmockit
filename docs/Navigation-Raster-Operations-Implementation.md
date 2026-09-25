# Navigation & Raster Operations — Implementation Notes

Last Updated: 09-25-26 11:03 · Revision 1.1

This document describes every change made to implement the Navigation & Raster Operations PRD. It covers what was changed, why, and how the pieces fit together.

---

## 1. Command Infrastructure

### 1a. RasterCutCommand — pixel erasure with undo

**File:** `snapmock/commands/raster_commands.py`

The `RasterCutCommand` was stubbed with `pass` in both `redo()` and `undo()`. It now fully erases pixels within a selection rectangle on a specific layer.

**`redo()`** iterates every `RasterRegionItem` on the target layer. For each item whose bounding rect intersects the selection:

1. Saves the original `QPixmap` to a `_backups` list for undo.
2. Converts the pixmap to a `QImage` in `Format_ARGB32_Premultiplied` format. This conversion is necessary because `QPixmap` on X11/Linux does not support per-pixel alpha — `CompositionMode_Clear` has no effect on RGB-only pixmaps.
3. Uses `QPainter` with `CompositionMode_Clear` to erase the intersection region.
4. Converts back to `QPixmap` and assigns it to the item.

**`undo()`** restores each affected item's original pixmap from the backup list.

**Why QImage instead of QPixmap:** On X11, `QPixmap(100, 100).fill(red)` produces `Format_RGB32` with no alpha channel. Painting with `CompositionMode_Clear` zeroes the RGB but leaves alpha at 255 — pixels become black, not transparent. Working in `QImage` space with an explicit ARGB32 format guarantees correct alpha erasure on all platforms.

### 1b. ResizeImageCommand — geometry scaling

**File:** `snapmock/commands/raster_commands.py`

The original `ResizeImageCommand` only repositioned items proportionally but did not scale their internal geometry (a 50×50 rectangle stayed 50×50 after a 2× resize). Now `redo()` calls `item.scale_geometry(sx, sy)` on each item in addition to repositioning.

For undo, the command stores serialized snapshots of every item before scaling. `undo()` deserializes each snapshot and copies geometry fields back via `_restore_geometry()`, a static method that handles all 13 item types through isinstance dispatch.

### 1c. Polymorphic `scale_geometry()` across all items

**Files:** `snapmock/items/base_item.py` + all 13 concrete item files

Added `scale_geometry(sx, sy)` to `SnapGraphicsItem` as a default no-op. Each subclass overrides it to scale its specific internal geometry:

| Item type | What gets scaled |
|-----------|-----------------|
| `VectorItem` | `_stroke_width` by average of sx/sy |
| `RectangleItem` | `_rect` (x, y, width, height) and `_corner_radius` |
| `EllipseItem` | `_rect` |
| `LineItem` | `_line` endpoints (x1·sx, y1·sy, x2·sx, y2·sy) |
| `ArrowItem` | `_line` endpoints (same as LineItem) |
| `FreehandItem` | All `_points` tuples, then rebuilds `_path` |
| `HighlightItem` | All `_points` tuples, then rebuilds `_path` |
| `TextItem` | Font point size by avg(sx,sy), `_width` by sx |
| `CalloutItem` | `_rect`, `_tail_tip`, font point size |
| `BlurItem` | `_rect`, `_blur_radius` |
| `RasterRegionItem` | `_pixmap` via `QPixmap.scaled()` with `SmoothTransformation` |
| `NumberedStepItem` | `_radius`, font point size |
| `StampItem` | `_pixmap` via `QPixmap.scaled()` with `SmoothTransformation` |

Scalar properties like corner radius, blur radius, and stroke width scale by the average of sx and sy to maintain visual proportion under non-uniform scaling. Font sizes are clamped to a minimum of 1 point.

---

## 2. Transform Handle Resize, Rotate, and Skew

### 2a. Rotate handle

**File:** `snapmock/ui/transform_handles.py`

Added `HandlePosition.ROTATE` to the enum and created `RotateHandleItem`, a circular handle (radius 5px) positioned 30px above the top-center of the selection bounding rect. A thin line connects it visually to the top-center edge. The circular shape distinguishes it from the square resize handles.

Added `anchor_for_handle(handle)` which returns the opposite anchor point for any handle — corners map to opposite corners, edges to opposite edges, and ROTATE maps to the selection center. This is used by the SelectTool to compute scale factors relative to the correct origin.

Added `current_rect` property so the SelectTool can capture the selection bounding rect at the start of a drag.

### 2b. Handle drag in SelectTool

**File:** `snapmock/tools/select_tool.py`

Added `HANDLE_DRAG` state to the `_State` enum and five new methods that implement the transform logic:

**`_handle_transform_move()`** routes to the correct transform based on handle type:
- `ROTATE` → `_apply_rotation()`
- Corner handles → `_apply_corner_resize()`
- Edge handles → `_apply_edge_resize()` (or `_apply_skew()` when Ctrl is held)

**`_apply_rotation()`** computes the angle between the drag start and current cursor relative to the selection center using `math.atan2`. When Shift is held, the angle snaps to 15° increments. Each item's position is rotated around the center, and a `QTransform.rotate()` is applied.

**`_apply_corner_resize()`** computes independent sx/sy scale factors from the anchor-to-cursor distance vs anchor-to-original-handle distance. Shift locks aspect ratio (sx == sy), Alt resizes from center instead of the opposite corner. Minimum scale is clamped to 0.01 to prevent collapse.

**`_apply_edge_resize()`** scales one axis only from the opposite edge midpoint. When Ctrl is held, it delegates to `_apply_skew()` which applies a shear transform instead.

**`_handle_transform_release()`** commits the transform. For each item that changed, it reverts to original pos/transform, then creates a `TransformItemCommand`. Multiple items are wrapped in a `MacroCommand`. This ensures undo/redo correctly replays the full operation.

All transform operations show a tooltip near the cursor with dimensions (W×H), angle, or delta values.

---

## 3. SelectTool Remaining Behaviors

**File:** `snapmock/tools/select_tool.py`

### Double-click

`mouse_double_click()` now handles two cases:
- On a `TextItem` or `CalloutItem`: switches to the text tool via the ToolManager, enabling inline text editing.
- On empty canvas: toggles between fit-to-window and 100% zoom.

### Right-click context menu

Added `context_menu()` method that builds a QMenu with Cut, Copy, Paste, Delete, and Duplicate actions. If right-clicking on an unselected item, it is selected first (per PRD 2.2.5). Actions are disabled when no selection exists. Menu actions delegate to the MainWindow's `_edit_*()` methods.

**Files also changed:** `snapmock/tools/base_tool.py` (added `context_menu()` base method), `snapmock/tools/tool_manager.py` (added `handle_context_menu()` delegation), `snapmock/core/view.py` (overrode `contextMenuEvent` to route through ToolManager).

### Snap-to-grid

During item dragging, if the view's grid is visible, the cumulative movement delta is snapped to grid lines using `round(total / grid) * grid`. This keeps items aligned to the grid without affecting the drag feel.

### Move delta tooltip

During item dragging, a `QToolTip` shows `ΔX: +15  ΔY: -8` near the cursor, giving real-time feedback on the total displacement.

### Arrow key nudge

Arrow keys push a `MoveItemsCommand` with a 1px delta (10px with Shift). When no items are selected, `key_press()` returns `False` to let the event fall through to the MainWindow for viewport panning.

---

## 4. Pan & Zoom Enhancements

### Keyboard pan

**File:** `snapmock/main_window.py`

`keyPressEvent()` now handles arrow keys when no items are selected and no tool has an active operation. Plain arrows pan by 20px, Shift+arrows by 100px. This provides quick keyboard navigation of a zoomed-in canvas without switching tools.

### Auto edge scroll

**File:** `snapmock/core/view.py`

Added `_check_auto_scroll()`, `_stop_auto_scroll()`, and `_do_auto_scroll()` methods with a 16ms QTimer. During any active tool operation, if the cursor is within 20px of a viewport edge, the canvas scrolls in that direction at a speed proportional to the distance from the edge (up to 15px per frame). Scrolling stops when the cursor leaves the edge zone or the drag ends.

`mouseMoveEvent()` calls `_check_auto_scroll()` when the active tool reports `is_active_operation == True`. `mouseReleaseEvent()` calls `_stop_auto_scroll()`.

### Zoom animation

**File:** `snapmock/core/view.py`

Added `animate_zoom_to()` which uses a `QTimeLine` with 10 frames over 100ms and an `OutCubic` easing curve. It interpolates from the current zoom to the target and calls `set_zoom_centered()` per frame. If a new zoom is triggered during animation, the running timeline is replaced. `zoom_in()` and `zoom_out()` now use animated zoom.

### Zoom to selection

**Files:** `snapmock/main_window.py`, `snapmock/config/shortcuts.py`

Added `Ctrl+Shift+0` shortcut and View menu action. `_view_zoom_to_selection()` computes the bounding rect of selected items, adds padding, and calls `view.fitInView()` to frame the selection.

---

## 5. Raster Selection Tool Completion

**File:** `snapmock/tools/raster_select_tool.py`

Added `has_active_selection` and `selection_rect` properties so the MainWindow can detect an active raster selection and access its bounds for copy/cut operations.

**Shift-square constraint:** When Shift is held during drawing, the selection is constrained to a square. The anchor corner remains stable (the constraint adjusts the opposite corner, not the start point).

**Alt-from-center:** When Alt is held, the start point becomes the center of the selection rather than a corner. The rect expands equally in all directions. Shift+Alt produces a square from center.

**Dimensions tooltip:** During drawing, a `QToolTip` shows `W: 150  H: 80` near the cursor.

**Tool options:** `build_options_widgets()` adds a Feather radius spinbox (0–20px) and Anti-alias checkbox to the toolbar.

---

## 6. Lasso Selection Tool Completion

**File:** `snapmock/tools/lasso_select_tool.py`

### Commit action

Pressing Enter/Return when the lasso selection is in the ACTIVE state calls `_commit_as_item()`, which:

1. Gets the bounding rect of the selection path.
2. Renders that region via `RenderEngine.render_region()`.
3. Applies the freeform path as an alpha mask: creates a transparent `QImage`, sets a `QPainter` clip path to the lasso outline translated to local coordinates, draws the rendered image through the clip.
4. Creates a `RasterRegionItem` from the masked pixmap and pushes an `AddItemCommand`.

This extracts the selected pixels into a new movable item, similar to Photoshop's "Layer via Copy" behavior.

Added `has_active_selection` and `selection_rect` properties for clipboard integration.

**Status hints:** State-dependent hints guide the user through freeform ("Release to close") and polygonal ("Click to add vertex, Enter to close") workflows.

**Tool options:** Mode selector (Freeform/Polygonal), Feather, Anti-alias.

---

## 7. Clipboard & Paste Routing

### Raster clipboard support

**File:** `snapmock/core/clipboard_manager.py`

Added `_raster_data` (QImage) and `_raster_source_rect` (QRectF) fields alongside the existing internal item clipboard. Key methods:

- `copy_raster_region(image, source_rect)`: Stores the image and rect, clears internal item data (raster takes priority), and puts a PNG on the system clipboard.
- `paste_raster()`: Returns a copy of the stored image and rect, or `(None, None)`.
- `has_raster` property: True when raster data is available.
- `clear()`: Resets both item and raster data.

Copying raster data clears internal item data to prevent ambiguity in paste priority.

### Raster copy/cut from active selections

**File:** `snapmock/main_window.py`

`_edit_copy()` and `_edit_cut()` now check if the active tool is a `RasterSelectTool` or `LassoSelectTool` with `has_active_selection`. If so, they route to `_copy_raster_selection()` (renders the selection region via RenderEngine and stores in clipboard) and `_cut_raster_selection()` (copies, then pushes a `RasterCutCommand` to erase the pixels, then cancels the selection).

### Unified paste routing

**File:** `snapmock/main_window.py`

`_edit_paste()` follows a 4-tier priority:

1. **Internal vector items** — `paste_items()` returns serialized data → deserialize and add.
2. **Internal raster data** — `paste_raster()` returns QImage → create `RasterRegionItem`.
3. **System clipboard image** — `paste_image_from_system()` → `place_image` (the background of an empty project, else a `RasterRegionItem`).
4. **System clipboard text** — `QApplication.clipboard().text()` → create `TextItem`.

Each tier returns early if it has data, so the first match wins. After pasting, the tool switches to Select and the new items are selected.

### Where a paste lands (PRD 5.5.3, 9.3.1, 9.3.3, 9.3.4; 1.12, 09-25-26)

Every tier puts the top-left corner of the content, for several items the top-left of their joint bounding box with the arrangement kept, at one anchor from `_paste_anchor(at)`:

1. `at`, an explicit scene point. The canvas and item context menus pass the right-click point (`build_canvas_context_menu(parent, scene_pos)`, `build_item_context_menu(parent, scene_pos)`), since by the time a row is chosen the pointer is over the menu.
2. Else `SnapView.pointer_scene_pos`, the pointer's last position over the viewport. The view records it in `mouseMoveEvent` and clears it in `leaveEvent`; it counts only while the viewport is visible, so a paste from the Welcome card never uses a stale point.
3. Else the viewport centre: Edit > Paste, or a shortcut pressed with the pointer off the canvas.

Before 1.12, items landed ten pixels from the original, a raster at its source rectangle, and an image or text centred on the viewport.

`_edit_paste_in_place()` keeps items at their original positions and a raster at its source rectangle; content with no original position (a raster without a source rectangle, a system image) lands at the same anchor as Paste.

---

## 8. Inter-Tool Interactions & Edge Cases

### Undo guard

**File:** `snapmock/main_window.py`

`_edit_undo()` checks `active_tool.is_active_operation` before undoing. If a tool has an active drag, resize, or selection in progress, the first Ctrl+Z cancels that operation instead of undoing a command. The second Ctrl+Z performs the actual undo. This prevents undo from firing mid-drag, which would leave the tool in an inconsistent state.

### Layer state handlers

**File:** `snapmock/main_window.py`

Connected `layer_lock_changed`, `layer_visibility_changed`, and `active_layer_changed` signals:

- **Layer locked:** Deselects all items on that layer. A locked layer's items should not be movable or transformable.
- **Layer hidden:** Deselects all items on that layer. Hidden items should not participate in selection.
- **Active layer changed:** Cancels any active raster or lasso selection. The selection overlay is specific to a layer; switching layers invalidates it.

### Focus loss cleanup

**File:** `snapmock/core/view.py`

`focusOutEvent()` releases any active middle-mouse panning, restores the previous tool if space-bar temporary pan was active, cancels the active tool operation if `is_active_operation` is True, and stops auto-scroll. This prevents ghost drags when the window loses focus mid-operation.

### Deleted Qt object guard

**File:** `snapmock/core/selection_manager.py`

When a `QGraphicsItem` is removed from the scene and garbage collected on the C++ side, the Python reference in `_selected` becomes a dangling pointer. Calling `setSelected(False)` on it crashes with `RuntimeError: wrapped C/C++ object has been deleted`.

Fixed by checking `sip.isdeleted(item)` before calling `setSelected()` in `_deselect_all_internal()` and `toggle()`. The `toggle()` method also prunes any deleted items from the list when a stale reference is encountered.

---

## 9. Status Bar Hints

**Files:** `snapmock/tools/base_tool.py` + all 15 tool files

Added a `status_hint` property to `BaseTool` (default empty string). Each tool overrides it with context-sensitive guidance:

| Tool | Hint examples |
|------|--------------|
| SelectTool | "Click to select \| Drag to move" / "Shift: constrain axis" / "Shift: snap to 15°" |
| RasterSelectTool | "Click and drag to select region" / "Shift: square \| Alt: from center" / "Enter: commit" |
| LassoSelectTool | "Click and drag to draw freeform selection" / "Click to add vertices, double-click to close" |
| CropTool | "Click and drag to define crop area" |
| PanTool | "Click and drag to pan the canvas" |
| ZoomTool | "Click to zoom in \| Alt+click to zoom out" |
| Drawing tools | "Click and drag to draw [shape]" |
| EyedropperTool | "Click to sample a color from the canvas" |

The MainWindow connects the `tool_changed` signal to update the status bar with the new tool's hint.

---

## 10. CommandStack Merge Fix

**File:** `snapmock/core/command_stack.py`

**Bug:** When `push()` merged a new command into the top command via `merge_with()`, it then called `top.undo(); top.redo()`. But `merge_with()` had already mutated the top command's delta to the combined value. So `undo()` reversed the *new combined* delta (overshooting past the original position), and `redo()` applied the *same combined* delta (landing back where it started). Net effect: zero movement. Consecutive arrow key nudges were silently lost.

**Fix:** After a successful merge, call `command.redo()` instead. This applies only the new command's incremental effect. The top command's prior effect is already reflected in the scene, and `merge_with()` has already updated the top's internal state for correct future undo/redo.

---

## 11. Test Suite

Four new test files with 39 tests covering the implementation:

### `tests/test_raster_commands.py` (9 tests)
- RasterCutCommand: erases pixels, undo restores them, ignores other layers, no-op when no intersection.
- ResizeImageCommand: scales canvas size, item positions, item geometry (via scale_geometry), undo restores all state, scales raster pixmaps.

### `tests/test_transform_resize.py` (15 tests)
- `scale_geometry()` for all 13 item types with appropriate assertions (rect dimensions, point coordinates, pixmap sizes, font sizes, radius values).
- TransformHandles: handle positions hit-test correctly, anchor returns the opposite point.
- TransformItemCommand: redo applies pos/transform, undo restores them.

### `tests/test_clipboard_raster.py` (7 tests)
- `copy_raster_region()` stores data and clears internal items.
- `paste_raster()` returns stored image and source rect.
- Empty clipboard returns `(None, None)`.
- `clear()` resets all data.
- `clipboard_changed` signal fires on raster copy.
- Raster copy clears previously stored internal items.

### `tests/test_inter_tool.py` (8 tests)
- Undo guard: active operation is cancelled before undo fires.
- Layer lock/hide: items on affected layer are deselected.
- RasterCutCommand via command stack: full push/undo/redo cycle.
- BaseTool contract: default status_hint is empty, cancel is safe to call.
- SelectionManager: toggle deselects, select_items replaces.

---

## Revision control

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 09-25-26 11:03 | Claude (Claude Code) | Section 7: paste lands at the pointer (PRD 1.12), the anchor rule, and the context menus' right-click point; the revision block added. |
| 1.0 | — | Claude (Claude Code) | First issue, written at the close of the Navigation & Raster Operations build. |

## Change log

| Date | Section | Type | Detail |
|---|---|---|---|
| 09-25-26 11:03 | 7 | Changed | **Changed** the paste routing text: every tier lands at one anchor, the pointer over the viewport, else the viewport centre, or a context menu's right-click point. |
