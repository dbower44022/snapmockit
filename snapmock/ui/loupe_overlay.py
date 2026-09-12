"""LoupeOverlay — the Eyedropper's magnified preview (Blur PRD 4.3).

A 120 pixel circular window at 8 times magnification that follows the cursor, with the
centre crosshair, the sampled area's outline, and the sampled colour's swatch and
hexadecimal value beneath it. It is a widget over the canvas view's viewport, not a scene
item and not a pass of the view's foreground (Eyedropper and Blur performance decision 1,
option B): every measurement of 4.3 is in screen pixels and the repositioning rule is a
screen-edge rule, so the arithmetic is the viewport rectangle's, and a widget can never
reach a render of the scene.

The magnified content comes from the Eyedropper's own sampling render, so what the loupe
shows is exactly what a click would sample (decision 2).
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from snapmock.core.theme_manager import current_theme

LOUPE_DIAMETER = 120
"""4.3's circular magnification window, in screen pixels."""

LOUPE_MAGNIFICATION = 8
"""4.3: each canvas pixel is rendered as an 8 by 8 block, whatever the view's zoom."""

LOUPE_CAPTURE_SIDE = LOUPE_DIAMETER // LOUPE_MAGNIFICATION
"""The canvas pixels that fit across the loupe: fifteen, as 4.3's own arithmetic gives."""

LOUPE_CURSOR_OFFSET = 20
"""4.3: the loupe sits this far above and to the right of the cursor."""

LOUPE_BORDER_WIDTH = 2
"""4.3's border, in the accent colour."""

LOUPE_SWATCH_WIDTH = 40
LOUPE_SWATCH_HEIGHT = 24
"""4.3's colour swatch below the circle."""

_SHADOW_MARGIN = 6
"""Room around the circle for the drop shadow."""

_SWATCH_GAP = 6
_TEXT_GAP = 3
_TEXT_HEIGHT = 14
_CHECKER_CELL = 6
_CROSSHAIR_ARM = 7


