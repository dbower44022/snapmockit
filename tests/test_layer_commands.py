"""Layer commands: a new layer becomes the active layer (General UI PRD 7.4; decided
09-14-26 after the display run of that day, where "Layer 1 remained active")."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from snapmock.commands.layer_commands import AddLayerCommand
from snapmock.core.scene import SnapScene
from snapmock.main_window import MainWindow


def test_a_new_layer_becomes_active_and_undo_restores_the_earlier_one(
    qapp: QApplication,
) -> None:
    scene = SnapScene()
    lm = scene.layer_manager
    first = lm.active_layer
    assert first is not None and first.name == "Layer 1"
    scene.command_stack.push(AddLayerCommand(lm, "Layer 2"))
    active = lm.active_layer
    assert active is not None and active.name == "Layer 2"
    scene.command_stack.push(AddLayerCommand(lm, "Layer 3", 1))  # inserted between
    active = lm.active_layer
    assert active is not None and active.name == "Layer 3"
    scene.command_stack.undo()
    assert lm.active_layer is not None and lm.active_layer.name == "Layer 2"
    scene.command_stack.undo()
    assert lm.active_layer is first
    scene.command_stack.redo()
    assert lm.active_layer is not None and lm.active_layer.name == "Layer 2"


def test_new_layer_from_the_window_highlights_the_new_row(main_window: MainWindow) -> None:
    lm = main_window.scene.layer_manager
    main_window._layer_new()  # noqa: SLF001
    assert lm.active_layer is not None and lm.active_layer.name == "Layer 2"
    rows = main_window._layer_panel._list  # noqa: SLF001
    current = rows.item(rows.currentRow())
    assert current is not None and current.text() == "Layer 2"
    main_window.scene.command_stack.undo()
    assert lm.active_layer is not None and lm.active_layer.name == "Layer 1"
    current = rows.item(rows.currentRow())
    assert current is not None and current.text() == "Layer 1"
