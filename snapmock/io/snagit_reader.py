"""SnagitReader — load Snagit .snagx ZIP archives into a SnapScene."""

from __future__ import annotations

import base64
import json
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap

from snapmock.config.constants import HeadStyle, VerticalAlign
from snapmock.core.layer import LAYER_TYPE_BACKGROUND
from snapmock.core.scene import SnapScene
from snapmock.io.rtf_utils import extract_font_from_rtf, extract_text_from_rtf
from snapmock.items.arrow_item import ArrowItem
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.callout_item import CalloutItem
from snapmock.items.line_item import LineItem
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.items.text_item import TextItem

log = logging.getLogger(__name__)


def load_snagx(path: Path) -> SnapScene:
    """Load a Snagit ``.snagx`` file and return a fully-populated *SnapScene*."""
    with zipfile.ZipFile(path, "r") as zf:
        index = json.loads(zf.read("index.json"))
        pages = index.get("Pages", [])
        if not pages:
            raise ValueError("snagx index.json contains no pages")

        page_filename = pages[0]
        page = json.loads(zf.read(page_filename))

        width = int(page.get("CaptureCanvasWidth", 1920))
        height = int(page.get("CaptureCanvasHeight", 1080))

        # A Snagit border is painted into the background bitmap, with the pre-effect
        # original kept beside it; recover it as an editable border where we can (10.8).
        border = _recover_border(zf, page_filename, page)
        if border is not None:
            width, height = border.canvas_width, border.canvas_height

        scene = SnapScene(width=width, height=height)
        if border is not None:
            scene.set_border_width(border.width)
            scene.set_border_color(border.color)

        bg_color_str = page.get("CaptureBackgroundColor", "#00000000")
        bg_color = QColor(bg_color_str)
        if bg_color.alpha() > 0:
            scene.set_background_color(bg_color)

        # -- Background layer --
        bg_layer = scene.layer_manager.active_layer
        if bg_layer is None:
            bg_layer = scene.layer_manager.add_layer("Background")
        else:
            scene.layer_manager.rename_layer(bg_layer.layer_id, "Background")
        scene.layer_manager.set_layer_type(bg_layer.layer_id, LAYER_TYPE_BACKGROUND)

        bg_image_name = page.get("CaptureBackgroundImage", "")
        if border is not None:
            bg_image_name = border.backup_png
        if bg_image_name and bg_image_name in zf.namelist():
            png_data = zf.read(bg_image_name)
            img = QImage()
            img.loadFromData(png_data)
            if not img.isNull():
                bg_item = RasterRegionItem(pixmap=QPixmap.fromImage(img))
                bg_item.layer_id = bg_layer.layer_id
                bg_layer.item_ids.append(bg_item.item_id)
                bg_item.setZValue(bg_layer.z_base)
                # Position background at CaptureBackgroundLocation
                bg_loc = page.get("CaptureBackgroundLocation", "0,0")
                bx, by = _parse_point(bg_loc)
                bg_item.setPos(bx, by)
                scene.addItem(bg_item)

        # -- Annotations layer --
        ann_layer = scene.layer_manager.add_layer("Annotations")
        scene.layer_manager.set_active(ann_layer.layer_id)

        z_offset = 1
        for obj in page.get("CaptureObjects", []):
            item = _convert_object(obj, zf)
            if item is None:
                continue
            item.layer_id = ann_layer.layer_id
            ann_layer.item_ids.append(item.item_id)
            item.setZValue(ann_layer.z_base + z_offset)
            z_offset += 1
            if border is not None:
                # The page's coordinates include the border; the canvas no longer does
                item.moveBy(-border.width, -border.width)
            scene.addItem(item)

        # Store page-level metadata on the scene for round-trip
        scene._snagit_metadata = {  # type: ignore[attr-defined]
            "page": page,
            "index": index,
        }
        try:
            meta_raw = zf.read("metadata.json")
            scene._snagit_metadata["metadata"] = json.loads(meta_raw)  # type: ignore[attr-defined]
        except KeyError:
            pass

    scene.command_stack.clear()
    scene.command_stack.mark_clean()
    return scene