def _checkerboard(painter: QPainter, rect: QRect) -> None:
    """The transparency pattern 4.3 asks for over transparent canvas, in the theme's own
    checkerboard colours, as the canvas itself draws it."""
    theme = current_theme()
    painter.fillRect(rect, theme.checkerboard_a)
    for y in range(rect.top(), rect.bottom() + 1, _CHECKER_CELL):
        for x in range(rect.left(), rect.right() + 1, _CHECKER_CELL):
            if ((x - rect.left()) // _CHECKER_CELL + (y - rect.top()) // _CHECKER_CELL) % 2:
                painter.fillRect(x, y, _CHECKER_CELL, _CHECKER_CELL, theme.checkerboard_b)


def loupe_size() -> tuple[int, int]:
    """The whole widget's size: the circle with its border and shadow, then the swatch
    and the hexadecimal value beneath it."""
    circle = LOUPE_DIAMETER + 2 * LOUPE_BORDER_WIDTH
    width = circle + 2 * _SHADOW_MARGIN
    height = (
        _SHADOW_MARGIN
        + circle
        + _SWATCH_GAP
        + LOUPE_SWATCH_HEIGHT
        + _TEXT_GAP
        + _TEXT_HEIGHT
        + _SHADOW_MARGIN
    )
    return width, height


def circle_rect() -> QRectF:
    """The magnified circle inside the widget, the border's centre line included."""
    return QRectF(
        _SHADOW_MARGIN + LOUPE_BORDER_WIDTH / 2,
        _SHADOW_MARGIN + LOUPE_BORDER_WIDTH / 2,
        LOUPE_DIAMETER + LOUPE_BORDER_WIDTH,
        LOUPE_DIAMETER + LOUPE_BORDER_WIDTH,
    )


def swatch_rect() -> QRect:
    """4.3's 40 by 24 px colour swatch, centred below the circle."""
    circle = circle_rect()
    swatch = QRect(0, 0, LOUPE_SWATCH_WIDTH, LOUPE_SWATCH_HEIGHT)
    swatch.moveLeft(int(circle.center().x() - LOUPE_SWATCH_WIDTH / 2))
    swatch.moveTop(int(circle.bottom() + _SWATCH_GAP))
    return swatch


def beside_cursor(
    cursor: QPoint, size: tuple[int, int], viewport: QRect, offset: int, *, above: bool
) -> QPoint:
    """The top-left corner of an overlay of *size* beside a cursor at *cursor* inside
    *viewport*, both in the viewport's coordinates.

    The screen-edge rule every overlay over the canvas view's viewport shares, so the
    Eyedropper's loupe (Blur PRD 4.3) and the dimension tooltip (Basic Shape PRD 2.4) are
    one piece of arithmetic rather than two copies of it (Basic Shape shared drawing
    decision 1). The overlay sits *offset* pixels to the right of the cursor and *offset*
    pixels above it (*above*) or below it; it flips to the left of the cursor rather than
    past the right edge, and to the other side vertically rather than past the top or the
    bottom edge, and is clamped to the viewport after either flip, so it is always wholly
    visible.
    """
    width, height = size
    x = cursor.x() + offset
    if x + width > viewport.width():
        x = cursor.x() - offset - width
    if above:
        y = cursor.y() - offset - height
        if y < 0:
            y = cursor.y() + offset
    else:
        y = cursor.y() + offset
        if y + height > viewport.height():
            y = cursor.y() - offset - height
    x = max(0, min(x, max(0, viewport.width() - width)))
    y = max(0, min(y, max(0, viewport.height() - height)))
    return QPoint(x, y)


def loupe_position(cursor: QPoint, viewport: QRect) -> QPoint:
    """The widget's top-left corner for a cursor at *cursor* inside *viewport* (4.3).

    The loupe sits 20 px above and to the right of the cursor, and is repositioned when
    it would leave the viewport, by the rule of :func:`beside_cursor`.
    """
    return beside_cursor(cursor, loupe_size(), viewport, LOUPE_CURSOR_OFFSET, above=True)


class LoupeOverlay(QWidget):
    """The magnified preview, parented to the canvas view's viewport (4.3)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAccessibleName("Eyedropper preview")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._image: QImage | None = None
        self._color = QColor(0, 0, 0, 0)
        self._sample_size = 1
        self.resize(*loupe_size())
        self.hide()
        parent.installEventFilter(self)

    # ---- what it shows ----

    @property
    def sampled_color(self) -> QColor:
        return QColor(self._color)

    @property
    def sampled_image(self) -> QImage | None:
        """The capture the loupe is magnifying: what a click would sample."""
        return self._image

    @property
    def sample_size(self) -> int:
        return self._sample_size

    def show_sample(
        self, cursor: QPoint, image: QImage | None, color: QColor, sample_size: int
    ) -> None:
        """Put the loupe beside *cursor*, in the viewport's coordinates, showing *image*."""
        parent = self.parentWidget()
        if parent is None:
            return
        self._image = image
        self._color = QColor(color)
        self._sample_size = sample_size
        self.move(loupe_position(cursor, parent.rect()))
        self.raise_()
        self.show()
        self.update()

    def eventFilter(self, source: object, event: object) -> bool:  # noqa: N802
        """Hide when the pointer leaves the viewport: nothing is under the loupe then."""
        from PyQt6.QtCore import QEvent

        if (
            isinstance(event, QEvent)
            and event.type() == QEvent.Type.Leave
            and source is self.parentWidget()
        ):
            self.hide()
        return False

    # ---- painting ----

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        circle = circle_rect()
        self._paint_shadow(painter, circle)
        self._paint_magnified(painter, circle)
        self._paint_border(painter, circle)
        self._paint_swatch(painter)
        painter.end()

    def _paint_shadow(self, painter: QPainter, circle: QRectF) -> None:
        """4.3's subtle drop shadow, painted as a radial fade under the circle."""
        shadow = circle.adjusted(
            -_SHADOW_MARGIN, -_SHADOW_MARGIN + 2, _SHADOW_MARGIN, _SHADOW_MARGIN + 2
        )
        gradient = QRadialGradient(shadow.center(), shadow.width() / 2)
        inner = QColor(0, 0, 0, 90)
        gradient.setColorAt(0.0, inner)
        gradient.setColorAt(circle.width() / shadow.width(), inner)
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(shadow)

    def _paint_magnified(self, painter: QPainter, circle: QRectF) -> None:
        """The capture at 8 times its size with nearest-neighbour scaling, so the pixel
        grid shows (4.3), the checkerboard behind it where the canvas is transparent."""
        inner = circle.adjusted(
            LOUPE_BORDER_WIDTH / 2,
            LOUPE_BORDER_WIDTH / 2,
            -LOUPE_BORDER_WIDTH / 2,
            -LOUPE_BORDER_WIDTH / 2,
        )
        path = QPainterPath()
        path.addEllipse(inner)
        painter.save()
        painter.setClipPath(path)
        _checkerboard(painter, inner.toAlignedRect())
        if self._image is not None and not self._image.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            side = LOUPE_CAPTURE_SIDE * LOUPE_MAGNIFICATION
            target = QRectF(0, 0, side, side)
            target.moveCenter(inner.center())
            painter.drawImage(target, self._image)
        self._paint_sample_outline(painter, inner)
        self._paint_crosshair(painter, inner)
        painter.restore()

    def _paint_sample_outline(self, painter: QPainter, inner: QRectF) -> None:
        """4.3: the sampled area is outlined with a small coloured square."""
        side = self._sample_size * LOUPE_MAGNIFICATION
        area = QRectF(0, 0, side, side)
        area.moveCenter(inner.center())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(current_theme().accent, 1))
        painter.drawRect(area)

    def _paint_crosshair(self, painter: QPainter, inner: QRectF) -> None:
        """4.3's thin crosshair at the exact sample point."""
        centre = inner.center()
        painter.setPen(QPen(QColor(0, 0, 0, 160), 1))
        painter.drawLine(
            int(centre.x() - _CROSSHAIR_ARM),
            int(centre.y()),
            int(centre.x() + _CROSSHAIR_ARM),
            int(centre.y()),
        )
        painter.drawLine(
            int(centre.x()),
            int(centre.y() - _CROSSHAIR_ARM),
            int(centre.x()),
            int(centre.y() + _CROSSHAIR_ARM),
        )

    def _paint_border(self, painter: QPainter, circle: QRectF) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(current_theme().accent, LOUPE_BORDER_WIDTH))
        painter.drawEllipse(circle)

    def _paint_swatch(self, painter: QPainter) -> None:
        """The 40 by 24 px swatch and the hexadecimal value beneath the circle (4.3)."""
        swatch = swatch_rect()
        if self._color.alpha() == 0:
            _checkerboard(painter, swatch)
        else:
            painter.fillRect(swatch, self._color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(current_theme().border, 1))
        painter.drawRect(swatch)

        font = QFont(painter.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.0))
        painter.setFont(font)
        painter.setPen(QPen(current_theme().text_primary, 1))
        text = QRect(0, swatch.bottom() + _TEXT_GAP, self.width(), _TEXT_HEIGHT)
        painter.drawText(text, int(Qt.AlignmentFlag.AlignCenter), self.value_text())

    def value_text(self) -> str:
        """The hexadecimal value under the swatch, or "transparent" (4.3)."""
        if self._color.alpha() == 0:
            return "transparent"
        return self._color.name().upper()
