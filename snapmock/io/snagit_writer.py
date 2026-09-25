"""SnagitWriter — save a SnapScene as a Snagit .snagx ZIP archive."""

from __future__ import annotations

import base64
import json
import logging
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QBuffer, QIODevice, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from snapmock.config.constants import APP_NAME, APP_VERSION
from snapmock.core.scene import SnapScene
from snapmock.io.rtf_utils import text_to_rtf_base64
from snapmock.items.arc_item import ArcItem
from snapmock.items.arrow_item import ArrowItem
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.blur_item import BlurItem
from snapmock.items.callout_item import CalloutItem
from snapmock.items.ellipse_item import EllipseItem
from snapmock.items.emoji_item import EmojiItem
from snapmock.items.freehand_item import FreehandItem
from snapmock.items.highlight_item import HighlightItem
from snapmock.items.line_item import LineItem
from snapmock.items.numbered_step_item import NumberedStepItem
from snapmock.items.polygon_item import PolygonItem
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.items.stamp_item import StampItem
from snapmock.items.text_item import TextItem

log = logging.getLogger(__name__)

# Max thumbnail width in pixels
_THUMB_WIDTH = 1024


def save_snagx(scene: SnapScene, path: Path) -> list[str]:
    """Save *scene* as a ``.snagx`` ZIP archive.

    Returns a list of warning strings for items that could not be written.
    """
    warnings: list[str] = []
    page_guid = _new_guid()
    page_json_name = f"{page_guid}.json"
    page_png_name = f"{page_guid}.png"

    # A canvas border grows what is written, as Snagit's own Border effect does: the
    # border is painted into the background image and the canvas holds both (PRD 10.8).
    output = scene.output_rect
    canvas_w = int(round(output.width()))
    canvas_h = int(round(output.height()))
    offset = QPointF(-output.left(), -output.top())

    # Separate background raster from annotation items
    bg_item, annotation_items = _split_bg_and_annotations(scene)

    # Background PNG bytes
    if scene.has_border:
        bg_png = _flattened_background_png(scene, bg_item, canvas_w, canvas_h, offset)
    else:
        bg_png = _pixmap_to_png_bytes(bg_item) if bg_item is not None else b""

    # Thumbnail — of the page as written, so a border shows in it too
    thumb_png = _thumbnail_from_png(bg_png) if scene.has_border else _make_thumbnail(bg_item)

    # Build CaptureObjects
    capture_objects: list[dict[str, Any]] = []
    for item in annotation_items:
        obj = _item_to_snagit(item, warnings)
        if obj is not None:
            _offset_object(obj, offset)
            capture_objects.append(obj)

    bg_color = scene.background_color.name(QColor.NameFormat.HexArgb)

    # Page JSON
    page_data: dict[str, Any] = {
        "CaptureBackgroundColor": bg_color,
        "CaptureBackgroundImage": page_png_name,
        "CaptureBackgroundLocation": "0,0",
        "CaptureCanvasHeight": canvas_h,
        "CaptureCanvasWidth": canvas_w,
        "CaptureObjects": capture_objects,
        "ExportedFromPlatform": "linux",
        "ImageExpansionFromObjects": ["0,0", "0,0"],
        "SimplifySettings": {
            "ActiveColorPaletteName": "ImageColors",
            "LockAllObjects": False,
            "Opacity": 100,
            "ShowOriginal": False,
            "SuiDetail": 0,
        },
        "SoftwareVersion": f"{APP_NAME} {APP_VERSION}",
        "StepToolSequenceLowercaseLetter": 1,
        "StepToolSequenceNumeric": 1,
        "StepToolSequenceUppercaseLetter": 1,
        "Version": "1.0",
        "ViewBoxExpansionFromObjects": ["0,0", "0,0"],
    }

    # Index JSON
    index_data = {"Pages": [page_json_name], "Version": "1.0"}

    # Metadata JSON
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    metadata_data: dict[str, Any] = {
        "AppCompany": "",
        "AppName": APP_NAME,
        "AppVersion": APP_VERSION,
        "CaptureDate": now,
        "CaptureId": _new_guid(),
        "LanguageCode": "",
        "OperatingSystemVersion": "",
        "Version": "1.0",
        "WebURL": "",
        "WindowName": "",
    }

    # If scene has round-trip metadata, prefer it
    saved_meta: dict[str, Any] = getattr(scene, "_snagit_metadata", {})
    if "metadata" in saved_meta:
        metadata_data = saved_meta["metadata"]

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.json", json.dumps(index_data, indent=2))
        zf.writestr("metadata.json", json.dumps(metadata_data, indent=2))
        zf.writestr(page_json_name, json.dumps(page_data, indent=2))
        if bg_png:
            zf.writestr(page_png_name, bg_png)
        if thumb_png:
            zf.writestr("thumbnail.png", thumb_png)

    return warnings


