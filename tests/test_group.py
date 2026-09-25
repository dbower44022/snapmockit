"""Group and Ungroup (General UI PRD 3.6): the group item, its commands, and the walks."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.commands.arrange_commands import apply_layer_z_values
from snapmock.commands.group_commands import GroupItemsCommand, UngroupItemsCommand
from snapmock.commands.move_item_layer import MoveItemToLayerCommand
from snapmock.core.clipboard_manager import ClipboardManager
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.io.project_serializer import ITEM_REGISTRY, load_project, save_project
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.ellipse_item import EllipseItem
from snapmock.items.group_item import GroupItem, transform_from_list, transform_to_list
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=800, height=600)


def _rect(x: float, y: float, w: float = 100, h: float = 60) -> RectangleItem:
    item = RectangleItem(rect=QRectF(0, 0, w, h))
    item.setPos(x, y)
    return item


def _group_of(*items: SnapGraphicsItem) -> GroupItem:
    """A group at the members' top-left, the members offset to keep their scene positions."""
    union = items[0].sceneBoundingRect()
    for item in items[1:]:
        union = union.united(item.sceneBoundingRect())
    group = GroupItem()
    group.setPos(union.topLeft())
    for index, item in enumerate(items):
        item.setPos(item.pos() - union.topLeft())
        item.setZValue(index)
        group.add_member(item)
    return group


def _add(scene: SnapScene, item: SnapGraphicsItem) -> None:
    layer = scene.layer_manager.active_layer
    assert layer is not None
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))


# --- the item (step 2) ---


def test_group_is_registered_and_named() -> None:
    assert ITEM_REGISTRY["GroupItem"] is GroupItem
    assert GroupItem().type_name == "Group"


def test_group_members_keep_their_scene_positions_and_stacking() -> None:
    a = _rect(10, 20)
    b = _rect(200, 100)
    group = _group_of(a, b)
    assert group.pos() == QPointF(10, 20) - QPointF(1, 1)  # the stroke's half width
    assert a.sceneBoundingRect().topLeft() == QPointF(9, 19)
    assert b.sceneBoundingRect().topLeft() == QPointF(199, 99)
    assert group.members == [a, b]
    assert group.member_count == 2
    assert group.boundingRect() == group.childrenBoundingRect()
    assert group.sceneBoundingRect() == a.sceneBoundingRect().united(b.sceneBoundingRect())


def test_group_shape_is_the_union_of_the_members_shapes() -> None:
    a = _rect(0, 0)
    b = _rect(300, 300)
    group = _group_of(a, b)
    on_a = group.mapFromScene(QPointF(0, 30))  # a's left stroke
    gap = group.mapFromScene(QPointF(200, 200))
    assert group.shape().contains(on_a)
    assert not group.shape().contains(gap)
    assert group.boundingRect().contains(gap)


def test_group_paints_nothing_and_members_are_carried(scene: SnapScene) -> None:
    from snapmock.core.render_engine import RenderEngine

    a = _rect(10, 10)
    a.fill_color = a.stroke_color  # a filled red square
    group = _group_of(a)
    _add(scene, group)
    image = RenderEngine(scene).render_to_image()
    assert image.pixelColor(50, 30) == a.stroke_color
    group.setPos(group.pos() + QPointF(300, 0))
    image = RenderEngine(scene).render_to_image()
    assert image.pixelColor(50, 30).name() == "#ffffff"
    assert image.pixelColor(350, 30) == a.stroke_color


def test_layer_state_and_lock_reach_the_members(scene: SnapScene) -> None:
    a = _rect(0, 0)
    group = _group_of(a)
    manager = scene.layer_manager
    other = manager.add_layer("Layer 2")
    _add(scene, group)
    assert a.layer_id == group.layer_id
    group.layer_id = other.layer_id
    assert a.layer_id == other.layer_id
    manager.set_opacity(other.layer_id, 0.5)
    assert group.layer_opacity == 0.5
    assert a.layer_opacity == 0.5
    manager.set_visibility(other.layer_id, False)
    assert not a.isVisible()
    group.locked = True
    assert a.locked
    group.locked = False
    assert not a.locked


