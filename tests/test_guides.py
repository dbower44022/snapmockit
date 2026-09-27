"""Guides of General UI PRD 6.5: model, commands, rendering, ruler creation, move, delete,
snapping, locking, the View rows, and persistence in the project file (kickoff decision 3)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PyQt6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.commands.guide_commands import (
    AddGuideCommand,
    ClearGuidesCommand,
    MoveGuideCommand,
    RemoveGuideCommand,
)
from snapmock.config.settings import AppSettings
from snapmock.config.shortcuts import SHORTCUTS
from snapmock.core.document import Document
from snapmock.core.guides import Guide, GuideOrientation, snap_rect_delta, snap_value
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import GUIDE_HIT_TOLERANCE, SnapView
from snapmock.io.project_serializer import load_project, save_project
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.tools.rectangle_tool import RectangleTool
from snapmock.tools.select_tool import SelectTool
from snapmock.tools.tool_manager import ToolManager
from snapmock.ui.ruler_widget import RulerWidget

H = GuideOrientation.HORIZONTAL
V = GuideOrientation.VERTICAL


# --- model and arithmetic ---


def test_guide_round_trips_through_a_manifest_entry_and_rejects_bad_ones() -> None:
    guide = Guide(H, 120.5)
    assert Guide.from_dict(guide.to_dict()) == guide
    assert Guide.from_dict({"orientation": "vertical", "position": 3}) == Guide(V, 3.0)
    assert Guide.from_dict({"orientation": "diagonal", "position": 3}) is None
    assert Guide.from_dict({"orientation": "vertical"}) is None
    assert Guide.from_dict("nonsense") is None


def test_snap_value_picks_the_nearest_target_within_tolerance() -> None:
    assert snap_value(103, [50, 100, 200], 5) == 100
    assert snap_value(97, [50, 100, 200], 5) == 100
    assert snap_value(110, [50, 100, 200], 5) is None
    assert snap_value(100, [], 5) is None


def test_snap_rect_delta_moves_an_edge_or_the_centre_onto_a_guide() -> None:
    guides = [Guide(V, 100.0), Guide(H, 300.0)]
    # left edge 97 -> 100; bottom edge 303 -> 300
    delta = snap_rect_delta(QRectF(97, 253, 50, 50), guides, 5)
    assert (delta.x(), delta.y()) == (3.0, -3.0)
    # centre x 101 -> 100 wins over the farther edges
    delta = snap_rect_delta(QRectF(76, 0, 50, 50), guides, 5)
    assert delta.x() == -1.0 and delta.y() == 0.0
    assert snap_rect_delta(QRectF(500, 500, 10, 10), guides, 5).isNull()


# --- scene and commands ---


def test_scene_guides_change_through_commands_with_undo(scene: SnapScene, qtbot: QtBot) -> None:
    stack = scene.command_stack
    with qtbot.waitSignal(scene.guides_changed):
        stack.push(AddGuideCommand(scene, Guide(H, 40.0)))
    stack.push(AddGuideCommand(scene, Guide(V, 80.0)))
    assert scene.guides == [Guide(H, 40.0), Guide(V, 80.0)]
    assert stack.is_dirty
    stack.push(MoveGuideCommand(scene, Guide(H, 40.0), 45.0))
    stack.push(MoveGuideCommand(scene, Guide(H, 45.0), 50.0))  # merges with the previous move
    assert scene.guides == [Guide(H, 50.0), Guide(V, 80.0)]
    stack.undo()
    assert scene.guides == [Guide(H, 40.0), Guide(V, 80.0)]
    stack.redo()
    stack.push(RemoveGuideCommand(scene, Guide(V, 80.0)))
    assert scene.guides == [Guide(H, 50.0)]
    stack.undo()
    stack.push(ClearGuidesCommand(scene))
    assert scene.guides == []
    stack.undo()
    assert scene.guides == [Guide(H, 50.0), Guide(V, 80.0)]
    assert ClearGuidesCommand(scene).description == "Clear All Guides"
    assert AddGuideCommand(scene, Guide(H, 1.0)).description == "Add Guide"


def test_duplicate_guides_are_not_added_twice(scene: SnapScene) -> None:
    scene.add_guide(Guide(H, 10.0))
    scene.add_guide(Guide(H, 10.0))
    assert len(scene.guides) == 1


# --- persistence (decision 3: an optional "guides" key in manifest.json) ---


def test_guides_are_saved_in_the_manifest_and_restored(qapp: QApplication, tmp_path: Path) -> None:
    scene = SnapScene(width=400, height=300)
    scene.set_guides([Guide(H, 25.0), Guide(V, 130.5)])
    path = tmp_path / "guides.smk"
    save_project(scene, path, write_thumbnail=False)
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["format_version"] == 1
    assert manifest["guides"] == [
        {"orientation": "horizontal", "position": 25.0},
        {"orientation": "vertical", "position": 130.5},
    ]
    loaded = load_project(path)
    assert loaded.guides == [Guide(H, 25.0), Guide(V, 130.5)]
    assert not loaded.command_stack.is_dirty


def test_a_project_without_guides_has_no_key_and_loads_empty(
    qapp: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "plain.smk"
    save_project(SnapScene(width=100, height=100), path, write_thumbnail=False)
    with zipfile.ZipFile(path) as zf:
        assert "guides" not in json.loads(zf.read("manifest.json"))
    assert load_project(path).guides == []


def test_malformed_guide_entries_are_skipped_on_load(qapp: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "odd.smk"
    save_project(SnapScene(width=100, height=100), path, write_thumbnail=False)
    with zipfile.ZipFile(path) as src:
        entries = {name: src.read(name) for name in src.namelist()}
    manifest = json.loads(entries["manifest.json"])
    manifest["guides"] = [{"orientation": "vertical", "position": 7}, {"bogus": 1}, "x"]
    entries["manifest.json"] = json.dumps(manifest).encode()
    with zipfile.ZipFile(path, "w") as dst:
        for name, data in entries.items():
            dst.writestr(name, data)
    assert load_project(path).guides == [Guide(V, 7.0)]


# --- view: rendering, hit test, drag, delete, lock, ruler creation ---


def _view(qtbot: QtBot) -> tuple[SnapScene, SnapView, ToolManager]:
    scene = SnapScene(width=800, height=600)
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    sm = SelectionManager(scene)
    tm = ToolManager(scene, sm)
    tm.register(SelectTool())
    tm.register(RectangleTool())
    view.set_tool_manager(tm)
    tm.activate("select")
    view.centerOn(400, 300)
    return scene, view, tm


def _mouse(
    kind: QEvent.Type,
    vp_pos: QPointF,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    buttons: Qt.MouseButton = Qt.MouseButton.NoButton,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> QMouseEvent:
    return QMouseEvent(kind, vp_pos, vp_pos, button, buttons, modifiers)


def _press(view: SnapView, scene_pos: QPointF) -> None:
    vp = QPointF(view.mapFromScene(scene_pos))
    view.mousePressEvent(
        _mouse(QEvent.Type.MouseButtonPress, vp, buttons=Qt.MouseButton.LeftButton)
    )


def _drag(view: SnapView, scene_pos: QPointF, shift: bool = False) -> None:
    vp = QPointF(view.mapFromScene(scene_pos))
    mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    view.mouseMoveEvent(
        _mouse(QEvent.Type.MouseMove, vp, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, mods)
    )


def _release(view: SnapView, scene_pos: QPointF) -> None:
    vp = QPointF(view.mapFromScene(scene_pos))
    view.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, vp))


def _hover(view: SnapView, scene_pos: QPointF) -> None:
    vp = QPointF(view.mapFromScene(scene_pos))
    view.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, vp, Qt.MouseButton.NoButton))


def test_guides_draw_in_the_foreground_and_hit_within_tolerance(qtbot: QtBot) -> None:
    scene, view, _tm = _view(qtbot)
    scene.set_guides([Guide(H, 200.0), Guide(V, 300.0)])
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    view.drawForeground(painter, QRectF(0, 0, 800, 600))
    painter.end()
    on_h = view.mapFromScene(QPointF(50, 200))
    assert view.guide_at(on_h) == Guide(H, 200.0)
    assert view.guide_at(on_h + QPoint(0, GUIDE_HIT_TOLERANCE)) == Guide(H, 200.0)
    assert view.guide_at(on_h + QPoint(0, GUIDE_HIT_TOLERANCE + 2)) is None
    assert view.guide_at(view.mapFromScene(QPointF(300, 50))) == Guide(V, 300.0)
    assert view.guide_pen.color().alpha() == round(70 * 2.55)
    view.set_guides_visible(False)
    assert not view.guides_visible


def test_dragging_a_guide_moves_it_undoably_and_shift_rounds(qtbot: QtBot) -> None:
    scene, view, _tm = _view(qtbot)
    scene.set_guides([Guide(H, 200.0)])
    _hover(view, QPointF(100, 200))
    vp = view.viewport()
    assert vp is not None
    assert vp.cursor().shape() == Qt.CursorShape.SizeVerCursor
    _press(view, QPointF(100, 200))
    assert view.dragging_guide == Guide(H, 200.0)
    _drag(view, QPointF(100, 250.4), shift=True)
    _release(view, QPointF(100, 250.4))
    assert scene.guides == [Guide(H, 250.0)]
    assert scene.command_stack.is_dirty
    scene.command_stack.undo()
    assert scene.guides == [Guide(H, 200.0)]
    _hover(view, QPointF(100, 400))
    assert vp.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_dropping_a_guide_on_its_ruler_removes_it(qtbot: QtBot) -> None:
    scene, view, _tm = _view(qtbot)
    view.set_rulers_visible(True)
    scene.set_guides([Guide(V, 300.0)])
    _press(view, QPointF(300, 100))
    view.mouseMoveEvent(
        _mouse(
            QEvent.Type.MouseMove,
            QPointF(-10, 100),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
        )
    )
    view.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, QPointF(-10, 100)))
    assert scene.guides == []
    scene.command_stack.undo()
    assert scene.guides == [Guide(V, 300.0)]


def test_locked_or_hidden_guides_are_not_dragged(qtbot: QtBot) -> None:
    scene, view, _tm = _view(qtbot)
    scene.set_guides([Guide(H, 200.0)])
    view.set_guides_locked(True)
    _press(view, QPointF(100, 200))
    assert view.dragging_guide is None
    _release(view, QPointF(100, 200))
    view.set_guides_locked(False)
    view.set_guides_visible(False)
    _press(view, QPointF(100, 200))
    assert view.dragging_guide is None
    _release(view, QPointF(100, 200))
    assert scene.guides == [Guide(H, 200.0)]


def test_dragging_out_of_a_ruler_creates_a_guide(qtbot: QtBot) -> None:
    scene, view, _tm = _view(qtbot)
    view.set_rulers_visible(True)
    ruler = view._h_ruler  # noqa: SLF001
    assert isinstance(ruler, RulerWidget)
    assert ruler.guide_orientation is H
    vp = view.viewport()
    assert vp is not None
    view.begin_guide_preview(H)
    inside = vp.mapToGlobal(view.mapFromScene(QPointF(100, 150.3)))
    view.update_guide_preview(inside, whole=True)
    assert view.guide_preview == Guide(H, 150.0)
    outside = vp.mapToGlobal(QPoint(-50, -50))
    view.update_guide_preview(outside)
    assert view.guide_preview is None
    view.finish_guide_preview()
    assert scene.guides == []  # released off the canvas: nothing placed
    view.begin_guide_preview(V)
    view.update_guide_preview(vp.mapToGlobal(view.mapFromScene(QPointF(320, 100))))
    view.finish_guide_preview()
    assert len(scene.guides) == 1 and scene.guides[0].orientation is V
    assert abs(scene.guides[0].position - 320) < 1
    assert scene.command_stack.can_undo
    # The ruler widget itself starts the preview on a left press and ignores it when locked
    view.set_guides_locked(True)
    ruler.mousePressEvent(
        _mouse(QEvent.Type.MouseButtonPress, QPointF(5, 5), buttons=Qt.MouseButton.LeftButton)
    )
    assert ruler._dragging_guide is False  # noqa: SLF001


# --- snapping ---


def test_snap_point_follows_the_grid_and_guide_toggles(qtbot: QtBot) -> None:
    scene, view, _tm = _view(qtbot)
    scene.set_guides([Guide(V, 100.0), Guide(H, 200.0)])
    view.set_grid_size(10)
    assert view.snap_point(QPointF(103, 197)) == QPointF(103, 197)
    view.set_snap_to_guides(True)
    view.set_snap_tolerance(5)
    assert view.snap_point(QPointF(103, 197)) == QPointF(100, 200)
    assert view.snap_point(QPointF(150, 150)) == QPointF(150, 150)
    view.set_snap_to_guides(False)
    view.set_snap_to_grid(True)
    assert view.snap_point(QPointF(103, 197)) == QPointF(100, 200)
    assert view.snap_point(QPointF(126, 174)) == QPointF(130, 170)
    view.set_zoom(200)  # tolerance is in screen pixels: 5 px is 2.5 scene units
    view.set_snap_to_grid(False)
    view.set_snap_to_guides(True)
    assert view.snap_point(QPointF(103, 150)) == QPointF(103, 150)
    assert view.snap_point(QPointF(102, 150)) == QPointF(100, 150)


def test_select_drag_snaps_to_guides_and_grid_only_when_the_toggles_say(qtbot: QtBot) -> None:
    scene, view, tm = _view(qtbot)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(rect=QRectF(0, 0, 50, 50))
    item.setPos(200, 200)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    scene.set_guides([Guide(V, 300.0)])
    view.set_grid_visible(True)  # a visible grid alone must not snap (View > Snap to Grid is off)
    view.set_grid_size(10)
    tm.activate("select")
    # Drag the top-left corner by (+7, +3): no snapping
    _press(view, QPointF(200, 200))
    _drag(view, QPointF(207, 203))
    _release(view, QPointF(207, 203))
    assert (item.pos().x(), item.pos().y()) == (207.0, 203.0)
    # Snap to Guides: the right edge (257 + 41 = 298) lands on the vertical guide at 300
    view.set_snap_to_guides(True)
    view.set_snap_tolerance(5)
    grip = QPointF(218, 203)  # on the top stroke, clear of the transform handles
    _press(view, grip)
    _drag(view, grip + QPointF(41, 0))
    _release(view, grip + QPointF(41, 0))
    assert item.sceneBoundingRect().right() == pytest.approx(300.0, abs=1.5)
    # Snap to Grid lands the selection frame's corner on the grid (end-to-end pass decision 5)
    view.set_snap_to_guides(False)
    view.set_snap_to_grid(True)
    edges = item.scene_geometry_rect()  # the rectangle's own line, not the handles' frame
    grip = QPointF(item.pos().x() + 11, item.pos().y())
    _press(view, grip)
    _drag(view, grip + QPointF(13, 0))
    _release(view, grip + QPointF(13, 0))
    moved = item.scene_geometry_rect()
    assert moved.left() == pytest.approx(round((edges.left() + 13) / 10) * 10)
    assert moved.top() == pytest.approx(round(edges.top() / 10) * 10)


def test_rectangle_creation_snaps_to_guides(qtbot: QtBot) -> None:
    scene, view, tm = _view(qtbot)
    scene.set_guides([Guide(V, 100.0), Guide(H, 100.0)])
    view.set_snap_to_guides(True)
    view.set_snap_tolerance(5)
    tm.activate("rectangle")
    _press(view, QPointF(97, 103))
    _drag(view, QPointF(200, 200))
    _release(view, QPointF(200, 200))
    items = [i for i in scene.items() if isinstance(i, RectangleItem)]
    assert len(items) == 1
    assert (items[0].pos().x(), items[0].pos().y()) == (100.0, 100.0)


# --- the View menu rows and their persistence ---


def test_view_rows_toggle_every_document_and_persist(main_window: MainWindow) -> None:
    assert SHORTCUTS["view.toggle_guides"] == "Ctrl+;"
    assert main_window._guides_action.shortcut().toString() == "Ctrl+;"  # noqa: SLF001
    second = Document(SnapScene())
    main_window._add_document(second, activate=False)  # noqa: SLF001
    docs = main_window.documents.documents
    assert all(d.view.guides_visible for d in docs)
    main_window._guides_action.setChecked(False)  # noqa: SLF001
    assert not any(d.view.guides_visible for d in docs)
    assert not AppSettings().guides_visible()
    main_window._snap_guides_action.setChecked(True)  # noqa: SLF001
    assert all(d.view.snap_to_guides for d in docs)
    assert AppSettings().snap_to_guides()
    main_window._lock_guides_action.setChecked(True)  # noqa: SLF001
    assert all(d.view.guides_locked for d in docs)
    assert AppSettings().guides_locked()
    main_window._snap_grid_action.setChecked(True)  # noqa: SLF001
    assert all(d.view.snap_to_grid for d in docs)
    third = Document(SnapScene())
    main_window._add_document(third, activate=False)  # noqa: SLF001
    assert not third.view.guides_visible
    assert third.view.snap_to_guides and third.view.guides_locked and third.view.snap_to_grid


def test_clear_all_guides_explains_confirms_and_is_undoable(
    main_window: MainWindow,
    unmet_messages: list[tuple[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_window._view_clear_guides()  # noqa: SLF001
    assert unmet_messages and "at least one guide" in unmet_messages[-1][1]
    scene = main_window.scene
    scene.command_stack.push(AddGuideCommand(scene, Guide(H, 10.0)))
    scene.command_stack.push(AddGuideCommand(scene, Guide(V, 20.0)))
    asked: list[str] = []

    def _no(_parent: object, _title: str, text: str, *_a: object, **_k: object) -> object:
        asked.append(text)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_no))
    main_window._view_clear_guides()  # noqa: SLF001
    assert asked == ["Remove all 2 guides from the canvas?"]
    assert len(scene.guides) == 2

    def _yes(*_a: object, **_k: object) -> object:
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_yes))
    main_window._view_clear_guides()  # noqa: SLF001
    assert scene.guides == []
    scene.command_stack.undo()
    assert len(scene.guides) == 2
    scene.command_stack.mark_clean()


def test_preferences_guide_colour_and_tolerance_reach_the_view(main_window: MainWindow) -> None:
    from PyQt6.QtGui import QColor

    changes: dict[str, tuple[object, object]] = {
        "guide_color": (None, QColor("#FF00FF")),
        "guide_opacity": (None, 40),
        "snap_tolerance": (None, 9),
    }
    main_window._apply_appearance_preference_changes(changes)  # noqa: SLF001
    view = main_window.view
    assert view.guide_pen.color().name().upper() == "#FF00FF"
    assert view.guide_pen.color().alpha() == round(40 * 2.55)
    assert view._snap_tolerance == 9  # noqa: SLF001


# --- the selected guide (General UI PRD 2.64, 09-26-26): click, colour, nudge, delete ---


def _key(view: SnapView, key: Qt.Key, shift: bool = False) -> None:
    from PyQt6.QtGui import QKeyEvent

    mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods))


def test_a_click_selects_a_guide_and_paints_it_in_the_selection_colour(qtbot: QtBot) -> None:
    """Since 2.67 the selection colour is a halo behind the line, not the line itself."""
    from snapmock.core.theme_manager import current_theme

    scene, view, tm = _view(qtbot)
    scene.set_guides([Guide(H, 200.0), Guide(V, 300.0)])
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(rect=QRectF(0, 0, 100, 60))
    item.setPos(500, 400)
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    tm.selection_manager.select(item)
    assert view.selected_guide is None
    _press(view, QPointF(100, 200))
    _release(view, QPointF(100, 200))
    assert view.selected_guide == Guide(H, 200.0)
    assert tm.selection_manager.items == []  # a guide and the items are never both selected
    image = QImage(400, 400, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    view.drawForeground(painter, QRectF(0, 0, 800, 600))
    painter.end()
    # The selection is a halo in the selection colour beside the line; the other guide
    # has none
    white = QColor(Qt.GlobalColor.white).rgb()
    beside = image.pixelColor(50, 202)
    assert beside.rgb() != white
    assert beside.blue() > beside.red()  # tinted by the theme's blue selection colour
    assert image.pixelColor(302, 50).rgb() == white
    assert current_theme().selection_handle.alpha() == 255
    # A click on empty canvas lets the guide go; a click on an item does too
    _press(view, QPointF(400, 100))
    _release(view, QPointF(400, 100))
    assert view.selected_guide is None
    _press(view, QPointF(100, 200))
    _release(view, QPointF(100, 200))
    tm.selection_manager.select(item)
    assert view.selected_guide is None


def test_arrow_keys_nudge_a_selected_guide_by_the_standard_rules(qtbot: QtBot) -> None:
    scene, view, _tm = _view(qtbot)
    scene.set_guides([Guide(H, 200.0), Guide(V, 300.0)])
    view.select_guide(Guide(H, 200.0))
    _key(view, Qt.Key.Key_Down)
    assert scene.guides[0] == Guide(H, 201.0)
    assert view.selected_guide == Guide(H, 201.0)  # the selection follows the move
    _key(view, Qt.Key.Key_Up)
    _key(view, Qt.Key.Key_Up)
    assert scene.guides[0] == Guide(H, 199.0)
    _key(view, Qt.Key.Key_Down, shift=True)  # to the next grid line: one pixel
    assert scene.guides[0] == Guide(H, 200.0)
    _key(view, Qt.Key.Key_Down, shift=True)  # on a line: a whole step
    assert scene.guides[0] == Guide(H, 210.0)
    _key(view, Qt.Key.Key_Left)  # the wrong axis: consumed, nothing moves
    _key(view, Qt.Key.Key_Right, shift=True)
    assert scene.guides == [Guide(H, 210.0), Guide(V, 300.0)]
    assert scene.command_stack.is_dirty
    scene.command_stack.undo()  # consecutive moves of one guide are one undo step
    assert scene.guides[0] == Guide(H, 200.0)
    assert view.selected_guide == Guide(H, 200.0)
    view.select_guide(Guide(V, 300.0))
    _key(view, Qt.Key.Key_Right)
    _key(view, Qt.Key.Key_Up)
    assert scene.guides[1] == Guide(V, 301.0)


def test_delete_removes_a_selected_guide_and_lock_hide_and_clear_let_it_go(
    qtbot: QtBot,
) -> None:
    scene, view, _tm = _view(qtbot)
    scene.set_guides([Guide(H, 200.0), Guide(V, 300.0)])
    view.select_guide(Guide(H, 200.0))
    _key(view, Qt.Key.Key_Delete)
    assert scene.guides == [Guide(V, 300.0)]
    assert view.selected_guide is None
    scene.command_stack.undo()
    assert scene.guides == [Guide(V, 300.0), Guide(H, 200.0)]
    view.select_guide(Guide(V, 300.0))
    view.set_guides_locked(True)
    assert view.selected_guide is None
    _press(view, QPointF(300, 100))
    _release(view, QPointF(300, 100))
    assert view.selected_guide is None  # a locked guide cannot be selected
    view.set_guides_locked(False)
    view.select_guide(Guide(V, 300.0))
    view.set_guides_visible(False)
    assert view.selected_guide is None
    view.set_guides_visible(True)
    view.select_guide(Guide(V, 300.0))
    scene.command_stack.push(ClearGuidesCommand(scene))
    assert view.selected_guide is None


def test_escape_lets_a_selected_guide_go_without_a_message(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    scene = main_window.scene
    view = main_window._view  # noqa: SLF001
    scene.set_guides([Guide(H, 200.0)])
    main_window.tool_manager.activate("select")
    view.select_guide(Guide(H, 200.0))
    main_window._edit_deselect()  # noqa: SLF001
    assert view.selected_guide is None
    assert unmet_messages == []
    scene.command_stack.mark_clean()


def test_the_delete_key_and_the_arrows_reach_a_selected_guide_through_the_window(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    """Doug's display, 09-26-26: Delete did nothing on a selected guide, since the key is
    Edit > Delete's shortcut and the window takes it before the view's key handler."""
    from PyQt6.QtTest import QTest

    scene = main_window.scene
    view = main_window._view  # noqa: SLF001
    main_window.show()
    scene.set_guides([Guide(H, 200.0)])
    main_window.tool_manager.activate("select")
    view.setFocus()
    view.select_guide(Guide(H, 200.0))
    handle = main_window.windowHandle()
    assert handle is not None
    QTest.keyClick(handle, Qt.Key.Key_Down)
    assert scene.guides == [Guide(H, 201.0)]
    QTest.keyClick(handle, Qt.Key.Key_Delete)
    assert scene.guides == []
    assert view.selected_guide is None
    assert unmet_messages == []
    scene.command_stack.undo()
    assert scene.guides == [Guide(H, 201.0)]
    QTest.keyClick(handle, Qt.Key.Key_Delete)  # nothing selected: the usual message
    assert scene.guides == [Guide(H, 201.0)]
    assert unmet_messages == [("Delete", "Delete needs at least one item selected.")]
    scene.command_stack.mark_clean()


# --- a guide's own colour, line style, and lock (General UI PRD 2.66, decision A) ---


def test_a_guide_carries_colour_style_and_lock_through_the_manifest() -> None:
    from snapmock.core.guides import GuideStyle

    plain = Guide(H, 120.5)
    assert plain.to_dict() == {"orientation": "horizontal", "position": 120.5}  # as before
    dressed = Guide(V, 40.0, "#ffff0000", GuideStyle.DASHED, True)
    data = dressed.to_dict()
    assert data == {
        "orientation": "vertical",
        "position": 40.0,
        "color": "#ffff0000",
        "style": "dashed",
        "locked": True,
    }
    assert Guide.from_dict(data) == dressed
    assert Guide.from_dict({"orientation": "vertical", "position": 1, "style": "wavy"}) == Guide(
        V, 1.0
    )
    assert dressed.moved_to(50.0) == Guide(V, 50.0, "#ffff0000", GuideStyle.DASHED, True)
    assert dressed.with_changes(locked=False).locked is False
    assert GuideStyle.DOTTED.pen_style == Qt.PenStyle.DotLine


def test_a_guide_draws_in_its_own_colour_and_style_and_a_locked_one_refuses_the_mouse(
    qtbot: QtBot,
) -> None:
    from snapmock.commands.guide_commands import ChangeGuideCommand
    from snapmock.core.guides import GuideStyle

    scene, view, _tm = _view(qtbot)
    red = Guide(H, 200.0, "#ffff0000", GuideStyle.DASHED)
    scene.set_guides([red, Guide(V, 300.0)])
    assert view.guide_pen_for(red).color() == QColor("#ffff0000")
    assert view.guide_pen_for(red).style() == Qt.PenStyle.DashLine
    assert view.guide_pen_for(Guide(V, 300.0)).color() == view.guide_pen.color()
    assert view.guide_pen_for(Guide(V, 300.0)).style() == Qt.PenStyle.SolidLine
    # Locked: the click selects it, the cursor forbids the drag, the drag and the keys
    # and Delete do nothing, and the lock is undoable
    scene.command_stack.push(ChangeGuideCommand(scene, red, red.with_changes(locked=True), "Lock"))
    locked = scene.guides[0]
    assert locked.locked
    _hover(view, QPointF(100, 200))
    vp = view.viewport()
    assert vp is not None
    assert vp.cursor().shape() == Qt.CursorShape.ForbiddenCursor
    _press(view, QPointF(100, 200))
    assert view.selected_guide == locked
    assert view.dragging_guide is None
    _drag(view, QPointF(100, 250))
    _release(view, QPointF(100, 250))
    _key(view, Qt.Key.Key_Down)
    _key(view, Qt.Key.Key_Delete)
    assert scene.guides[0] == locked
    scene.command_stack.undo()
    assert not scene.guides[0].locked
    assert view.selected_guide == scene.guides[0]  # the selection follows the undo


def test_the_property_panel_shows_the_selected_guide_and_edits_it(
    main_window: MainWindow, qtbot: QtBot, unmet_messages: list[tuple[str, str]]
) -> None:
    from snapmock.core.guides import GuideStyle

    scene = main_window.scene
    view = main_window._view  # noqa: SLF001
    panel = main_window._property_panel  # noqa: SLF001
    main_window.show()
    main_window.tool_manager.activate("select")
    scene.set_guides([Guide(H, 200.0)])
    assert not panel._guide_section.isVisible()  # noqa: SLF001
    view.select_guide(Guide(H, 200.0))
    assert panel._guide_section.isVisible()  # noqa: SLF001
    assert not panel._canvas_section.isVisible()  # noqa: SLF001
    assert panel._guide_type_label.text() == "Horizontal guide"  # noqa: SLF001
    assert panel._guide_pos_spin.value() == 200.0  # noqa: SLF001
    assert not panel._guide_locked_check.isChecked()  # noqa: SLF001
    # Every row is one undoable command, and the panel follows the changed guide
    panel._guide_pos_spin.setValue(250.0)  # noqa: SLF001
    assert scene.guides == [Guide(H, 250.0)]
    assert view.selected_guide == Guide(H, 250.0)
    panel._guide_color_picker.color = QColor("#ff00ff00")  # noqa: SLF001
    panel._guide_color_picker.color_changed.emit(QColor("#ff00ff00"))  # noqa: SLF001
    assert scene.guides[0].color == "#ff00ff00"
    index = panel._guide_style_combo.findData(GuideStyle.DOTTED)  # noqa: SLF001
    panel._guide_style_combo.setCurrentIndex(index)  # noqa: SLF001
    assert scene.guides[0].style is GuideStyle.DOTTED
    panel._guide_locked_check.setChecked(True)  # noqa: SLF001
    assert scene.guides[0].locked
    assert scene.command_stack.undo_text.endswith("Lock Guide")
    # Locked: the other rows refuse with the 1.3 message and show the value again
    panel._guide_pos_spin.setValue(300.0)  # noqa: SLF001
    qtbot.waitUntil(lambda: bool(unmet_messages))
    assert unmet_messages[-1] == (
        "Guide position",
        "Guide position needs an unlocked guide selected.",
    )
    assert scene.guides[0].position == 250.0
    assert panel._guide_pos_spin.value() == 250.0  # noqa: SLF001
    panel._guide_locked_check.setChecked(False)  # noqa: SLF001
    assert not scene.guides[0].locked
    for _ in range(4):
        scene.command_stack.undo()
    assert scene.guides == [Guide(H, 250.0)]
    # Deselecting the guide brings the usual sections back
    view.select_guide(None)
    assert not panel._guide_section.isVisible()  # noqa: SLF001
    assert panel._canvas_section.isVisible()  # noqa: SLF001
    scene.command_stack.mark_clean()


def test_a_colour_picked_for_a_selected_guide_shows_at_once(qtbot: QtBot) -> None:
    """Doug's display, 09-27-26: the selection colour covered the guide's own colour
    until the guide was let go, so a colour change seemed to do nothing."""
    from snapmock.commands.guide_commands import ChangeGuideCommand

    scene, view, _tm = _view(qtbot)
    guide = Guide(H, 200.0)
    scene.set_guides([guide])
    view.select_guide(guide)
    red = guide.with_changes(color="#ffff0000")
    scene.command_stack.push(ChangeGuideCommand(scene, guide, red, "Change Guide Color"))
    assert view.selected_guide == red
    assert view.guide_pen_for(red).color() == QColor("#ffff0000")
    image = QImage(400, 400, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    view.drawForeground(painter, QRectF(0, 0, 800, 600))
    painter.end()
    on_the_line = {image.pixelColor(50, 200).rgb(), image.pixelColor(50, 199).rgb()}
    assert QColor("#ffff0000").rgb() in on_the_line