# ---- Snagit's Border effect (Navigation & Raster Operations PRD 10.8) ----


@dataclass(frozen=True)
class _RecoveredBorder:
    """A Snagit border read back out of a flattened page and its backup pair."""

    width: int
    color: QColor
    canvas_width: int
    canvas_height: int
    backup_png: str


def _recover_border(
    zf: zipfile.ZipFile, page_filename: str, page: dict[str, Any]
) -> _RecoveredBorder | None:
    """The editable border behind a Snagit page, or None to load the page flattened.

    Snagit keeps the pre-effect original beside the result as ``{GUID}.backup.png`` and
    ``{GUID}.backup.json``. A border is recovered only when the page canvas is larger
    than the backup canvas by the same positive, even amount in both dimensions and the
    ring between the two is one uniform colour; anything else — a backup pair left by
    another effect, a ring that differs from side to side — loads as it always has.
    """
    stem = page_filename[: -len(".json")] if page_filename.endswith(".json") else page_filename
    backup_json = f"{stem}.backup.json"
    backup_png = f"{stem}.backup.png"
    names = set(zf.namelist())
    if backup_json not in names or backup_png not in names:
        return None
    page_png = page.get("CaptureBackgroundImage", "")
    if page_png not in names:
        return None

    try:
        backup = json.loads(zf.read(backup_json))
    except (KeyError, ValueError):  # pragma: no cover - a malformed backup
        return None

    page_w = int(page.get("CaptureCanvasWidth", 0))
    page_h = int(page.get("CaptureCanvasHeight", 0))
    back_w = int(backup.get("CaptureCanvasWidth", 0))
    back_h = int(backup.get("CaptureCanvasHeight", 0))
    if min(back_w, back_h) <= 0:
        return None
    dw = page_w - back_w
    dh = page_h - back_h
    if dw != dh or dw <= 0 or dw % 2 != 0:
        return None
    border_width = dw // 2

    image = QImage()
    image.loadFromData(zf.read(page_png))
    if image.isNull() or image.width() != page_w or image.height() != page_h:
        return None
    color = _uniform_ring_color(image, border_width)
    if color is None:
        return None
    log.info("Recovered a %d px Snagit border from %s", border_width, page_filename)
    return _RecoveredBorder(border_width, color, back_w, back_h, backup_png)


def _uniform_ring_color(image: QImage, width: int) -> QColor | None:
    """The single colour of the *width* px ring inside *image*'s edges, else None."""
    if width <= 0 or image.width() <= 2 * width or image.height() <= 2 * width:
        return None
    converted = image.convertToFormat(QImage.Format.Format_ARGB32)
    pointer = converted.bits()
    if pointer is None:  # pragma: no cover - a null image is caught above
        return None
    pointer.setsize(converted.sizeInBytes())
    height, stride = converted.height(), converted.bytesPerLine()
    raw = np.frombuffer(pointer.asstring(converted.sizeInBytes()), dtype=np.uint8)
    pixels = raw.reshape(height, stride)[:, : converted.width() * 4].reshape(
        height, converted.width(), 4
    )
    bands = (
        pixels[:width, :, :],
        pixels[-width:, :, :],
        pixels[width:-width, :width, :],
        pixels[width:-width, -width:, :],
    )
    first = pixels[0, 0]
    for band in bands:
        if not np.array_equal(band, np.broadcast_to(first, band.shape)):
            return None
    blue, green, red, alpha = (int(v) for v in first)  # ARGB32 is BGRA in memory
    return QColor(red, green, blue, alpha)


# ---- dispatch ----


