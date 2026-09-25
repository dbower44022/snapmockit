"""The Border tool (Navigation & Raster Operations PRD Section 10).

One test per acceptance row of 13.8, plus the model and edge cases of 10.2 and 10.9.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PyQt6.QtCore import QRectF, QSizeF
from PyQt6.QtGui import QColor, QImage, QPixmap
from pytestqt.qtbot import QtBot

from snapmock.commands.canvas_property_commands import SetCanvasBorderCommand
from snapmock.commands.raster_commands import CropCanvasCommand, ResizeImageCommand
from snapmock.config.constants import BORDER_WIDTH_MAX, CANVAS_DIMENSION_MAX, BorderStyle
from snapmock.core.render_engine import RenderEngine
from snapmock.core.scene import SnapScene
from snapmock.io.exporter import (
    ExportFormat,
    ExportRegion,
    ExportSettings,
    export_png,
    export_scene,
    resolve_region,
)
from snapmock.io.project_serializer import load_project, save_project
from snapmock.io.snagit_reader import load_snagx
from snapmock.io.snagit_writer import save_snagx
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.items.rectangle_item import RectangleItem
from snapmock.main_window import MainWindow
from snapmock.tools.border_tool import BorderTool

EXAMPLE = Path("Example Snag Files/Border Tool Example - 2026-09-21_10-21-47.snagx")


def _bordered(scene: SnapScene, width: int = 8, colour: str = "black") -> SnapScene:
    scene.set_border_width(width)
    scene.set_border_color(QColor(colour))
    return scene


def _with_background(scene: SnapScene, colour: str = "white") -> RasterRegionItem:
    size = scene.canvas_size
    pixmap = QPixmap(int(size.width()), int(size.height()))
    pixmap.fill(QColor(colour))
    item = RasterRegionItem(pixmap=pixmap)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    item.layer_id = layer.layer_id
    scene.addItem(item)
    return item


# --- 10.2, the border model ---


def test_border_grows_the_output_and_never_the_canvas(scene: SnapScene) -> None:
    scene.set_canvas_size(QSizeF(2550, 3300))
    _bordered(scene)
    assert scene.canvas_size == QSizeF(2550, 3300)
    assert scene.output_rect == QRectF(-8, -8, 2566, 3316)


def test_no_border_leaves_the_output_at_the_canvas(scene: SnapScene) -> None:
    assert not scene.has_border
    assert scene.output_rect == scene.canvas_rect


def test_border_width_does_not_move_items(scene: SnapScene) -> None:
    item = RectangleItem()
    item.setPos(40, 30)
    scene.addItem(item)
    _bordered(scene, 12)
    assert item.pos().x() == 40
    assert item.pos().y() == 30


def test_shadow_grows_the_output_further(scene: SnapScene) -> None:
    _bordered(scene, 8)
    without = scene.output_rect
    scene.set_border_shadow({"shadow_enabled": True, "shadow_offset_x": 4, "shadow_blur": 6})
    grown = scene.output_rect
    assert grown.width() > without.width()
    assert grown.contains(without)


# --- 13.8 row 1, the tool and its bar ---


def test_tool_is_registered_with_its_shortcut(main_window: MainWindow) -> None:
    from snapmock.config.shortcuts import SHORTCUTS

    tool = main_window._tool_manager.tool("border")
    assert isinstance(tool, BorderTool)
    assert tool.display_name == "Border"
    assert SHORTCUTS["tool.border"] == "Shift+B"


def test_bar_reads_the_document(main_window: MainWindow) -> None:
    _bordered(main_window._scene, 6, "#ff0000")
    main_window._tool_manager.activate("border")
    tool = main_window._tool_manager.tool("border")
    assert isinstance(tool, BorderTool)
    assert tool._width_spin is not None
    assert tool._width_spin.value() == 6
    assert tool._color_picker is not None
    assert tool._color_picker.color == QColor("#ff0000")


def test_tool_has_no_canvas_interaction(main_window: MainWindow) -> None:
    main_window._tool_manager.activate("border")
    tool = main_window._tool_manager.tool("border")
    assert tool is not None
    assert not tool.is_active_operation


# --- 13.8 row 2, the ring falls outside the image ---


def test_border_paints_outside_the_image(scene: SnapScene) -> None:
    scene.set_canvas_size(QSizeF(100, 80))
    _with_background(scene, "white")
    _bordered(scene, 8, "black")
    image = RenderEngine(scene).render_to_image(background=QColor("white"))
    assert image.size().width() == 116
    assert image.size().height() == 96
    assert image.pixelColor(0, 0) == QColor("black")
    assert image.pixelColor(7, 7) == QColor("black")
    assert image.pixelColor(9, 9) == QColor("white")


# --- 13.8 row 3, one undoable step per edit, merging ---


def test_each_edit_is_one_undoable_step(scene: SnapScene, qtbot: QtBot) -> None:
    scene.command_stack.push(SetCanvasBorderCommand(scene, "border_width", 0, 8))
    scene.command_stack.push(
        SetCanvasBorderCommand(scene, "border_style", BorderStyle.SOLID, BorderStyle.DASHED)
    )
    assert scene.border_width == 8
    assert scene.border_style is BorderStyle.DASHED
    scene.command_stack.undo()
    assert scene.border_style is BorderStyle.SOLID
    assert scene.border_width == 8
    scene.command_stack.undo()
    assert scene.border_width == 0


def test_same_property_edits_merge(scene: SnapScene) -> None:
    first = SetCanvasBorderCommand(scene, "border_width", 0, 4)
    second = SetCanvasBorderCommand(scene, "border_width", 4, 10)
    assert first.merge_id == second.merge_id
    assert first.merge_with(second)


def test_a_different_property_does_not_merge(scene: SnapScene) -> None:
    width = SetCanvasBorderCommand(scene, "border_width", 0, 4)
    style = SetCanvasBorderCommand(scene, "border_style", BorderStyle.SOLID, BorderStyle.DOTTED)
    assert width.merge_id != style.merge_id
    assert not width.merge_with(style)


# --- 13.8 row 4, the exported size ---


def test_whole_canvas_export_region_is_the_output_rect(scene: SnapScene) -> None:
    _bordered(scene, 8)
    assert resolve_region(scene, ExportRegion.CANVAS) == scene.output_rect


def test_selection_export_stays_inside_the_canvas(scene: SnapScene) -> None:
    _bordered(scene, 8)
    region = resolve_region(scene, ExportRegion.SELECTION, selection=QRectF(10, 10, 20, 20))
    assert scene.canvas_rect.contains(region)


def test_every_raster_export_carries_the_border(scene: SnapScene, tmp_path: Path) -> None:
    scene.set_canvas_size(QSizeF(120, 90))
    _with_background(scene, "#dbeafe")
    _bordered(scene, 10, "black")

    export_png(scene, tmp_path / "quick.png")
    quick = QImage(str(tmp_path / "quick.png"))
    assert quick.size().width() == 140
    assert quick.size().height() == 110
    assert quick.pixelColor(0, 0) == QColor("black")
    assert quick.pixelColor(11, 11) == QColor("#dbeafe")

    for name, fmt in (("dialog.png", ExportFormat.PNG), ("dialog.jpg", ExportFormat.JPEG)):
        export_scene(scene, tmp_path / name, ExportSettings(format=fmt))
        written = QImage(str(tmp_path / name))
        assert written.size().width() == 140, name
        assert written.size().height() == 110, name


def test_the_vector_exports_carry_the_border(scene: SnapScene, tmp_path: Path) -> None:
    scene.set_canvas_size(QSizeF(120, 90))
    _with_background(scene, "#dbeafe")
    _bordered(scene, 10, "black")
    svg = tmp_path / "bordered.svg"
    export_scene(scene, svg, ExportSettings(format=ExportFormat.SVG))
    assert 'viewBox="0 0 140 110"' in svg.read_text()
    pdf = tmp_path / "bordered.pdf"
    export_scene(scene, pdf, ExportSettings(format=ExportFormat.PDF))
    assert pdf.stat().st_size > 0


# --- 13.8 row 5, the project file ---


def test_border_survives_a_project_round_trip(scene: SnapScene, tmp_path: Path) -> None:
    _bordered(scene, 6, "#ff0000")
    scene.set_border_color(QColor(255, 0, 0, 128))
    scene.set_border_style(BorderStyle.DASHED)
    scene.set_border_shadow({"shadow_enabled": True})
    path = tmp_path / "bordered.smk"
    save_project(scene, path)
    loaded = load_project(path)
    assert loaded.border_width == 6
    assert loaded.border_color == QColor(255, 0, 0, 128)
    assert loaded.border_style is BorderStyle.DASHED
    assert loaded.border_shadow["shadow_enabled"] is True


def test_a_project_without_a_border_writes_no_border_block(
    scene: SnapScene, tmp_path: Path
) -> None:
    path = tmp_path / "plain.smk"
    save_project(scene, path)
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert "border" not in manifest["canvas"]
    assert manifest["format_version"] == 1


# --- 13.8 row 6, writing a Snagit file ---


def test_snagx_write_flattens_the_border_and_grows_the_canvas(
    scene: SnapScene, tmp_path: Path
) -> None:
    scene.set_canvas_size(QSizeF(100, 80))
    _with_background(scene, "white")
    _bordered(scene, 8, "black")
    path = tmp_path / "bordered.snagx"
    assert save_snagx(scene, path) == []
    with zipfile.ZipFile(path) as archive:
        page_name = json.loads(archive.read("index.json"))["Pages"][0]
        page = json.loads(archive.read(page_name))
        image = QImage()
        assert image.loadFromData(archive.read(page["CaptureBackgroundImage"]))
    assert page["CaptureCanvasWidth"] == 116
    assert page["CaptureCanvasHeight"] == 96
    assert image.size().width() == 116
    assert image.pixelColor(0, 0) == QColor("black")
    assert image.pixelColor(9, 9) == QColor("white")


def test_snagx_write_moves_annotations_with_the_image(scene: SnapScene, tmp_path: Path) -> None:
    scene.set_canvas_size(QSizeF(100, 80))
    _with_background(scene, "white")
    layer = scene.layer_manager.active_layer
    assert layer is not None
    rect = RectangleItem()
    rect.setPos(20, 20)
    rect.layer_id = layer.layer_id
    scene.addItem(rect)
    _bordered(scene, 8, "black")
    path = tmp_path / "bordered.snagx"
    save_snagx(scene, path)
    with zipfile.ZipFile(path) as archive:
        page_name = json.loads(archive.read("index.json"))["Pages"][0]
        page = json.loads(archive.read(page_name))
    shape = next(o for o in page["CaptureObjects"] if o["ToolMode"] == "Shape")
    assert shape["PointsArray"][0] == "28,28"


# --- 13.8 rows 7 and 8, reading a Snagit file ---


def test_snagit_border_comes_back_editable(qapp: object) -> None:
    assert EXAMPLE.exists(), "the reference Snagit border file is missing"
    loaded = load_snagx(EXAMPLE)
    assert loaded.canvas_size == QSizeF(2550, 3300)
    assert loaded.border_width == 8
    assert loaded.border_color == QColor(0, 0, 0, 255)
    assert loaded.border_style is BorderStyle.SOLID
    assert loaded.output_rect == QRectF(-8, -8, 2566, 3316)


def test_a_file_without_a_backup_pair_loads_flattened(
    scene: SnapScene, tmp_path: Path, qapp: object
) -> None:
    scene.set_canvas_size(QSizeF(100, 80))
    _with_background(scene, "white")
    _bordered(scene, 8, "black")
    path = tmp_path / "flat.snagx"
    save_snagx(scene, path)
    loaded = load_snagx(path)
    assert not loaded.has_border
    assert loaded.canvas_size == QSizeF(116, 96)


def test_a_non_uniform_ring_loads_flattened(tmp_path: Path, qapp: object) -> None:
    """A backup pair left by some other effect must not become a border (10.8)."""
    page_guid = "{AAAA}"
    page = {
        "CaptureBackgroundImage": f"{page_guid}.png",
        "CaptureCanvasWidth": 24,
        "CaptureCanvasHeight": 24,
    }
    backup = {"CaptureCanvasWidth": 20, "CaptureCanvasHeight": 20}
    grown = QImage(24, 24, QImage.Format.Format_ARGB32)
    grown.fill(QColor("black"))
    grown.setPixelColor(0, 0, QColor("red"))  # one stray pixel breaks the ring
    small = QImage(20, 20, QImage.Format.Format_ARGB32)
    small.fill(QColor("white"))
    path = tmp_path / "other-effect.snagx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("index.json", json.dumps({"Pages": [f"{page_guid}.json"]}))
        archive.writestr(f"{page_guid}.json", json.dumps(page))
        archive.writestr(f"{page_guid}.backup.json", json.dumps(backup))
        archive.writestr(f"{page_guid}.png", _png_bytes(grown))
        archive.writestr(f"{page_guid}.backup.png", _png_bytes(small))
    loaded = load_snagx(path)
    assert not loaded.has_border
    assert loaded.canvas_size == QSizeF(24, 24)


def _png_bytes(image: QImage) -> bytes:
    from PyQt6.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    data: bytes = buffer.data().data()
    return data


# --- 13.8 row 9, the canvas operations ---


def test_crop_leaves_the_border_alone(scene: SnapScene) -> None:
    scene.set_canvas_size(QSizeF(200, 200))
    _bordered(scene, 8)
    scene.command_stack.push(CropCanvasCommand(scene, QRectF(0, 0, 100, 100)))
    assert scene.border_width == 8
    assert scene.output_rect == QRectF(-8, -8, 116, 116)


def test_resize_image_scales_the_border(scene: SnapScene) -> None:
    scene.set_canvas_size(QSizeF(200, 200))
    _bordered(scene, 8)
    scene.command_stack.push(ResizeImageCommand(scene, QSizeF(100, 100)))
    assert scene.border_width == 4
    scene.command_stack.undo()
    assert scene.border_width == 8


def test_resize_image_never_scales_a_border_away(scene: SnapScene) -> None:
    scene.set_canvas_size(QSizeF(1000, 1000))
    _bordered(scene, 2)
    scene.command_stack.push(ResizeImageCommand(scene, QSizeF(50, 50)))
    assert scene.border_width == 1


# --- 13.8 row 10, removing the border ---


def test_width_zero_removes_the_border(scene: SnapScene) -> None:
    _bordered(scene, 8)
    scene.set_border_width(0)
    assert not scene.has_border
    assert scene.output_rect == scene.canvas_rect


# --- 10.9, the edge cases ---


def test_width_is_clamped_to_the_canvas_limit(scene: SnapScene) -> None:
    scene.set_canvas_size(QSizeF(CANVAS_DIMENSION_MAX - 10, 100))
    scene.set_border_width(BORDER_WIDTH_MAX)
    assert scene.border_width == 5
    assert scene.output_rect.width() <= CANVAS_DIMENSION_MAX


def test_a_canvas_that_grows_shrinks_the_border_it_carries(scene: SnapScene) -> None:
    _bordered(scene, 100)
    scene.set_canvas_size(QSizeF(CANVAS_DIMENSION_MAX - 10, 100))
    assert scene.border_width == 5


def test_a_fully_transparent_border_still_occupies_its_ring(scene: SnapScene) -> None:
    _bordered(scene, 8)
    scene.set_border_color(QColor(0, 0, 0, 0))
    assert scene.has_border
    assert scene.output_rect != scene.canvas_rect


# --- 10.6, the Property Panel's Canvas section ---


def test_panel_edits_the_border(main_window: MainWindow) -> None:
    panel = main_window._property_panel
    scene = main_window._scene
    panel.show_canvas_section()
    panel._border_w_spin.setValue(10)
    assert scene.border_width == 10
    panel._border_opacity_spin.setValue(50)
    assert scene.border_color.alpha() == 128
    scene.command_stack.undo()
    assert scene.border_color.alpha() == 255
    scene.command_stack.undo()
    assert scene.border_width == 0


def test_panel_edits_the_border_shadow(main_window: MainWindow) -> None:
    panel = main_window._property_panel
    scene = main_window._scene
    panel.show_canvas_section()
    panel._border_w_spin.setValue(8)
    panel._border_shadow_check.setChecked(True)
    panel._border_shadow_blur.setValue(6.0)
    assert scene.border_shadow["shadow_enabled"] is True
    assert scene.border_shadow["shadow_blur"] == 6.0
    assert scene.output_rect.width() > scene.border_rect.width()
    scene.command_stack.undo()
    assert scene.border_shadow["shadow_blur"] != 6.0


def test_the_two_surfaces_stay_in_step(main_window: MainWindow) -> None:
    """A change from the tool's bar reaches the panel and back (Navigation PRD 10.6)."""
    panel = main_window._property_panel
    scene = main_window._scene
    panel.show_canvas_section()
    main_window._tool_manager.activate("border")
    tool = main_window._tool_manager.tool("border")
    assert isinstance(tool, BorderTool)
    assert tool._width_spin is not None

    tool._width_spin.setValue(14)
    assert scene.border_width == 14
    assert panel._border_w_spin.value() == 14

    panel._border_w_spin.setValue(4)
    assert scene.border_width == 4
    assert tool._width_spin.value() == 4


