"""The shape tools' shared drawing lifecycle (Basic Shape PRD 2.1, 2.3, Section 12).

The press guard of 2.1 — no shape on a locked or a hidden layer, refused with the
never-disabled message of General UI PRD 1.3 — and the preview's life: ``cancel``
drops it, ``is_active_operation`` is true while a drag lasts, and Escape ends the
drag leaving nothing behind.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.view import SnapView
from snapmock.main_window import MainWindow
from snapmock.tools.arrow_tool import ArrowTool
from snapmock.tools.base_tool import BaseTool
from snapmock.tools.ellipse_tool import EllipseTool
from snapmock.tools.freehand_tool import FreehandTool
from snapmock.tools.highlight_tool import HighlightTool
from snapmock.tools.line_tool import LineTool
from snapmock.tools.rectangle_tool import RectangleTool

NONE = Qt.KeyboardModifier.NoModifier
LEFT = Qt.MouseButton.LeftButton

# The five drag-drawn shape tools of 2.1: one press, one move, one release each.
DRAG_TOOLS: tuple[tuple[str, type[BaseTool]], ...] = (
    ("rectangle", RectangleTool),
    ("ellipse", EllipseTool),
    ("line", LineTool),
    ("arrow", ArrowTool),
    ("freehand", FreehandTool),
)


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=800, height=600)


def _setup(qtbot: QtBot, scene: SnapScene, factory: type[BaseTool]) -> tuple[SnapView, BaseTool]:
    view = SnapView(scene)
    view.resize(800, 600)
    qtbot.addWidget(view)
    view.show()
    view.centerOn(300, 200)
    tool = factory()
    tool.activate(scene, SelectionManager(scene))
    return view, tool


def _mouse(view: SnapView, kind: QEvent.Type, pos: QPointF) -> QMouseEvent:
    vp = QPointF(view.mapFromScene(pos))
    return QMouseEvent(kind, vp, vp, LEFT, LEFT, NONE)


def _press(tool: BaseTool, view: SnapView, pos: QPointF) -> bool:
    return tool.mouse_press(_mouse(view, QEvent.Type.MouseButtonPress, pos))


def _move(tool: BaseTool, view: SnapView, pos: QPointF) -> bool:
    return tool.mouse_move(_mouse(view, QEvent.Type.MouseMove, pos))


def _release(tool: BaseTool, view: SnapView, pos: QPointF) -> bool:
    return tool.mouse_release(_mouse(view, QEvent.Type.MouseButtonRelease, pos))


def _drag(tool: BaseTool, view: SnapView, start: QPointF, end: QPointF) -> None:
    _press(tool, view, start)
    _move(tool, view, end)
    _release(tool, view, end)


# --------------------------------------------------------------- the press guard (2.1)


@pytest.mark.parametrize(("tool_id", "factory"), DRAG_TOOLS)
def test_a_locked_layer_refuses_the_drag_with_the_message(
    qtbot: QtBot,
    scene: SnapScene,
    unmet_messages: list[tuple[str, str]],
    tool_id: str,
    factory: type[BaseTool],
) -> None:
    view, tool = _setup(qtbot, scene, factory)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    layer.locked = True

    _drag(tool, view, QPointF(100, 100), QPointF(200, 160))

    assert scene.annotation_items() == []
    assert not tool.is_active_operation
    assert unmet_messages == [
        (tool.display_name, f"{tool.display_name} needs an unlocked active layer.")
    ]


@pytest.mark.parametrize(("tool_id", "factory"), DRAG_TOOLS)
def test_a_hidden_layer_refuses_the_drag_with_the_message(
    qtbot: QtBot,
    scene: SnapScene,
    unmet_messages: list[tuple[str, str]],
    tool_id: str,
    factory: type[BaseTool],
) -> None:
    view, tool = _setup(qtbot, scene, factory)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    layer.visible = False

    _drag(tool, view, QPointF(100, 100), QPointF(200, 160))

    assert scene.annotation_items() == []
    assert unmet_messages == [
        (tool.display_name, f"{tool.display_name} needs a visible active layer.")
    ]


def test_both_unmet_are_named_together(
    qtbot: QtBot, scene: SnapScene, unmet_messages: list[tuple[str, str]]
) -> None:
    """General UI PRD 1.3: the message names exactly which requirements are unmet."""
    view, tool = _setup(qtbot, scene, RectangleTool)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    layer.locked = True
    layer.visible = False

    _drag(tool, view, QPointF(100, 100), QPointF(200, 160))

    assert scene.annotation_items() == []
    (_title, text) = unmet_messages[0]
    assert "an unlocked active layer" in text
    assert "a visible active layer" in text


def test_the_highlighter_and_the_blur_tool_make_the_same_check(
    main_window: MainWindow, unmet_messages: list[tuple[str, str]]
) -> None:
    """Decision 2 and Blur PRD 8.1: every tool that draws makes the check, not only
    the seven shape tools."""
    scene, view = main_window.scene, main_window.view
    layer = scene.layer_manager.active_layer
    assert layer is not None
    layer.locked = True

    for tool_id in ("highlight", "blur"):
        main_window.tool_manager.activate(tool_id)
        tool = main_window.tool_manager.active_tool
        assert tool is not None
        _drag(tool, view, QPointF(60, 60), QPointF(200, 160))

    assert scene.annotation_items() == []
    assert [title for title, _text in unmet_messages] == ["Highlight", "Blur"]


def test_an_unlocked_visible_layer_draws_and_shows_no_message(
    qtbot: QtBot, scene: SnapScene, unmet_messages: list[tuple[str, str]]
) -> None:
    view, tool = _setup(qtbot, scene, RectangleTool)
    _drag(tool, view, QPointF(100, 100), QPointF(200, 160))
    assert len(scene.annotation_items()) == 1
    assert unmet_messages == []


# ------------------------------------------------- the preview's life (2.1, 2.3, 12)


@pytest.mark.parametrize(("tool_id", "factory"), DRAG_TOOLS)
def test_a_drag_in_progress_is_an_active_operation(
    qtbot: QtBot, scene: SnapScene, tool_id: str, factory: type[BaseTool]
) -> None:
    """The Space-bar pan and the momentary Alt eyedropper both stand down while this
    is true, so a drag cannot be taken away mid-way."""
    view, tool = _setup(qtbot, scene, factory)
    assert not tool.is_active_operation

    _press(tool, view, QPointF(100, 100))
    assert tool.is_active_operation
    _move(tool, view, QPointF(200, 160))
    assert tool.is_active_operation

    _release(tool, view, QPointF(200, 160))
    assert not tool.is_active_operation


@pytest.mark.parametrize(("tool_id", "factory"), DRAG_TOOLS)
def test_cancel_during_a_drag_leaves_nothing_in_the_scene(
    qtbot: QtBot, scene: SnapScene, tool_id: str, factory: type[BaseTool]
) -> None:
    view, tool = _setup(qtbot, scene, factory)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160))
    before = len(scene.items())

    tool.cancel()

    assert len(scene.items()) == before - 1
    assert scene.annotation_items() == []
    assert not tool.is_active_operation
    assert not scene.command_stack.can_undo


@pytest.mark.parametrize(("tool_id", "factory"), DRAG_TOOLS)
def test_escape_during_a_drag_leaves_nothing(
    qtbot: QtBot, scene: SnapScene, tool_id: str, factory: type[BaseTool]
) -> None:
    """2.3's Escape row: cancel the drawing operation, remove the preview, return to
    Idle. The window's Edit > Deselect asks the active tool first."""
    view, tool = _setup(qtbot, scene, factory)
    assert not tool.handle_escape()  # nothing in progress: Deselect runs instead

    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160))

    assert tool.handle_escape()
    assert scene.annotation_items() == []
    assert not tool.is_active_operation
    # The release that follows the Escape creates nothing
    _release(tool, view, QPointF(200, 160))
    assert scene.annotation_items() == []


