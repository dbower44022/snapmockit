"""Exporter — export scene to PNG, JPG, SVG, PDF, and print the flattened canvas.

The Export dialog (General UI PRD 11.2) drives :func:`export_scene` with an
:class:`ExportSettings`; the older one-call-per-format functions remain for
callers that need a plain PNG or JPG of the whole canvas.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QBuffer, QIODevice, QMarginsF, QRectF, QSize, QSizeF
from PyQt6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPaintDevice, QPainter

from snapmock.config.constants import APP_NAME
from snapmock.core.render_engine import RenderEngine

if TYPE_CHECKING:
    from collections.abc import Iterable

    from PyQt6.QtWidgets import QGraphicsItem

    from snapmock.core.scene import SnapScene

BASE_DPI = 72
"""Scene units are pixels at this resolution; export DPI scales from it."""

DPI_CHOICES: tuple[int, ...] = (72, 150, 300)
PNG_COLOR_DEPTHS: tuple[int, ...] = (8, 16)
INCHES_PER_METRE = 39.3701


class ExportFormat(StrEnum):
    """The formats the Export dialog offers. ``SMK`` is the Library's copy-the-file format."""

    PNG = "png"
    JPEG = "jpeg"
    SVG = "svg"
    PDF = "pdf"
    SMK = "smk"

    @property
    def label(self) -> str:
        labels = {"png": "PNG", "jpeg": "JPEG", "svg": "SVG", "pdf": "PDF"}
        labels["smk"] = f"{APP_NAME} Project"
        return labels[self.value]

    @property
    def suffix(self) -> str:
        return {"png": ".png", "jpeg": ".jpg", "svg": ".svg", "pdf": ".pdf", "smk": ".smk"}[
            self.value
        ]

    @property
    def file_filter(self) -> str:
        return {
            "png": "PNG Image (*.png)",
            "jpeg": "JPEG Image (*.jpg *.jpeg)",
            "svg": "SVG Image (*.svg)",
            "pdf": "PDF Document (*.pdf)",
            "smk": f"{APP_NAME} Project (*.smk)",
        }[self.value]

    @classmethod
    def from_suffix(cls, suffix: str) -> ExportFormat | None:
        table = {".png": cls.PNG, ".jpg": cls.JPEG, ".jpeg": cls.JPEG, ".svg": cls.SVG}
        table.update({".pdf": cls.PDF, ".smk": cls.SMK})
        return table.get(suffix.lower())


class ExportRegion(StrEnum):
    CANVAS = "canvas"
    SELECTION = "selection"
    VISIBLE = "visible"


class PdfPageSize(StrEnum):
    CANVAS = "canvas"
    A4 = "a4"
    LETTER = "letter"

    @property
    def label(self) -> str:
        return {"canvas": "Match canvas", "a4": "A4", "letter": "Letter"}[self.value]


@dataclass
class ExportSettings:
    """Every option of the Export dialog; one instance is remembered per format."""

    format: ExportFormat = ExportFormat.PNG
    region: ExportRegion = ExportRegion.CANVAS
    dpi: int = BASE_DPI
    png_transparency: bool = True
    png_color_depth: int = 8
    jpeg_quality: int = 90
    svg_embed_raster: bool = True
    pdf_page_size: PdfPageSize = PdfPageSize.CANVAS

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["format"] = self.format.value
        data["region"] = self.region.value
        data["pdf_page_size"] = self.pdf_page_size.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ExportSettings:
        """Build settings from a stored mapping; unknown or bad values fall back to defaults."""
        base = cls()
        try:
            fmt = ExportFormat(str(data.get("format", base.format.value)))
        except ValueError:
            fmt = base.format
        try:
            region = ExportRegion(str(data.get("region", base.region.value)))
        except ValueError:
            region = base.region
        try:
            page = PdfPageSize(str(data.get("pdf_page_size", base.pdf_page_size.value)))
        except ValueError:
            page = base.pdf_page_size
        return cls(
            format=fmt,
            region=region,
            dpi=_clamp_int(data.get("dpi"), 1, 2400, base.dpi),
            png_transparency=_as_bool(data.get("png_transparency"), base.png_transparency),
            png_color_depth=16 if _clamp_int(data.get("png_color_depth"), 8, 16, 8) == 16 else 8,
            jpeg_quality=_clamp_int(data.get("jpeg_quality"), 1, 100, base.jpeg_quality),
            svg_embed_raster=_as_bool(data.get("svg_embed_raster"), base.svg_embed_raster),
            pdf_page_size=page,
        )

    def with_format(self, fmt: ExportFormat) -> ExportSettings:
        return replace(self, format=fmt)

    @property
    def scale(self) -> float:
        return self.dpi / BASE_DPI


