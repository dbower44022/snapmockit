"""The colour picker popover of General UI PRD 11.1 (Phase 6)."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent
from PyQt6.QtWidgets import QPushButton
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.settings import AppSettings
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.tools.eyedropper_tool import EyedropperTool
from snapmock.ui.color_picker import SQUARE_SIZE, SWATCH_COUNT, ColorPicker, ColorPopover


def _picker(qtbot: QtBot, color: str = "#FF0000", **kwargs: object) -> ColorPicker:
    picker = ColorPicker(QColor(color), **kwargs)  # type: ignore[arg-type]
    qtbot.addWidget(picker)
    picker.show()
    return picker


def _open(qtbot: QtBot, picker: ColorPicker) -> ColorPopover:
    picker.open_popover()
    popover = picker.popover
    assert popover is not None and popover.isVisible()
    qtbot.addWidget(popover)
    return popover


def test_swatch_opens_popover_beside_it_without_a_toggle(qtbot: QtBot) -> None:
    picker = _picker(qtbot)
    assert [b for b in picker.findChildren(QPushButton) if b.text() == "∅"] == []
    picker._swatch.click()  # noqa: SLF001
    popover = picker.popover
    assert popover is not None and popover.isVisible()
    assert popover.windowFlags() & Qt.WindowType.Popup
    assert popover._square.width() == SQUARE_SIZE  # noqa: SLF001
    assert popover._hex_edit.text() == "#FF0000"  # noqa: SLF001
    assert [s.value() for s in popover._rgb_spins] == [255, 0, 0]  # noqa: SLF001
    assert [s.value() for s in popover._hsl_spins] == [0, 100, 50]  # noqa: SLF001
    assert popover._transparent_btn is not None  # noqa: SLF001
    popover.hide()


def test_square_and_bars_apply_live(qtbot: QtBot) -> None:
    picker = _picker(qtbot)
    seen: list[QColor] = []
    picker.color_changed.connect(seen.append)
    popover = _open(qtbot, picker)
    square = popover._square  # noqa: SLF001
    qtbot.mouseClick(
        square, Qt.MouseButton.LeftButton, pos=QPoint(SQUARE_SIZE - 1, SQUARE_SIZE - 1)
    )
    assert picker.color == QColor(0, 0, 0)  # value 0 is black
    assert seen and seen[-1] == QColor(0, 0, 0)
    qtbot.mouseClick(square, Qt.MouseButton.LeftButton, pos=QPoint(SQUARE_SIZE - 1, 0))
    assert picker.color == QColor(255, 0, 0)
    hue = popover._hue_bar  # noqa: SLF001
    qtbot.mouseClick(hue, Qt.MouseButton.LeftButton, pos=QPoint(hue.width() // 3, 5))
    assert picker.color.hsvHue() in range(115, 125)
    alpha = popover._alpha_bar  # noqa: SLF001
    qtbot.mouseClick(alpha, Qt.MouseButton.LeftButton, pos=QPoint(0, 5))
    assert picker.color.alpha() == 0
    assert popover._hex_edit.text().startswith("#00")  # noqa: SLF001
    popover.hide()


def test_inputs_sync_each_other(qtbot: QtBot) -> None:
    picker = _picker(qtbot)
    popover = _open(qtbot, picker)
    popover._hex_edit.setText("#336699")  # noqa: SLF001
    popover._hex_edit.editingFinished.emit()  # noqa: SLF001
    assert picker.color == QColor("#336699")
    assert [s.value() for s in popover._rgb_spins] == [0x33, 0x66, 0x99]  # noqa: SLF001
    assert popover._hsl_spins[0].value() == 210  # noqa: SLF001
    popover._rgb_spins[0].setValue(255)  # noqa: SLF001
    assert picker.color == QColor(255, 0x66, 0x99)
    popover._hsl_spins[2].setValue(100)  # noqa: SLF001
    assert picker.color == QColor("#FFFFFF")
    popover._hex_edit.setText("nonsense")  # noqa: SLF001
    popover._hex_edit.editingFinished.emit()  # noqa: SLF001
    assert popover._hex_edit.text() == "#FFFFFF"  # noqa: SLF001
    popover.hide()


def test_transparent_swatch_and_its_absence(qtbot: QtBot) -> None:
    picker = _picker(qtbot)
    popover = _open(qtbot, picker)
    assert popover._transparent_btn is not None  # noqa: SLF001
    popover._transparent_btn.click()  # noqa: SLF001
    assert picker.color.alpha() == 0
    popover.hide()
    opaque_only = _picker(qtbot, allow_transparent=False)
    popover2 = _open(qtbot, opaque_only)
    assert popover2._transparent_btn is None  # noqa: SLF001
    popover2.hide()


def test_recent_colors_dedupe_newest_first_and_cap(qtbot: QtBot) -> None:
    settings = AppSettings()
    for i in range(SWATCH_COUNT + 3):
        settings.push_recent_color(QColor(i, i, i))
    settings.push_recent_color(QColor(3, 3, 3))
    recent = settings.recent_colors()
    assert len(recent) == SWATCH_COUNT
    assert recent[0] == QColor(3, 3, 3)
    assert [c.red() for c in recent].count(3) == 1
    picker = _picker(qtbot)
    popover = _open(qtbot, picker)
    assert popover._recent_swatches[0].color == QColor(3, 3, 3)  # noqa: SLF001
    popover._recent_swatches[1].click()  # noqa: SLF001
    assert picker.color == recent[1]
    popover.hide()
    # Closing with a changed colour commits it to the recent list
    assert AppSettings().recent_colors()[0] == recent[1]


def test_saved_slots_store_on_right_click(qtbot: QtBot) -> None:
    picker = _picker(qtbot, "#ABCDEF")
    popover = _open(qtbot, picker)
    slot = popover._saved_swatches[4]  # noqa: SLF001
    assert slot.color is None
    slot.save_requested.emit(4)
    assert AppSettings().saved_colors()[4] == QColor("#ABCDEF")
    assert slot.color == QColor("#ABCDEF")
    popover.hide()
    picker2 = _picker(qtbot, "#000000")
    popover2 = _open(qtbot, picker2)
    popover2._saved_swatches[4].click()  # noqa: SLF001
    assert picker2.color == QColor("#ABCDEF")
    popover2.hide()


def test_a_click_on_an_empty_saved_slot_saves_the_colour(qtbot: QtBot) -> None:
    """Doug, 09-12-26: "there is no button to save it". A click on an empty slot is it."""
    picker = _picker(qtbot, "#123456")
    popover = _open(qtbot, picker)
    slot = popover._saved_swatches[2]  # noqa: SLF001
    assert slot.color is None
    slot.click()
    assert slot.color == QColor("#123456")
    assert AppSettings().saved_colors()[2] == QColor("#123456")
    # A second click on the now-filled slot applies it rather than overwriting it.
    picker.color = QColor("#FFFFFF")
    slot.click()
    assert picker.color == QColor("#123456")
    assert AppSettings().saved_colors()[2] == QColor("#123456")
    popover.hide()


def test_a_click_on_an_empty_recent_slot_does_nothing(qtbot: QtBot) -> None:
    picker = _picker(qtbot, "#123456")
    popover = _open(qtbot, picker)
    slot = popover._recent_swatches[SWATCH_COUNT - 1]  # noqa: SLF001
    assert slot.color is None
    slot.click()
    assert slot.color is None
    assert picker.color == QColor("#123456")
    popover.hide()


def test_every_swatch_says_what_a_click_does(qtbot: QtBot) -> None:
    """A row of empty squares labelled "Saved" has to explain itself (PRD 11.1)."""
    picker = _picker(qtbot, "#ABCDEF")
    popover = _open(qtbot, picker)
    saved = popover._saved_swatches[0]  # noqa: SLF001
    recent = popover._recent_swatches[0]  # noqa: SLF001
    assert "click to save" in saved.toolTip().lower()
    assert saved.toolTip() == saved.accessibleDescription()
    saved.click()  # now it holds a colour
    assert "click to use it" in saved.toolTip()
    assert "right-click to replace" in saved.toolTip()
    if recent.color is not None:
        assert "click to use it" in recent.toolTip()
    else:
        assert "appear here" in recent.toolTip()
    popover.hide()


def test_setting_color_updates_an_open_popover_without_emitting(qtbot: QtBot) -> None:
    picker = _picker(qtbot)
    seen: list[QColor] = []
    picker.color_changed.connect(seen.append)
    popover = _open(qtbot, picker)
    picker.color = QColor("#00FF00")
    assert popover._hex_edit.text() == "#00FF00"  # noqa: SLF001
    assert seen == []
    popover.hide()


def test_eyedropper_button_without_a_window_explains(
    qtbot: QtBot, unmet_messages: list[tuple[str, str]]
) -> None:
    ColorPicker.set_eyedropper_handler(None)
    picker = _picker(qtbot)
    popover = _open(qtbot, picker)
    popover._eyedropper_btn.click()  # noqa: SLF001
    assert unmet_messages == [("Eyedropper", "Eyedropper needs an open canvas to pick from.")]


def test_eyedropper_pick_lands_in_the_picker_and_restores_the_tool(
    main_window: MainWindow, qtbot: QtBot
) -> None:
    main_window.show()
    scene = main_window.scene
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item = RectangleItem(QRectF(0, 0, 200, 200))
    item.fill_color = QColor("#123456")
    item.stroke_width = 0
    scene.command_stack.push(AddItemCommand(scene, item, layer.layer_id))
    main_window.tool_manager.activate("rectangle")
    picker = ColorPicker(QColor("#FF0000"), main_window)
    seen: list[QColor] = []
    picker.color_changed.connect(seen.append)
    picker.open_popover()
    popover = picker.popover
    assert popover is not None
    popover._eyedropper_btn.click()  # noqa: SLF001
    assert not popover.isVisible()
    assert main_window.tool_manager.active_tool_id == "eyedropper"
    eyedropper = main_window.tool_manager.tool("eyedropper")
    assert isinstance(eyedropper, EyedropperTool)
    view = main_window.view
    view_pos = view.mapFromScene(QPointF(100, 100))
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(view_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(view_pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # The release applies the colour under the cursor at that moment (Blur PRD 4.2).
    assert eyedropper.mouse_press(press)
    assert eyedropper.mouse_release(release)
    assert seen and seen[-1] == QColor("#123456")
    assert picker.color == QColor("#123456")
    assert main_window.tool_manager.active_tool_id == "rectangle"
    reopened = picker.popover
    assert reopened is not None and reopened.isVisible()
    assert reopened._hex_edit.text() == "#123456"  # noqa: SLF001
    assert AppSettings().recent_colors()[0] == QColor("#123456")
    reopened.hide()
