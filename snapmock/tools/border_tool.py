"""BorderTool — the canvas border (Navigation & Raster Operations PRD Section 10).

The only tool in the palette with no canvas interaction: it draws nothing on press or
drag, and its whole surface is the Tool Options Bar. What the bar edits is a property of
the document rather than a creation default, as the Crop tool's aspect presets already
do, so every control reads the scene it is given and writes one command per edit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolBar,
    QWidget,
)

from snapmock.commands.canvas_property_commands import SetCanvasBorderCommand
from snapmock.config.constants import BorderStyle
from snapmock.tools.base_tool import BaseTool
from snapmock.ui.color_picker import ColorPicker

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager

_STYLE_LABELS: tuple[tuple[str, BorderStyle], ...] = tuple(
    (style.value.replace("dashdot", "dash-dot").title(), style) for style in BorderStyle
)

_SWATCH_SIZE = 24


def _live[W: QWidget](widget: W | None) -> W | None:
    """*widget*, or None when Qt has already destroyed the C++ object behind it.

    The Tool Options Bar clears its widgets whenever it rebuilds, and a reactivation
    reads the document before the new widgets exist, so every read goes through this.
    """
    if widget is None or sip.isdeleted(widget):
        return None
    return widget


class BorderTool(BaseTool):
    """Put a border around the image (Navigation PRD Section 10).

    The border is a property of the scene, not an item: there is one per document, it is
    never selected, and it survives every canvas operation. Width 0 is the absence of a
    border.
    """

    def __init__(self) -> None:
        super().__init__()
        self._width_spin: QSpinBox | None = None
        self._color_picker: ColorPicker | None = None
        self._opacity_spin: QSpinBox | None = None
        self._style_combo: QComboBox | None = None
        self._shadow_check: QCheckBox | None = None
        self._remove_button: QPushButton | None = None
        self._writing = False

    @property
    def tool_id(self) -> str:
        return "border"

    @property
    def display_name(self) -> str:
        return "Border"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.ArrowCursor

    # --- lifecycle ---

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        super().activate(scene, selection_manager)
        scene.border_changed.connect(self._read_scene)
        scene.canvas_size_changed.connect(self._on_canvas_size_changed)
        self._read_scene()

    def deactivate(self) -> None:
        scene = self._scene
        if scene is not None:
            try:
                scene.border_changed.disconnect(self._read_scene)
                scene.canvas_size_changed.disconnect(self._on_canvas_size_changed)
            except TypeError:  # pragma: no cover - already disconnected
                pass
        # The Tool Options Bar destroys its widgets when it rebuilds for the next tool,
        # and a reactivation reads the scene before the bar has built new ones. Drop the
        # references here so nothing reaches a deleted widget.
        self._forget_widgets()
        super().deactivate()

    def _forget_widgets(self) -> None:
        self._width_spin = None
        self._color_picker = None
        self._opacity_spin = None
        self._style_combo = None
        self._shadow_check = None
        self._remove_button = None

    # --- the bar (10.5) ---

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        toolbar.addWidget(QLabel(" Width:"))
        width = QSpinBox()
        width.setRange(0, self._max_width())
        width.setSuffix(" px")
        width.setAccessibleName("Border width")
        width.setToolTip("Border thickness on each side; 0 removes the border")
        width.valueChanged.connect(self._on_width_changed)
        toolbar.addWidget(width)
        self._width_spin = width

        toolbar.addWidget(QLabel(" Color:"))
        picker = ColorPicker(swatch_size=_SWATCH_SIZE)
        picker.setAccessibleName("Border color")
        picker.setToolTip("Border colour")
        picker.color_changed.connect(self._on_color_changed)
        toolbar.addWidget(picker)
        self._color_picker = picker

        toolbar.addWidget(QLabel(" Opacity:"))
        opacity = QSpinBox()
        opacity.setRange(0, 100)
        opacity.setSuffix("%")
        opacity.setAccessibleName("Border opacity")
        opacity.setToolTip("Border transparency, stored as the border colour's alpha")
        opacity.valueChanged.connect(self._on_opacity_changed)
        toolbar.addWidget(opacity)
        self._opacity_spin = opacity

        toolbar.addWidget(QLabel(" Style:"))
        style = QComboBox()
        style.setAccessibleName("Border style")
        style.setToolTip("Border line type")
        for label, value in _STYLE_LABELS:
            style.addItem(label, value)
        style.currentIndexChanged.connect(self._on_style_changed)
        toolbar.addWidget(style)
        self._style_combo = style

        shadow = QCheckBox("Shadow")
        shadow.setAccessibleName("Border shadow")
        shadow.setToolTip("Cast a drop shadow from the border's outer edge")
        shadow.toggled.connect(self._on_shadow_toggled)
        toolbar.addWidget(shadow)
        self._shadow_check = shadow

        remove = QPushButton("Remove Border")
        remove.setAccessibleName("Remove border")
        remove.clicked.connect(self._on_remove_clicked)
        toolbar.addWidget(remove)
        self._remove_button = remove

        self._read_scene()

    # --- reading the document into the bar ---

    def _max_width(self) -> int:
        scene = self._scene
        from snapmock.config.constants import BORDER_WIDTH_MAX

        return scene.max_border_width() if scene is not None else BORDER_WIDTH_MAX

    def _on_canvas_size_changed(self, _size: object) -> None:
        width_spin = _live(self._width_spin)
        if width_spin is not None:
            width_spin.setRange(0, self._max_width())
        self._read_scene()

    def _read_scene(self) -> None:
        """Put the document's border values into the bar without writing commands.

        Every widget is checked for life first: the bar destroys and rebuilds them around
        a tool change, and this runs from the scene's signals as well as from the bar.
        """
        scene = self._scene
        if scene is None:
            return
        width_spin = _live(self._width_spin)
        color_picker = _live(self._color_picker)
        opacity_spin = _live(self._opacity_spin)
        style_combo = _live(self._style_combo)
        shadow_check = _live(self._shadow_check)
        remove_button = _live(self._remove_button)
        self._writing = True
        try:
            if width_spin is not None:
                width_spin.setRange(0, self._max_width())
                width_spin.setValue(scene.border_width)
            color = scene.border_color
            if color_picker is not None:
                color_picker.color = color
            if opacity_spin is not None:
                opacity_spin.setValue(round(color.alpha() / 255 * 100))
            if style_combo is not None:
                index = style_combo.findData(scene.border_style)
                if index >= 0:
                    style_combo.setCurrentIndex(index)
            if shadow_check is not None:
                shadow_check.setChecked(bool(scene.border_shadow.get("shadow_enabled", False)))
            if remove_button is not None:
                remove_button.setEnabled(scene.has_border)
        finally:
            self._writing = False
        self._show_status_hint()

    # --- writing the bar into the document, one command per edit ---

    def _push(self, prop_name: str, old_value: object, new_value: object) -> None:
        scene = self._scene
        if scene is None or self._writing or old_value == new_value:
            return
        scene.command_stack.push(SetCanvasBorderCommand(scene, prop_name, old_value, new_value))
        self._show_status_hint()

    def _on_width_changed(self, value: int) -> None:
        scene = self._scene
        if scene is None:
            return
        self._push("border_width", scene.border_width, int(value))

    def _on_color_changed(self, color: QColor) -> None:
        scene = self._scene
        if scene is None:
            return
        # The swatch carries no alpha of its own; the Opacity control owns it (10.5)
        new_color = QColor(color)
        new_color.setAlpha(scene.border_color.alpha())
        self._push("border_color", scene.border_color, new_color)

    def _on_opacity_changed(self, percent: int) -> None:
        scene = self._scene
        if scene is None:
            return
        new_color = QColor(scene.border_color)
        new_color.setAlpha(round(max(0, min(100, percent)) / 100 * 255))
        self._push("border_color", scene.border_color, new_color)

    def _on_style_changed(self, _index: int) -> None:
        scene = self._scene
        combo = self._style_combo
        if scene is None or combo is None:
            return
        value = combo.currentData()
        if isinstance(value, BorderStyle):
            self._push("border_style", scene.border_style, value)

    def _on_shadow_toggled(self, checked: bool) -> None:
        scene = self._scene
        if scene is None:
            return
        old = scene.border_shadow
        new = dict(old)
        new["shadow_enabled"] = bool(checked)
        self._push("border_shadow", old, new)

    def _on_remove_clicked(self) -> None:
        scene = self._scene
        if scene is None:
            return
        self._push("border_width", scene.border_width, 0)

    # --- status bar (10.10) ---

    @property
    def status_hint(self) -> str:
        scene = self._scene
        if scene is None or not scene.has_border:
            return "Set Width above 0 to put a border around the image."
        if scene.border_width >= scene.max_border_width():
            return (
                f"Border limited to {scene.max_border_width()} px: "
                "the image plus its border may not exceed 32000 px."
            )
        style = scene.border_style.value.replace("dashdot", "dash-dot")
        return f"Border: {scene.border_width} px {style} | Width 0 removes it"