def _clamp_int(value: object, low: int, high: int, default: int) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)


# --- regions ---------------------------------------------------------------


def selection_rect(items: Iterable[QGraphicsItem]) -> QRectF:
    """The scene-space bounding rectangle of *items*; null when there are none."""
    united = QRectF()
    for item in items:
        united = united.united(item.sceneBoundingRect())
    return united


def resolve_region(
    scene: SnapScene,
    region: ExportRegion,
    *,
    selection: QRectF | None = None,
    visible: QRectF | None = None,
) -> QRectF:
    """The scene rectangle an export of *region* covers, clipped to the canvas.

    A Selection Only or Visible Area Only export with nothing to clip to falls
    back to the whole canvas; the dialog checks the requirement before it gets here.
    """
    canvas = scene.canvas_rect
    chosen: QRectF | None = None
    if region is ExportRegion.SELECTION:
        chosen = selection
    elif region is ExportRegion.VISIBLE:
        chosen = visible
    if chosen is None or chosen.isEmpty():
        return QRectF(canvas)
    clipped = chosen.intersected(canvas)
    return clipped if not clipped.isEmpty() else QRectF(canvas)


# --- rendering -------------------------------------------------------------


def _opaque_background(scene: SnapScene) -> QColor:
    """The canvas colour with its alpha removed; white when the canvas is fully transparent."""
    color = QColor(scene.background_color)
    if color.alpha() == 0:
        return QColor("white")
    color.setAlpha(255)
    return color


def render_export_image(scene: SnapScene, settings: ExportSettings, region: QRectF) -> QImage:
    """The flattened raster of *region* as the PNG or JPEG export would write it."""
    transparent = settings.format is ExportFormat.PNG and settings.png_transparency
    background = scene.background_color if transparent else _opaque_background(scene)
    image = RenderEngine(scene).render_region(region, background=background, scale=settings.scale)
    dots_per_metre = round(settings.dpi * INCHES_PER_METRE)
    image.setDotsPerMeterX(dots_per_metre)
    image.setDotsPerMeterY(dots_per_metre)
    if settings.format is ExportFormat.PNG and settings.png_color_depth == 16:
        image = image.convertToFormat(QImage.Format.Format_RGBA64)
    elif settings.format is ExportFormat.JPEG:
        image = image.convertToFormat(QImage.Format.Format_RGB32)
    return image


def _raster_items(scene: SnapScene) -> list[QGraphicsItem]:
    from snapmock.items.raster_region_item import RasterRegionItem
    from snapmock.items.stamp_item import StampItem

    # Members included: a raster inside a group is hidden with the rest
    return [i for i in scene.all_annotation_items() if isinstance(i, RasterRegionItem | StampItem)]