def _convert_object(obj: dict[str, Any], zf: zipfile.ZipFile) -> SnapGraphicsItem | None:
    """Dispatch a Snagit CaptureObject to the appropriate converter."""
    tool_mode = obj.get("ToolMode", "")
    item: SnapGraphicsItem | None = None
    try:
        if tool_mode == "Arrow":
            item = _convert_arrow(obj)
        elif tool_mode == "Line":
            item = _convert_line(obj)
        elif tool_mode == "Shape":
            item = _convert_shape(obj)
        elif tool_mode == "Highlight":
            item = _convert_highlight(obj)
        elif tool_mode == "Callout":
            item = _convert_callout(obj)
        elif tool_mode == "Text":
            item = _convert_text(obj)
        elif tool_mode == "Image":
            item = _convert_image(obj, zf)
        elif tool_mode == "Stamp":
            item = _convert_stamp(obj, zf)
        else:
            log.warning("Unsupported Snagit ToolMode %r — skipping", tool_mode)
            return None
    except Exception:
        log.exception("Failed to convert Snagit object %r", obj.get("ObjectID", "?"))
        return None

    if item is not None:
        # Stash raw Snagit data for round-trip
        item._snagit_data = obj  # type: ignore[union-attr]
        # Apply shared opacity
        opacity = obj.get("Opacity", 100)
        item.setOpacity(opacity / 100.0)
    return item


# ---- converters ----


def _convert_arrow(obj: dict[str, Any]) -> ArrowItem:
    points = obj.get("PointsArray", [])
    p1 = _parse_point(points[0]) if len(points) > 0 else (0.0, 0.0)
    p2 = _parse_point(points[1]) if len(points) > 1 else (100.0, 0.0)
    item = ArrowItem(line=QLineF(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1])))
    item._stroke_color = QColor(obj.get("ForegroundColor", "#FFFF0000"))
    item._stroke_width = float(obj.get("StrokeWidth", 2))
    # Snagit's EquilateralArrow is a filled head; the item's own default is Open.
    item.head_style = HeadStyle.FILLED
    return item


def _convert_line(obj: dict[str, Any]) -> LineItem:
    points = obj.get("PointsArray", [])
    p1 = _parse_point(points[0]) if len(points) > 0 else (0.0, 0.0)
    p2 = _parse_point(points[1]) if len(points) > 1 else (100.0, 0.0)
    item = LineItem(line=QLineF(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1])))
    item._stroke_color = QColor(obj.get("ForegroundColor", "#FFFF0000"))
    item._stroke_width = float(obj.get("StrokeWidth", 2))
    return item


def _convert_shape(obj: dict[str, Any]) -> RectangleItem:
    points = obj.get("PointsArray", [])
    p1 = _parse_point(points[0]) if len(points) > 0 else (0.0, 0.0)
    p2 = _parse_point(points[1]) if len(points) > 1 else (100.0, 60.0)
    x, y = min(p1[0], p2[0]), min(p1[1], p2[1])
    w = abs(p2[0] - p1[0])
    h = abs(p2[1] - p1[1])

    corner_radius = 0.0
    tool_shape = obj.get("ToolShape", "Rectangle")
    if tool_shape == "RoundedRectangle":
        ratio = obj.get("CornerRadiusRatio", 0.25)
        corner_radius = ratio * min(w, h)

    item = RectangleItem(corner_radius=corner_radius)
    # Set position via setPos and use a local-origin rect
    item.setPos(x, y)
    item._rect = QRectF(0, 0, w, h)

    item._stroke_color = QColor(obj.get("ForegroundColor", "#FFFF0000"))
    item._stroke_width = float(obj.get("StrokeWidth", 2))
    item._fill_color = QColor(obj.get("BackgroundColor", "#00000000"))
    item.setRotation(float(obj.get("RotationAngle", 0)))
    return item


