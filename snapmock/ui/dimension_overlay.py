"""DimensionOverlay — the shape tools' drawing feedback beside the cursor (Basic Shape PRD 2.4).

A dimension tooltip following the cursor at a 15 by 15 pixel offset with the shape's own
measurements, the constrain icon beside the measurements while Shift is held, and the
crosshair marker at the origin point while the centre-draw modifier is held. It is a
widget over the canvas view's viewport, as the Eyedropper's preview loupe is, and not a
scene item or a pass of the view's foreground (Basic Shape shared drawing decision 1,
option A): every measurement of 2.4 is in screen pixels and the repositioning is a
screen-edge rule, so the arithmetic is the viewport rectangle's, and a widget can never
reach a render of the scene.

The tooltip and the marker cannot be one widget, since the one follows the cursor and the
other stays on the origin point, so the marker is a second small widget the overlay owns
(notes Section 9). Each tool computes its measurements once (``BaseTool.
drawing_measurement``); the tooltip shows them here and the status bar hint is built from
the same values, so the two can never disagree.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QWidget

from snapmock.core.theme_manager import current_theme
from snapmock.ui.loupe_overlay import beside_cursor

TOOLTIP_CURSOR_OFFSET = 15
"""2.4: the tooltip sits 15 by 15 pixels from the cursor."""

CONSTRAIN_ICON_SIZE = 12
"""2.4's small constrain icon beside the measurements, in screen pixels."""

CENTRE_MARKER_SIZE = 15
"""2.4's small crosshair marker at the origin point, in screen pixels."""

_PADDING_X = 6
_PADDING_Y = 3
_ICON_GAP = 5
_MARKER_ARM = 6


def length_angle_text(dx: float, dy: float) -> str:
    """``L: 245px ∠ 32.5°`` (3.2, 4.2, 7.2): a length in pixels and the angle from the
    horizontal, counter-clockwise positive as the screen shows it."""
    length = math.hypot(dx, dy)
    # Rounded first, so a leftward line reads 180° and not -180°, and a level one never
    # reads -0.0° (adding 0.0 turns a negative zero positive)
    angle = round(-math.degrees(math.atan2(dy, dx)), 1) + 0.0 if length else 0.0
    if angle <= -180.0:
        angle += 360.0
    return f"L: {length:.0f}px ∠ {angle:.1f}°"


def size_text(width: float, height: float) -> str:
    """``W: 320 H: 240`` (5.2, 6.2): a bounding box in pixels."""
    return f"W: {abs(width):.0f} H: {abs(height):.0f}"


def diameter_text(diameter: float) -> str:
    """``D: 320`` (6.2): a circle drawn with Shift held."""
    return f"D: {abs(diameter):.0f}"


def tooltip_position(cursor: QPoint, size: tuple[int, int], viewport: QRect) -> QPoint:
    """The tooltip's top-left corner for a cursor at *cursor* inside *viewport* (2.4).

    15 pixels right of and below the cursor, flipped to the left or above rather than past
    an edge, by the rule the loupe shares (:func:`beside_cursor`).
    """
    return beside_cursor(cursor, size, viewport, TOOLTIP_CURSOR_OFFSET, above=False)


def marker_position(origin: QPoint) -> QPoint:
    """The centre marker's top-left corner, so its crosshair is on *origin*."""
    half = CENTRE_MARKER_SIZE // 2
    return QPoint(origin.x() - half, origin.y() - half)