def _paint_canvas_colour(
    painter: QPainter, scene: SnapScene, target: QRectF, region: QRectF
) -> None:
    """Fill the canvas's part of *target* with the canvas colour (General UI PRD 6.2).

    The scene draws no background of its own: the view paints the canvas colour, and the
    raster exports fill their image first. The SVG and PDF exports paint it here, so a
    blended layer has the canvas beneath it as it has on the display.
    """
    colour = scene.background_color
    if colour.alpha() == 0 or region.isEmpty():
        return
    canvas = scene.canvas_rect.intersected(region)
    if canvas.isEmpty():
        return
    sx = target.width() / region.width()
    sy = target.height() / region.height()
    fill = QRectF(
        target.left() + (canvas.left() - region.left()) * sx,
        target.top() + (canvas.top() - region.top()) * sy,
        canvas.width() * sx,
        canvas.height() * sy,
    )
    painter.fillRect(fill, colour)


def _write_svg(scene: SnapScene, settings: ExportSettings, region: QRectF, target: object) -> None:
    from PyQt6.QtSvg import QSvgGenerator

    generator = QSvgGenerator()
    if isinstance(target, Path):
        generator.setFileName(str(target))
    else:
        generator.setOutputDevice(target)  # type: ignore[arg-type]
    generator.setResolution(BASE_DPI)
    generator.setSize(QSize(round(region.width()), round(region.height())))
    generator.setViewBox(QRectF(0, 0, region.width(), region.height()))
    generator.setTitle(scene.objectName() or f"{APP_NAME} export")
    hidden: list[QGraphicsItem] = []
    if not settings.svg_embed_raster:
        hidden = [i for i in _raster_items(scene) if i.isVisible()]
        for item in hidden:
            item.setVisible(False)
    try:
        painter = QPainter(generator)
        target = QRectF(0, 0, region.width(), region.height())
        _paint_canvas_colour(painter, scene, target, region)
        scene.render(painter, target=target, source=region)
        painter.end()
    finally:
        for item in hidden:
            item.setVisible(True)


def pdf_page_layout(settings: ExportSettings, region: QRectF) -> QPageLayout:
    """The page for a PDF export: the region's own size, or A4 / Letter turned to fit it."""
    landscape = region.width() > region.height()
    if settings.pdf_page_size is PdfPageSize.CANVAS:
        # Scene pixels are points at BASE_DPI, so the page is the region's size exactly.
        page = QPageSize(QSizeF(region.width(), region.height()), QPageSize.Unit.Point)
        return QPageLayout(page, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))
    page_id = (
        QPageSize.PageSizeId.A4
        if settings.pdf_page_size is PdfPageSize.A4
        else QPageSize.PageSizeId.Letter
    )
    orientation = (
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait
    )
    return QPageLayout(QPageSize(page_id), orientation, QMarginsF(0, 0, 0, 0))


def _write_pdf(scene: SnapScene, settings: ExportSettings, region: QRectF, path: Path) -> None:
    from PyQt6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setResolution(settings.dpi)
    printer.setPageLayout(pdf_page_layout(settings, region))
    painter = QPainter(printer)
    device = painter.device()
    page = QRectF(0, 0, device.width(), device.height())  # type: ignore[union-attr]
    target = fit_to_page(QSizeF(region.width(), region.height()), page)
    _paint_canvas_colour(painter, scene, target, region)
    scene.render(painter, target=target, source=region)
    painter.end()


def export_scene(
    scene: SnapScene,
    path: Path,
    settings: ExportSettings,
    region: QRectF | None = None,
    *,
    source_file: Path | None = None,
) -> None:
    """Write *scene* to *path* in ``settings.format``.

    *region* is the scene rectangle to export (the whole canvas when None).
    ``ExportFormat.SMK`` copies *source_file* instead of rendering.
    """
    rect = region if region is not None and not region.isEmpty() else scene.canvas_rect
    fmt = settings.format
    if fmt is ExportFormat.SMK:
        if source_file is None:
            raise ValueError("SMK export needs the project file to copy")
        if source_file.resolve() != path.resolve():
            shutil.copyfile(source_file, path)
        return
    if fmt is ExportFormat.SVG:
        _write_svg(scene, settings, rect, path)
        return
    if fmt is ExportFormat.PDF:
        _write_pdf(scene, settings, rect, path)
        return
    image = render_export_image(scene, settings, rect)
    if fmt is ExportFormat.JPEG:
        image.save(str(path), "JPEG", settings.jpeg_quality)
    else:
        image.save(str(path), "PNG")


