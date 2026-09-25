"""ProjectSerializer — save/load .smk ZIP archives."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QBuffer, QIODevice, Qt
from PyQt6.QtGui import QColor, QImage, QPixmap

from snapmock.config.constants import (
    APP_VERSION,
    DEFAULT_CANVAS_DPI,
    PROJECT_FORMAT_VERSION,
    THUMBNAIL_MAX_SIZE,
    BorderStyle,
)
from snapmock.core.guides import Guide
from snapmock.core.layer import Layer, normalize_blend_mode, normalize_layer_type
from snapmock.core.scene import SnapScene
from snapmock.items.arc_item import ArcItem
from snapmock.items.arrow_item import ArrowItem
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.blur_item import BlurItem
from snapmock.items.callout_item import CalloutItem
from snapmock.items.ellipse_item import EllipseItem
from snapmock.items.emoji_item import EmojiItem
from snapmock.items.freehand_item import FreehandItem
from snapmock.items.group_item import GroupItem
from snapmock.items.highlight_item import HighlightItem
from snapmock.items.line_item import LineItem
from snapmock.items.mask_utils import mask_file_reference
from snapmock.items.numbered_step_item import NumberedStepItem
from snapmock.items.polygon_item import PolygonItem
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.items.stamp_item import StampItem
from snapmock.items.text_item import TextItem

ITEM_REGISTRY: dict[str, type[SnapGraphicsItem]] = {
    "RectangleItem": RectangleItem,
    "EllipseItem": EllipseItem,
    "LineItem": LineItem,
    "ArrowItem": ArrowItem,
    "ArcItem": ArcItem,
    "PolygonItem": PolygonItem,
    "TextItem": TextItem,
    "FreehandItem": FreehandItem,
    "CalloutItem": CalloutItem,
    "HighlightItem": HighlightItem,
    "BlurItem": BlurItem,
    "NumberedStepItem": NumberedStepItem,
    "RasterRegionItem": RasterRegionItem,
    "StampItem": StampItem,
    "EmojiItem": EmojiItem,
    "GroupItem": GroupItem,
}


THUMBNAIL_ENTRY = "thumbnails/thumb.png"


def render_thumbnail(scene: SnapScene, max_size: int = THUMBNAIL_MAX_SIZE) -> QImage:
    """Render a flattened preview of *scene* fitting within *max_size* pixels."""
    from snapmock.core.render_engine import RenderEngine

    image = RenderEngine(scene).render_to_image()
    if image.width() > max_size or image.height() > max_size:
        image = image.scaled(
            max_size,
            max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return image


def _encode_png(image: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data().data())


def save_project(
    scene: SnapScene,
    path: Path,
    library_metadata: dict[str, Any] | None = None,
    *,
    write_thumbnail: bool = True,
    capture_metadata: dict[str, Any] | None = None,
) -> None:
    """Save the scene to a .smk ZIP archive.

    *library_metadata* (display_name, captured_at, source) is stored in
    manifest.json when given, and so is *capture_metadata* (Screen Capture
    PRD 12.1).  A flattened preview is written to ``thumbnails/thumb.png``
    unless *write_thumbnail* is False.
    """
    manifest: dict[str, Any] = {
        "format_version": PROJECT_FORMAT_VERSION,
        "app_version": APP_VERSION,
        "canvas": {
            "width": scene.canvas_size.width(),
            "height": scene.canvas_size.height(),
            "dpi": scene.canvas_dpi,
        },
    }
    if scene.has_border:
        # An absent block means no border, so a file written before the border existed
        # reads correctly and format_version stays 1 (Navigation PRD 10.8).
        manifest["canvas"]["border"] = {
            "width": scene.border_width,
            "color": scene.border_color.name(QColor.NameFormat.HexArgb),
            "style": scene.border_style.value,
            "shadow": dict(scene.border_shadow),
        }
    if scene.guides:
        manifest["guides"] = [g.to_dict() for g in scene.guides]
    if library_metadata:
        manifest["library_metadata"] = dict(library_metadata)
    if capture_metadata:
        manifest["capture_metadata"] = dict(capture_metadata)
    active = scene.layer_manager.active_layer
    if active is not None:
        manifest["active_layer_id"] = active.layer_id

    layers_data: list[dict[str, Any]] = []
    items_data: list[dict[str, Any]] = []

    for layer in scene.layer_manager.layers:
        layers_data.append(
            {
                "layer_id": layer.layer_id,
                "name": layer.name,
                "visible": layer.visible,
                "locked": layer.locked,
                "opacity": layer.opacity,
                "blend_mode": layer.blend_mode,
                "layer_type": layer.layer_type,
                "item_ids": layer.item_ids,
            }
        )

    # Serialize the top-level items; a group's entry carries its members
    for item in scene.annotation_items():
        items_data.append(item.serialize())

    # A freeform blur mask too large to inline is written to raster/ (Blur PRD 7.1)
    side_files: dict[str, bytes] = {}
    for item in scene.all_annotation_items():
        if isinstance(item, BlurItem):
            side = item.mask_side_file()
            if side is not None:
                side_files[side[0]] = side[1]

    thumb_png = _encode_png(render_thumbnail(scene)) if write_thumbnail else b""

    # Write to a sibling temp file then replace, so a crash mid-write never
    # leaves a truncated archive behind (important for continuous write-back).
    tmp_path = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("layers.json", json.dumps(layers_data, indent=2))
        zf.writestr("items.json", json.dumps(items_data, indent=2))
        for name, blob in side_files.items():
            zf.writestr(name, blob)
        if thumb_png:
            zf.writestr(THUMBNAIL_ENTRY, thumb_png)
    tmp_path.replace(path)


def read_manifest(path: Path) -> dict[str, Any]:
    """Return the parsed manifest.json of a .smk archive."""
    with zipfile.ZipFile(path, "r") as zf:
        data = json.loads(zf.read("manifest.json"))
    return data if isinstance(data, dict) else {}


def read_library_metadata(path: Path) -> dict[str, Any] | None:
    """Return the optional ``library_metadata`` block of a .smk manifest."""
    try:
        meta = read_manifest(path).get("library_metadata")
    except (OSError, zipfile.BadZipFile, KeyError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def read_capture_metadata(path: Path) -> dict[str, Any] | None:
    """Return the optional ``capture_metadata`` block of a .smk manifest (PRD 12.1)."""
    try:
        meta = read_manifest(path).get("capture_metadata")
    except (OSError, zipfile.BadZipFile, KeyError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def update_library_metadata(path: Path, **fields: Any) -> None:
    """Merge *fields* into the ``library_metadata`` block of an existing .smk.

    Every other archive entry is copied through unchanged.
    """
    tmp_path = path.with_name(path.name + ".tmp")
    with (
        zipfile.ZipFile(path, "r") as src,
        zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "manifest.json":
                manifest = json.loads(data)
                if not isinstance(manifest, dict):
                    manifest = {}
                meta = manifest.get("library_metadata")
                if not isinstance(meta, dict):
                    meta = {}
                meta.update(fields)
                manifest["library_metadata"] = meta
                data = json.dumps(manifest, indent=2).encode("utf-8")
            dst.writestr(info.filename, data)
    tmp_path.replace(path)


def read_thumbnail(path: Path) -> QPixmap | None:
    """Return the stored thumbnail of a .smk archive, or None if absent."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if THUMBNAIL_ENTRY not in zf.namelist():
                return None
            data = zf.read(THUMBNAIL_ENTRY)
    except (OSError, zipfile.BadZipFile):
        return None
    pix = QPixmap()
    if not pix.loadFromData(data, "PNG"):
        return None
    return pix


