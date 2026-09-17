"""Tests for LibraryManager, LibraryFileInfo, and library commands."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from snapmock.commands.add_item import AddItemCommand
from snapmock.core.document import Document
from snapmock.core.scene import SnapScene
from snapmock.io.project_serializer import (
    load_project,
    read_library_metadata,
    read_thumbnail,
    save_project,
)
from snapmock.items.rectangle_item import RectangleItem
from snapmock.library import manager as manager_module
from snapmock.library.commands import (
    CreateFolderCommand,
    DeleteLibraryFileCommand,
    MoveLibraryFileCommand,
    RenameLibraryFileCommand,
)
from snapmock.library.file_info import LibraryFileInfo
from snapmock.library.manager import LibraryManager


@pytest.fixture()
def library(qapp: QApplication, tmp_path: Path) -> LibraryManager:
    return LibraryManager(tmp_path / "Library")


def _fake_send2trash(sent: list[Path]) -> Callable[[str], None]:
    """Stand in for send2trash: record the path and remove it from disk."""

    def _send(p: str) -> None:
        path = Path(p)
        sent.append(path)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    return _send


def _image(w: int = 40, h: int = 30) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("red"))
    return img


def test_root_is_created(library: LibraryManager, tmp_path: Path) -> None:
    assert library.root == tmp_path / "Library"
    assert library.root.is_dir()


def test_auto_name_pattern() -> None:
    when = datetime(2026, 3, 1, 14, 23, 45)
    assert LibraryManager.auto_name("capture", when) == "Capture_2026-03-01_14-23-45"
    assert LibraryManager.auto_name("import", when) == "Import_2026-03-01_14-23-45"
    assert LibraryManager.auto_name("new", when) == "Untitled_2026-03-01_14-23-45"


def test_unique_file_path_adds_numeric_suffix(library: LibraryManager) -> None:
    first = library.unique_file_path(library.root, "Capture_x")
    first.write_bytes(b"")
    second = library.unique_file_path(library.root, "Capture_x")
    assert second.name == "Capture_x_2.smk"


def test_create_from_image_builds_two_layers_and_metadata(library: LibraryManager) -> None:
    when = datetime(2026, 3, 1, 14, 23, 45)
    path = library.create_from_image(_image(), source="capture", when=when)
    assert path.exists()
    assert path.name == "Capture_2026-03-01_14-23-45.smk"
    scene = load_project(path)
    names = [layer.name for layer in scene.layer_manager.layers]
    assert names == ["Background", "Annotations"]
    assert [layer.layer_type for layer in scene.layer_manager.layers] == [
        "Background",
        "Annotation",
    ]
    assert scene.canvas_size.width() == 40
    assert scene.layer_manager.active_layer is not None
    assert scene.layer_manager.active_layer.name == "Annotations"
    meta = read_library_metadata(path)
    assert meta is not None
    assert meta["source"] == "capture"
    assert meta["display_name"] == "Capture_2026-03-01_14-23-45"
    assert meta["captured_at"].endswith("Z")
    assert read_thumbnail(path) is not None


def test_create_blank_uses_untitled_prefix(library: LibraryManager) -> None:
    path = library.create_blank(200, 100)
    assert path.name.startswith("Untitled_")
    meta = read_library_metadata(path)
    assert meta is not None and meta["source"] == "new"


def test_import_image_and_smk(library: LibraryManager, tmp_path: Path) -> None:
    img_path = tmp_path / "shot.png"
    _image().save(str(img_path))
    imported = library.import_file(img_path)
    assert imported is not None and imported.name.startswith("Import_")

    external = tmp_path / "ext.smk"
    save_project(SnapScene(width=10, height=10), external)
    copied = library.import_file(external)
    assert copied == library.root / "ext.smk"
    copied_again = library.import_file(external)
    assert copied_again is not None and copied_again.name == "ext (2).smk"

    assert library.import_file(tmp_path / "notes.txt") is None


def test_is_library_path(library: LibraryManager, tmp_path: Path) -> None:
    inside = library.root / "sub" / "a.smk"
    assert library.is_library_path(inside)
    assert not library.is_library_path(tmp_path / "a.smk")
    assert not library.is_library_path(library.root / "a.png")
    assert not library.is_library_path(None)


def test_file_info_from_path(library: LibraryManager) -> None:
    path = library.create_from_image(_image(), source="import")
    info = LibraryFileInfo.from_path(path)
    assert info.is_valid
    assert info.display_name == path.stem
    assert info.canvas_width == 40
    assert info.layer_count == 2
    assert info.item_count == 1
    assert info.source == "import"
    assert info.captured_at is not None
    assert info.file_size > 0
    assert info.thumbnail is not None


def test_file_info_invalid_archive(library: LibraryManager) -> None:
    bad = library.root / "bad.smk"
    bad.write_bytes(b"not a zip")
    info = LibraryFileInfo.from_path(bad)
    assert info.is_valid is False
    assert info.thumbnail is None


def test_list_files_and_folders(library: LibraryManager) -> None:
    library.create_blank(10, 10)
    library.create_folder(name="Screens")
    (library.root / ".trash").mkdir()
    files = library.list_files()
    folders = library.list_folders()
    assert len(files) == 1
    assert [f.name for f in folders] == ["Screens"]


def test_rename_updates_disk_and_manifest(library: LibraryManager) -> None:
    path = library.create_blank(10, 10)
    new_path = library.rename_file(path, "My Mockup")
    assert new_path.name == "My Mockup.smk"
    assert not path.exists()
    meta = read_library_metadata(new_path)
    assert meta is not None and meta["display_name"] == "My Mockup"
    # Other metadata survives the rewrite
    assert meta["source"] == "new"


def test_rename_conflict_raises(library: LibraryManager) -> None:
    a = library.create_blank(10, 10)
    b = library.create_blank(10, 10)
    with pytest.raises(FileExistsError):
        library.rename_file(a, b.stem)


def test_rename_command_undo(library: LibraryManager) -> None:
    path = library.create_blank(10, 10)
    cmd = RenameLibraryFileCommand(library, path, "Renamed")
    library.command_stack.push(cmd)
    assert (library.root / "Renamed.smk").exists()
    library.command_stack.undo()
    assert path.exists()
    assert not (library.root / "Renamed.smk").exists()


def test_move_command_and_undo(library: LibraryManager) -> None:
    path = library.create_blank(10, 10)
    folder = library.create_folder(name="Sub")
    cmd = MoveLibraryFileCommand(library, [path], folder)
    library.command_stack.push(cmd)
    assert (folder / path.name).exists()
    assert not path.exists()
    library.command_stack.undo()
    assert path.exists()


def test_create_folder_unique_names_and_undo(library: LibraryManager) -> None:
    first = CreateFolderCommand(library, library.root)
    library.command_stack.push(first)
    second = CreateFolderCommand(library, library.root)
    library.command_stack.push(second)
    assert first.created_path is not None and first.created_path.name == "New Folder"
    assert second.created_path is not None and second.created_path.name == "New Folder (2)"
    library.command_stack.undo()
    assert not second.created_path.exists()
    # A non-empty folder is not removed on undo
    (first.created_path / "keep.txt").write_text("x")
    library.command_stack.undo()
    assert first.created_path.exists()
    assert first.undo_blocked_message is not None


def test_trash_and_restore_files(library: LibraryManager) -> None:
    path = library.create_blank(10, 10)
    assert not library.session_trash_dir.exists()
    pairs = library.trash_files([path])
    assert pairs == [(path, library.session_trash_dir / path.name)]
    assert not path.exists() and pairs[0][1].exists()
    assert library.session_trash_dir.parent == library.root / ".trash"
    assert library.list_files() == []
    restored = library.restore_files(pairs)
    assert restored == [(pairs[0][1], path)]
    assert path.exists()


def test_trash_files_keeps_same_names_apart(library: LibraryManager) -> None:
    a = library.create_blank(10, 10)
    b = library.copy_files([a], library.root)[0]
    library.rename_file(b, "Twin")
    twin = library.root / "Twin.smk"
    first = library.trash_files([twin])[0][1]
    library.create_blank(10, 10)
    twin2 = library.rename_file(library.list_files()[0].file_path, "Twin")
    second = library.trash_files([twin2])[0][1]
    assert first != second and first.exists() and second.exists()


def test_restore_takes_unique_name_when_original_is_occupied(library: LibraryManager) -> None:
    path = library.create_blank(10, 10)
    pairs = library.trash_files([path])
    path.write_bytes(b"newer")
    restored = library.restore_files(pairs)
    assert restored[0][1] != path
    assert restored[0][1].exists() and path.read_bytes() == b"newer"


def test_delete_command_undo_redo_and_discard(
    library: LibraryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Path] = []
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    path = library.create_blank(10, 10)
    cmd = DeleteLibraryFileCommand(library, [path])
    library.command_stack.push(cmd)
    assert not path.exists()
    assert cmd.trash_paths and cmd.trash_paths[0].exists()
    library.command_stack.undo()
    assert path.exists() and cmd.trash_paths == [] and cmd.paths == [path]
    library.command_stack.redo()
    assert not path.exists()
    trashed = cmd.trash_paths[0]
    library.command_stack.clear()
    assert sent == [trashed] and not trashed.exists()
    assert cmd.trash_paths == []


def test_delete_command_discard_after_undo_sends_nothing(
    library: LibraryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Path] = []
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    path = library.create_blank(10, 10)
    library.command_stack.push(DeleteLibraryFileCommand(library, [path]))
    library.command_stack.undo()
    library.command_stack.clear()
    assert sent == [] and path.exists()


def test_delete_command_moves_folder_whole(
    library: LibraryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash([]))
    folder = library.create_folder(name="Sub")
    inner = library.create_blank(10, 10, folder=folder)
    cmd = DeleteLibraryFileCommand(library, [folder])
    library.command_stack.push(cmd)
    assert not folder.exists()
    assert (cmd.trash_paths[0] / inner.name).exists()
    assert cmd.description == "Delete Sub"
    library.command_stack.undo()
    assert inner.exists()


def test_purge_session_trash_sends_each_entry(
    library: LibraryManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Path] = []
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    a = library.create_blank(10, 10)
    folder = library.create_folder(name="Sub")
    pairs = library.trash_files([a, folder])
    assert library.purge_session_trash() == 2
    assert sorted(sent) == sorted(t for _o, t in pairs)
    assert not library.session_trash_dir.exists()
    assert library.purge_session_trash() == 0


def test_construction_sweeps_other_sessions_trash(
    tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Path] = []
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    root = tmp_path / "Library"
    trash = root / ".trash"
    foreign = trash / "1-deadbeef"
    foreign.mkdir(parents=True)
    (foreign / "old.smk").write_bytes(b"x")
    own = trash / f"{os.getpid()}-abcd1234"
    own.mkdir()
    (own / "held.smk").write_bytes(b"x")
    stray = trash / "stray.smk"
    stray.write_bytes(b"x")
    LibraryManager(root)
    assert sorted(sent) == [foreign / "old.smk", stray]
    assert not foreign.exists()
    assert (own / "held.smk").exists()


def test_move_library_sweeps_trash_first(
    library: LibraryManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Path] = []
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    kept = library.create_blank(10, 10)
    doomed = library.create_blank(10, 10, folder=library.root / "Sub")
    cmd = DeleteLibraryFileCommand(library, [doomed])
    library.command_stack.push(cmd)
    held = cmd.trash_paths[0]
    foreign = library.root / ".trash" / "1-deadbeef"
    foreign.mkdir()
    (foreign / "old.smk").write_bytes(b"x")
    old_root = library.root
    new_root = tmp_path / "Elsewhere"
    assert library.move_library(new_root) == 2
    assert sorted(sent) == sorted([held, foreign / "old.smk"])
    assert not library.command_stack.can_undo
    assert not (old_root / ".trash").exists()
    assert (new_root / kept.name).exists()
    assert not (new_root / ".trash").exists()


def test_set_root_ends_undo_history_and_purges(
    library: LibraryManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Path] = []
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    doomed = library.create_blank(10, 10)
    cmd = DeleteLibraryFileCommand(library, [doomed])
    library.command_stack.push(cmd)
    held = cmd.trash_paths[0]
    old_root = library.root
    library.set_root(tmp_path / "Other")
    assert sent == [held]
    assert not library.command_stack.can_undo
    assert not (old_root / ".trash").exists()


def test_copy_files_adds_copy_suffix(library: LibraryManager) -> None:
    path = library.create_blank(10, 10)
    copies = library.copy_files([path], library.root)
    assert copies[0].name == f"{path.stem} (Copy).smk"


def test_total_size_excludes_trash(library: LibraryManager) -> None:
    library.create_blank(10, 10)
    trash = library.root / ".trash"
    trash.mkdir()
    (trash / "big.bin").write_bytes(b"x" * 10_000)
    size = library.total_size_bytes()
    assert 0 < size < 10_000


def test_write_back_on_command(library: LibraryManager, qapp: QApplication) -> None:
    path = library.create_blank(300, 200)
    scene = load_project(path)
    doc = Document(
        scene,
        file_path=path,
        is_library_file=True,
        library_metadata=read_library_metadata(path),
    )
    library.attach_document(doc)
    layer = scene.layer_manager.active_layer
    assert layer is not None
    scene.command_stack.push(
        AddItemCommand(scene, RectangleItem(rect=QRectF(0, 0, 5, 5)), layer.layer_id)
    )
    assert library.has_pending_writes
    library.flush()
    assert not library.has_pending_writes
    reloaded = load_project(path)
    assert len([i for i in reloaded.items() if isinstance(i, RectangleItem)]) == 1
    meta = read_library_metadata(path)
    assert meta is not None and meta["source"] == "new"

    # Undo is written back too
    scene.command_stack.undo()
    library.flush()
    reloaded = load_project(path)
    assert len([i for i in reloaded.items() if isinstance(i, RectangleItem)]) == 0


def test_move_library(library: LibraryManager, tmp_path: Path) -> None:
    a = library.create_blank(10, 10)
    library.create_folder(name="Sub")
    new_root = tmp_path / "Elsewhere"
    calls: list[tuple[int, int]] = []
    moved = library.move_library(new_root, lambda d, t: calls.append((d, t)) or True)
    assert moved == 2
    assert library.root == new_root
    assert (new_root / a.name).exists()
    assert (new_root / "Sub").is_dir()
    assert calls[-1] == (2, 2)


# ---- the trash route inside a Flatpak (Flatpak notes, Section 5.2) -------------------------


def test_outside_a_flatpak_the_trash_route_is_send2trash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Path] = []
    asked: list[Path] = []
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    monkeypatch.setattr(manager_module, "in_flatpak", lambda: False)
    monkeypatch.setattr(manager_module, "trash_through_portal", lambda p: asked.append(p) or True)
    target = tmp_path / "one.smk"
    target.write_text("x", encoding="utf-8")

    assert manager_module.send_to_system_trash(target) is True
    assert sent == [target] and asked == []


def test_inside_a_flatpak_the_desktop_s_own_trash_service_is_asked_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sandbox's own trash directory is invisible to the user, so the portal wins."""
    sent: list[Path] = []
    asked: list[Path] = []

    def _portal(path: Path) -> bool:
        asked.append(path)
        path.unlink()
        return True

    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    monkeypatch.setattr(manager_module, "in_flatpak", lambda: True)
    monkeypatch.setattr(manager_module, "trash_through_portal", _portal)
    target = tmp_path / "one.smk"
    target.write_text("x", encoding="utf-8")

    assert manager_module.send_to_system_trash(target) is True
    assert asked == [target] and sent == []