# ---- item dispatch ----


def _item_to_snagit(item: SnapGraphicsItem, warnings: list[str]) -> dict[str, Any] | None:
    """Convert a SnapMock item to a Snagit CaptureObject dict."""
    # If we have round-trip data, update positions and return it
    raw: dict[str, Any] | None = getattr(item, "_snagit_data", None)
    if raw is not None:
        return _round_trip_update(item, dict(raw))

    if isinstance(item, ArrowItem):
        return _item_to_arrow(item)
    if isinstance(item, LineItem):
        return _item_to_line(item)
    if isinstance(item, HighlightItem):
        return _item_to_highlight(item)
    if isinstance(item, RectangleItem):
        # Check if this was a highlight in disguise
        if getattr(item, "_snagit_highlight", False):
            return _item_to_highlight_rect(item)
        return _item_to_shape(item)
    if isinstance(item, CalloutItem):
        return _item_to_callout(item)
    if isinstance(item, TextItem):
        return _item_to_text(item)
    if isinstance(item, RasterRegionItem):
        return _item_to_image(item)

    # Unsupported types
    type_name = type(item).__name__
    if isinstance(
        item,
        (
            EllipseItem,
            FreehandItem,
            BlurItem,
            NumberedStepItem,
            StampItem,
            EmojiItem,
            ArcItem,
            PolygonItem,
        ),
    ):
        warnings.append(f"{type_name} is not supported in .snagx format — skipped")
        log.warning("Skipping unsupported item type %s for .snagx export", type_name)
    else:
        warnings.append(f"Unknown item type {type_name} — skipped")
    return None