def test_group_flip_is_a_transform_about_the_centre() -> None:
    a = _rect(0, 0, 100, 50)
    b = _rect(200, 0, 100, 50)
    group = _group_of(a, b)
    centre = group.sceneBoundingRect().center()
    left_before = a.sceneBoundingRect()
    group.flip_horizontal = True
    assert group.flip_horizontal
    assert group.sceneBoundingRect().center() == centre
    # a now sits where b was, mirrored
    assert a.sceneBoundingRect().left() == pytest.approx(199)
    group.flip_horizontal = False
    assert a.sceneBoundingRect() == left_before
    assert group.transform().isIdentity()
    group.setRotation(30)
    group.flip_vertical = True
    group.flip_vertical = False
    assert group.transform().isIdentity()


def test_group_scale_geometry_scales_members_and_their_offsets() -> None:
    a = _rect(0, 0, 100, 50)
    b = _rect(200, 0, 100, 50)
    group = _group_of(a, b)
    width = group.boundingRect().width()
    group.scale_geometry(2.0, 1.0)
    assert b.pos().x() == pytest.approx(400 + 2)  # its offset from the group, doubled
    assert a.rect.width() == 200
    assert group.boundingRect().width() == pytest.approx(width * 2, abs=4)


def test_group_serialize_round_trip_carries_members_and_transform() -> None:
    a = _rect(10, 20)
    b = EllipseItem(rect=QRectF(0, 0, 40, 40))
    b.setPos(300, 300)
    group = _group_of(a, b)
    group.setTransform(QTransform().scale(2, 3))
    group.setRotation(15)
    group.setOpacity(0.5)
    data = group.serialize()
    assert data["type"] == "GroupItem"
    assert [m["type"] for m in data["members"]] == ["RectangleItem", "EllipseItem"]
    restored = GroupItem.deserialize(data)
    assert restored.item_id == group.item_id
    assert restored.pos() == group.pos()
    assert restored.rotation() == 15
    assert restored.opacity() == 0.5
    assert restored.transform() == group.transform()
    members = restored.members
    assert [type(m) for m in members] == [RectangleItem, EllipseItem]
    assert [m.item_id for m in members] == [a.item_id, b.item_id]
    assert members[1].pos() == b.pos()
    assert restored.sceneBoundingRect() == group.sceneBoundingRect()


def test_transform_list_helpers() -> None:
    t = QTransform().rotate(20).scale(1.5, 0.5).shear(0.1, 0)
    assert transform_from_list(transform_to_list(t)) == t
    assert transform_from_list(None).isIdentity()
    assert transform_from_list([1, 2]).isIdentity()
    assert transform_from_list(["x"] * 9).isIdentity()


def test_deserialize_skips_unknown_member_types() -> None:
    data = GroupItem().serialize()
    data["members"] = [{"type": "NoSuchItem"}, _rect(0, 0).serialize(), "junk"]
    restored = GroupItem.deserialize(data)
    assert restored.member_count == 1


def test_group_save_and_load_through_the_project_file(scene: SnapScene, tmp_path: Path) -> None:
    a = _rect(10, 20)
    b = _rect(200, 100)
    group = _group_of(a, b)
    _add(scene, group)
    path = tmp_path / "group.smk"
    save_project(scene, path)
    loaded = load_project(path)
    top_level = loaded.annotation_items()
    assert len(top_level) == 1
    assert len(loaded.all_annotation_items()) == 3
    loaded_group = top_level[0]
    assert isinstance(loaded_group, GroupItem)
    assert loaded_group.member_count == 2
    assert loaded_group.sceneBoundingRect() == group.sceneBoundingRect()
    layer = loaded.layer_manager.layers[0]
    assert layer.item_ids == [group.item_id]
    assert all(m.layer_id == layer.layer_id for m in loaded_group.members)


def test_group_of_groups_round_trips(scene: SnapScene, tmp_path: Path) -> None:
    inner = _group_of(_rect(0, 0), _rect(150, 0))
    outer = _group_of(inner, _rect(0, 200))
    _add(scene, outer)
    assert [type(m) for m in outer.members] == [GroupItem, RectangleItem]
    assert len(outer.descendants()) == 4
    path = tmp_path / "nested.smk"
    save_project(scene, path)
    loaded = load_project(path)
    groups = [i for i in loaded.annotation_items() if isinstance(i, GroupItem)]
    assert len(groups) == 1
    assert len(loaded.all_annotation_items()) == 5  # two groups and three rectangles
    assert isinstance(groups[0].members[0], GroupItem)
    assert groups[0].members[0].member_count == 2
    assert groups[0].sceneBoundingRect() == outer.sceneBoundingRect()