def estimate_export_size(
    scene: SnapScene,
    settings: ExportSettings,
    region: QRectF | None = None,
    *,
    source_file: Path | None = None,
) -> int:
    """The byte count the export would write, produced by encoding it in memory.

    PDF has to go through a temporary file; SMK is the size of the file copied.
    """
    rect = region if region is not None and not region.isEmpty() else scene.canvas_rect
    fmt = settings.format
    if fmt is ExportFormat.SMK:
        if source_file is None or not source_file.exists():
            return 0
        return source_file.stat().st_size
    if fmt is ExportFormat.PDF:
        handle, name = tempfile.mkstemp(suffix=".pdf", prefix="snapmock-estimate-")
        os.close(handle)
        try:
            _write_pdf(scene, settings, rect, Path(name))
            return Path(name).stat().st_size
        finally:
            Path(name).unlink(missing_ok=True)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if fmt is ExportFormat.SVG:
        _write_svg(scene, settings, rect, buffer)
    else:
        image = render_export_image(scene, settings, rect)
        if fmt is ExportFormat.JPEG:
            image.save(buffer, "JPEG", settings.jpeg_quality)
        else:
            image.save(buffer, "PNG")
    size = buffer.size()
    buffer.close()
    return size


def format_byte_size(size: int) -> str:
    """``1.2 MB`` style text for the Export dialog's size estimate."""
    if size < 1024:
        return f"{size} B"
    value = size / 1024
    for unit in ("KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if value < 100 else f"{value:.0f} {unit}"
        value /= 1024
    return f"{size} B"  # pragma: no cover - unreachable


# --- whole-canvas convenience exports --------------------------------------


def export_png(scene: SnapScene, path: Path, background: QColor | None = None) -> None:
    """Export the scene to a PNG file."""
    engine = RenderEngine(scene)
    img = engine.render_to_image(background=background)
    img.save(str(path), "PNG")


def export_jpg(
    scene: SnapScene, path: Path, quality: int = 90, background: QColor | None = None
) -> None:
    """Export the scene to a JPG file."""
    engine = RenderEngine(scene)
    bg = background if background is not None else QColor("white")
    img = engine.render_to_image(background=bg)
    img.save(str(path), "JPEG", quality)


def export_pdf(scene: SnapScene, path: Path) -> None:
    """Export the whole canvas to a PDF file at its own page size."""
    export_scene(scene, path, ExportSettings(format=ExportFormat.PDF))


def export_svg(scene: SnapScene, path: Path) -> None:
    """Export the whole canvas to an SVG file."""
    export_scene(scene, path, ExportSettings(format=ExportFormat.SVG))


# --- printing --------------------------------------------------------------


def fit_to_page(content: QSizeF, page: QRectF) -> QRectF:
    """The largest rectangle of *content*'s aspect ratio centred inside *page* (PRD 3.1 Print)."""
    if content.width() <= 0 or content.height() <= 0 or page.isEmpty():
        return QRectF()
    scale = min(page.width() / content.width(), page.height() / content.height())
    w = content.width() * scale
    h = content.height() * scale
    return QRectF(page.left() + (page.width() - w) / 2, page.top() + (page.height() - h) / 2, w, h)


def print_scene(scene: SnapScene, device: QPaintDevice, page: QRectF | None = None) -> QRectF:
    """Paint the flattened canvas onto a printer or any paint device, scaled to fit the page.

    Returns the rectangle the canvas was painted into, in device pixels.
    """
    engine = RenderEngine(scene)
    image = engine.render_to_image(background=scene.background_color)
    target_page = page if page is not None else QRectF(0, 0, device.width(), device.height())
    target = fit_to_page(QSizeF(image.size()), target_page)
    painter = QPainter(device)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(target, image)
    painter.end()
    return target
