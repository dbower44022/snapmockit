"""Tests for LibraryModel, LibraryPanel, and the library wiring in MainWindow."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QMimeData, QModelIndex, QRectF, Qt
from PyQt6.QtGui import QAction, QColor, QImage
from PyQt6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from snapmock.commands.add_item import AddItemCommand
from snapmock.config.constants import LIBRARY_PATHS_MIME
from snapmock.config.settings import AppSettings
from snapmock.io.project_serializer import load_project, read_library_metadata
from snapmock.items.rectangle_item import RectangleItem
from snapmock.library import manager as manager_module
from snapmock.library.commands import DeleteLibraryFileCommand
from snapmock.library.manager import LibraryManager
from snapmock.library.model import (
    COL_NAME,
    IS_FOLDER_ROLE,
    PATH_ROLE,
    LibraryModel,
    human_size,
)
from snapmock.main_window import MainWindow
from snapmock.ui.library_panel import LibraryPanel
from snapmock.ui.preferences_dialog import PreferencesDialog


@pytest.fixture()
def library(qapp: QApplication, tmp_path: Path) -> LibraryManager:
    return LibraryManager(tmp_path / "Lib")


@pytest.fixture()
def panel(qtbot: QtBot, library: LibraryManager) -> LibraryPanel:
    p = LibraryPanel(library, AppSettings())
    qtbot.addWidget(p)
    return p


def _image() -> QImage:
    img = QImage(20, 10, QImage.Format.Format_ARGB32)
    img.fill(QColor("blue"))
    return img


# --- model ---


def test_human_size() -> None:
    assert human_size(512) == "512 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(1_300_000) == "1.2 MB"


def test_model_lists_folders_first_then_files(library: LibraryManager) -> None:
    library.create_blank(10, 10)
    library.create_folder(name="Zeta")
    model = LibraryModel(library)
    model.refresh()
    assert model.rowCount() == 2
    assert bool(model.index(0, COL_NAME).data(IS_FOLDER_ROLE)) is True
    assert bool(model.index(1, COL_NAME).data(IS_FOLDER_ROLE)) is False
    assert model.folder_count == 1
    assert model.file_count == 1


def test_model_filter_and_counts(library: LibraryManager) -> None:
    a = library.create_blank(10, 10)
    library.rename_file(a, "Alpha")
    b = library.create_blank(10, 10)
    library.rename_file(b, "Beta")
    model = LibraryModel(library)
    model.refresh()
    model.set_filter("alp")
    assert model.file_count == 1
    assert model.total_file_count == 2
    assert model.index(0, COL_NAME).data(Qt.ItemDataRole.DisplayRole) == "Alpha"
    model.set_filter("")
    assert model.file_count == 2


def test_model_sort_by_name(library: LibraryManager) -> None:
    for name in ("b", "c", "a"):
        p = library.create_blank(10, 10)
        library.rename_file(p, name)
    model = LibraryModel(library)
    model.set_sort_id("name_asc")
    names = [model.index(r, COL_NAME).data() for r in range(model.rowCount())]
    assert names == ["a", "b", "c"]
    model.set_sort_id("name_desc")
    names = [model.index(r, COL_NAME).data() for r in range(model.rowCount())]
    assert names == ["c", "b", "a"]
    assert model.sort_id == "name_desc"


def test_model_navigation_and_breadcrumbs(library: LibraryManager) -> None:
    sub = library.create_folder(name="Sub")
    model = LibraryModel(library)
    assert model.can_go_up is False
    model.navigate_to(sub)
    assert model.current_path == sub
    assert [c[0] for c in model.breadcrumbs()] == [library.root.name, "Sub"]
    assert model.can_go_up is True
    model.go_up()
    assert model.current_path == library.root


def test_model_internal_drop_emits_move(library: LibraryManager, qtbot: QtBot) -> None:
    file = library.create_blank(10, 10)
    library.create_folder(name="Target")
    model = LibraryModel(library)
    model.set_sort_id("name_asc")
    folder_idx = model.index(0, COL_NAME)
    assert bool(folder_idx.data(IS_FOLDER_ROLE))
    mime = QMimeData()
    mime.setData(LIBRARY_PATHS_MIME, str(file).encode())
    with qtbot.waitSignal(model.move_requested) as blocker:
        assert model.dropMimeData(mime, Qt.DropAction.MoveAction, -1, -1, folder_idx)
    assert blocker.args[0] == [file]
    assert blocker.args[1] == folder_idx.data(PATH_ROLE)


def test_model_external_drop_emits_import(
    library: LibraryManager, qtbot: QtBot, tmp_path: Path
) -> None:
    img = tmp_path / "pic.png"
    _image().save(str(img))
    model = LibraryModel(library)
    mime = QMimeData()
    from PyQt6.QtCore import QUrl

    mime.setUrls([QUrl.fromLocalFile(str(img)), QUrl.fromLocalFile(str(tmp_path / "x.txt"))])
    with qtbot.waitSignal(model.import_requested) as blocker:
        assert model.dropMimeData(mime, Qt.DropAction.CopyAction, -1, -1, QModelIndex())
    assert blocker.args[0] == [img]
    assert blocker.args[1] == library.root


def test_model_rename_via_set_data(library: LibraryManager, qtbot: QtBot) -> None:
    file = library.create_blank(10, 10)
    model = LibraryModel(library)
    idx = model.index(0, COL_NAME)
    with qtbot.waitSignal(model.rename_requested) as blocker:
        assert model.setData(idx, "Fresh", Qt.ItemDataRole.EditRole)
    assert blocker.args == [file, "Fresh"]


def test_model_decoration_is_pixmap(library: LibraryManager) -> None:
    library.create_from_image(_image())
    model = LibraryModel(library)
    model.set_thumb_size(96)
    pix = model.index(0, COL_NAME).data(Qt.ItemDataRole.DecorationRole)
    assert pix is not None and pix.width() == 96


# --- panel ---


def test_panel_initial_state(panel: LibraryPanel) -> None:
    assert panel.view_mode in ("grid", "list")
    assert panel.current_path == panel.manager.root
    assert panel._count_label.text().startswith("0 file")  # noqa: SLF001
    assert panel._stack.currentWidget() is panel._empty  # noqa: SLF001


def test_panel_shows_files_and_footer(panel: LibraryPanel) -> None:
    panel.manager.create_blank(10, 10)
    panel.manager.create_folder(name="Sub")
    assert panel.model.rowCount() == 2
    assert panel._count_label.text() == "1 file in 1 folder"  # noqa: SLF001
    assert panel._stack.currentWidget() is not panel._empty  # noqa: SLF001


def test_panel_view_mode_persists(panel: LibraryPanel) -> None:
    panel.set_view_mode("list")
    assert panel.view_mode == "list"
    assert AppSettings().library_view_mode() == "list"
    assert panel._size_slider.minimum() == 48  # noqa: SLF001
    panel.set_view_mode("grid")
    assert panel._size_slider.minimum() == 80  # noqa: SLF001


def test_panel_sort_persists(panel: LibraryPanel) -> None:
    panel.set_sort_id("size_asc")
    assert panel.model.sort_id == "size_asc"
    assert AppSettings().library_sort() == "size_asc"
    assert panel._sort_combo.currentData() == "size_asc"  # noqa: SLF001


def test_panel_rename_pushes_undoable_command(panel: LibraryPanel) -> None:
    file = panel.manager.create_blank(10, 10)
    panel.model.rename_requested.emit(file, "Renamed")
    assert (panel.manager.root / "Renamed.smk").exists()
    panel.manager.command_stack.undo()
    assert file.exists()


def test_panel_create_folder_and_select_path(panel: LibraryPanel) -> None:
    panel.create_folder()
    assert (panel.manager.root / "New Folder").is_dir()
    file = panel.manager.create_blank(10, 10)
    panel.select_path(file)
    assert panel.selected_paths() == [file]


def test_panel_select_all_files_skips_folders(panel: LibraryPanel) -> None:
    panel.manager.create_folder(name="A")
    f1 = panel.manager.create_blank(10, 10)
    f2 = panel.manager.create_blank(10, 10)
    panel.select_all_files()
    assert set(panel.selected_paths()) == {f1, f2}


def test_panel_copy_paste_files(panel: LibraryPanel) -> None:
    file = panel.manager.create_blank(10, 10)
    panel.select_path(file)
    panel.copy_selected_files()
    panel.paste_files()
    assert (panel.manager.root / f"{file.stem} (Copy).smk").exists()


def test_panel_delete_pushes_undoable_command(
    panel: LibraryPanel, library: LibraryManager, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    path = library.create_blank(10, 10)
    with qtbot.waitSignal(panel.files_about_to_be_deleted) as blocker:
        panel.delete_paths([path])
    assert blocker.args == [[path]]
    assert not path.exists()
    assert library.command_stack.undo_text == f"Delete {path.stem}"
    assert library.list_files() == []
    library.command_stack.undo()
    assert path.exists()
    assert [f.file_path for f in library.list_files()] == [path]


def test_panel_delete_cancelled_pushes_nothing(
    panel: LibraryPanel, library: LibraryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    path = library.create_blank(10, 10)
    panel.delete_paths([path])
    assert path.exists() and not library.command_stack.can_undo


def test_panel_double_click_opens_file(panel: LibraryPanel, qtbot: QtBot) -> None:
    file = panel.manager.create_blank(10, 10)
    idx = panel.model.index(0, COL_NAME)
    with qtbot.waitSignal(panel.open_requested) as blocker:
        panel._on_double_clicked(idx)  # noqa: SLF001
    assert blocker.args[0] == [file]


def test_panel_double_click_folder_navigates(panel: LibraryPanel) -> None:
    sub = panel.manager.create_folder(name="Sub")
    idx = panel.model.index(0, COL_NAME)
    panel._on_double_clicked(idx)  # noqa: SLF001
    assert panel.current_path == sub
    assert panel._back_btn.isEnabled()  # noqa: SLF001


def test_panel_import_drops_create_files(panel: LibraryPanel, tmp_path: Path) -> None:
    img = tmp_path / "shot.png"
    _image().save(str(img))
    panel._import_paths([img], panel.current_path)  # noqa: SLF001
    files = panel.manager.list_files()
    assert len(files) == 1 and files[0].display_name.startswith("Import_")


def test_panel_copy_png_to_clipboard(panel: LibraryPanel, qapp: QApplication) -> None:
    file = panel.manager.create_from_image(_image())
    panel.select_path(file)
    panel.copy_selected_png_to_clipboard()
    cb = qapp.clipboard()
    assert cb is not None
    assert not cb.image().isNull()


# --- main window integration ---


def test_window_has_library_panel_and_menu(main_window: MainWindow) -> None:
    assert main_window.library_panel is not None
    assert main_window.library.root == AppSettings().library_directory()
    assert main_window.library.root.is_dir()


def test_open_library_file_is_written_back(main_window: MainWindow) -> None:
    path = main_window.library.create_blank(300, 200)
    doc = main_window._open_project(path)  # noqa: SLF001
    assert doc is not None and doc.is_library_file
    assert doc.tab_title == doc.display_name  # never dirty
    layer = doc.scene.layer_manager.active_layer
    assert layer is not None
    doc.scene.command_stack.push(
        AddItemCommand(doc.scene, RectangleItem(rect=QRectF(0, 0, 5, 5)), layer.layer_id)
    )
    assert doc.is_dirty is False
    assert main_window.library.has_pending_writes
    main_window.library.flush()
    reloaded = load_project(path)
    assert any(isinstance(i, RectangleItem) for i in reloaded.items())


def test_open_library_file_from_panel_signal(main_window: MainWindow) -> None:
    path = main_window.library.create_blank(10, 10)
    main_window.library_panel.open_requested.emit([path])
    assert main_window.active_document.file_path == path
    assert main_window.documents.find_by_path(path) is not None


def test_deleting_open_library_file_closes_its_tab(main_window: MainWindow) -> None:
    path = main_window.library.create_blank(10, 10)
    main_window._open_project(path)  # noqa: SLF001
    assert main_window.documents.count == 1
    main_window.library_panel.files_about_to_be_deleted.emit([path])
    assert main_window.documents.find_by_path(path) is None
    assert main_window.documents.count == 1
    assert main_window.active_document.display_name == "Untitled"


def test_window_close_purges_session_trash(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[Path] = []

    def _send(p: str) -> None:
        sent.append(Path(p))
        Path(p).unlink()

    monkeypatch.setattr(manager_module, "send2trash", _send)
    window = MainWindow()
    qtbot.addWidget(window)
    path = window.library.create_blank(10, 10)
    cmd = DeleteLibraryFileCommand(window.library, [path])
    window.library.command_stack.push(cmd)
    held = cmd.trash_paths[0]
    assert held.exists()
    window.close()
    assert sent == [held]
    assert not window.library.session_trash_dir.exists()


def test_new_canvas_in_library(main_window: MainWindow) -> None:
    main_window.library_panel.new_canvas_requested.emit(main_window.library.root)
    doc = main_window.active_document
    assert doc.is_library_file
    assert doc.file_path is not None and doc.file_path.name.startswith("Untitled_")
    meta = read_library_metadata(doc.file_path)
    assert meta is not None and meta["source"] == "new"


def _library_menu_texts(main_window: MainWindow) -> list[str]:
    menu_bar = main_window.menuBar()
    assert menu_bar is not None
    for menu_action in menu_bar.actions():
        if menu_action.text().replace("&", "") != "Library":
            continue
        menu = menu_action.menu()
        assert menu is not None
        return [a.text().replace("&", "") for a in menu.actions()]
    raise AssertionError("No Library menu")


def _library_menu_action(main_window: MainWindow, text: str) -> QAction:
    menu_bar = main_window.menuBar()
    assert menu_bar is not None
    for menu_action in menu_bar.actions():
        menu = menu_action.menu()
        if menu is None or menu_action.text().replace("&", "") != "Library":
            continue
        for action in menu.actions():
            if action.text().replace("&", "") == text:
                return action
    raise AssertionError(f"No Library menu item named {text!r}")


def test_library_menu_new_canvas_uses_shown_folder(main_window: MainWindow) -> None:
    sub = main_window.library.create_folder(name="Sub")
    main_window.library_panel.model.navigate_to(sub)
    assert main_window.library_panel.current_path == sub
    texts = _library_menu_texts(main_window)
    assert texts.index("New Canvas") == texts.index("New Folder") + 1
    _library_menu_action(main_window, "New Canvas").trigger()
    doc = main_window.active_document
    assert doc.is_library_file
    assert doc.file_path is not None and doc.file_path.parent == sub
    assert doc.file_path.name.startswith("Untitled_")
    meta = read_library_metadata(doc.file_path)
    assert meta is not None and meta["source"] == "new"


def test_add_to_library_auto_opens(main_window: MainWindow) -> None:
    AppSettings().set_library_auto_open(True)
    path = main_window.add_to_library(_image(), source="capture")
    assert path is not None and path.name.startswith("Capture_")
    assert main_window.active_document.file_path == path
    AppSettings().set_library_auto_open(False)
    path2 = main_window.add_to_library(_image(), source="capture")
    assert path2 is not None
    assert main_window.active_document.file_path == path


def test_session_restore_reopens_tabs(qtbot: QtBot) -> None:
    w1 = MainWindow()
    qtbot.addWidget(w1)
    a = w1.library.create_blank(10, 10)
    b = w1.library.create_blank(10, 10)
    w1._open_project(a)  # noqa: SLF001
    w1._open_project(b)  # noqa: SLF001
    w1.documents.set_active_index(0)
    w1._save_session()  # noqa: SLF001

    w2 = MainWindow(restore_session=True)
    qtbot.addWidget(w2)
    paths = [d.file_path for d in w2.documents.documents]
    assert paths == [a, b]
    assert w2.active_document.file_path == a


def test_reveal_in_library_selects_file(main_window: MainWindow) -> None:
    path = main_window.library.create_blank(10, 10)
    doc = main_window._open_project(path)  # noqa: SLF001
    assert doc is not None
    main_window._reveal_document_in_library(doc)  # noqa: SLF001
    assert main_window.library_panel.selected_paths() == [path]


def test_preferences_dialog_library_changes(qtbot: QtBot, tmp_path: Path) -> None:
    settings = AppSettings()
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg.get_changes() == {}
    dlg._library_auto_open_cb.setChecked(False)  # noqa: SLF001
    dlg._library_dir_edit.setText(str(tmp_path / "Other"))  # noqa: SLF001
    changes = dlg.get_changes()
    assert changes["library_auto_open"] == (True, False)
    assert changes["library_directory"][1] == str(tmp_path / "Other")


def test_apply_library_directory_preference(main_window: MainWindow, tmp_path: Path) -> None:
    new_dir = tmp_path / "Other"
    main_window._apply_preference_changes(  # noqa: SLF001
        {"library_directory": (str(main_window.library.root), str(new_dir))}
    )
    assert main_window.library.root == new_dir
    assert new_dir.is_dir()
    assert AppSettings().library_directory() == new_dir


# ---- the selection survives a library refresh (display run, finding 6) ---------------------


def _select(panel: LibraryPanel, row: int) -> None:
    from PyQt6.QtCore import QItemSelectionModel

    sel = panel._grid.selectionModel()  # noqa: SLF001
    assert sel is not None
    sel.select(
        panel._model.index(row, 0),  # noqa: SLF001
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )


def test_a_library_refresh_keeps_the_selection(
    panel: LibraryPanel, library: LibraryManager
) -> None:
    """A capture or a write-back between a right-click and the menu used to clear it."""
    first = library.create_from_image(_image())
    library.create_from_image(_image())
    panel.select_path(first)
    assert panel.selected_paths() == [first]

    library.files_changed.emit()  # what a capture, a write-back, or another window causes

    assert panel.selected_paths() == [first]


def test_delete_still_finds_the_selection_after_a_refresh(
    panel: LibraryPanel, library: LibraryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = library.create_from_image(_image())
    panel.select_path(path)
    library.files_changed.emit()

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    panel.delete_selected()

    assert not path.exists()


def test_a_file_that_went_away_is_not_selected_again(
    panel: LibraryPanel, library: LibraryManager
) -> None:
    path = library.create_from_image(_image())
    panel.select_path(path)
    path.unlink()

    library.files_changed.emit()

    assert panel.selected_paths() == []
