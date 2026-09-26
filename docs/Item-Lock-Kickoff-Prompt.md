# Kickoff Prompt: The Item Lock

Last Updated: 09-25-26 20:47 · Revision 1.0

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. Start it only when no other session is committing in this working directory: the work edits `snapmock/tools/select_tool.py`, `snapmock/main_window.py`, `snapmock/items/base_item.py`, the Property Panel, and the serializer, which every other session touches too.

This prompt exists because Doug asked on 09-25-26 what the Locked checkbox does and the answer was: almost nothing. The Technical Architecture PRD says a locked item "cannot be selected, moved, or edited"; the code reads the flag in three places and enforces none of that. Doug's instruction: build exactly what the PRD defines.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root. No other repository is involved in this session. Every reply opens with the local time from `date`, as the global guidance says.

## Task

Build the per-item lock as the PRDs define it, so that a locked item cannot be selected, moved, or edited until it is unlocked, whatever layer it sits on, and so that the lock survives a save, a copy, and a duplicate.

The definition is spread over four places, and all four are binding:

- Technical Architecture PRD 3.1.4, the item base class table (`PRDs/SnapMock-Technical-Architecture-PRD.html`, version 1.72 at the start of this work): `locked`, bool, "If True, item cannot be selected, moved, or edited. Mirrors the parent layer lock state OR per-item lock." The same document's 3.2 says a layer's lock toggle "update[s] all child items' lock state", and its 3.4 says only items on unlocked, visible layers can be selected.
- General UI PRD Section 8, the Property Panel's Item Info section (`PRDs/SnapMock-General-UI-PRD.html`, version 2.60): "Item Lock: checkbox to lock this specific item (independent of layer lock)". Section 10.2, the item context menu: the row "Lock Item / Unlock Item".
- Navigation & Raster Operations PRD Section 2 (`PRDs/SnapMock-Navigation-Raster-Operations-PRD.html`, version 1.13): 2.2.2 ignores a click on an item of a locked layer and shows the forbidden cursor on hover; the rubber band filters such items out; Delete silently skips them; the status bar hint row reads "This item is locked. Unlock its layer to interact with it." Every one of these rules gains the item's own lock as a second cause in this work, and the hint's wording changes to cover both.
- Technical Architecture PRD 3.8, the `.smk` format (its change-log rows call it 6.1): every item property that a user can set is saved in `items.json`. The lock is not saved today; after this work it is.

The session opens by presenting the one decision below with the consequential decision template and waits. Nothing is built before it is taken.

## Read first, in this order