def _convert_highlight(obj: dict[str, Any]) -> RectangleItem:
    points = obj.get("PointsArray", [])
    p1 = _parse_point(points[0]) if len(points) > 0 else (0.0, 0.0)
    p2 = _parse_point(points[1]) if len(points) > 1 else (100.0, 30.0)
    x, y = min(p1[0], p2[0]), min(p1[1], p2[1])
    w = abs(p2[0] - p1[0])
    h = abs(p2[1] - p1[1])

    item = RectangleItem()
    item.setPos(x, y)
    item._rect = QRectF(0, 0, w, h)
    # Highlight: semi-transparent fill, no stroke
    item._fill_color = QColor(obj.get("BackgroundColor", "#FFF7AC08"))
    item._stroke_color = QColor(0, 0, 0, 0)
    item._stroke_width = 0.0
    # Tag as highlight for round-trip
    item._snagit_highlight = True  # type: ignore[attr-defined]
    return item


def _convert_callout(obj: dict[str, Any]) -> CalloutItem:
    points = obj.get("PointsArray", [])
    p1 = _parse_point(points[0]) if len(points) > 0 else (0.0, 0.0)
    p2 = _parse_point(points[1]) if len(points) > 1 else (150.0, 60.0)
    x, y = min(p1[0], p2[0]), min(p1[1], p2[1])
    w = abs(p2[0] - p1[0])
    h = abs(p2[1] - p1[1])

    # Tail
    tails = obj.get("CalloutTails", [])
    if tails:
        tx, ty = _parse_point(tails[0])
        tail_tip = QPointF(tx - x, ty - y)  # Convert to local coords
    else:
        tail_tip = QPointF(w / 2, h + 30)

    # Text from RTF
    text = "Callout"
    font_family = "Sans Serif"
    font_size = 14
    text_color = QColor(0, 0, 0)
    rtf = obj.get("RTFEncodedText", "")
    if rtf:
        text = extract_text_from_rtf(rtf)
        font_family, font_size, text_color = extract_font_from_rtf(rtf)

    item = CalloutItem(
        text=text,
        rect=QRectF(0, 0, w, h),
        tail_tip=tail_tip,
    )
    item.setPos(x, y)
    item.font = QFont(font_family, font_size)
    item.text_color = text_color
    item._bg_color = QColor(obj.get("BackgroundColor", "#FFFFFFFF"))
    item._border_color = QColor(obj.get("ForegroundColor", "#FFFC4242"))
    item._border_width = float(obj.get("StrokeWidth", 2))
    item._padding = float(obj.get("ToolPadding", 4))
    valign_map = {
        "Top": VerticalAlign.TOP,
        "Center": VerticalAlign.CENTER,
        "Bottom": VerticalAlign.BOTTOM,
    }
    item._vertical_align = valign_map.get(
        obj.get("ToolVerticalAlign", "Center"), VerticalAlign.CENTER
    )
    halign_map = {
        "Left": Qt.AlignmentFlag.AlignLeft,
        "Center": Qt.AlignmentFlag.AlignCenter,
        "Right": Qt.AlignmentFlag.AlignRight,
    }
    ha = halign_map.get(obj.get("ToolHorizontalAlign", "Center"))
    if ha is not None:
        item.set_alignment(ha)
    return item


def _convert_text(obj: dict[str, Any]) -> TextItem:
    points = obj.get("PointsArray", [])
    p1 = _parse_point(points[0]) if len(points) > 0 else (0.0, 0.0)
    p2 = _parse_point(points[1]) if len(points) > 1 else (200.0, 30.0)
    x, y = min(p1[0], p2[0]), min(p1[1], p2[1])
    w = abs(p2[0] - p1[0])

    text = "Text"
    font_family = "Sans Serif"
    font_size = 14
    text_color = QColor(0, 0, 0)
    rtf = obj.get("RTFEncodedText", "")
    if rtf:
        text = extract_text_from_rtf(rtf)
        font_family, font_size, text_color = extract_font_from_rtf(rtf)

    item = TextItem(text=text, pos_x=x, pos_y=y)
    item.font = QFont(font_family, font_size)
    item.text_color = text_color
    item._width = max(w, 20.0)

    # Frame properties from Snagit data
    item._bg_color = QColor(obj.get("BackgroundColor", "#00000000"))
    item._border_color = QColor(obj.get("ForegroundColor", "#00000000"))
    item._border_width = float(obj.get("StrokeWidth", 0))
    item._padding = float(obj.get("ToolPadding", 4))

    # Vertical alignment
    valign_map = {
        "Top": VerticalAlign.TOP,
        "Center": VerticalAlign.CENTER,
        "Bottom": VerticalAlign.BOTTOM,
    }
    va_key = obj.get("ToolVerticalAlign", "Top")
    item._vertical_align = valign_map.get(va_key, VerticalAlign.TOP)

    halign_map = {
        "Left": Qt.AlignmentFlag.AlignLeft,
        "Center": Qt.AlignmentFlag.AlignCenter,
        "Right": Qt.AlignmentFlag.AlignRight,
    }
    ha = halign_map.get(obj.get("ToolHorizontalAlign", "Left"))
    if ha is not None:
        item.set_alignment(ha)

    return item