def test_clone_gives_every_item_a_new_id() -> None:
    inner = _group_of(_rect(0, 0), _rect(150, 0))
    outer = _group_of(inner, _rect(0, 200))
    copy = outer.clone()
    assert isinstance(copy, GroupItem)
    old_ids = {outer.item_id} | {i.item_id for i in outer.descendants()}
    new_ids = {copy.item_id} | {i.item_id for i in copy.descendants()}
    assert len(new_ids) == 5
    assert old_ids.isdisjoint(new_ids)
    assert copy.sceneBoundingRect() == outer.sceneBoundingRect()


def test_clipboard_carries_a_group_and_pastes_it_through_the_registry(scene: SnapScene) -> None:
    group = _group_of(_rect(0, 0), _rect(150, 0))
    _add(scene, group)
    clipboard = ClipboardManager(scene)
    clipboard.copy_items([group])
    data = clipboard.paste_items()
    assert len(data) == 1
    assert data[0]["type"] == "GroupItem"
    pasted = ITEM_REGISTRY[data[0]["type"]].deserialize(data[0])
    assert isinstance(pasted, GroupItem)
    assert pasted.member_count == 2


# --- the commands and the rows (step 3) ---


def _two_rects_on_layer(scene: SnapScene) -> tuple[RectangleItem, RectangleItem, RectangleItem]:
    """Three rectangles in z-order a, b, c; the tests group a and c."""
    a, b, c = _rect(0, 0), _rect(50, 50), _rect(300, 300)
    for item in (a, b, c):
        _add(scene, item)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    apply_layer_z_values(scene, layer.layer_id)
    return a, b, c


def test_group_command_builds_the_group_in_the_topmost_members_place(scene: SnapScene) -> None:
    a, b, c = _two_rects_on_layer(scene)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    manager = SelectionManager(scene)
    before = {i: i.sceneBoundingRect() for i in (a, b, c)}
    command = GroupItemsCommand(scene, [c, a], manager)
    scene.command_stack.push(command)
    group = command.group
    assert group is not None
    assert group.members == [a, c]  # bottom first, the layer's order
    assert group.layer_id == layer.layer_id
    assert layer.item_ids == [b.item_id, group.item_id]
    assert group.zValue() == layer.z_base + 1
    assert scene.annotation_items() == [group, b] or set(scene.annotation_items()) == {group, b}
    for item, rect in before.items():
        assert item.sceneBoundingRect() == rect
    assert group.sceneBoundingRect() == before[a].united(before[c])
    assert manager.items == [group]
    assert command.description == "Group 2 items"


def test_group_command_undo_and_redo_restore_items_and_selection(scene: SnapScene) -> None:
    a, b, c = _two_rects_on_layer(scene)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    ids_before = list(layer.item_ids)
    z_before = [i.zValue() for i in (a, b, c)]
    manager = SelectionManager(scene)
    command = GroupItemsCommand(scene, [a, c], manager)
    scene.command_stack.push(command)
    scene.command_stack.undo()
    assert layer.item_ids == ids_before
    assert [i.zValue() for i in (a, b, c)] == z_before
    assert all(i.parentItem() is None for i in (a, b, c))
    assert command.group is not None and command.group.scene() is None
    assert a.pos() == QPointF(0, 0) and c.pos() == QPointF(300, 300)
    assert manager.items == [a, c]
    scene.command_stack.redo()
    assert layer.item_ids == [b.item_id, command.group.item_id]
    assert a.parentItem() is command.group
    assert manager.items == [command.group]