class CentreMarker(QWidget):
    """2.4's small crosshair at the origin point while the centre-draw modifier is held."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAccessibleName("Center-draw origin")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(CENTRE_MARKER_SIZE, CENTRE_MARKER_SIZE)
        self.hide()

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        centre = CENTRE_MARKER_SIZE // 2
        # A light halo under the accent-coloured cross, so it reads over any screenshot
        for color, width in ((QColor(255, 255, 255, 200), 3), (current_theme().accent, 1)):
            painter.setPen(QPen(color, width))
            painter.drawLine(centre - _MARKER_ARM, centre, centre + _MARKER_ARM, centre)
            painter.drawLine(centre, centre - _MARKER_ARM, centre, centre + _MARKER_ARM)
        painter.end()


class DimensionOverlay(QWidget):
    """The dimension tooltip with its constrain icon, parented to the canvas view's viewport
    (2.4), and the centre marker it owns."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAccessibleName("Drawing dimensions")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._text = ""
        self._constrained = False
        self._marker = CentreMarker(parent)
        self.hide()
        parent.installEventFilter(self)

    # ---- what it shows ----

    @property
    def text(self) -> str:
        return self._text

    @property
    def constrained(self) -> bool:
        """Whether the constrain icon is shown beside the measurements (2.4)."""
        return self._constrained

    @property
    def centre_marker(self) -> CentreMarker:
        return self._marker

    def tooltip_size(self, text: str, constrained: bool) -> tuple[int, int]:
        """The tooltip's size for *text*, with room for the icon when *constrained*."""
        metrics = QFontMetrics(self.font())
        width = metrics.horizontalAdvance(text) + 2 * _PADDING_X
        height = max(metrics.height(), CONSTRAIN_ICON_SIZE) + 2 * _PADDING_Y
        if constrained:
            width += _ICON_GAP + CONSTRAIN_ICON_SIZE
        return width, height

    def show_measurement(
        self, cursor: QPoint, text: str, constrained: bool, centre: QPoint | None
    ) -> None:
        """Show *text* beside *cursor* and the marker on *centre*, both in the viewport's
        coordinates; *centre* None hides the marker."""
        parent = self.parentWidget()
        if parent is None:
            return
        size = self.tooltip_size(text, constrained)
        if text != self._text or constrained != self._constrained:
            self._text = text
            self._constrained = constrained
            self.update()
        if (self.width(), self.height()) != size:
            self.resize(*size)
        self.move(tooltip_position(cursor, size, parent.rect()))
        if self.isHidden():
            self.raise_()
            self.show()
        if centre is None:
            self._marker.hide()
        else:
            self._marker.move(marker_position(centre))
            if self._marker.isHidden():
                self._marker.raise_()
                self._marker.show()

    def hide_feedback(self) -> None:
        """Hide the tooltip and the marker: the drawing operation is over."""
        self.hide()
        self._marker.hide()

    def eventFilter(self, source: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        """Hide when the pointer leaves the viewport, as the loupe does."""
        if (
            event is not None
            and event.type() == QEvent.Type.Leave
            and source is self.parentWidget()
        ):
            self.hide_feedback()
        return False

    # ---- painting ----

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        theme = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bubble = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setPen(QPen(theme.border, 1))
        painter.setBrush(theme.tooltip_bg)
        painter.drawRoundedRect(bubble, 3.0, 3.0)
        metrics = QFontMetrics(self.font())
        text_width = metrics.horizontalAdvance(self._text)
        painter.setPen(QPen(theme.text_primary, 1))
        painter.drawText(
            QRect(_PADDING_X, 0, text_width + 1, self.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self._text,
        )
        if self._constrained:
            left = _PADDING_X + text_width + _ICON_GAP
            top = (self.height() - CONSTRAIN_ICON_SIZE) / 2
            self._paint_constrain_icon(
                painter, QRectF(left, top, CONSTRAIN_ICON_SIZE, CONSTRAIN_ICON_SIZE)
            )
        painter.end()

    @staticmethod
    def _paint_constrain_icon(painter: QPainter, area: QRectF) -> None:
        """A small padlock in the accent colour: the proportions or the angle are held."""
        accent = current_theme().accent
        body = QRectF(
            area.left() + 1,
            area.top() + area.height() * 0.45,
            area.width() - 2,
            area.height() * 0.55,
        )
        shackle = QRectF(
            area.left() + area.width() * 0.25,
            area.top() + 1,
            area.width() * 0.5,
            area.height() * 0.7,
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(accent, 1.5))
        painter.drawArc(shackle, 0, 180 * 16)
        painter.drawLine(
            QPointF(shackle.left(), shackle.center().y()), QPointF(shackle.left(), body.top())
        )
        painter.drawLine(
            QPointF(shackle.right(), shackle.center().y()), QPointF(shackle.right(), body.top())
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(body, 1.5, 1.5)


def dimension_overlay(viewport: QWidget) -> DimensionOverlay:
    """The viewport's one dimension overlay, created the first time a tool draws over it.

    Every drawing tool shares it, so nothing on the tool or the view holds it and a tool
    switch cannot leave a second one behind.
    """
    found = viewport.findChild(DimensionOverlay, options=Qt.FindChildOption.FindDirectChildrenOnly)
    if isinstance(found, DimensionOverlay):
        return found
    return DimensionOverlay(viewport)


def existing_dimension_overlay(viewport: QWidget) -> DimensionOverlay | None:
    """The viewport's dimension overlay if a tool has drawn over it, else None."""
    found = viewport.findChild(DimensionOverlay, options=Qt.FindChildOption.FindDirectChildrenOnly)
    return found if isinstance(found, DimensionOverlay) else None