def test_a_refused_trash_service_still_removes_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file the user asked to delete leaves the library whichever route works."""
    sent: list[Path] = []
    monkeypatch.setattr(manager_module, "send2trash", _fake_send2trash(sent))
    monkeypatch.setattr(manager_module, "in_flatpak", lambda: True)
    monkeypatch.setattr(manager_module, "trash_through_portal", lambda _p: False)
    target = tmp_path / "one.smk"
    target.write_text("x", encoding="utf-8")

    assert manager_module.send_to_system_trash(target) is True
    assert sent == [target] and not target.exists()


def test_a_path_that_is_already_gone_is_never_trashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[Path] = []
    monkeypatch.setattr(manager_module, "in_flatpak", lambda: True)
    monkeypatch.setattr(manager_module, "trash_through_portal", lambda p: asked.append(p) or True)
    assert manager_module.send_to_system_trash(tmp_path / "gone.smk") is False
    assert asked == []


def test_the_trash_service_is_not_reached_without_a_session_bus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no bus there is nothing to ask, and the call says so instead of raising."""
    from PyQt6.QtDBus import QDBusConnection

    monkeypatch.setattr(
        QDBusConnection, "sessionBus", staticmethod(lambda: QDBusConnection("no bus"))
    )
    target = tmp_path / "one.smk"
    target.write_text("x", encoding="utf-8")
    assert manager_module.trash_through_portal(target) is False
    assert target.exists()