def test_ungroup_command_restores_positions_and_properties(scene: SnapScene) -> None:
    a, b, c = _two_rects_on_layer(scene)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    manager = SelectionManager(scene)
    grouping = GroupItemsCommand(scene, [a, c], manager)
    scene.command_stack.push(grouping)
    group = grouping.group
    assert group is not None
    # The user moved, scaled, and rotated the group as one unit
    group.setPos(group.pos() + QPointF(40, 10))
    group.setTransform(QTransform().scale(2, 2))
    group.setRotation(30)
    shown = {i: (i.sceneBoundingRect(), i.mapToScene(QPointF(3, 4))) for i in (a, c)}
    ids_before = list(layer.item_ids)
    ungroup = UngroupItemsCommand(scene, [group], manager)
    scene.command_stack.push(ungroup)
    assert group.scene() is None
    assert layer.item_ids == [b.item_id, a.item_id, c.item_id]
    for item, (rect, point) in shown.items():
        assert item.parentItem() is None
        assert item.mapToScene(QPointF(3, 4)).x() == pytest.approx(point.x())
        assert item.mapToScene(QPointF(3, 4)).y() == pytest.approx(point.y())
        got = item.sceneBoundingRect()
        for attr in ("left", "top", "width", "height"):
            assert getattr(got, attr)() == pytest.approx(getattr(rect, attr)(), abs=1e-6)
        assert item.rotation() == 0  # the member's own rotation is untouched
    assert a.zValue() == layer.z_base + 1 and c.zValue() == layer.z_base + 2
    assert manager.items == [a, c]
    assert ungroup.description == "Ungroup"
    scene.command_stack.undo()
    assert group.scene() is scene
    assert a.parentItem() is group and c.parentItem() is group
    assert layer.item_ids == ids_before
    assert manager.items == [group]
    scene.command_stack.redo()
    assert layer.item_ids == [b.item_id, a.item_id, c.item_id]
    assert a.parentItem() is None


def test_ungroup_peels_one_level(scene: SnapScene) -> None:
    a, b, c = _two_rects_on_layer(scene)
    manager = SelectionManager(scene)
    inner_cmd = GroupItemsCommand(scene, [a, c], manager)
    scene.command_stack.push(inner_cmd)
    inner = inner_cmd.group
    assert inner is not None
    outer_cmd = GroupItemsCommand(scene, [inner, b], manager)
    scene.command_stack.push(outer_cmd)
    outer = outer_cmd.group
    assert outer is not None
    assert outer.members == [b, inner]
    scene.command_stack.push(UngroupItemsCommand(scene, [outer], manager))
    assert inner.parentItem() is None and inner.scene() is scene
    assert a.parentItem() is inner
    assert set(manager.items) == {b, inner}
    assert set(scene.annotation_items()) == {b, inner}


