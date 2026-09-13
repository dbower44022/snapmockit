"""The marker tools' placement hints after their window is gone.

The Stamp, Emoji, and Numbered Step tools show "Placed …" for two seconds after a
placement and then put the Idle hint back from a parentless ``QTimer``. When a window is
torn down within those two seconds without its tool being deactivated — which is what a
test's teardown does — the timer used to fire into a tool whose scene had been deleted,
and ``BaseTool._view`` raised ``RuntimeError: wrapped C/C++ object of type SnapScene has
been deleted`` inside whichever later test happened to be running the event loop. That
was the timing-sensitive Zoom tool failure of every full-suite run from 09-11-26 to
09-12-26 (shared drawing notes, Section 9.2).
"""

from __future__ import annotations

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from snapmock.main_window import MainWindow
from snapmock.tools.base_tool import BaseTool

LEFT = Qt.MouseButton.LeftButton
NONE = Qt.KeyboardModifier.NoModifier


def _click(window: MainWindow, pos: QPointF) -> None:
    vp = QPointF(window.view.mapFromScene(pos))
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        handle = (
            window.tool_manager.handle_mouse_press
            if kind is QEvent.Type.MouseButtonPress
            else window.tool_manager.handle_mouse_release
        )
        handle(QMouseEvent(kind, vp, vp, LEFT, LEFT, NONE))


def _placed_then_torn_down(qapp: QApplication, tool_id: str) -> BaseTool:
    """Place one marker, then delete the window within the hint's two seconds."""
    window = MainWindow()
    window.show()
    window.tool_manager.activate(tool_id)
    tool = window.tool_manager.active_tool
    assert tool is not None
    if tool_id == "stamp":
        tool.set_active_stamp("status/approved")  # type: ignore[attr-defined]
    elif tool_id == "emoji":
        tool.set_active_emoji("\U0001f44d")  # type: ignore[attr-defined]
    _click(window, QPointF(120, 120))
    timer = tool._hint_timer  # type: ignore[attr-defined]  # noqa: SLF001
    assert timer is not None and timer.isActive()
    assert tool.status_hint.startswith("Placed")

    for doc in window.documents.documents:
        doc.scene.command_stack.mark_clean()
    scene = window.scene
    window.close()
    sip.delete(window)
    qapp.processEvents()
    if not sip.isdeleted(scene):
        sip.delete(scene)
    assert sip.isdeleted(scene)
    return tool


@pytest.mark.parametrize("tool_id", ["stamp", "emoji", "numbered_step"])
def test_the_idle_hint_timer_finds_no_view_once_the_scene_is_gone(
    qapp: QApplication, tool_id: str
) -> None:
    tool = _placed_then_torn_down(qapp, tool_id)

    assert tool._view is None  # noqa: SLF001
    # What the timer's timeout runs; before the guard this raised RuntimeError
    tool._show_idle_hint()  # type: ignore[attr-defined]  # noqa: SLF001
    assert not tool._hint_timer.isActive()  # type: ignore[attr-defined]  # noqa: SLF001


def test_a_tool_whose_scene_is_deleted_has_no_view(qapp: QApplication) -> None:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager
    from snapmock.core.view import SnapView
    from snapmock.tools.rectangle_tool import RectangleTool

    scene = SnapScene(width=200, height=200)
    view = SnapView(scene)
    tool = RectangleTool()
    tool.activate(scene, SelectionManager(scene))
    assert tool._view is view  # noqa: SLF001

    sip.delete(view)
    sip.delete(scene)

    assert tool._view is None  # noqa: SLF001