1. `docs/General-UI-Implementation.md`, revision 1.49: Section 1 for the phase table, Section 5.1 for the decisions taken so far, Sections 28 and 29 for the two most recent pieces of work and the shape a section takes.
2. The four PRD passages named under Task, and in the General UI PRD also 1.3 (no control is ever disabled; a handler checks its own requirement and shows the message), 6.6 (the canvas cursors: the forbidden cursor over what cannot be dragged), 8.6 (the multi-selection rules the Property Panel follows, which decide what a mixed locked and unlocked selection shows), and the change log from 2.60 down to 2.55.
3. `snapmock/items/base_item.py`: `SnapGraphicsItem.locked` is a plain flag with no side effect (line 127); `serialize` and `deserialize` carry no lock; `clone` goes through them, so a duplicate is unlocked today. `snapmock/items/group_item.py`: `add_member` copies the group's lock onto a member and the `locked` setter pushes it down to every member, the one place the flag propagates.
4. `snapmock/tools/select_tool.py`: `_item_at` (the click and hover resolver) skips items on locked or hidden layers and the Background image and never reads the item's own flag; `_locked_item_at` decides the forbidden cursor by the layer alone; the rubber band (about line 984) and `cycle_selection` (about line 1508) filter by layer alone; the arrow-key nudge table at about line 1429; `_handle_transform_move` and `_handle_transform_release` move and resize whatever is selected; `mouse_double_click` enters text editing and point editing.
5. `snapmock/main_window.py`: `_toggle_item_lock` (about line 3615) sets the flag directly with no command, so the context-menu row is not undoable while the Property Panel's checkbox is; `_edit_select_all_on_layer`, `_edit_select_all_layers`, `_edit_select_all_text` skip locked items already; `_edit_delete`, `_edit_cut`, `_edit_duplicate`, `_move_items_to_layer`, `_edit_find_replace_color`, the align, distribute, and z-order handlers, and `_show_item_properties` (the Item Properties dialog, which also carries a Locked checkbox) act on whatever is selected.
6. `snapmock/ui/property_panel.py`: `_locked_check` (about line 1172) and `_on_locked_changed` (about line 2314), which pushes `ModifyPropertyCommand(item, "locked", ...)`; `_selected_items` and `_selected_vectors`, which every row's handler uses; the Item Info section's rows.
7. `snapmock/ui/context_menus.py` (`build_item_context_menu`: the Lock Item / Unlock Item row reads the first selected item's flag), `snapmock/tools/text_tool.py` (its hover cursor and its click both read the layer's lock, about lines 537 to 563), `snapmock/core/scene.py` (`apply_layer_state` mirrors a layer's visibility, opacity, and blend mode onto an item, and nothing of its lock; `annotation_items` and `all_annotation_items` are the two walks), `snapmock/core/selection_manager.py` (`select` refuses only the Background image, through `scene.is_fixed_in_place`), `snapmock/io/project_serializer.py` (`ITEM_REGISTRY`, and the layer's `locked` at lines 139 and 330 as the pattern to follow for the item's).
8. `tests/test_context_menus.py` (`test_lock_text_shows_lock_item`, `test_lock_text_shows_unlock_item`, `test_lock_text_toggles`), `tests/test_item_properties_dialog.py::test_detects_locked_toggle`, `tests/test_cursors.py` (the two locked-layer cursor tests, about lines 140 and 209), `tests/test_group.py` (the locked-group tests), `tests/test_property_panel.py`, `tests/test_tools/test_select_tool.py`, and `tests/test_io/test_project_serializer.py`: read the names to know what each area already asserts.

Do not write anything until all eight are read.

## Starting state, verified at commit 2ea2f57 on 09-25-26

- The suite passes at about 1,910 tests with 14 skipped, ruff and mypy strict clean, once the two environmental tests are deselected (see the suite command below).
- `SnapGraphicsItem.locked` exists and is set by three routes: the Property Panel's Locked checkbox (undoable), the item context menu's Lock Item / Unlock Item row (not undoable), and a group onto its members.
- The flag is read in exactly three places: Select All on Layer, Select All Layers, and Select All Text skip a locked item, and the context menu's row reads Lock Item or Unlock Item. A locked item can still be clicked, rubber-banded, Tab-cycled, dragged, resized, rotated, nudged, deleted, cut, recoloured, aligned, moved to another layer, and edited in place. The hover cursor over it is the open hand.
- The flag is not saved in `items.json`, not carried by the clipboard, and not carried by Duplicate.
- The layer lock is enforced by the Select tool and the Text tool through the layer, never through the item's flag; the Technical Architecture PRD's "update all child items' lock state" on a layer toggle is not built, and this work decides whether it needs to be (see the silences).
- The Navigation PRD's hint row for a locked item names the layer as the only cause.

## Steps, one commit each

1. **Decision.** Present decision 1 below; record the choice in a new Section 30 of `docs/General-UI-Implementation.md`, "The Item Lock", with a phase-table row in Section 1 marked in progress; bump the notes' revision.
2. **The model.** One question answered in one place: `SnapScene.is_locked(item)`, true when the item's own flag is set, when any group above it is locked, or when its layer is locked. `serialize` and `deserialize` on the base class carry `locked` (a missing key reads as unlocked, per the format-version rule), so a save, the clipboard, and Duplicate keep it. `_toggle_item_lock` pushes the same `ModifyPropertyCommand` the checkbox does, so both routes undo. Technical Architecture PRD 1.73: the 3.8 format note and the 3.1.4 row's wording if the decision changes it. Tests: the round trip, the clone, the undo of each route.
3. **Selection.** The Select tool's `_item_at`, rubber band, and `cycle_selection`, the Text tool's click, and `SelectionManager.select` all refuse a locked item through `is_locked`; the hover cursor over one is the forbidden cursor; the hint reads as decision 1 says. What a right-click on a locked item does follows decision 1. Tests in `tests/test_tools/test_select_tool.py` and `tests/test_cursors.py`.
4. **Mutation.** Every handler that changes selected items skips a locked one, silently where the Navigation PRD says silently (Delete, Cut, the nudge, a drag that began on an unlocked item of a mixed selection) and with the 1.3 message where the whole selection is locked and the row was asked for by name (the Property Panel's rows, Align, Distribute, z-order, Move to Layer, Find/Replace Color, the Item Properties dialog). The Locked checkbox itself and the Lock Item / Unlock Item row are the two controls that must keep working on a locked item, since they are the way out. Tests per handler.
5. **Close-out.** General UI PRD 2.61: rows for the Item Info checkbox and the 10.2 row as built, the decision, and every silence decided; Navigation PRD 1.14: the 2.2.2, rubber band, Delete, and hint rows gain the item's own lock; Technical Architecture PRD 1.73 if not already bumped. Notes: Section 30 complete with what was built and the deviations, the phase-table row done, the revision bumped, and the next required step stated. Then the display checks, one per rung of Steps 3 and 4, as a numbered list for Doug.

Each commit is ruff-clean and mypy-strict-clean with the suite passing. Run the full suite in the background to a log file as

```bash
QT_QPA_PLATFORM=offscreen uv run pytest -q --deselect tests/test_app.py::test_main_window_default_size --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font -p no:cacheprovider
```

It takes about seven minutes here. A modal dialog left open by a test hangs the run: any test that can reach an unmet-requirement message takes the `unmet_messages` fixture of `tests/conftest.py`. A headless `QTest.keyClick` on a widget never fires a menu action's shortcut; `QTest.keyClick(window.windowHandle(), ...)` does.

## Decision to surface

Apply the two-part test from the global guidance. One decision is expected to pass it; present it with the consequential decision template before step 2 and wait.

- **1. How a locked item is unlocked.** The Technical Architecture PRD says a locked item cannot be selected, and the General UI PRD puts the unlock in the Property Panel's Item Info section, which shows only for a selection. Both cannot hold as written. Option A, unselectable, as the item table says: a click, a rubber band, and Tab pass over a locked item as they pass over a locked layer's; the way out is the context menu, whose Unlock Item row acts on the item under the pointer without selecting it, and the Layer Panel's lock is untouched; the Property Panel's checkbox therefore only ever locks. Its cost: nothing on the canvas shows that an item is locked but the forbidden cursor and the hint, and a user who locked an item through the checkbox cannot unlock it there. Option B, selectable but frozen: a locked item can be selected, its handles draw in a locked style and do nothing, no drag, nudge, edit, or delete reaches it, and the Property Panel shows Item Info with the checkbox live and every other section's rows answering with the 1.3 message; the item table's "cannot be selected" is reworded to "cannot be moved or edited" in Technical Architecture PRD 1.73. Its cost: the wording of the PRD changes, and the Select tool needs a locked look for the handles. Recommendation: A, since Doug asked for the PRD as written and the context-menu route exists in the PRD already; the cost is named.

Everything else follows the PRDs; where they are silent, decide, note it under the notes' Section 30 and the PRD rows, and continue. Five silences are known:

- Whether a layer's lock toggle writes the item flags (Technical Architecture 3.2) or `is_locked` reads the layer live. Reading live keeps the item's own flag its own, which is what "independent of layer lock" needs; writing would erase it. Decide for reading live unless the reading list shows a reason not to.
- What Group does with a locked member, and what a group's lock means to Ungroup (`tests/test_group.py` holds today's answers; keep them unless they conflict with step 2).
- Whether the clipboard's PNG rendering and the exports are affected. They are not; a lock changes nothing that paints.
- Whether Paste and Paste in Place of a locked item produce a locked copy. Yes, by step 2, and the copy is then selected by the paste handlers of 09-25-26, which must not select a locked item: the paste selects what it can.
- What the Escape ladder of General UI PRD 2.58 does when the item last added is locked: nothing is selected, as `_selectable` in `snapmock/main_window.py` already says; extend that helper to read `is_locked` and keep the test.

## Revision control

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-25-26 20:47 | Claude (Claude Code) | First issue, written at the close of the 09-25-26 session that found the gap. |