def test_switching_away_and_back_does_not_touch_dead_widgets(
    main_window: MainWindow, qtbot: QtBot
) -> None:
    """The bar destroys its widgets on a tool change; reactivation reads the scene first.

    Reproduces the RuntimeError ("wrapped C/C++ object of type QSpinBox has been
    deleted") Doug hit on the first display run.
    """
    manager = main_window._tool_manager
    scene = main_window._scene

    manager.activate("border")
    tool = manager.tool("border")
    assert isinstance(tool, BorderTool)
    assert tool._width_spin is not None
    tool._width_spin.setValue(9)
    assert scene.border_width == 9

    manager.activate("select")
    # The bar retires its widgets with deleteLater, so the event loop has to run before
    # the C++ objects actually go; without this the crash cannot be reproduced headless.
    qtbot.wait(1)
    manager.activate("border")  # crashed here before

    assert tool._width_spin is not None
    assert tool._width_spin.value() == 9
    tool._width_spin.setValue(3)
    assert scene.border_width == 3


def test_a_border_change_while_another_tool_is_active_is_harmless(
    main_window: MainWindow, qtbot: QtBot
) -> None:
    """The scene's border signal reaches a tool whose widgets the bar has destroyed."""
    manager = main_window._tool_manager
    scene = main_window._scene
    manager.activate("border")
    manager.activate("rectangle")
    qtbot.wait(1)
    scene.set_border_width(7)  # the Border tool is disconnected, but the panel is not
    assert scene.border_width == 7
