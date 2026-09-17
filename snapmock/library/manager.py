"""LibraryManager — the active library directory and every operation on it."""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPixmap
from send2trash import send2trash

from snapmock.config.constants import (
    LIBRARY_IMPORT_EXTENSIONS,
    LIBRARY_WRITE_BACK_DELAY_MS,
    PROJECT_EXTENSION,
)
from snapmock.config.packaging import in_flatpak
from snapmock.core.command_stack import CommandStack
from snapmock.core.layer import LAYER_TYPE_BACKGROUND
from snapmock.core.scene import SnapScene
from snapmock.io.project_serializer import save_project, update_library_metadata
from snapmock.items.raster_region_item import RasterRegionItem
from snapmock.library.file_info import LibraryFileInfo

if TYPE_CHECKING:
    from snapmock.core.document import Document

TRASH_DIR_NAME = ".trash"
SOURCE_PREFIX = {"capture": "Capture", "import": "Import", "new": "Untitled"}


class LibraryManager(QObject):
    """Owns the library root, file operations, naming, and continuous write-back.

    Signals
    -------
    root_changed(object)
        The active library directory changed (Path).
    files_changed()
        Something on disk changed; views should rescan.
    file_created(object)
        A new library file was created (Path).
    file_renamed(object, object)
        (old Path, new Path).
    file_written(object)
        A write-back or explicit save finished (Path).
    """

    root_changed = pyqtSignal(object)
    files_changed = pyqtSignal()
    file_created = pyqtSignal(object)
    file_renamed = pyqtSignal(object, object)
    file_written = pyqtSignal(object)

    def __init__(self, root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._root = root
        self._session_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._command_stack = CommandStack(self)
        self._pending: dict[str, Document] = {}
        self._attached: dict[str, Document] = {}
        self._write_timer = QTimer(self)
        self._write_timer.setSingleShot(True)
        self._write_timer.setInterval(LIBRARY_WRITE_BACK_DELAY_MS)
        self._write_timer.timeout.connect(self.flush)
        self.ensure_root()
        self.sweep_foreign_trash()

    # --- root ---

    @property
    def root(self) -> Path:
        return self._root

    def ensure_root(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def set_root(self, path: Path) -> None:
        """Switch to a different library directory (files are not moved).

        The Library undo history ends here: clearing the stack sends any files
        held in this session's trash to the system trash, so nothing is left
        behind in the old library.
        """
        self.flush()
        self._command_stack.clear()
        self.purge_session_trash()
        self._root = path
        self.ensure_root()
        self.sweep_foreign_trash()
        self.root_changed.emit(path)
        self.files_changed.emit()

    def move_library(
        self, new_root: Path, progress: Callable[[int, int], bool] | None = None
    ) -> int:
        """Move every entry of the library to *new_root* and switch to it.

        *progress(done, total)* is called after each top-level entry; returning
        False cancels the remaining moves. Returns the number of entries moved.

        ``.trash`` is swept to the system trash first, ending the Library undo
        history, so the old location is left with nothing in it.
        """
        self.flush()
        self._command_stack.clear()
        self.sweep_trash()
        new_root.mkdir(parents=True, exist_ok=True)
        entries = [p for p in self._root.iterdir() if p.name != TRASH_DIR_NAME]
        moved = 0
        for i, entry in enumerate(entries, start=1):
            target = new_root / entry.name
            if target.exists():
                target = _unique_path(target)
            shutil.move(str(entry), str(target))
            moved += 1
            if progress is not None and not progress(i, len(entries)):
                break
        self._root = new_root
        self.root_changed.emit(new_root)
        self.files_changed.emit()
        return moved

    def is_library_path(self, path: Path | None) -> bool:
        if path is None:
            return False
        try:
            path.resolve().relative_to(self._root.resolve())
        except (ValueError, OSError):
            return False
        return path.suffix.lower() == PROJECT_EXTENSION

    @property
    def command_stack(self) -> CommandStack:
        """Undo stack for library file operations (rename, move, new folder)."""
        return self._command_stack

    # --- naming ---

    @staticmethod
    def auto_name(source: str, when: datetime | None = None) -> str:
        """``[Prefix]_[YYYY-MM-DD]_[HH-MM-SS]`` per Library PRD 6.2 (no extension)."""
        prefix = SOURCE_PREFIX.get(source, "Capture")
        when = when or datetime.now()
        return f"{prefix}_{when.strftime('%Y-%m-%d_%H-%M-%S')}"

    def unique_file_path(self, folder: Path, stem: str) -> Path:
        """Return ``folder/stem.smk``, adding ``_2``, ``_3``… on collision."""
        candidate = folder / f"{stem}{PROJECT_EXTENSION}"
        n = 2
        while candidate.exists():
            candidate = folder / f"{stem}_{n}{PROJECT_EXTENSION}"
            n += 1
        return candidate

    # --- creation ---

    def create_from_image(
        self,
        image: QImage | QPixmap,
        *,
        source: str = "capture",
        folder: Path | None = None,
        when: datetime | None = None,
        capture_metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Create a new library file whose background layer holds *image*.

        *capture_metadata* (Screen Capture PRD 12.1) is written to the manifest
        beside ``library_metadata``; *when* becomes ``captured_at``.
        """
        pixmap = image if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        scene = SnapScene(width=max(1, pixmap.width()), height=max(1, pixmap.height()))
        lm = scene.layer_manager
        bg_layer = lm.active_layer
        if bg_layer is None:
            bg_layer = lm.add_layer("Background")
        else:
            lm.rename_layer(bg_layer.layer_id, "Background")
        lm.set_layer_type(bg_layer.layer_id, LAYER_TYPE_BACKGROUND)
        item = RasterRegionItem(pixmap=pixmap)
        item.layer_id = bg_layer.layer_id
        bg_layer.item_ids.append(item.item_id)
        item.setZValue(bg_layer.z_base)
        scene.addItem(item)
        ann_layer = lm.add_layer("Annotations")
        lm.set_active(ann_layer.layer_id)
        scene.command_stack.clear()
        scene.command_stack.mark_clean()
        return self.create_from_scene(
            scene, source=source, folder=folder, when=when, capture_metadata=capture_metadata
        )

    def create_blank(
        self,
        width: int,
        height: int,
        *,
        folder: Path | None = None,
        when: datetime | None = None,
        color: QColor | None = None,
    ) -> Path:
        """Create a new empty library file (source ``new``)."""
        scene = SnapScene(width=width, height=height)
        if color is not None:
            scene.set_background_color(color)
        return self.create_from_scene(scene, source="new", folder=folder, when=when)

    def create_from_scene(
        self,
        scene: SnapScene,
        *,
        source: str,
        folder: Path | None = None,
        when: datetime | None = None,
        capture_metadata: dict[str, Any] | None = None,
    ) -> Path:
        folder = folder or self._root
        folder.mkdir(parents=True, exist_ok=True)
        when = when or datetime.now()
        stem = self.auto_name(source, when)
        path = self.unique_file_path(folder, stem)
        metadata = self.new_metadata(path.stem, source, when)
        save_project(scene, path, metadata, capture_metadata=capture_metadata)
        self.file_created.emit(path)
        self.files_changed.emit()
        return path

    @staticmethod
    def new_metadata(display_name: str, source: str, when: datetime) -> dict[str, Any]:
        return {
            "display_name": display_name,
            "captured_at": when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": source,
        }

    def import_file(self, path: Path, *, folder: Path | None = None) -> Path | None:
        """Import an image (new .smk) or copy an existing .smk into *folder*."""
        folder = folder or self._root
        suffix = path.suffix.lower()
        if suffix == PROJECT_EXTENSION:
            target = _unique_path(folder / path.name)
            shutil.copy2(path, target)
            self.file_created.emit(target)
            self.files_changed.emit()
            return target
        if suffix in LIBRARY_IMPORT_EXTENSIONS:
            image = QImage(str(path))
            if image.isNull():
                return None
            return self.create_from_image(image, source="import", folder=folder)
        return None

    @staticmethod
    def is_importable(path: Path) -> bool:
        return path.suffix.lower() in LIBRARY_IMPORT_EXTENSIONS + (PROJECT_EXTENSION,)

    # --- continuous write-back ---

    def attach_document(self, doc: Document) -> None:
        """Write *doc* back to disk after every completed command."""
        if doc.tab_id in self._attached:
            return
        self._attached[doc.tab_id] = doc
        doc.scene.command_stack.stack_changed.connect(lambda d=doc: self.schedule_write_back(d))

    def detach_document(self, doc: Document) -> None:
        self._attached.pop(doc.tab_id, None)
        pending = self._pending.pop(doc.tab_id, None)
        if pending is not None:
            self.write_back(pending)

    def schedule_write_back(self, doc: Document) -> None:
        if not doc.is_library_file or doc.file_path is None:
            return
        self._pending[doc.tab_id] = doc
        self._write_timer.start()

    def flush(self) -> None:
        """Write every pending document now."""
        self._write_timer.stop()
        pending = list(self._pending.values())
        self._pending.clear()
        for doc in pending:
            self.write_back(doc)

    def write_back(self, doc: Document) -> bool:
        if doc.file_path is None:
            return False
        try:
            save_project(
                doc.scene,
                doc.file_path,
                doc.library_metadata,
                capture_metadata=doc.capture_metadata,
            )
        except OSError:
            return False
        self.file_written.emit(doc.file_path)
        return True

    @property
    def has_pending_writes(self) -> bool:
        return bool(self._pending)

    # --- listing ---

    def list_folders(self, folder: Path | None = None) -> list[Path]:
        folder = folder or self._root
        try:
            return sorted(
                (p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")),
                key=lambda p: p.name.lower(),
            )
        except OSError:
            return []

    def list_files(self, folder: Path | None = None) -> list[LibraryFileInfo]:
        folder = folder or self._root
        try:
            paths = [
                p
                for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() == PROJECT_EXTENSION
            ]
        except OSError:
            return []
        return [LibraryFileInfo.from_path(p) for p in paths]

    def total_size_bytes(self, folder: Path | None = None) -> int:
        folder = folder or self._root
        total = 0
        try:
            for p in folder.rglob("*"):
                if TRASH_DIR_NAME in p.parts:
                    continue
                try:
                    if p.is_file():
                        total += p.stat().st_size
                except OSError:
                    continue
        except OSError:
            return total
        return total

    # --- session trash (Library PRD 3.8, 10.2) ---

    @property
    def session_id(self) -> str:
        """Identifies this manager's session trash folder: ``<pid>-<random>``."""
        return self._session_id

    @property
    def session_trash_dir(self) -> Path:
        """``<root>/.trash/<session id>``; not created until :meth:`trash_files` runs."""
        return self._root / TRASH_DIR_NAME / self._session_id

    def trash_files(self, paths: list[Path]) -> list[tuple[Path, Path]]:
        """Move files or whole folders into the session trash.

        Returns (original, trashed) pairs for what moved; a path that is
        already gone is skipped.
        """
        moved: list[tuple[Path, Path]] = []
        for p in paths:
            if not p.exists():
                continue
            trash_dir = self.session_trash_dir
            trash_dir.mkdir(parents=True, exist_ok=True)
            target = _unique_path(trash_dir / p.name)
            shutil.move(str(p), str(target))
            moved.append((p, target))
        if moved:
            self.files_changed.emit()
        return moved

    def restore_files(self, pairs: list[tuple[Path, Path]]) -> list[tuple[Path, Path]]:
        """Move (original, trashed) pairs back out of the session trash.

        Returns (trashed, restored) pairs. The original path is used when it
        is free; otherwise the restored file takes the next unique name.
        """
        restored: list[tuple[Path, Path]] = []
        for original, trashed in pairs:
            if not trashed.exists():
                continue
            original.parent.mkdir(parents=True, exist_ok=True)
            target = _unique_path(original)
            shutil.move(str(trashed), str(target))
            restored.append((trashed, target))
        if restored:
            self.files_changed.emit()
        return restored

    def purge_session_trash(self) -> int:
        """Send everything in this session's trash folder to the system trash.

        Returns the number of entries sent. Called on the window's close path.
        ``.trash`` itself is removed once no session folder is left in it.
        """
        sent = _sweep_folder(self.session_trash_dir)
        try:
            (self._root / TRASH_DIR_NAME).rmdir()
        except OSError:
            pass
        return sent

    def sweep_foreign_trash(self) -> int:
        """Send every ``.trash`` entry that is not this process's to the system trash.

        Session folders are named ``<pid>-<random>``, so folders left by a
        crashed or unclean earlier run are cleared while another window of this
        process keeps its own. Returns the number of entries sent.
        """
        return self._sweep_trash(keep_own_process=True)

    def sweep_trash(self) -> int:
        """Send everything under ``.trash`` to the system trash and remove it."""
        return self._sweep_trash(keep_own_process=False)

    def _sweep_trash(self, *, keep_own_process: bool) -> int:
        trash_root = self._root / TRASH_DIR_NAME
        if not trash_root.is_dir():
            return 0
        own_prefix = f"{os.getpid()}-"
        sent = 0
        try:
            entries = list(trash_root.iterdir())
        except OSError:
            return 0
        for entry in entries:
            if keep_own_process and entry.is_dir() and entry.name.startswith(own_prefix):
                continue
            if entry.is_dir():
                sent += _sweep_folder(entry)
            elif send_to_system_trash(entry):
                sent += 1
        try:
            trash_root.rmdir()
        except OSError:
            pass
        return sent

    # --- file operations (raw; undo is provided by library commands) ---

    def rename_file(self, path: Path, new_stem: str) -> Path:
        """Rename on disk and update ``display_name`` in the manifest."""
        new_stem = _sanitize_stem(new_stem)
        if not new_stem:
            raise ValueError("Name cannot be empty")
        target = path.with_name(f"{new_stem}{PROJECT_EXTENSION}")
        if target.exists() and target != path:
            raise FileExistsError(f'A file named "{target.name}" already exists')
        if target != path:
            path.rename(target)
        update_library_metadata(target, display_name=new_stem)
        self.file_renamed.emit(path, target)
        self.files_changed.emit()
        return target

    def move_files(self, paths: list[Path], dest_folder: Path) -> list[tuple[Path, Path]]:
        """Move files into *dest_folder*. Returns (old, new) pairs."""
        dest_folder.mkdir(parents=True, exist_ok=True)
        moved: list[tuple[Path, Path]] = []
        for p in paths:
            target = dest_folder / p.name
            if target == p:
                continue
            if target.exists():
                target = _unique_path(target)
            shutil.move(str(p), str(target))
            moved.append((p, target))
            self.file_renamed.emit(p, target)
        if moved:
            self.files_changed.emit()
        return moved

    def copy_files(self, paths: list[Path], dest_folder: Path) -> list[Path]:
        """Copy files into *dest_folder*, adding " (Copy)" on name conflict."""
        dest_folder.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for p in paths:
            target = dest_folder / p.name
            if target.exists():
                target = _unique_path(dest_folder / f"{p.stem} (Copy){p.suffix}")
            shutil.copy2(p, target)
            copied.append(target)
        if copied:
            self.files_changed.emit()
        return copied

    def create_folder(self, parent: Path | None = None, name: str = "New Folder") -> Path:
        parent = parent or self._root
        target = parent / name
        n = 2
        while target.exists():
            target = parent / f"{name} ({n})"
            n += 1
        target.mkdir(parents=True)
        self.files_changed.emit()
        return target

    def rename_folder(self, path: Path, new_name: str) -> Path:
        new_name = _sanitize_stem(new_name)
        if not new_name:
            raise ValueError("Name cannot be empty")
        target = path.with_name(new_name)
        if target.exists() and target != path:
            raise FileExistsError(f'A folder named "{new_name}" already exists')
        path.rename(target)
        self.files_changed.emit()
        return target

    def remove_empty_folder(self, path: Path) -> bool:
        try:
            path.rmdir()
        except OSError:
            return False
        self.files_changed.emit()
        return True

    @staticmethod
    def folder_item_count(path: Path) -> int:
        try:
            return sum(1 for _ in path.rglob("*"))
        except OSError:
            return 0


TRASH_PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
TRASH_PORTAL_PATH = "/org/freedesktop/portal/desktop"
TRASH_PORTAL_INTERFACE = "org.freedesktop.portal.Trash"
TRASH_PORTAL_SUCCESS = 1
"""The portal answers 1 when the file reached the trash and 0 when it did not."""


def trash_through_portal(path: Path) -> bool:
    """Ask the desktop's own trash service to trash *path*; False when it declines.

    Inside a Flatpak, ``send2trash`` and Qt alike write to the trash directory under
    ``$XDG_DATA_HOME``, which the sandbox points at
    ``~/.var/app/<id>/data/Trash``: the file leaves the library and never appears in
    the user's trash. The desktop portal's Trash interface is the route that reaches
    the real one. Verified on this machine on 09-17-26: the descriptor must be opened
    ``O_PATH`` (``O_RDONLY`` is refused), and a whole folder is accepted that way too.
    """
    from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusUnixFileDescriptor

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return False
    try:
        handle = os.open(str(path), os.O_PATH)
    except OSError:
        return False
    try:
        interface = QDBusInterface(
            TRASH_PORTAL_SERVICE, TRASH_PORTAL_PATH, TRASH_PORTAL_INTERFACE, bus
        )
        if not interface.isValid():
            return False
        reply = interface.call("TrashFile", QDBusUnixFileDescriptor(handle))
        arguments = reply.arguments()
    finally:
        os.close(handle)
    return bool(arguments) and arguments[0] == TRASH_PORTAL_SUCCESS


def send_to_system_trash(path: Path) -> bool:
    """Send one file or folder to the system trash. False if it is gone or refused.

    Inside a Flatpak the desktop's trash service is asked first, so the file lands in
    the user's own trash and not in the sandbox's (Flatpak notes, Section 5.2); if the
    service declines, ``send2trash`` still takes it, since a file the user asked to
    delete must leave the library either way.
    """
    if not path.exists():
        return False
    if in_flatpak() and trash_through_portal(path):
        return True
    try:
        send2trash(str(path))
    except OSError:
        return False
    return True


def _sweep_folder(folder: Path) -> int:
    """Send every entry of *folder* to the system trash, then remove the folder."""
    if not folder.is_dir():
        return 0
    sent = 0
    try:
        entries = list(folder.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if send_to_system_trash(entry):
            sent += 1
    try:
        folder.rmdir()
    except OSError:
        pass
    return sent


def _unique_path(target: Path) -> Path:
    """Append " (2)", " (3)"… before the suffix until the path is free."""
    if not target.exists():
        return target
    n = 2
    while True:
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _sanitize_stem(name: str) -> str:
    bad = '<>:"/\\\\|?*'
    cleaned = "".join("_" if c in bad else c for c in name).strip()
    if cleaned.lower().endswith(PROJECT_EXTENSION):
        cleaned = cleaned[: -len(PROJECT_EXTENSION)]
    return cleaned.strip()