def read_project_summary(path: Path) -> dict[str, Any]:
    """Return lightweight facts about a .smk file without building a scene.

    Keys: canvas_width, canvas_height, layer_count, item_count, library_metadata,
    capture_metadata.
    """
    with zipfile.ZipFile(path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        layers = json.loads(zf.read("layers.json"))
        items = json.loads(zf.read("items.json"))
    canvas = manifest.get("canvas", {}) if isinstance(manifest, dict) else {}
    meta = manifest.get("library_metadata") if isinstance(manifest, dict) else None
    capture = manifest.get("capture_metadata") if isinstance(manifest, dict) else None
    return {
        "canvas_width": int(canvas.get("width", 0)),
        "canvas_height": int(canvas.get("height", 0)),
        "layer_count": len(layers) if isinstance(layers, list) else 0,
        "item_count": len(items) if isinstance(items, list) else 0,
        "library_metadata": meta if isinstance(meta, dict) else None,
        "capture_metadata": capture if isinstance(capture, dict) else None,
    }


def _mask_references(entries: list[Any]) -> dict[str, str]:
    """item_id to archive entry for every blur mask stored as a file (Blur PRD 7.1),
    a group's members included."""
    found: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        reference = mask_file_reference(entry.get("alpha_mask_data"))
        item_id = entry.get("item_id")
        if reference is not None and isinstance(item_id, str):
            found[item_id] = reference
        members = entry.get("members")
        if isinstance(members, list):
            found.update(_mask_references(members))
    return found


def _apply_border(scene: SnapScene, data: Any) -> None:
    """Put a manifest ``canvas.border`` block onto *scene* (Navigation PRD 10.8).

    Absent or malformed leaves the scene's default, which is no border.
    """
    if not isinstance(data, dict):
        return
    scene.set_border_width(int(data.get("width", 0)))
    if "color" in data:
        scene.set_border_color(QColor(str(data["color"])))
    try:
        scene.set_border_style(BorderStyle(str(data.get("style", "solid"))))
    except ValueError:
        scene.set_border_style(BorderStyle.SOLID)
    shadow = data.get("shadow")
    if isinstance(shadow, dict):
        scene.set_border_shadow(shadow)


def load_project(path: Path) -> SnapScene:
    """Load a .smk ZIP archive and reconstruct the scene."""
    with zipfile.ZipFile(path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        layers_data = json.loads(zf.read("layers.json"))
        items_data = json.loads(zf.read("items.json"))
        masks: dict[str, bytes] = {}
        names = set(zf.namelist())
        for item_id, entry_name in _mask_references(items_data).items():
            if entry_name in names:
                masks[item_id] = zf.read(entry_name)

    canvas = manifest.get("canvas", {})
    scene = SnapScene(
        width=int(canvas.get("width", 1920)),
        height=int(canvas.get("height", 1080)),
    )
    scene.set_canvas_dpi(int(canvas.get("dpi", DEFAULT_CANVAS_DPI)))
    _apply_border(scene, canvas.get("border"))
    # Remove the default layer
    default_layer = scene.layer_manager.active_layer
    if default_layer is not None:
        scene.layer_manager._layers.clear()  # noqa: SLF001

    # Reconstruct layers
    for ld in layers_data:
        layer = Layer(
            name=ld["name"],
            layer_id=ld["layer_id"],
            visible=ld.get("visible", True),
            locked=ld.get("locked", False),
            opacity=ld.get("opacity", 1.0),
            # Absent in files from earlier builds: Normal and Annotation
            blend_mode=normalize_blend_mode(ld.get("blend_mode")),
            layer_type=normalize_layer_type(ld.get("layer_type")),
            item_ids=ld.get("item_ids", []),
        )
        scene.layer_manager.insert_layer(layer, scene.layer_manager.count)

    if scene.layer_manager.count > 0:
        active_id = manifest.get("active_layer_id")
        if not isinstance(active_id, str) or scene.layer_manager.layer_by_id(active_id) is None:
            active_id = scene.layer_manager.layers[0].layer_id
        scene.layer_manager.set_active(active_id)

    # Reconstruct items
    for item_data in items_data:
        item_type = item_data.get("type", "")
        cls = ITEM_REGISTRY.get(item_type)
        if cls is not None:
            item = cls.deserialize(item_data)
            scene.addItem(item)

    # Stacking order: the saved array is topmost first, so give every top-level item
    # the z-value of its place in its layer's item_ids
    from snapmock.commands.arrange_commands import apply_layer_z_values

    for layer in scene.layer_manager.layers:
        apply_layer_z_values(scene, layer.layer_id)

    if masks:
        for item in scene.all_annotation_items():
            data = masks.get(item.item_id)
            if data is not None and isinstance(item, BlurItem):
                item.set_mask_png(data)

    raw_guides = manifest.get("guides", [])
    if isinstance(raw_guides, list):
        guides = [g for g in (Guide.from_dict(entry) for entry in raw_guides) if g is not None]
        if guides:
            scene.set_guides(guides)

    scene.command_stack.clear()
    scene.command_stack.mark_clean()
    return scene