def _round_trip_update(item: SnapGraphicsItem, obj: dict[str, Any]) -> dict[str, Any]:
    """Update a round-tripped Snagit object with the item's current position."""
    obj["Opacity"] = int(item.opacity() * 100)
    # Update PointsArray from item position for the common case
    if isinstance(item, (ArrowItem, LineItem)):
        line = item._line
        pos = item.scenePos()
        x1 = line.x1() + pos.x()
        y1 = line.y1() + pos.y()
        x2 = line.x2() + pos.x()
        y2 = line.y2() + pos.y()
        obj["PointsArray"] = [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"]
    elif isinstance(item, RectangleItem):
        pos = item.scenePos()
        r = item._rect
        x1 = r.x() + pos.x()
        y1 = r.y() + pos.y()
        x2 = x1 + r.width()
        y2 = y1 + r.height()
        obj["PointsArray"] = [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"]
    elif isinstance(item, CalloutItem):
        pos = item.scenePos()
        r = item._rect
        x1 = r.x() + pos.x()
        y1 = r.y() + pos.y()
        x2 = x1 + r.width()
        y2 = y1 + r.height()
        obj["PointsArray"] = [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"]
        # Update tail
        tip = item._tail_tip
        obj["CalloutTails"] = [f"{tip.x() + pos.x():.0f},{tip.y() + pos.y():.0f}"]
    elif isinstance(item, TextItem):
        pos = item.scenePos()
        w = item._width
        br = item.boundingRect()
        obj["PointsArray"] = [
            f"{pos.x():.0f},{pos.y():.0f}",
            f"{pos.x() + w:.0f},{pos.y() + br.height():.0f}",
        ]
    return obj


# ---- converters ----


def _item_to_arrow(item: ArrowItem) -> dict[str, Any]:
    line = item._line
    pos = item.scenePos()
    x1 = line.x1() + pos.x()
    y1 = line.y1() + pos.y()
    x2 = line.x2() + pos.x()
    y2 = line.y2() + pos.y()
    return {
        "ArrowEnd": "EquilateralArrow",
        "ArrowEndWidth": 3,
        "ArrowStart": "Round",
        "DashType": "Solid",
        "DropShadowEnabled": False,
        "ForegroundColor": item._stroke_color.name(QColor.NameFormat.HexArgb),
        "ObjectID": _new_guid_bare(),
        "Opacity": int(item.opacity() * 100),
        "PointsArray": [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"],
        "ShadowBlur": 2,
        "ShadowColor": "#FF000000",
        "ShadowDirectionX": 0,
        "ShadowDirectionY": 4,
        "ShadowOpacity": 50,
        "StrokeWidth": int(item._stroke_width),
        "ToolMode": "Arrow",
    }


def _item_to_line(item: LineItem) -> dict[str, Any]:
    line = item._line
    pos = item.scenePos()
    x1 = line.x1() + pos.x()
    y1 = line.y1() + pos.y()
    x2 = line.x2() + pos.x()
    y2 = line.y2() + pos.y()
    return {
        "ArrowEnd": "Round",
        "ArrowEndWidth": 3,
        "ArrowStart": "Round",
        "DashType": "Solid",
        "DropShadowEnabled": False,
        "ForegroundColor": item._stroke_color.name(QColor.NameFormat.HexArgb),
        "ObjectID": _new_guid_bare(),
        "Opacity": int(item.opacity() * 100),
        "PointsArray": [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"],
        "ShadowBlur": 2,
        "ShadowColor": "#FF000000",
        "ShadowDirectionX": 0,
        "ShadowDirectionY": 4,
        "ShadowOpacity": 50,
        "StrokeWidth": int(item._stroke_width),
        "ToolMode": "Line",
    }


def _item_to_shape(item: RectangleItem) -> dict[str, Any]:
    pos = item.scenePos()
    r = item._rect
    x1 = r.x() + pos.x()
    y1 = r.y() + pos.y()
    x2 = x1 + r.width()
    y2 = y1 + r.height()

    tool_shape = "Rectangle"
    obj: dict[str, Any] = {}
    if item._corner_radius > 0:
        tool_shape = "RoundedRectangle"
        min_dim = min(r.width(), r.height())
        ratio = item._corner_radius / min_dim if min_dim > 0 else 0.25
        obj["CornerRadiusRatio"] = round(ratio, 4)

    obj.update(
        {
            "BackgroundColor": item._fill_color.name(QColor.NameFormat.HexArgb),
            "BorderStyle": "Inset",
            "DashType": "Solid",
            "DropShadowEnabled": False,
            "ForegroundColor": item._stroke_color.name(QColor.NameFormat.HexArgb),
            "ObjectID": _new_guid_bare(),
            "Opacity": int(item.opacity() * 100),
            "PointsArray": [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"],
            "RotationAngle": int(item.rotation()),
            "ShadowBlur": 2,
            "ShadowColor": "#FF000000",
            "ShadowDirectionX": 0,
            "ShadowDirectionY": 4,
            "ShadowOpacity": 50,
            "StrokeWidth": int(item._stroke_width),
            "ToolMode": "Shape",
            "ToolShape": tool_shape,
        }
    )
    return obj


def _item_to_highlight(item: HighlightItem) -> dict[str, Any]:
    pos = item.scenePos()
    br = item.boundingRect()
    x1 = br.x() + pos.x()
    y1 = br.y() + pos.y()
    x2 = x1 + br.width()
    y2 = y1 + br.height()
    return {
        "BackgroundColor": item._stroke_color.name(QColor.NameFormat.HexArgb),
        "ObjectID": _new_guid_bare(),
        "Opacity": int(item.opacity() * 100),
        "PointsArray": [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"],
        "ToolMode": "Highlight",
    }


def _item_to_highlight_rect(item: RectangleItem) -> dict[str, Any]:
    """Convert a RectangleItem tagged as a Snagit highlight."""
    pos = item.scenePos()
    r = item._rect
    x1 = r.x() + pos.x()
    y1 = r.y() + pos.y()
    x2 = x1 + r.width()
    y2 = y1 + r.height()
    return {
        "BackgroundColor": item._fill_color.name(QColor.NameFormat.HexArgb),
        "ObjectID": _new_guid_bare(),
        "Opacity": int(item.opacity() * 100),
        "PointsArray": [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"],
        "ToolMode": "Highlight",
    }


def _get_halign_str(item: TextItem | CalloutItem) -> str:
    """Return the Snagit ToolHorizontalAlign string for a text-bearing item."""
    block_fmt = item.get_block_format()
    align = block_fmt.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask
    return {
        Qt.AlignmentFlag.AlignLeft: "Left",
        Qt.AlignmentFlag.AlignHCenter: "Center",
        Qt.AlignmentFlag.AlignRight: "Right",
        Qt.AlignmentFlag.AlignJustify: "Justify",
    }.get(align, "Left")


def _item_to_callout(item: CalloutItem) -> dict[str, Any]:
    pos = item.scenePos()
    r = item._rect
    x1 = r.x() + pos.x()
    y1 = r.y() + pos.y()
    x2 = x1 + r.width()
    y2 = y1 + r.height()

    tip = item._tail_tip
    tail_x = tip.x() + pos.x()
    tail_y = tip.y() + pos.y()

    rtf = text_to_rtf_base64(
        item.text,
        item.font.family(),
        item.font.pointSize(),
        item.text_color,
    )

    return {
        "Antialiasing": 1,
        "BackgroundColor": item._bg_color.name(QColor.NameFormat.HexArgb),
        "BorderStyle": "Middle",
        "CalloutShape": "CTBalloon1",
        "CalloutStyle": "Plain",
        "CalloutTails": [f"{tail_x:.0f},{tail_y:.0f}"],
        "ControlPoints": [],
        "DashType": "Solid",
        "DropShadowEnabled": False,
        "FitToWidth": False,
        "ForegroundColor": item._border_color.name(QColor.NameFormat.HexArgb),
        "ObjectID": _new_guid_bare(),
        "Opacity": int(item.opacity() * 100),
        "PlaceholderText": "",
        "PointsArray": [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"],
        "PreSnagx": True,
        "RTFEncodedText": rtf,
        "RotationAngle": 0,
        "ShadowBlur": 2,
        "ShadowColor": "#FF000000",
        "ShadowDirectionX": 0,
        "ShadowDirectionY": 4,
        "ShadowOpacity": 50,
        "StrokeWidth": int(item._border_width),
        "TailStyle": "Triangle",
        "TextOutlineColor": "#FFFFFFFF",
        "TextOutlineWidth": 0,
        "TextSelectionColor": "#FF000000",
        "ToolHorizontalAlign": _get_halign_str(item),
        "ToolMode": "Callout",
        "ToolPadding": int(item._padding),
        "ToolVerticalAlign": {"top": "Top", "center": "Center", "bottom": "Bottom"}.get(
            item._vertical_align.value, "Center"
        ),
    }


def _item_to_text(item: TextItem) -> dict[str, Any]:
    pos = item.scenePos()
    w = item._width
    br = item.boundingRect()
    x1 = pos.x()
    y1 = pos.y()
    x2 = x1 + w
    y2 = y1 + br.height()

    rtf = text_to_rtf_base64(
        item.text,
        item.font.family(),
        item.font.pointSize(),
        item.text_color,
    )

    # Map vertical align to Snagit string
    valign_map = {"top": "Top", "center": "Center", "bottom": "Bottom"}
    valign_str = valign_map.get(item._vertical_align.value, "Top")

    return {
        "Antialiasing": 1,
        "BackgroundColor": item._bg_color.name(QColor.NameFormat.HexArgb),
        "CalloutShape": "CTBalloon6",
        "CalloutStyle": "Plain",
        "DashType": "Solid",
        "DropShadowEnabled": False,
        "FitToWidth": False,
        "ForegroundColor": item._border_color.name(QColor.NameFormat.HexArgb),
        "ObjectID": _new_guid_bare(),
        "Opacity": int(item.opacity() * 100),
        "Placeholder": False,
        "PlaceholderText": "",
        "PointsArray": [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"],
        "PreSnagx": True,
        "RTFEncodedText": rtf,
        "RotationAngle": 0,
        "ShadowBlur": 2,
        "ShadowColor": "#FF000000",
        "ShadowDirectionX": 0,
        "ShadowDirectionY": 4,
        "ShadowOpacity": 50,
        "StrokeWidth": int(item._border_width),
        "TailStyle": "None",
        "TextOutlineColor": "#FFFFFFFF",
        "TextOutlineWidth": 0,
        "TextSelectionColor": "#FF000000",
        "ToolHorizontalAlign": _get_halign_str(item),
        "ToolMode": "Text",
        "ToolPadding": int(item._padding),
        "ToolVerticalAlign": valign_str,
    }


def _item_to_image(item: RasterRegionItem) -> dict[str, Any]:
    pos = item.scenePos()
    pw = item._pixmap.width()
    ph = item._pixmap.height()
    x1 = pos.x()
    y1 = pos.y()
    x2 = x1 + pw
    y2 = y1 + ph

    png_bytes = _pixmap_to_png_bytes(item)
    image_b64 = base64.b64encode(png_bytes).decode("ascii") if png_bytes else ""

    return {
        "Image": image_b64,
        "ObjectID": _new_guid_bare(),
        "Opacity": int(item.opacity() * 100),
        "PointsArray": [f"{x1:.0f},{y1:.0f}", f"{x2:.0f},{y2:.0f}"],
        "RotationAngle": int(item.rotation()),
        "ToolMode": "Image",
    }


# ---- helpers ----


_POINT_FIELDS = ("PointsArray", "CalloutTails")
"""The Snagit object fields that hold ``"x,y"`` strings in canvas coordinates."""


def _offset_object(obj: dict[str, Any], offset: QPointF) -> None:
    """Move a CaptureObject's points by *offset*; a no-op at the origin (PRD 10.8).

    A canvas border moves the image away from the page origin, so every annotation moves
    with it. Only two fields carry coordinates, and the round-trip path rewrites both
    from the item before this runs.
    """
    if offset.isNull():
        return
    for field in _POINT_FIELDS:
        points = obj.get(field)
        if not isinstance(points, list):
            continue
        moved: list[str] = []
        for point in points:
            try:
                x_text, y_text = str(point).split(",")
                x = float(x_text) + offset.x()
                y = float(y_text) + offset.y()
            except ValueError:  # pragma: no cover - a field we did not write
                moved.append(str(point))
                continue
            moved.append(f"{x:.0f},{y:.0f}")
        obj[field] = moved


def _flattened_background_png(
    scene: SnapScene,
    bg_item: RasterRegionItem | None,
    width: int,
    height: int,
    offset: QPointF,
) -> bytes:
    """The background image with the canvas border painted around it (PRD 10.8).

    Snagit has no border object; its Border effect lives in the background bitmap and the
    canvas holds both. This writes the same thing, so Snagit opens the file with the
    border showing and nothing is lost.
    """
    from snapmock.core.render_engine import paint_canvas_border

    image = QImage(max(1, width), max(1, height), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(offset)
    paint_canvas_border(painter, scene)
    if bg_item is not None:
        painter.drawPixmap(QPointF(0, 0), bg_item._pixmap)  # noqa: SLF001
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    data: bytes = buf.data().data()
    return data


def _split_bg_and_annotations(
    scene: SnapScene,
) -> tuple[RasterRegionItem | None, list[SnapGraphicsItem]]:
    """The background raster region and the annotation items, bottom first.

    The background is the lowest top-level ``RasterRegionItem`` on the Background layer
    when the project has one (follow-up decision 2), else the lowest anywhere. A group is
    written as its members, each at the position the group showed it (the group's
    translation composed in; a group's scale, rotation, or skew has no Snagit form and is
    dropped), with no warning (Group and Ungroup kickoff, silence 4).
    """
    from snapmock.items.group_item import GroupItem

    # Top-level items in z-order, bottom first
    all_items = sorted(scene.annotation_items(), key=lambda i: i.zValue())
    rasters = [i for i in all_items if isinstance(i, RasterRegionItem)]
    background_layer = scene.layer_manager.background_layer
    bg: RasterRegionItem | None = None
    if background_layer is not None:
        bg = next((r for r in rasters if r.layer_id == background_layer.layer_id), None)
    if bg is None and rasters:
        bg = rasters[0]

    annotations: list[SnapGraphicsItem] = []
    for item in all_items:
        if item is bg:
            continue
        if isinstance(item, GroupItem):
            annotations.extend(m for m in item.descendants() if not isinstance(m, GroupItem))
        else:
            annotations.append(item)
    return bg, annotations


def _pixmap_to_png_bytes(item: RasterRegionItem) -> bytes:
    """Render a RasterRegionItem's pixmap to PNG bytes."""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    item._pixmap.save(buf, "PNG")
    data: bytes = buf.data().data()
    return data


def _make_thumbnail(bg_item: RasterRegionItem | None) -> bytes:
    """Create a thumbnail PNG (max *_THUMB_WIDTH* px wide)."""
    if bg_item is None:
        return b""

    pixmap = bg_item._pixmap  # noqa: SLF001
    if pixmap.width() > _THUMB_WIDTH:
        pixmap = pixmap.scaledToWidth(_THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation)

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    data: bytes = buf.data().data()
    return data


def _thumbnail_from_png(png: bytes) -> bytes:
    """A thumbnail of the page image just written, border and all."""
    if not png:
        return b""
    image = QImage()
    if not image.loadFromData(png, "PNG"):  # pragma: no cover - we just wrote it
        return b""
    if image.width() > _THUMB_WIDTH:
        image = image.scaledToWidth(_THUMB_WIDTH, Qt.TransformationMode.SmoothTransformation)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    data: bytes = buf.data().data()
    return data


def _new_guid() -> str:
    """Return a new GUID in ``{XXXXXXXX-...}`` format."""
    return "{" + str(uuid.uuid4()).upper() + "}"


def _new_guid_bare() -> str:
    """Return a new GUID in ``XXXXXXXX-...`` format (no braces)."""
    return str(uuid.uuid4()).upper()
