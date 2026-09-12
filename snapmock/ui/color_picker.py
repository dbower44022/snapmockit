"""ColorPicker — a colour swatch that opens the picker popover of General UI PRD 11.1.

The swatch keeps the surface its consumers use (``color``, ``color_changed``,
``allow_transparent``, ``swatch_size``, ``mixed``); the popover beside it holds
the saturation and value square, the hue and opacity bars, the hex, RGB, and
HSL inputs, the recent and saved swatches, the Transparent swatch, and the
eyedropper button. Every change applies live through ``color_changed``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QContextMenuEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from snapmock.config.settings import AppSettings
from snapmock.core.theme_manager import current_theme, theme_manager
from snapmock.ui.unmet_requirements import check_requirements

SQUARE_SIZE = 200
"""Side of the saturation and value square (PRD 11.1)."""
BAR_HEIGHT = 14
SWATCH_COUNT = 12
"""Recent and saved swatches per row (PRD 11.1)."""
MINI_SWATCH = 18

EyedropperHandler = Callable[[Callable[[QColor], None]], bool]
"""Activates the eyedropper and later calls the callback with the pick; False if it cannot."""


def _hex_text(color: QColor) -> str:
    fmt = QColor.NameFormat.HexArgb if color.alpha() < 255 else QColor.NameFormat.HexRgb
    return color.name(fmt).upper()


def _draw_checkerboard(painter: QPainter, rect: QRect, cell: int = 4) -> None:
    light = QColor(204, 204, 204)
    dark = QColor(153, 153, 153)
    for y in range(rect.top(), rect.bottom() + 1, cell):
        for x in range(rect.left(), rect.right() + 1, cell):
            even = ((x - rect.left()) // cell + (y - rect.top()) // cell) % 2 == 0
            w = min(cell, rect.right() + 1 - x)
            h = min(cell, rect.bottom() + 1 - y)
            painter.fillRect(QRect(x, y, w, h), light if even else dark)


class _SwatchButton(QPushButton):
    """A button that paints its current color, with checkerboard behind alpha."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor("red")
        self._mixed = False

    @property
    def color(self) -> QColor:
        return self._color

    @color.setter
    def color(self, value: QColor) -> None:
        self._color = QColor(value)
        self.update()

    @property
    def mixed(self) -> bool:
        return self._mixed

    @mixed.setter
    def mixed(self, value: bool) -> None:
        self._mixed = value
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        inner = self.rect().adjusted(1, 1, -1, -1)

        if self._color.alpha() < 255:
            _draw_checkerboard(painter, inner)

        # A mixed selection fills the left half only (PRD 8.6)
        if self._mixed:
            half = QRect(inner)
            half.setWidth(inner.width() // 2)
            painter.fillRect(half, self._color)
            painter.setPen(QColor("#888888"))
            painter.drawLine(inner.topRight(), inner.bottomLeft())
        else:
            painter.fillRect(inner, self._color)

        # A diagonal through a transparent swatch (PRD 5.2)
        if self._color.alpha() == 0 and not self._mixed:
            painter.setPen(QPen(QColor("#D32F2F"), 2))
            painter.drawLine(inner.bottomLeft(), inner.topRight())

        painter.setPen(QColor("#888888"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()


class _SaturationValueSquare(QWidget):
    """The 200 px square: saturation left to right, value bottom to top."""

    changed = pyqtSignal(int, int)
    """(saturation 0..255, value 0..255)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(SQUARE_SIZE, SQUARE_SIZE)
        self.setAccessibleName("Saturation and value")
        self._hue = 0
        self._saturation = 255
        self._value = 255

    def set_hsv(self, hue: int, saturation: int, value: int) -> None:
        self._hue = max(0, hue)
        self._saturation = saturation
        self._value = value
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        rect = self.rect()
        horizontal = QLinearGradient(rect.topLeft().toPointF(), rect.topRight().toPointF())
        horizontal.setColorAt(0.0, QColor("white"))
        horizontal.setColorAt(1.0, QColor.fromHsv(self._hue, 255, 255))
        painter.fillRect(rect, horizontal)
        vertical = QLinearGradient(rect.topLeft().toPointF(), rect.bottomLeft().toPointF())
        vertical.setColorAt(0.0, QColor(0, 0, 0, 0))
        vertical.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(rect, vertical)
        # Marker
        x = round(self._saturation / 255 * (SQUARE_SIZE - 1))
        y = round((255 - self._value) / 255 * (SQUARE_SIZE - 1))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawEllipse(QPoint(x, y), 5, 5)
        painter.setPen(QPen(QColor("black"), 1))
        painter.drawEllipse(QPoint(x, y), 6, 6)
        painter.end()

    def _pick(self, pos: QPoint) -> None:
        x = max(0, min(SQUARE_SIZE - 1, pos.x()))
        y = max(0, min(SQUARE_SIZE - 1, pos.y()))
        self._saturation = round(x / (SQUARE_SIZE - 1) * 255)
        self._value = round(255 - y / (SQUARE_SIZE - 1) * 255)
        self.update()
        self.changed.emit(self._saturation, self._value)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._pick(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._pick(event.pos())


class _GradientBar(QWidget):
    """A horizontal bar with a gradient and a marker: the hue and opacity sliders."""

    changed = pyqtSignal(int)

    def __init__(self, maximum: int, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._maximum = maximum
        self._value = 0
        self._stops: list[QColor] = []
        self._checkerboard = False
        self.setFixedSize(SQUARE_SIZE, BAR_HEIGHT)
        self.setAccessibleName(name)

    @property
    def value(self) -> int:
        return self._value

    def set_value(self, value: int) -> None:
        self._value = max(0, min(self._maximum, value))
        self.update()

    def set_stops(self, stops: list[QColor], *, checkerboard: bool = False) -> None:
        self._stops = list(stops)
        self._checkerboard = checkerboard
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        rect = self.rect()
        if self._checkerboard:
            _draw_checkerboard(painter, rect)
        gradient = QLinearGradient(rect.topLeft().toPointF(), rect.topRight().toPointF())
        for i, color in enumerate(self._stops):
            gradient.setColorAt(i / max(1, len(self._stops) - 1), color)
        painter.fillRect(rect, gradient)
        x = round(self._value / self._maximum * (rect.width() - 1))
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawLine(x, 0, x, rect.height())
        painter.setPen(QPen(QColor("black"), 1))
        painter.drawRect(x - 2, 0, 4, rect.height() - 1)
        painter.end()

    def _pick(self, pos: QPoint) -> None:
        x = max(0, min(self.width() - 1, pos.x()))
        self._value = round(x / (self.width() - 1) * self._maximum)
        self.update()
        self.changed.emit(self._value)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._pick(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._pick(event.pos())


class _MiniSwatch(QToolButton):
    """A recent or saved colour.

    A saved slot is filled by a click while it is empty or by a right-click at any time,
    and applies its colour on a click once it holds one (PRD 11.1). The tooltip says which,
    because a row of empty squares labelled "Saved" says nothing about how to fill it: Doug
    reported exactly that on 09-12-26 — "there is no button to save it".
    """

    save_requested = pyqtSignal(int)

    def __init__(self, index: int, *, saveable: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._saveable = saveable
        self._color: QColor | None = None
        self.setFixedSize(MINI_SWATCH, MINI_SWATCH)
        self.setAutoRaise(True)
        self.setAccessibleName(f"{'Saved' if saveable else 'Recent'} color {index + 1}")

    @property
    def color(self) -> QColor | None:
        return self._color

    @property
    def index(self) -> int:
        """Which slot of the row this is."""
        return self._index

    @property
    def saveable(self) -> bool:
        """Whether this is a saved slot, which a click may write to."""
        return self._saveable

    def set_color(self, color: QColor | None) -> None:
        self._color = QColor(color) if color is not None else None
        self.setToolTip(self._hint())
        self.setAccessibleDescription(self._hint())
        self.update()

    def _hint(self) -> str:
        """What a click and a right-click do here, in words, for the tooltip and the
        accessible description."""
        if self._color is None:
            if self._saveable:
                return "Empty slot — click to save the colour above here"
            return "Empty slot — colours you use appear here"
        value = _hex_text(self._color)
        if self._saveable:
            return f"{value} — click to use it, right-click to replace it"
        return f"{value} — click to use it"

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        inner = self.rect().adjusted(1, 1, -2, -2)
        if self._color is None:
            painter.setPen(QPen(current_theme().border, 1, Qt.PenStyle.DashLine))
            painter.drawRect(inner)
        else:
            if self._color.alpha() < 255:
                _draw_checkerboard(painter, inner)
            painter.fillRect(inner, self._color)
            painter.setPen(current_theme().border)
            painter.drawRect(inner)
        painter.end()

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        if self._saveable:
            self.save_requested.emit(self._index)
        elif event is not None:
            event.ignore()


class ColorPopover(QWidget):
    """The picker popover (PRD 11.1); closes on a click outside it.

    Signals
    -------
    color_changed(QColor)
        Every change, for live preview.
    eyedropper_requested()
        The eyedropper button.
    closed()
        The popover hid; the swatch commits the colour to the recent list.
    """

    color_changed = pyqtSignal(QColor)
    eyedropper_requested = pyqtSignal()
    closed = pyqtSignal()

    def __init__(
        self,
        color: QColor,
        *,
        allow_transparent: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self._settings = AppSettings()
        self._color = QColor(color).toRgb()
        self._updating = False
        self.setAccessibleName("Color picker")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self._square = _SaturationValueSquare()
        self._square.changed.connect(self._on_square_changed)
        layout.addWidget(self._square)

        self._hue_bar = _GradientBar(359, "Hue")
        self._hue_bar.set_stops(
            [QColor.fromHsv(h, 255, 255) for h in range(0, 360, 60)]
            + [QColor.fromHsv(359, 255, 255)]
        )
        self._hue_bar.changed.connect(self._on_hue_changed)
        layout.addWidget(self._hue_bar)

        self._alpha_bar = _GradientBar(100, "Opacity")
        self._alpha_bar.changed.connect(self._on_alpha_changed)
        layout.addWidget(self._alpha_bar)

        inputs = QGridLayout()
        inputs.setContentsMargins(0, 0, 0, 0)
        inputs.setHorizontalSpacing(4)
        self._hex_edit = QLineEdit()
        self._hex_edit.setMaxLength(9)
        self._hex_edit.setAccessibleName("Hex")
        self._hex_edit.editingFinished.connect(self._on_hex_edited)
        inputs.addWidget(QLabel("Hex"), 0, 0)
        inputs.addWidget(self._hex_edit, 0, 1, 1, 5)
        self._rgb_spins: list[QSpinBox] = []
        for i, name in enumerate(("R", "G", "B")):
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.setAccessibleName({"R": "Red", "G": "Green", "B": "Blue"}[name])
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._on_rgb_changed)
            inputs.addWidget(QLabel(name), 1, i * 2)
            inputs.addWidget(spin, 1, i * 2 + 1)
            self._rgb_spins.append(spin)
        self._hsl_spins: list[QSpinBox] = []
        for i, (name, top) in enumerate((("H", 360), ("S", 100), ("L", 100))):
            spin = QSpinBox()
            spin.setRange(0, top)
            spin.setAccessibleName({"H": "Hue", "S": "Saturation", "L": "Lightness"}[name])
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._on_hsl_changed)
            inputs.addWidget(QLabel(name), 2, i * 2)
            inputs.addWidget(spin, 2, i * 2 + 1)
            self._hsl_spins.append(spin)
        layout.addLayout(inputs)

        self._recent_swatches = self._swatch_row(layout, "Recent", saveable=False)
        self._saved_swatches = self._swatch_row(layout, "Saved", saveable=True)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self._eyedropper_btn = QToolButton()
        self._eyedropper_btn.setToolTip("Eyedropper")
        self._eyedropper_btn.setAccessibleName("Eyedropper")
        self._eyedropper_btn.setIcon(theme_manager().icon("color-picker"))
        self._eyedropper_btn.clicked.connect(self.eyedropper_requested)
        buttons.addWidget(self._eyedropper_btn)
        self._transparent_btn: QPushButton | None = None
        if allow_transparent:
            btn = QPushButton("Transparent")
            btn.setAccessibleName("Transparent")
            btn.clicked.connect(self._on_transparent)
            buttons.addWidget(btn)
            self._transparent_btn = btn
        buttons.addStretch()
        layout.addLayout(buttons)

        self._load_swatches()
        self._sync_controls()

    # --- building ---

    def _swatch_row(self, layout: QVBoxLayout, label: str, *, saveable: bool) -> list[_MiniSwatch]:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        caption = QLabel(label)
        caption.setFixedWidth(44)
        caption.setToolTip(
            "Click a slot to save the colour above; right-click one to replace it"
            if saveable
            else "The colours you have used recently"
        )
        row.addWidget(caption)
        swatches: list[_MiniSwatch] = []
        for i in range(SWATCH_COUNT):
            swatch = _MiniSwatch(i, saveable=saveable)
            swatch.clicked.connect(lambda _checked=False, s=swatch: self._on_swatch_clicked(s))
            if saveable:
                swatch.save_requested.connect(self._on_save_requested)
            row.addWidget(swatch)
            swatches.append(swatch)
        row.addStretch()
        layout.addLayout(row)
        return swatches

    def _load_swatches(self) -> None:
        recent = self._settings.recent_colors()
        for i, swatch in enumerate(self._recent_swatches):
            swatch.set_color(recent[i] if i < len(recent) else None)
        saved = self._settings.saved_colors()
        for i, swatch in enumerate(self._saved_swatches):
            swatch.set_color(saved[i] if i < len(saved) else None)

    # --- state ---

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor, *, emit: bool = True) -> None:
        # Always RGB: QColor equality also compares the colour spec (HSV, HSL, RGB).
        self._color = QColor(color).toRgb()
        self._sync_controls()
        if emit:
            self.color_changed.emit(QColor(self._color))

    def _sync_controls(self) -> None:
        self._updating = True
        try:
            c = self._color
            hue = max(0, c.hsvHue())
            self._square.set_hsv(hue, c.hsvSaturation(), c.value())
            self._hue_bar.set_value(hue)
            self._alpha_bar.set_value(round(c.alphaF() * 100))
            opaque = QColor(c)
            opaque.setAlpha(255)
            transparent = QColor(c)
            transparent.setAlpha(0)
            self._alpha_bar.set_stops([transparent, opaque], checkerboard=True)
            self._hex_edit.setText(_hex_text(c))
            for spin, value in zip(self._rgb_spins, (c.red(), c.green(), c.blue())):
                spin.setValue(value)
            hsl = (
                max(0, c.hslHue()),
                round(c.hslSaturationF() * 100),
                round(c.lightnessF() * 100),
            )
            for spin, value in zip(self._hsl_spins, hsl):
                spin.setValue(value)
        finally:
            self._updating = False

    def _apply(self, color: QColor) -> None:
        if self._updating:
            return
        self.set_color(color)

    # --- control handlers ---

    def _on_square_changed(self, saturation: int, value: int) -> None:
        color = QColor.fromHsv(self._hue_bar.value, saturation, value, self._color.alpha())
        self._apply(color)

    def _on_hue_changed(self, hue: int) -> None:
        c = self._color
        color = QColor.fromHsv(hue, c.hsvSaturation(), c.value(), c.alpha())
        self._apply(color)

    def _on_alpha_changed(self, percent: int) -> None:
        color = QColor(self._color)
        color.setAlphaF(percent / 100)
        self._apply(color)

    def _on_hex_edited(self) -> None:
        if self._updating:
            return
        color = QColor(self._hex_edit.text().strip())
        if color.isValid():
            self._apply(color)
        else:
            self._hex_edit.setText(_hex_text(self._color))

    def _on_rgb_changed(self, _value: int) -> None:
        if self._updating:
            return
        r, g, b = (spin.value() for spin in self._rgb_spins)
        self._apply(QColor(r, g, b, self._color.alpha()))

    def _on_hsl_changed(self, _value: int) -> None:
        if self._updating:
            return
        h, s, lightness = (spin.value() for spin in self._hsl_spins)
        color = QColor.fromHslF(min(h, 359) / 360, s / 100, lightness / 100, self._color.alphaF())
        self._apply(color)

    def _on_transparent(self) -> None:
        self._apply(QColor(0, 0, 0, 0))

    def _on_swatch_clicked(self, swatch: _MiniSwatch) -> None:
        """A filled swatch applies its colour; an empty saved slot takes the current one.

        11.1 gives a saved slot two gestures, a click to apply and a right-click to save,
        and an empty slot has nothing to apply: a click there saves instead, so the row can
        be filled without knowing that right-click is the way (PRD 2.26 row).
        """
        if swatch.color is not None:
            self._apply(QColor(swatch.color))
        elif swatch.saveable:
            self._on_save_requested(swatch.index)

    def _on_save_requested(self, index: int) -> None:
        """Right-click on a saved slot stores the current colour there (PRD 11.1)."""
        self._settings.set_saved_color(index, QColor(self._color))
        self._saved_swatches[index].set_color(self._color)

    # --- lifetime ---

    def hideEvent(self, event: object) -> None:  # noqa: N802
        super().hideEvent(event)  # type: ignore[arg-type]
        self.closed.emit()


class ColorPicker(QWidget):
    """A swatch button that opens :class:`ColorPopover` beside it (PRD 11.1).

    Signals
    -------
    color_changed(QColor)
        Emitted on every change while the popover is open (live preview) and
        when an eyedropper pick lands.
    """

    color_changed = pyqtSignal(QColor)

    _eyedropper_handler: ClassVar[EyedropperHandler | None] = None

    def __init__(
        self,
        color: QColor | None = None,
        parent: QWidget | None = None,
        *,
        allow_transparent: bool = True,
        swatch_size: int = 32,
    ) -> None:
        super().__init__(parent)
        self._color = color if color is not None else QColor("red")
        self._allow_transparent = allow_transparent
        self._popover: ColorPopover | None = None
        self._popover_color_on_open: QColor | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._swatch = _SwatchButton()
        self._swatch.setFixedSize(swatch_size, swatch_size)
        self._swatch.color = self._color
        self._swatch.setAccessibleName("Color swatch")
        self._swatch.clicked.connect(self.open_popover)
        layout.addWidget(self._swatch)

    @classmethod
    def set_eyedropper_handler(cls, handler: EyedropperHandler | None) -> None:
        """The main window installs the handler that routes a pick to the eyedropper tool."""
        cls._eyedropper_handler = handler

    @property
    def allow_transparent(self) -> bool:
        return self._allow_transparent

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    @color.setter
    def color(self, value: QColor) -> None:
        self._color = QColor(value)
        self._swatch.mixed = False
        self._swatch.color = self._color
        if self._popover is not None and self._popover.isVisible():
            self._popover.set_color(self._color, emit=False)

    @property
    def mixed(self) -> bool:
        """True while the swatch shows a mixed selection (PRD 8.6); any colour set clears it."""
        return self._swatch.mixed

    @mixed.setter
    def mixed(self, value: bool) -> None:
        self._swatch.mixed = value

    @property
    def popover(self) -> ColorPopover | None:
        return self._popover

    def open_popover(self) -> None:
        """Open the popover below the swatch, kept on screen."""
        if self._popover is not None and self._popover.isVisible():
            return
        popover = ColorPopover(self._color, allow_transparent=self._allow_transparent, parent=self)
        popover.color_changed.connect(self._on_popover_color)
        popover.eyedropper_requested.connect(self._on_eyedropper_requested)
        popover.closed.connect(self._on_popover_closed)
        popover.adjustSize()
        self._popover = popover
        self._popover_color_on_open = QColor(self._color)
        self._place_popover(popover)
        popover.show()

    def _place_popover(self, popover: QWidget) -> None:
        anchor = self._swatch.mapToGlobal(QPoint(0, self._swatch.height() + 2))
        size: QSize = popover.sizeHint()
        x, y = anchor.x(), anchor.y()
        screen = QApplication.screenAt(anchor)
        if screen is not None:
            available = screen.availableGeometry()
            if x + size.width() > available.right():
                x = max(available.left(), available.right() - size.width())
            if y + size.height() > available.bottom():
                y = max(
                    available.top(), self._swatch.mapToGlobal(QPoint(0, 0)).y() - size.height() - 2
                )
        popover.move(x, y)

    def _on_popover_color(self, color: QColor) -> None:
        self._color = QColor(color).toRgb()
        self._swatch.mixed = False
        self._swatch.color = self._color
        self.color_changed.emit(QColor(self._color))

    def _on_popover_closed(self) -> None:
        opened_with = self._popover_color_on_open
        if opened_with is None or opened_with != self._color:
            AppSettings().push_recent_color(self._color)
        self._popover_color_on_open = None

    def _on_eyedropper_requested(self) -> None:
        """Hide the popover, let the eyedropper pick, then reopen with the pick (Blur PRD 4.6)."""
        popover = self._popover
        if popover is not None:
            popover.hide()
        handler = ColorPicker._eyedropper_handler
        started = handler is not None and handler(self._on_eyedropper_pick)
        if not started:
            check_requirements(self, "Eyedropper", [(False, "an open canvas to pick from")])

    def _on_eyedropper_pick(self, color: QColor) -> None:
        self._on_popover_color(color)
        AppSettings().push_recent_color(color)
        self.open_popover()