@pytest.mark.parametrize(("tool_id", "factory"), DRAG_TOOLS)
def test_a_tool_switch_during_a_drag_leaves_nothing_in_the_scene(
    main_window: MainWindow, tool_id: str, factory: type[BaseTool]
) -> None:
    """``ToolManager.activate`` calls ``cancel`` before ``deactivate``; before this work
    the preview stayed in the scene, in no layer and behind no command."""
    scene, view = main_window.scene, main_window.view
    main_window.tool_manager.activate(tool_id)
    tool = main_window.tool_manager.active_tool
    assert tool is not None

    _press(tool, view, QPointF(60, 60))
    _move(tool, view, QPointF(200, 160))
    assert tool.is_active_operation

    main_window.tool_manager.activate("select")

    assert scene.annotation_items() == []
    assert not scene.command_stack.can_undo
    assert not tool.is_active_operation


def _neutral_input_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """No real mouse button held and no focused widget.

    ``SnapView.focusOutEvent`` refuses to cancel when a mouse button is down or when
    focus moved to a child of its own viewport, so that a transient focus loss during
    a real drag does not throw the drag away. Neither is the case being tested here,
    and both read the application's ambient state, which other tests in the same
    process can leave set — so they are pinned rather than left to chance.
    """
    monkeypatch.setattr(
        QApplication, "mouseButtons", staticmethod(lambda: Qt.MouseButton.NoButton)
    )
    monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: None))