def _convert_image(obj: dict[str, Any], zf: zipfile.ZipFile) -> RasterRegionItem | None:
    image_b64 = obj.get("Image", "")
    if not image_b64:
        return None

    img_data = base64.b64decode(image_b64)
    img = QImage()
    img.loadFromData(img_data)
    if img.isNull():
        log.warning("Could not decode Image data for object %s", obj.get("ObjectID"))
        return None

    points = obj.get("PointsArray", [])
    p1 = _parse_point(points[0]) if len(points) > 0 else (0.0, 0.0)
    p2 = (
        _parse_point(points[1]) if len(points) > 1 else (p1[0] + img.width(), p1[1] + img.height())
    )
    x, y = min(p1[0], p2[0]), min(p1[1], p2[1])
    w = abs(p2[0] - p1[0])
    h = abs(p2[1] - p1[1])

    # Scale image to the bounding box specified by PointsArray
    pixmap = QPixmap.fromImage(img)
    if w > 0 and h > 0 and (pixmap.width() != int(w) or pixmap.height() != int(h)):
        pixmap = pixmap.scaled(int(w), int(h))

    item = RasterRegionItem(pixmap=pixmap)
    item.setPos(x, y)
    item.setRotation(float(obj.get("RotationAngle", 0)))
    return item


def _convert_stamp(obj: dict[str, Any], zf: zipfile.ZipFile) -> RasterRegionItem | None:
    """Convert a Stamp object.

    Stamps may contain PDF data.  We attempt to decode as a raster image
    first; if that fails we skip the stamp.
    """
    image_b64 = obj.get("Image", "")
    if not image_b64:
        return None

    img_data = base64.b64decode(image_b64)
    img = QImage()
    img.loadFromData(img_data)

    if img.isNull():
        # Stamp data is likely a PDF — not directly loadable as QImage.
        log.warning(
            "Stamp %s uses PDF data that cannot be rendered — skipping",
            obj.get("ObjectID"),
        )
        return None

    points = obj.get("PointsArray", [])
    p1 = _parse_point(points[0]) if len(points) > 0 else (0.0, 0.0)
    p2 = (
        _parse_point(points[1]) if len(points) > 1 else (p1[0] + img.width(), p1[1] + img.height())
    )
    x, y = min(p1[0], p2[0]), min(p1[1], p2[1])
    w = abs(p2[0] - p1[0])
    h = abs(p2[1] - p1[1])

    pixmap = QPixmap.fromImage(img)
    if w > 0 and h > 0 and (pixmap.width() != int(w) or pixmap.height() != int(h)):
        pixmap = pixmap.scaled(int(w), int(h))

    item = RasterRegionItem(pixmap=pixmap)
    item.setPos(x, y)
    item.setRotation(float(obj.get("RotationAngle", 0)))
    return item


# ---- helpers ----


def _parse_point(s: str) -> tuple[float, float]:
    """Parse ``"x,y"`` string into a float tuple."""
    parts = s.split(",")
    return float(parts[0]), float(parts[1])