def test_group_row_checks_its_requirements(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    a, b = _rect(0, 0), _rect(100, 100)
    _add(scene, a)
    _add(scene, b)
    main_window.selection_manager.select_items([a])
    main_window._arrange_group()  # noqa: SLF001
    assert unmet_messages == [("Group", "Group needs at least two items selected.")]
    unmet_messages.clear()
    other = scene.layer_manager.add_layer("Layer 2")
    scene.command_stack.push(MoveItemToLayerCommand(scene, [b], other.layer_id))
    main_window.selection_manager.select_items([a, b])
    main_window._arrange_group()  # noqa: SLF001
    assert unmet_messages == [("Group", "Group needs the selected items on one layer.")]
    assert all(i.parentItem() is None for i in (a, b))
    unmet_messages.clear()
    main_window._arrange_ungroup()  # noqa: SLF001
    assert unmet_messages == [("Ungroup", "Ungroup needs a group selected.")]


def test_group_and_ungroup_rows_act_through_the_window(main_window: MainWindow) -> None:
    scene = main_window.scene
    a, b = _rect(0, 0), _rect(100, 100)
    _add(scene, a)
    _add(scene, b)
    main_window.selection_manager.select_items([a, b])
    main_window._arrange_group()  # noqa: SLF001
    selected = main_window.selection_manager.items
    assert len(selected) == 1 and isinstance(selected[0], GroupItem)
    assert scene.command_stack.undo_text.endswith("Group 2 items")
    main_window._arrange_ungroup()  # noqa: SLF001
    assert main_window.selection_manager.items == [a, b]
    assert scene.command_stack.undo_text.endswith("Ungroup")


# --- every other walk (step 5) ---


def _window_group(main_window: MainWindow) -> tuple[GroupItem, RectangleItem, RectangleItem]:
    scene = main_window.scene
    a, b = _rect(10, 10), _rect(200, 10)
    for item in (a, b):
        item.fill_color = item.stroke_color
        _add(scene, item)
    command = GroupItemsCommand(scene, [a, b], main_window.selection_manager)
    scene.command_stack.push(command)
    group = command.group
    assert group is not None
    return group, a, b


def test_layer_region_render_draws_a_group_on_its_layer_only(scene: SnapScene) -> None:
    from snapmock.core.render_engine import RenderEngine

    manager = scene.layer_manager
    first = manager.active_layer
    assert first is not None
    second = manager.add_layer("Layer 2")
    a = _rect(10, 10)
    a.fill_color = a.stroke_color
    group = _group_of(a)
    _add(scene, group)
    scene.command_stack.push(MoveItemToLayerCommand(scene, [group], second.layer_id))
    engine = RenderEngine(scene)
    canvas = scene.canvas_rect
    assert engine.render_layer_region(second.layer_id, canvas).pixelColor(50, 30) == a.stroke_color
    assert engine.render_layer_region(first.layer_id, canvas).pixelColor(50, 30).alpha() == 0
    # A hidden layer's group still renders in its thumbnail, and its members' own
    # visibility flags are untouched afterwards
    manager.set_visibility(second.layer_id, False)
    assert engine.render_layer_region(second.layer_id, canvas).pixelColor(50, 30) == a.stroke_color
    manager.set_visibility(second.layer_id, True)
    assert a.isVisible()


def test_select_all_and_select_all_layers_pick_the_group_not_its_members(
    main_window: MainWindow,
) -> None:
    group, a, b = _window_group(main_window)
    loose = _rect(400, 400)
    _add(main_window.scene, loose)
    main_window.selection_manager.deselect_all()
    main_window._edit_select_all_on_layer()  # noqa: SLF001
    assert set(main_window.selection_manager.items) == {group, loose}
    main_window.selection_manager.deselect_all()
    main_window._edit_select_all_layers()  # noqa: SLF001
    assert set(main_window.selection_manager.items) == {group, loose}


def test_select_all_text_reaches_text_inside_a_group(main_window: MainWindow) -> None:
    from snapmock.items.text_item import TextItem

    scene = main_window.scene
    text = TextItem()
    text.text = "inside"
    text.setPos(0, 0)
    other = _rect(200, 0)
    for item in (text, other):
        _add(scene, item)
    scene.command_stack.push(GroupItemsCommand(scene, [text, other]))
    main_window._edit_select_all_text()  # noqa: SLF001
    assert main_window.selection_manager.items == [text]


def test_find_replace_color_reaches_a_member(scene: SnapScene) -> None:
    from PyQt6.QtGui import QColor

    from snapmock.ui.find_replace_color_dialog import color_matches, replace_color_command

    a = _rect(0, 0)
    a.stroke_color = QColor("#ff112233")
    group = _group_of(a)
    _add(scene, group)
    matches = color_matches(scene, QColor("#ff112233"))
    assert matches == [(a, "stroke_color")]
    scene.command_stack.push(replace_color_command(matches, QColor("#ff112233"), QColor("blue")))
    assert a.stroke_color == QColor("blue")


def test_duplicate_deep_clones_a_group(main_window: MainWindow) -> None:
    group, a, b = _window_group(main_window)
    layer = main_window.scene.layer_manager.active_layer
    assert layer is not None
    main_window.selection_manager.select_items([group])
    main_window._edit_duplicate()  # noqa: SLF001
    selected = main_window.selection_manager.items
    assert len(selected) == 1
    copy = selected[0]
    assert isinstance(copy, GroupItem) and copy is not group
    assert copy.member_count == 2
    assert copy.pos() == group.pos() + QPointF(10, 10)
    assert {m.item_id for m in copy.members}.isdisjoint({a.item_id, b.item_id})
    assert layer.item_ids == [group.item_id, copy.item_id]
    assert len(main_window.scene.all_annotation_items()) == 6


def test_move_to_layer_and_lock_item_take_the_group_and_its_members(
    main_window: MainWindow,
) -> None:
    group, a, b = _window_group(main_window)
    scene = main_window.scene
    first = scene.layer_manager.active_layer
    assert first is not None
    second = scene.layer_manager.add_layer("Layer 2")
    main_window.selection_manager.select_items([group])
    main_window._move_items_to_layer(second.layer_id)  # noqa: SLF001
    assert group.layer_id == second.layer_id
    assert a.layer_id == second.layer_id and b.layer_id == second.layer_id
    assert first.item_ids == [] and second.item_ids == [group.item_id]
    main_window._toggle_item_lock()  # noqa: SLF001
    assert group.locked and a.locked and b.locked
    scene.command_stack.undo()
    assert group.layer_id == first.layer_id and a.layer_id == first.layer_id


def test_align_distribute_and_z_order_treat_a_group_as_one_box(main_window: MainWindow) -> None:
    group, a, b = _window_group(main_window)
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    loose = _rect(400, 400)
    _add(scene, loose)
    main_window.selection_manager.select_items([group, loose])
    main_window._arrange_align("left")  # noqa: SLF001
    assert loose.sceneBoundingRect().left() == group.sceneBoundingRect().left()
    assert a.sceneBoundingRect().left() == group.sceneBoundingRect().left()
    assert scene.command_stack.undo_text.endswith("Align Left")
    main_window._arrange_align_canvas_center()  # noqa: SLF001
    union = group.sceneBoundingRect().united(loose.sceneBoundingRect())
    assert union.center().x() == pytest.approx(scene.canvas_rect.center().x())
    main_window.selection_manager.select_items([group])
    main_window._arrange_bring_to_front()  # noqa: SLF001
    assert layer.item_ids == [loose.item_id, group.item_id]
    assert group.zValue() == layer.z_base + 1
    assert a.zValue() < b.zValue()  # the members keep their order inside the group


def test_property_panel_shows_a_group_and_edits_its_vector_members(qtbot: QtBot) -> None:
    from snapmock.core.selection_manager import SelectionManager
    from snapmock.ui.property_panel import PropertyPanel

    scene = SnapScene()
    manager = SelectionManager(scene)
    panel = PropertyPanel(manager, scene)
    qtbot.addWidget(panel)
    panel.show()
    a, b = _rect(0, 0), _rect(200, 0)
    for item in (a, b):
        _add(scene, item)
    command = GroupItemsCommand(scene, [a, b], manager)
    scene.command_stack.push(command)
    group = command.group
    assert group is not None
    assert panel._transform_section.isVisible()  # noqa: SLF001
    assert panel._appearance_section.isVisible()  # noqa: SLF001
    assert panel._info_section.isVisible()  # noqa: SLF001
    assert panel._type_label.text() == "Group (2 items)"  # noqa: SLF001
    assert panel._x_spin.value() == pytest.approx(group.pos_x)  # noqa: SLF001
    assert panel._w_spin.value() == pytest.approx(group.boundingRect().width())  # noqa: SLF001
    assert panel._stroke_w_spin.value() == a.stroke_width  # noqa: SLF001
    panel._stroke_w_spin.setValue(7.0)  # noqa: SLF001
    assert a.stroke_width == 7.0 and b.stroke_width == 7.0
    assert scene.command_stack.undo_text.endswith("Change stroke_width on 2 items")
    scene.command_stack.undo()
    assert a.stroke_width != 7.0
    # A group with no vector member has no Appearance section
    from PyQt6.QtGui import QPixmap

    from snapmock.items.raster_region_item import RasterRegionItem

    raster = RasterRegionItem(pixmap=QPixmap(20, 20))
    raster.setPos(400, 400)
    _add(scene, raster)
    manager.select_items([_group_of(raster)])
    assert not panel._appearance_section.isVisible()  # noqa: SLF001


def test_svg_export_carries_the_group_transform_into_each_member(
    scene: SnapScene, tmp_path: Path
) -> None:
    from snapmock.io.exporter import export_svg

    a = _rect(10, 10, 50, 40)
    group = _group_of(a)
    _add(scene, group)
    group.setTransform(QTransform().scale(2, 1))
    path = tmp_path / "group.svg"
    export_svg(scene, path)
    text = path.read_text()
    assert '<rect x="0" y="0" width="50" height="40"/>' in text
    # The canvas colour's own rect comes first since the follow-up (exporter 3.9 row)
    start = text.index('<rect x="0" y="0" width="50" height="40"/>')
    element = text[text.rfind("<g ", 0, start) : start]
    assert 'transform="matrix(2,0,0,1,11,10)"' in element


def test_raster_export_and_thumbnail_paint_the_group_where_it_moved(scene: SnapScene) -> None:
    from snapmock.io.project_serializer import render_thumbnail

    a = _rect(10, 10)
    a.fill_color = a.stroke_color
    group = _group_of(a)
    _add(scene, group)
    group.setPos(group.pos() + QPointF(300, 0))
    thumb = render_thumbnail(scene, max_size=800)
    assert thumb.pixelColor(350, 30) == a.stroke_color
    assert thumb.pixelColor(50, 30).name() == "#ffffff"


def test_snagit_writer_writes_members_individually_at_their_scene_position(
    scene: SnapScene, tmp_path: Path
) -> None:
    import json
    import zipfile

    from snapmock.io.snagit_writer import save_snagx

    a = _rect(10, 10)
    b = _rect(200, 10)
    group = _group_of(a, b)
    _add(scene, group)
    group.setPos(group.pos() + QPointF(100, 50))
    path = tmp_path / "group.snagx"
    warnings = save_snagx(scene, path)
    assert warnings == []
    with zipfile.ZipFile(path) as archive:
        page_name = json.loads(archive.read("index.json"))["Pages"][0]
        objects = json.loads(archive.read(page_name))["CaptureObjects"]
    assert len(objects) == 2
    # The group moved by (100, 50): a's top-left 10,10 is written at 110,60 and b's at 300,60
    firsts = sorted(obj["PointsArray"][0] for obj in objects)
    assert firsts == ["110,60", "300,60"]


def test_canvas_rotate_flip_crop_and_resize_move_a_group_once(scene: SnapScene) -> None:
    from PyQt6.QtCore import QSizeF

    from snapmock.commands.canvas_transform_commands import FlipCanvasCommand, RotateCanvasCommand
    from snapmock.commands.raster_commands import (
        CropCanvasCommand,
        ResizeCanvasCommand,
        ResizeImageCommand,
    )

    a = _rect(10, 10, 50, 40)
    b = _rect(200, 10, 50, 40)
    group = _group_of(a, b)
    _add(scene, group)

    def offsets() -> tuple[QPointF, QPointF]:
        return QPointF(a.pos()), QPointF(b.pos())

    inside = offsets()
    for command in (
        RotateCanvasCommand(scene, clockwise=True),
        FlipCanvasCommand(scene, horizontal=True),
        CropCanvasCommand(scene, QRectF(5, 5, 700, 500)),
        ResizeCanvasCommand(scene, QSizeF(900, 700), 4, None),
    ):
        scene.command_stack.push(command)
        assert offsets() == inside, type(command).__name__
        assert a.sceneBoundingRect().width() == pytest.approx(52)
        scene.command_stack.undo()
        assert offsets() == inside
    scene.command_stack.push(ResizeImageCommand(scene, QSizeF(1600, 600)))
    assert a.rect.width() == 100 and b.rect.width() == 100
    assert b.pos().x() == pytest.approx(inside[1].x() * 2)
    assert a.sceneBoundingRect().left() == pytest.approx(9 * 2, abs=1)
    scene.command_stack.undo()
    assert a.rect.width() == 50 and b.rect.width() == 50
    assert offsets() == inside


def test_duplicate_layer_clones_a_group_once(scene: SnapScene) -> None:
    from snapmock.commands.layer_commands import DuplicateLayerCommand

    a = _rect(10, 10)
    group = _group_of(a)
    _add(scene, group)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    scene.command_stack.push(DuplicateLayerCommand(scene, layer.layer_id))
    copy = scene.layer_manager.active_layer
    assert copy is not None and copy is not layer
    assert len(copy.item_ids) == 1
    clones = [i for i in scene.annotation_items() if i.layer_id == copy.layer_id]
    assert len(clones) == 1 and isinstance(clones[0], GroupItem)
    assert len(scene.all_annotation_items()) == 4


def test_delete_layer_counts_a_group_once_and_auto_trim_uses_its_box(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PyQt6.QtWidgets import QMessageBox

    group, a, b = _window_group(main_window)
    scene = main_window.scene
    assert main_window._visible_content_bounds() == group.sceneBoundingRect()  # noqa: SLF001
    layer = scene.layer_manager.active_layer
    assert layer is not None
    scene.layer_manager.add_layer("Layer 2")
    scene.layer_manager.set_active(layer.layer_id)
    asked: list[str] = []

    def _question(_parent: object, _title: str, text: str, *_a: object, **_k: object) -> object:
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_question))
    main_window._layer_delete()  # noqa: SLF001
    assert asked and "the 1 item on it" in asked[0]
    assert scene.all_annotation_items() == []