def test_a_focus_loss_during_a_drag_leaves_nothing(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``SnapView.focusOutEvent`` cancels the active tool's operation; it could not see
    a shape drag before this work, because ``is_active_operation`` was always False."""
    _neutral_input_state(monkeypatch)
    scene, view = main_window.scene, main_window.view
    main_window.tool_manager.activate("rectangle")
    tool = main_window.tool_manager.active_tool
    assert tool is not None

    _press(tool, view, QPointF(60, 60))
    _move(tool, view, QPointF(200, 160))
    view.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))

    assert scene.annotation_items() == []
    assert not tool.is_active_operation


def test_a_focus_loss_with_the_button_still_down_keeps_the_drag(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the same rule: a transient focus loss while the button is held
    — a tooltip stealing focus on Linux — leaves the drag alone to finish normally."""
    _neutral_input_state(monkeypatch)
    monkeypatch.setattr(
        QApplication, "mouseButtons", staticmethod(lambda: Qt.MouseButton.LeftButton)
    )
    scene, view = main_window.scene, main_window.view
    main_window.tool_manager.activate("rectangle")
    tool = main_window.tool_manager.active_tool
    assert tool is not None

    _press(tool, view, QPointF(60, 60))
    _move(tool, view, QPointF(200, 160))
    view.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))

    assert tool.is_active_operation
    _release(tool, view, QPointF(200, 160))
    assert len(scene.annotation_items()) == 1


def test_the_space_bar_pan_stands_down_while_a_drag_lasts(main_window: MainWindow) -> None:
    main_window.tool_manager.activate("rectangle")
    tool = main_window.tool_manager.active_tool
    assert tool is not None
    _press(tool, main_window.view, QPointF(60, 60))
    _move(tool, main_window.view, QPointF(200, 160))

    main_window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, NONE))

    assert main_window.tool_manager.active_tool_id == "rectangle"


def test_the_momentary_eyedropper_stands_down_while_a_drag_lasts(
    main_window: MainWindow,
) -> None:
    """General UI PRD 12.2: Alt keeps its drawing meaning while a drag lasts (Blur PRD
    4.7's mid-drag row is the recorded departure)."""
    main_window.tool_manager.activate("ellipse")
    tool = main_window.tool_manager.active_tool
    assert tool is not None
    _press(tool, main_window.view, QPointF(60, 60))
    _move(tool, main_window.view, QPointF(200, 160))

    main_window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Alt, NONE))

    assert main_window.tool_manager.active_tool_id == "ellipse"


def test_the_highlighter_reports_its_drag_as_before(qtbot: QtBot, scene: SnapScene) -> None:
    """The Highlighter already tracked its own preview; the shared lifecycle leaves it."""
    view, tool = _setup(qtbot, scene, HighlightTool)
    _press(tool, view, QPointF(100, 100))
    _move(tool, view, QPointF(200, 160))
    assert tool.is_active_operation
    tool.cancel()
    assert not tool.is_active_operation
    assert scene.annotation_items() == []
