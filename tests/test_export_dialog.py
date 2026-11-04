"""The Export dialog and its callers (General UI PRD 3.1, 11.2, 15.4; Library PRD 7.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot

from snapmock.config.settings import AppSettings
from snapmock.core.scene import SnapScene
from snapmock.io.exporter import ExportFormat, ExportRegion, ExportSettings, PdfPageSize
from snapmock.io.project_serializer import save_project
from snapmock.main_window import MainWindow
from snapmock.ui import export_dialog as export_dialog_module
from snapmock.ui.export_dialog import ExportDialog


@pytest.fixture()
def app_settings() -> AppSettings:
    return AppSettings()


@pytest.fixture()
def dialog(qtbot: QtBot, app_settings: AppSettings, tmp_path: Path) -> ExportDialog:
    scene = SnapScene(width=400, height=300)
    dlg = ExportDialog(
        scene,
        app_settings,
        document_name="Mockup",
        document_directory=tmp_path,
        selection=None,
        visible=QRectF(0, 0, 200, 150),
    )
    qtbot.addWidget(dlg)
    return dlg


def _choose(dlg: ExportDialog, fmt: ExportFormat) -> None:
    dlg._format_buttons[fmt].click()  # noqa: SLF001


def test_default_path_and_format_switch(dialog: ExportDialog, tmp_path: Path) -> None:
    assert dialog.current_format() is ExportFormat.PNG
    assert dialog.output_path() == tmp_path / "Mockup.png"
    _choose(dialog, ExportFormat.JPEG)
    assert dialog.output_path() == tmp_path / "Mockup.jpg"
    assert dialog._options.currentWidget() is dialog._pages[ExportFormat.JPEG]  # noqa: SLF001
    # A user-edited path keeps its directory and name; only the suffix follows the format.
    dialog._path_edit.setText(str(tmp_path / "out" / "final.jpg"))  # noqa: SLF001
    dialog._on_path_edited("")  # noqa: SLF001
    _choose(dialog, ExportFormat.PDF)
    assert dialog.output_path() == tmp_path / "out" / "final.pdf"
    assert dialog._pdf_orientation.text().startswith("Landscape")  # noqa: SLF001
    _choose(dialog, ExportFormat.SVG)
    assert dialog._svg_viewbox.text() == "0 0 400 300"  # noqa: SLF001


def test_custom_dpi_shows_spinbox(dialog: ExportDialog) -> None:
    dpi = dialog._png_dpi  # noqa: SLF001
    assert not dpi.is_custom()
    dpi.set_value(96)
    assert dpi.is_custom()
    assert dpi.value() == 96
    assert dialog.settings().dpi == 96
    dpi.set_value(300)
    assert not dpi.is_custom()
    assert dialog.settings().dpi == 300


def test_export_needs_a_path(dialog: ExportDialog, unmet_messages: list[tuple[str, str]]) -> None:
    dialog._path_edit.setText("")  # noqa: SLF001
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert unmet_messages == [("Export", "Export needs an output path.")]


def test_selection_only_needs_a_selection(
    dialog: ExportDialog, unmet_messages: list[tuple[str, str]]
) -> None:
    dialog._region_buttons[ExportRegion.SELECTION].click()  # noqa: SLF001
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert unmet_messages[-1][1] == "Export needs a selection on the canvas."
    dialog._region_buttons[ExportRegion.VISIBLE].click()  # noqa: SLF001
    assert dialog.region_rect() == QRectF(0, 0, 200, 150)


def test_accept_remembers_settings_per_format(
    qtbot: QtBot, dialog: ExportDialog, app_settings: AppSettings, tmp_path: Path
) -> None:
    _choose(dialog, ExportFormat.JPEG)
    dialog._jpeg_quality.setValue(35)  # noqa: SLF001
    dialog._jpeg_dpi.set_value(150)  # noqa: SLF001
    dialog._path_edit.setText(str(tmp_path / "exports" / "a.jpg"))  # noqa: SLF001
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert (tmp_path / "exports").is_dir()
    stored = app_settings.export_settings("jpeg")
    assert stored is not None
    remembered = ExportSettings.from_dict(stored)
    assert (remembered.jpeg_quality, remembered.dpi) == (35, 150)
    assert app_settings.export_last_directory("jpeg") == tmp_path / "exports"
    assert app_settings.export_last_format() == "jpeg"
    assert app_settings.export_settings("png") is None

    again = ExportDialog(SnapScene(), app_settings, document_name="Second")
    qtbot.addWidget(again)
    assert again.current_format() is ExportFormat.JPEG
    assert again.settings().jpeg_quality == 35
    assert again.output_path() == tmp_path / "exports" / "Second.jpg"


def test_library_variant_has_directory_apply_to_all_and_smk(
    qtbot: QtBot, app_settings: AppSettings, tmp_path: Path
) -> None:
    files = [tmp_path / "a.smk", tmp_path / "b.smk"]
    dlg = ExportDialog(SnapScene(), app_settings, library_files=files)
    qtbot.addWidget(dlg)
    assert ExportFormat.SMK in dlg.formats()
    assert not dlg._region_box.isVisibleTo(dlg)  # noqa: SLF001
    assert dlg._apply_all.isVisibleTo(dlg)  # noqa: SLF001
    assert dlg.apply_to_all()
    assert dlg.output_directory() == Path.home()
    dlg.set_output_directory(tmp_path)
    _choose(dlg, ExportFormat.SMK)
    assert dlg.output_directory() == tmp_path
    dlg._apply_all.setChecked(False)  # noqa: SLF001
    assert not dlg.apply_to_all()

    single = ExportDialog(SnapScene(), app_settings, document_name="One", library_files=files[:1])
    qtbot.addWidget(single)
    assert not single._apply_all.isVisibleTo(single)  # noqa: SLF001
    assert single.output_path().name == "One.png"
    assert single.apply_to_all()


# --- MainWindow callers ---


def _accept_with(monkeypatch: pytest.MonkeyPatch, path: Path | None) -> list[ExportDialog]:
    """Make every Export dialog accept with *path* (or reject when None) and record it."""
    shown: list[ExportDialog] = []

    def _exec(self: ExportDialog) -> int:
        shown.append(self)
        if path is None:
            self.reject()
            return int(QDialog.DialogCode.Rejected)
        self._path_edit.setText(str(path))  # noqa: SLF001
        self.accept()
        return int(self.result())

    monkeypatch.setattr(export_dialog_module.ExportDialog, "exec", _exec)
    return shown


def test_file_export_writes_through_the_dialog(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "canvas.png"
    shown = _accept_with(monkeypatch, target)
    main_window._file_export()  # noqa: SLF001
    assert len(shown) == 1
    assert target.exists()


def test_export_quick_opens_the_dialog_first_then_uses_the_last_settings(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    shown = _accept_with(monkeypatch, None)
    main_window._file_export_quick_png()  # noqa: SLF001
    assert len(shown) == 1
    settings = AppSettings()
    settings.set_export_settings("png", ExportSettings(dpi=144).to_dict())
    settings.set_export_last_directory("png", tmp_path / "quick")
    (tmp_path / "quick").mkdir()
    main_window._file_export_quick_png()  # noqa: SLF001
    assert len(shown) == 1
    from PyQt6.QtGui import QImage

    out = tmp_path / "quick" / "Untitled.png"
    assert out.exists()
    image = QImage(str(out))
    assert image.width() == main_window._scene.canvas_size.width() * 2  # noqa: SLF001


def test_export_quick_writes_beside_a_saved_file(main_window: MainWindow, tmp_path: Path) -> None:
    project = tmp_path / "proj.smk"
    save_project(main_window._scene, project)  # noqa: SLF001
    main_window._active_document.file_path = project  # noqa: SLF001
    AppSettings().set_export_settings("png", ExportSettings().to_dict())
    main_window._file_export_quick_png()  # noqa: SLF001
    assert (tmp_path / "proj.png").exists()


def _library_files(tmp_path: Path) -> list[Path]:
    files = []
    for name, display in (("one", "First Capture"), ("two", None)):
        scene = SnapScene(width=50, height=40)
        path = tmp_path / f"{name}.smk"
        meta = {"display_name": display} if display else None
        save_project(scene, path, meta)
        files.append(path)
    return files


def test_library_batch_names_files_by_display_name(
    main_window: MainWindow, tmp_path: Path
) -> None:
    files = _library_files(tmp_path)
    out = tmp_path / "out"
    settings = ExportSettings(format=ExportFormat.JPEG, jpeg_quality=50)
    main_window._export_library_batch(files, out, settings)  # noqa: SLF001
    assert sorted(p.name for p in out.iterdir()) == ["First Capture.jpg", "two.jpg"]


def test_library_export_dialog_single_file_and_smk_copy(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = _library_files(tmp_path)
    shown: list[ExportDialog] = []

    def _exec(self: ExportDialog) -> int:
        shown.append(self)
        self._format_buttons[ExportFormat.SMK].click()  # noqa: SLF001
        self._path_edit.setText(str(tmp_path / "copies" / "kept.smk"))  # noqa: SLF001
        self.accept()
        return int(self.result())

    monkeypatch.setattr(export_dialog_module.ExportDialog, "exec", _exec)
    main_window._export_library_files(files[:1])  # noqa: SLF001
    assert len(shown) == 1
    assert (tmp_path / "copies" / "kept.smk").read_bytes() == files[0].read_bytes()


def test_library_export_dialog_batch_with_apply_to_all(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = _library_files(tmp_path)
    shown = _accept_with(monkeypatch, tmp_path / "batch")
    main_window._export_library_files(files)  # noqa: SLF001
    assert len(shown) == 1
    assert sorted(p.name for p in (tmp_path / "batch").iterdir()) == [
        "First Capture.png",
        "two.png",
    ]


def test_library_export_quick_uses_last_png_settings(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = _library_files(tmp_path)
    AppSettings().set_export_settings("png", ExportSettings(dpi=144).to_dict())
    monkeypatch.setattr(
        "snapmock.main_window.QFileDialog.getExistingDirectory",
        staticmethod(lambda *_a, **_k: str(tmp_path / "q")),
    )
    main_window._export_library_files_quick(files)  # noqa: SLF001
    from PyQt6.QtGui import QImage

    assert QImage(str(tmp_path / "q" / "two.png")).width() == 100
    assert AppSettings().export_last_directory("png") == tmp_path / "q"


def test_pdf_page_size_round_trips_through_the_dialog(dialog: ExportDialog) -> None:
    _choose(dialog, ExportFormat.PDF)
    index = dialog._pdf_page_size.findData(PdfPageSize.LETTER.value)  # noqa: SLF001
    dialog._pdf_page_size.setCurrentIndex(index)  # noqa: SLF001
    assert dialog.settings().pdf_page_size is PdfPageSize.LETTER


# --- preview and size estimate (PRD 11.2, last step of Phase 2) ---


def test_preview_and_size_estimate_follow_the_settings(dialog: ExportDialog) -> None:
    dialog._refresh_preview()  # noqa: SLF001
    pixmap = dialog.preview_pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert pixmap.width() <= export_dialog_module.PREVIEW_SIZE
    assert pixmap.height() <= export_dialog_module.PREVIEW_SIZE
    # 400 x 300 canvas keeps its aspect ratio in the thumbnail.
    assert pixmap.width() == export_dialog_module.PREVIEW_SIZE
    assert pixmap.height() == pytest.approx(export_dialog_module.PREVIEW_SIZE * 3 / 4, abs=1)
    png_text = dialog.size_estimate_text()
    assert png_text.startswith("≈ ") and png_text.endswith("400 × 300 px")

    dialog._png_dpi.set_value(150)  # noqa: SLF001
    dialog._refresh_preview()  # noqa: SLF001
    assert dialog.size_estimate_text().endswith("833 × 625 px")

    _choose(dialog, ExportFormat.SVG)
    dialog._refresh_preview()  # noqa: SLF001
    assert "px" not in dialog.size_estimate_text()
    assert dialog.size_estimate_text().startswith("≈ ")


def test_preview_is_debounced(qtbot: QtBot, dialog: ExportDialog) -> None:
    timer = dialog._preview_timer  # noqa: SLF001
    dialog._size_label.setText("stale")  # noqa: SLF001
    dialog._png_transparency.toggle()  # noqa: SLF001
    assert timer.isActive()
    assert dialog.size_estimate_text() == "stale"
    qtbot.waitUntil(lambda: dialog.size_estimate_text() != "stale", timeout=2000)
    assert not timer.isActive()


def test_preview_region_follows_the_radio(dialog: ExportDialog) -> None:
    dialog._region_buttons[ExportRegion.VISIBLE].click()  # noqa: SLF001
    dialog._refresh_preview()  # noqa: SLF001
    assert dialog.size_estimate_text().endswith("200 × 150 px")
    pixmap = dialog.preview_pixmap()
    assert pixmap is not None
    assert pixmap.width() == export_dialog_module.PREVIEW_SIZE
    assert pixmap.height() == pytest.approx(export_dialog_module.PREVIEW_SIZE * 3 / 4, abs=1)


def test_export_quick_puts_image_path_and_file_on_the_clipboard(
    main_window: MainWindow, tmp_path: Path
) -> None:
    """General UI PRD 3.1, version 2.69: one clipboard entry, three formats."""
    from PyQt6.QtWidgets import QApplication

    AppSettings().set_export_settings("png", ExportSettings().to_dict())
    AppSettings().set_export_last_directory("png", tmp_path)
    main_window._file_export_quick_png()  # noqa: SLF001
    out = (tmp_path / "Untitled.png").resolve()
    assert out.exists()
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    mime = clipboard.mimeData()
    assert mime is not None
    assert mime.text() == str(out)
    assert [url.toLocalFile() for url in mime.urls()] == [str(out)]
    assert mime.hasImage()
    assert main_window._status_bar._hint_label.text().endswith(str(out))  # noqa: SLF001


def test_export_quick_never_overwrites(main_window: MainWindow, tmp_path: Path) -> None:
    AppSettings().set_export_settings("png", ExportSettings().to_dict())
    AppSettings().set_export_last_directory("png", tmp_path)
    main_window._file_export_quick_png()  # noqa: SLF001
    main_window._file_export_quick_png()  # noqa: SLF001
    names = sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".png")
    assert len(names) == 2
    assert names[0].startswith("Untitled ") or names[1].startswith("Untitled ")
    assert "Untitled.png" in names


def test_unused_export_path_adds_time_then_counter(tmp_path: Path) -> None:
    from datetime import datetime

    from snapmock.main_window import unused_export_path

    now = datetime(2026, 10, 30, 1, 46, 12)
    target = tmp_path / "Capture.png"
    assert unused_export_path(target, now) == target
    target.touch()
    stamped = tmp_path / "Capture 2026-10-30 01-46-12.png"
    assert unused_export_path(target, now) == stamped
    stamped.touch()
    assert unused_export_path(target, now) == tmp_path / "Capture 2026-10-30 01-46-12 (2).png"
