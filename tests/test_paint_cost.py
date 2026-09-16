"""Paint cost during a drag (end-to-end pass finding 8; Technical Architecture PRD 8).

Two caches keep a repaint cheap while an item is dragged: the shadow's blurred image is
reused while the path it was made from is unchanged, compared natively rather than by a
Python walk over the path's elements; and the grid is drawn once into an image for the
painted area and blitted while the view of the canvas is unchanged.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.config.constants import BorderStyle
from snapmock.core.scene import SnapScene
from snapmock.core.view import SnapView
from snapmock.items.rectangle_item import RectangleItem


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    return SnapScene(width=800, height=600)


def _paint(item: RectangleItem, image: QImage) -> None:
    painter = QPainter(image)
    painter.translate(40, 40)
    item.paint(painter, None, None)
    painter.end()


def test_the_shadow_image_is_reused_while_the_path_is_unchanged(qapp: QApplication) -> None:
    item = RectangleItem(QRectF(0, 0, 200, 120))
    item.shadow_enabled = True
    item.stroke_style = BorderStyle.DASHED  # a stroked outline of many elements
    item.corner_radius = 12
    image = QImage(400, 300, QImage.Format.Format_ARGB32_Premultiplied)
    _paint(item, image)
    first = item._shadow_cache_image  # noqa: SLF001
    assert first is not None
    _paint(item, image)
    assert item._shadow_cache_image is first  # noqa: SLF001
    # a change of the outline makes a new image; the cache compares the path itself
    item.rect = QRectF(0, 0, 220, 120)
    _paint(item, image)
    assert item._shadow_cache_image is not first  # noqa: SLF001
    assert item._shadow_cache_path is not None  # noqa: SLF001
    assert item._shadow_cache_path == item.shadow_path(item.outline())  # noqa: SLF001


def _view(qtbot: QtBot, scene: SnapScene) -> SnapView:
    view = SnapView(scene)
    view.resize(600, 400)
    qtbot.addWidget(view)
    view.show()
    view.set_grid_visible(True)
    view.set_grid_size(20)
    view.set_zoom(300)
    return view


def _draw_grid(view: SnapView, scene: SnapScene) -> QImage:
    image = QImage(600, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setTransform(view.viewportTransform())
    view._draw_grid(painter, view.mapToScene(view.viewport().rect()).boundingRect(), scene)  # noqa: SLF001
    painter.end()
    return image


def test_the_grid_image_is_reused_while_the_view_is_unchanged(
    qtbot: QtBot, scene: SnapScene
) -> None:
    view = _view(qtbot, scene)
    first_image = _draw_grid(view, scene)
    first = view._grid_cache  # noqa: SLF001
    assert first is not None
    second_image = _draw_grid(view, scene)
    assert view._grid_cache is first  # noqa: SLF001
    assert second_image == first_image
    # the grid was drawn: some pixels carry a line
    painted = sum(
        1
        for y in range(0, 400, 3)
        for x in range(0, 600, 3)
        if first_image.pixelColor(x, y).alpha()
    )
    assert painted > 100
    # a scroll, a zoom, or a grid size change draws afresh
    bar = view.horizontalScrollBar()
    assert bar is not None
    bar.setValue(bar.value() + 37)
    _draw_grid(view, scene)
    assert view._grid_cache is not first  # noqa: SLF001
    second = view._grid_cache  # noqa: SLF001
    view.set_grid_size(10)
    _draw_grid(view, scene)
    assert view._grid_cache is not second  # noqa: SLF001


def test_the_cached_grid_matches_a_direct_drawing(qtbot: QtBot, scene: SnapScene) -> None:
    view = _view(qtbot, scene)
    cached = _draw_grid(view, scene)
    direct = QImage(600, 400, QImage.Format.Format_ARGB32_Premultiplied)
    direct.fill(0)
    painter = QPainter(direct)
    painter.setTransform(view.viewportTransform())
    minor_pen, major_pen = view._grid_pens()  # noqa: SLF001
    clip = scene.canvas_rect.intersected(view.mapToScene(view.viewport().rect()).boundingRect())
    view._paint_grid_lines(painter, clip, scene.canvas_rect, 20, True, minor_pen, major_pen)  # noqa: SLF001
    painter.end()
    assert cached == direct
