"""LibraryPanel — dockable file browser for the active library (Library PRD 3)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QSlider,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from snapmock.config.constants import (
    LIBRARY_PATHS_MIME,
    LIBRARY_PREVIEW_MAX,
    LIBRARY_PREVIEW_MIN,
    LIBRARY_THUMBNAIL_MAX,
    LIBRARY_THUMBNAIL_MIN,
)
from snapmock.config.settings import AppSettings
from snapmock.core.theme_manager import current_theme
from snapmock.library.commands import (
    CreateFolderCommand,
    DeleteLibraryFileCommand,
    MoveLibraryFileCommand,
    RenameLibraryFileCommand,
)
from snapmock.library.file_info import LibraryFileInfo
from snapmock.library.manager import LibraryManager
from snapmock.library.model import (
    COL_MODIFIED,
    COL_NAME,
    COL_SIZE,
    IS_FOLDER_ROLE,
    IS_OPEN_ROLE,
    PATH_ROLE,
    SORT_COLUMN_TO_KEY,
    SORT_OPTIONS,
    SUBTITLE_ROLE,
    LibraryModel,
    format_datetime,
    human_size,
)
from snapmock.library.render import export_for_drag, render_file_to_image
from snapmock.ui.accessibility import apply_default_names

EMPTY_TEXT = "No files in library. Capture a screenshot or drag images here to get started."


# --------------------------------------------------------------------------- delegates


class _GridDelegate(QStyledItemDelegate):
    """Thumbnail card: image, name, and a gray subtitle (date or item count)."""

    def __init__(self, thumb_size: Callable[[], int], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thumb_size = thumb_size

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        size = self._thumb_size()
        return QSize(size + 16, size + 44)

    def paint(  # noqa: N802
        self, painter: QPainter | None, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        if painter is None:
            return
        size = self._thumb_size()
        rect = option.rect
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect.adjusted(2, 2, -2, -2), option.palette.highlight())
        pix = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pix, QPixmap) and not pix.isNull():
            x = rect.x() + (rect.width() - pix.width()) // 2
            painter.drawPixmap(x, rect.y() + 6, pix)
        fm = QFontMetrics(option.font)
        name = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        name_rect = QRect(rect.x() + 4, rect.y() + size + 10, rect.width() - 8, fm.height())
        painter.setPen(
            option.palette.highlightedText().color() if selected else option.palette.text().color()
        )
        painter.drawText(
            name_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            fm.elidedText(name, Qt.TextElideMode.ElideMiddle, name_rect.width()),
        )
        sub = str(index.data(SUBTITLE_ROLE) or "")
        sub_rect = QRect(name_rect.x(), name_rect.bottom() + 1, name_rect.width(), fm.height())
        theme = current_theme()
        painter.setPen(theme.accent_text if selected else theme.text_secondary)
        small = painter.font()
        small.setPointSizeF(max(6.0, small.pointSizeF() - 1))
        painter.setFont(small)
        painter.drawText(
            sub_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(small).elidedText(sub, Qt.TextElideMode.ElideRight, sub_rect.width()),
        )
        if bool(index.data(IS_OPEN_ROLE)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.accent)
            painter.drawEllipse(rect.right() - 14, rect.y() + 6, 8, 8)
        painter.restore()

    def updateEditorGeometry(  # noqa: N802
        self, editor: QWidget | None, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        if editor is None:
            return
        size = self._thumb_size()
        rect = option.rect
        editor.setGeometry(rect.x() + 4, rect.y() + size + 8, rect.width() - 8, 22)


# --------------------------------------------------------------------------- views


_HANDLED_KEYS = {
    Qt.Key.Key_Return,
    Qt.Key.Key_Enter,
    Qt.Key.Key_F2,
    Qt.Key.Key_Delete,
    Qt.Key.Key_Backspace,
}
_HANDLED_SEQUENCES = [
    QKeySequence("Ctrl+A"),
    QKeySequence("Ctrl+C"),
    QKeySequence("Ctrl+V"),
    QKeySequence("Ctrl+Shift+C"),
    QKeySequence("Ctrl+Z"),
    QKeySequence("Ctrl+Shift+Z"),
]


class _KeyRouter:
    """Mixin: claim keys before window-level shortcuts and forward to the panel."""

    _panel: LibraryPanel

    def _claims(self, event: QKeyEvent) -> bool:
        if event.key() in _HANDLED_KEYS:
            return True
        seq = QKeySequence(event.keyCombination())
        return any(
            seq.matches(s) == QKeySequence.SequenceMatch.ExactMatch for s in _HANDLED_SEQUENCES
        )


class _GridView(QListView, _KeyRouter):
    def __init__(self, panel: LibraryPanel) -> None:
        super().__init__(panel)
        self._panel = panel

    def event(self, e: QEvent | None) -> bool:
        if e is not None and e.type() == QEvent.Type.ShortcutOverride:
            if (
                isinstance(e, QKeyEvent)
                and self._claims(e)
                and self.state() != QAbstractItemView.State.EditingState
            ):
                e.accept()
                return True
        return super().event(e)

    def keyPressEvent(self, e: QKeyEvent | None) -> None:  # noqa: N802
        if (
            e is not None
            and self.state() != QAbstractItemView.State.EditingState
            and self._panel.handle_key(e)
        ):
            e.accept()
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e: object) -> None:  # noqa: N802
        self._panel.show_context_menu(self, e)


class _ListView(QTreeView, _KeyRouter):
    def __init__(self, panel: LibraryPanel) -> None:
        super().__init__(panel)
        self._panel = panel

    def event(self, e: QEvent | None) -> bool:
        if e is not None and e.type() == QEvent.Type.ShortcutOverride:
            if (
                isinstance(e, QKeyEvent)
                and self._claims(e)
                and self.state() != QAbstractItemView.State.EditingState
            ):
                e.accept()
                return True
        return super().event(e)

    def keyPressEvent(self, e: QKeyEvent | None) -> None:  # noqa: N802
        if (
            e is not None
            and self.state() != QAbstractItemView.State.EditingState
            and self._panel.handle_key(e)
        ):
            e.accept()
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e: object) -> None:  # noqa: N802
        self._panel.show_context_menu(self, e)


class _EmptyLabel(QLabel):
    """Placeholder shown for an empty folder; accepts external image drops."""

    dropped = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(EMPTY_TEXT, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setProperty("role", "secondary")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e: QDragEnterEvent | None) -> None:  # noqa: N802
        mime = e.mimeData() if e is not None else None
        if e is not None and mime is not None and mime.hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent | None) -> None:  # noqa: N802
        mime = e.mimeData() if e is not None else None
        if e is None or mime is None:
            return
        paths = [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
            e.acceptProposedAction()


class _SizeWorker(QObject):
    """Computes library size on a worker thread and reports via signal."""

    computed = pyqtSignal(int)

    def start(self, manager: LibraryManager) -> None:
        root = manager.root

        def run() -> None:
            self.computed.emit(manager.total_size_bytes(root))

        threading.Thread(target=run, daemon=True).start()


# --------------------------------------------------------------------------- panel


class LibraryPanel(QDockWidget):
    """Dockable browser for the library directory.

    Signals
    -------
    open_requested(list)
        Open these .smk files in tabs (list[Path]).
    open_in_new_window_requested(object)
        Open this file in a new SnapMock window (Path).
    files_about_to_be_deleted(list)
        Called before files are trashed so open tabs can be closed (list[Path]).
    export_requested(list)
        Export these files via the Export dialog (list[Path]).
    export_quick_requested(list)
        Export these files as PNG with last-used settings (list[Path]).
    new_canvas_requested(object)
        Create a blank canvas in this folder (Path).
    """

    open_requested = pyqtSignal(list)
    open_in_new_window_requested = pyqtSignal(object)
    files_about_to_be_deleted = pyqtSignal(list)
    export_requested = pyqtSignal(list)
    export_quick_requested = pyqtSignal(list)
    new_canvas_requested = pyqtSignal(object)

    def __init__(
        self,
        manager: LibraryManager,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Library", parent)
        self.setObjectName("LibraryPanel")
        self._manager = manager
        self._settings = settings
        self._model = LibraryModel(manager, self)
        self._model.set_drag_exporter(export_for_drag)
        self._file_clipboard: list[Path] = []
        self._pending_edit: Path | None = None
        self.setMinimumSize(200, 150)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        body = QWidget(self)
        root_layout = QVBoxLayout(body)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        # --- header ---
        header = QHBoxLayout()
        self._path_label = QLabel("")
        self._path_label.setSizePolicy(
            self._path_label.sizePolicy().horizontalPolicy(),
            self._path_label.sizePolicy().verticalPolicy(),
        )
        self._path_label.setMinimumWidth(60)
        header.addWidget(self._path_label, 1)

        self._change_btn = QToolButton()
        self._change_btn.setIcon(self._icon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self._change_btn.setToolTip("Change library folder…")
        self._change_btn.setAccessibleName("Change library folder")
        self._change_btn.clicked.connect(self.choose_library_directory)
        header.addWidget(self._change_btn)

        self._grid_btn = QToolButton()
        self._grid_btn.setText("▦")
        self._grid_btn.setToolTip("Grid view")
        self._grid_btn.setAccessibleName("Grid view")
        self._grid_btn.setCheckable(True)
        self._list_btn = QToolButton()
        self._list_btn.setText("☰")
        self._list_btn.setToolTip("Preview list view")
        self._list_btn.setAccessibleName("Preview list view")
        self._list_btn.setCheckable(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self._grid_btn)
        group.addButton(self._list_btn)
        self._grid_btn.clicked.connect(lambda: self.set_view_mode("grid"))
        self._list_btn.clicked.connect(lambda: self.set_view_mode("list"))
        header.addWidget(self._grid_btn)
        header.addWidget(self._list_btn)

        self._size_slider = QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setFixedWidth(90)
        self._size_slider.setToolTip("Thumbnail size")
        self._size_slider.setAccessibleName("Thumbnail size")
        self._size_slider.valueChanged.connect(self._on_size_changed)
        header.addWidget(self._size_slider)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Search")
        self._search.setAccessibleName("Search library")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(140)
        self._search.textChanged.connect(self._model.set_filter)
        self._search.textChanged.connect(lambda _t: self._update_footer())
        self._search.installEventFilter(self)
        header.addWidget(self._search)
        root_layout.addLayout(header)

        # --- navigation bar ---
        nav = QHBoxLayout()
        self._back_btn = QToolButton()
        self._back_btn.setIcon(self._icon(QStyle.StandardPixmap.SP_ArrowBack))
        self._back_btn.setToolTip("Back to parent folder")
        self._back_btn.setAccessibleName("Back to parent folder")
        self._back_btn.clicked.connect(self._model.go_up)
        nav.addWidget(self._back_btn)
        self._crumbs = QHBoxLayout()
        self._crumbs.setSpacing(0)
        nav.addLayout(self._crumbs)
        nav.addStretch(1)
        root_layout.addLayout(nav)

        # --- content ---
        self._stack = QStackedWidget()
        self._grid = _GridView(self)
        self._grid.setAccessibleName("Library files")
        self._grid.setModel(self._model)
        self._grid.setViewMode(QListView.ViewMode.IconMode)
        self._grid.setFlow(QListView.Flow.LeftToRight)
        self._grid.setWrapping(True)
        self._grid.setResizeMode(QListView.ResizeMode.Adjust)
        self._grid.setMovement(QListView.Movement.Static)
        self._grid.setSpacing(6)
        self._grid.setUniformItemSizes(True)
        self._grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._grid.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._grid.setDragEnabled(True)
        self._grid.setAcceptDrops(True)
        self._grid.setDropIndicatorShown(True)
        self._grid.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._grid.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._grid.setItemDelegate(_GridDelegate(lambda: self._model.thumb_size, self._grid))
        self._grid.doubleClicked.connect(self._on_double_clicked)
        self._stack.addWidget(self._grid)

        self._list = _ListView(self)
        self._list.setAccessibleName("Library files")
        self._list.setModel(self._model)
        self._list.setSelectionModel(self._grid.selectionModel())
        self._list.setRootIsDecorated(False)
        self._list.setUniformRowHeights(True)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked)
        self._list.setDragEnabled(True)
        self._list.setAcceptDrops(True)
        self._list.setDropIndicatorShown(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setSortingEnabled(False)
        self._list.doubleClicked.connect(self._on_double_clicked)
        list_header = self._list.header()
        if list_header is not None:
            list_header.setSectionsClickable(True)
            list_header.setSortIndicatorShown(True)
            list_header.sectionClicked.connect(self._on_header_clicked)
            list_header.setStretchLastSection(True)
            list_header.resizeSection(COL_NAME, 280)
            list_header.resizeSection(COL_SIZE, 90)
            list_header.resizeSection(COL_MODIFIED, 170)
        self._stack.addWidget(self._list)

        self._empty = _EmptyLabel()
        self._empty.dropped.connect(
            lambda paths: self._import_paths(paths, self._model.current_path)
        )
        self._stack.addWidget(self._empty)
        root_layout.addWidget(self._stack, 1)

        # --- footer ---
        footer = QHBoxLayout()
        self._count_label = QLabel("0 files")
        self._size_label = QLabel("")
        footer.addWidget(self._count_label)
        footer.addStretch(1)
        footer.addWidget(self._size_label)
        self._sort_combo = QComboBox()
        self._sort_combo.setAccessibleName("Sort by")
        for sort_id, label in SORT_OPTIONS:
            self._sort_combo.addItem(label, sort_id)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_combo_changed)
        footer.addWidget(self._sort_combo)
        root_layout.addLayout(footer)

        self.setWidget(body)
        self.setAccessibleName("Library Panel")
        apply_default_names(self)

        # --- wiring ---
        self._model.current_path_changed.connect(lambda _p: self._on_path_changed())
        self._selected_before_reset: list[Path] = []
        self._model.modelAboutToBeReset.connect(self._remember_selection)
        self._model.modelReset.connect(self._on_model_reset)
        self._model.rename_requested.connect(self._on_rename_requested)
        self._model.move_requested.connect(self._on_move_requested)
        self._model.import_requested.connect(self._import_paths)
        self._manager.root_changed.connect(lambda _p: self._on_path_changed())
        self._manager.files_changed.connect(self._schedule_size)
        self._size_worker = _SizeWorker(self)
        self._size_worker.computed.connect(self._on_size_computed)

        # --- initial state from settings ---
        self._view_mode = "grid"
        self._model.set_sort_id(settings.library_sort())
        self._sync_sort_combo()
        self.set_view_mode(settings.library_view_mode(), persist=False)
        self._model.refresh()
        self._on_path_changed()
        self._schedule_size()

    # ------------------------------------------------------------------ public API

    @property
    def model(self) -> LibraryModel:
        return self._model

    @property
    def manager(self) -> LibraryManager:
        return self._manager

    @property
    def view_mode(self) -> str:
        return self._view_mode

    @property
    def current_path(self) -> Path:
        return self._model.current_path

    def refresh(self) -> None:
        self._model.refresh()

    def refresh_open_state(self) -> None:
        """Repaint open-file badges after tabs open or close."""
        vp = self._grid.viewport()
        if vp is not None:
            vp.update()
        vp2 = self._list.viewport()
        if vp2 is not None:
            vp2.update()

    def set_is_open_provider(self, fn: Callable[[Path], bool]) -> None:
        self._model.set_is_open_provider(fn)

    def selected_paths(self, *, files_only: bool = False) -> list[Path]:
        """The paths selected in either view, in row order.

        Read from ``selectedIndexes`` and not from ``selectedRows``: the two views
        share one selection model, and a click in the thumbnail grid selects the
        row's first column alone, which ``selectedRows`` does not count as a
        selected row (display run, finding 7). The preview list selects every
        column of the row, so one index per row is kept.
        """
        paths: list[Path] = []
        sel = self._grid.selectionModel()
        if sel is None:
            return paths
        seen: set[int] = set()
        for idx in sorted(sel.selectedIndexes(), key=lambda i: i.row()):
            if idx.column() != COL_NAME or idx.row() in seen:
                continue
            seen.add(idx.row())
            if files_only and bool(idx.data(IS_FOLDER_ROLE)):
                continue
            p = idx.data(PATH_ROLE)
            if isinstance(p, Path):
                paths.append(p)
        return paths

    def _remember_selection(self) -> None:
        """Hold the selected paths while the model resets (display run, finding 6).

        Every reload of the library resets the model, and a reset clears the view's
        selection: a capture, a write-back, or another window's change between a
        right-click and the menu item clicked left the action with nothing selected.
        """
        self._selected_before_reset = self.selected_paths()

    def _restore_selection(self) -> None:
        """Select again what :meth:`_remember_selection` held, where it still exists."""
        paths = self._selected_before_reset
        self._selected_before_reset = []
        sel = self._grid.selectionModel()
        if not paths or sel is None:
            return
        first: QModelIndex | None = None
        for path in paths:
            row = self._model.row_for_path(path)
            if row < 0:
                continue
            idx = self._model.index(row, COL_NAME)
            sel.select(
                idx,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
            if first is None:
                first = idx
        if first is not None:
            sel.setCurrentIndex(first, QItemSelectionModel.SelectionFlag.NoUpdate)

    def select_path(self, path: Path) -> None:
        """Navigate to the file's folder, select it, and scroll into view."""
        if path.parent != self._model.current_path:
            self._model.navigate_to(path.parent)
        row = self._model.row_for_path(path)
        if row < 0:
            return
        idx = self._model.index(row, COL_NAME)
        sel = self._grid.selectionModel()
        if sel is not None:
            sel.select(
                idx,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
            sel.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._active_view().scrollTo(idx)

    def set_view_mode(self, mode: str, *, persist: bool = True) -> None:
        mode = "list" if mode == "list" else "grid"
        self._view_mode = mode
        self._grid_btn.setChecked(mode == "grid")
        self._list_btn.setChecked(mode == "list")
        self._size_slider.blockSignals(True)
        if mode == "grid":
            self._size_slider.setRange(LIBRARY_THUMBNAIL_MIN, LIBRARY_THUMBNAIL_MAX)
            size = self._settings.library_thumbnail_size()
        else:
            self._size_slider.setRange(LIBRARY_PREVIEW_MIN, LIBRARY_PREVIEW_MAX)
            size = self._settings.library_preview_size()
        size = max(self._size_slider.minimum(), min(self._size_slider.maximum(), size))
        self._size_slider.setValue(size)
        self._size_slider.blockSignals(False)
        self._apply_size(size)
        if persist:
            self._settings.set_library_view_mode(mode)
        self._update_stack()

    def choose_library_directory(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Open Library", str(self._manager.root))
        if chosen:
            self.set_library_directory(Path(chosen))

    def set_library_directory(self, path: Path) -> None:
        self._settings.set_library_directory(path)
        self._manager.set_root(path)

    def create_folder(self) -> None:
        cmd = CreateFolderCommand(self._manager, self._model.current_path)
        self._manager.command_stack.push(cmd)
        if cmd.created_path is not None:
            self._begin_edit(cmd.created_path)

    def open_selected(self) -> None:
        paths = self.selected_paths()
        folders = [p for p in paths if p.is_dir()]
        files = [p for p in paths if p.is_file()]
        if len(paths) == 1 and folders:
            self._model.navigate_to(folders[0])
            return
        if files:
            self.open_requested.emit(files)
        elif not paths:
            self._explain("Select a file to open.")

    def rename_selected(self) -> None:
        paths = self.selected_paths()
        if len(paths) != 1:
            self._explain("Select a single file or folder to rename.")
            return
        self._begin_edit(paths[0])

    def delete_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            self._explain("Select one or more files to delete.")
            return
        self.delete_paths(paths)

    def delete_paths(self, paths: list[Path]) -> None:
        files = [p for p in paths if p.is_file()]
        folders = [p for p in paths if p.is_dir()]
        need_confirm = bool(files) or any(self._manager.folder_item_count(f) > 0 for f in folders)
        if need_confirm:
            if len(paths) == 1:
                target = paths[0]
                if target.is_dir():
                    n = self._manager.folder_item_count(target)
                    msg = (
                        f'Delete folder "{target.name}" and its {n} item(s)? '
                        "They will be moved to the system trash."
                    )
                else:
                    msg = f'Delete "{target.stem}"? The file will be moved to the system trash.'
            else:
                msg = f"Delete {len(paths)} items? They will be moved to the system trash."
            answer = QMessageBox.question(
                self,
                "Delete",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if files:
            self.files_about_to_be_deleted.emit(files)
        self._manager.command_stack.push(DeleteLibraryFileCommand(self._manager, paths))

    def copy_selected_files(self) -> None:
        files = self.selected_paths(files_only=True)
        if not files:
            self._explain("Select one or more files to copy.")
            return
        self._file_clipboard = files

    def paste_files(self) -> None:
        if not self._file_clipboard:
            self._explain("Copy one or more library files first (Ctrl+C).")
            return
        existing = [p for p in self._file_clipboard if p.exists()]
        self._manager.copy_files(existing, self._model.current_path)

    def copy_selected_png_to_clipboard(self) -> None:
        files = self.selected_paths(files_only=True)
        if len(files) != 1:
            self._explain("Select a single file to copy its image to the clipboard.")
            return
        image = render_file_to_image(files[0])
        if image is None:
            self._explain(f'"{files[0].name}" could not be rendered.')
            return
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setImage(image)

    def select_all_files(self) -> None:
        sel = self._grid.selectionModel()
        if sel is None:
            return
        sel.clearSelection()
        for row in range(self._model.rowCount()):
            idx = self._model.index(row, COL_NAME)
            if bool(idx.data(IS_FOLDER_ROLE)):
                continue
            sel.select(
                idx,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )

    def move_selected_to_folder(self) -> None:
        files = self.selected_paths(files_only=True)
        if not files:
            self._explain("Select one or more files to move.")
            return
        chosen = QFileDialog.getExistingDirectory(self, "Move to Folder", str(self._manager.root))
        if not chosen:
            return
        dest = Path(chosen)
        try:
            dest.resolve().relative_to(self._manager.root.resolve())
        except ValueError:
            self._explain("The destination must be a folder inside the library.")
            return
        self._on_move_requested(files, dest)

    def reveal_selected_in_file_manager(self) -> None:
        paths = self.selected_paths()
        target = (
            paths[0].parent
            if paths and paths[0].is_file()
            else (paths[0] if paths else self._model.current_path)
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def show_selected_properties(self) -> None:
        files = self.selected_paths(files_only=True)
        if len(files) != 1:
            self._explain("Select a single file to show its properties.")
            return
        info = LibraryFileInfo.from_path(files[0])
        lines = [
            f"Name: {info.display_name}",
            f"File: {info.file_path}",
            f"Size: {human_size(info.file_size)}",
            f"Captured: {format_datetime(info.captured_at) or '—'}",
            f"Modified: {format_datetime(info.modified_at) or '—'}",
            f"Canvas: {info.canvas_width} × {info.canvas_height}",
            f"Layers: {info.layer_count}",
            f"Items: {info.item_count}",
            f"Source: {info.source or '—'}",
        ]
        capture = info.capture_metadata
        if capture:  # Screen Capture PRD 12.1
            rect = capture.get("screen_rect") or {}
            lines += [
                "",
                f"Capture mode: {capture.get('mode', '—')}"
                + (
                    f" (requested {capture['requested_mode']})"
                    if capture.get("requested_mode") not in (None, capture.get("mode"))
                    else ""
                ),
                f"Monitor: {capture.get('monitor_name') or 'All monitors'}",
                f"Scale: {capture.get('device_pixel_ratio', 1)}×",
                f"Screen rect: {rect.get('x', 0)}, {rect.get('y', 0)}, "
                f"{rect.get('width', 0)} × {rect.get('height', 0)}",
                f"Cursor included: {'yes' if capture.get('cursor_included') else 'no'}",
                f"Backend: {capture.get('backend', '—')} on {capture.get('platform', '—')}",
            ]
            if capture.get("window_title"):
                lines.append(f"Window: {capture['window_title']}")
        QMessageBox.information(self, "Properties", "\n".join(lines))

    # ------------------------------------------------------------------ keys / menus

    def handle_key(self, e: QKeyEvent) -> bool:  # noqa: C901
        key = e.key()
        seq = QKeySequence(e.keyCombination())

        def is_(s: str) -> bool:
            return seq.matches(QKeySequence(s)) == QKeySequence.SequenceMatch.ExactMatch

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.open_selected()
        elif key == Qt.Key.Key_F2:
            self.rename_selected()
        elif key == Qt.Key.Key_Delete or (
            key == Qt.Key.Key_Backspace and e.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.delete_selected()
        elif is_("Ctrl+A"):
            self.select_all_files()
        elif is_("Ctrl+Shift+C"):
            self.copy_selected_png_to_clipboard()
        elif is_("Ctrl+C"):
            self.copy_selected_files()
        elif is_("Ctrl+V"):
            self.paste_files()
        elif is_("Ctrl+Z"):
            self._manager.command_stack.undo()
        elif is_("Ctrl+Shift+Z"):
            self._manager.command_stack.redo()
        else:
            return False
        return True

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        if obj is self._search and event is not None and event.type() == QEvent.Type.KeyPress:
            if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Escape:
                self._search.clear()
                return True
        return super().eventFilter(obj, event)

    def show_context_menu(self, view: QAbstractItemView, e: object) -> None:  # noqa: C901
        pos = getattr(e, "pos", lambda: QPoint())()
        global_pos = getattr(e, "globalPos", lambda: QPoint())()
        idx = view.indexAt(pos)
        sel = view.selectionModel()
        if idx.isValid() and sel is not None and not sel.isSelected(idx):
            sel.select(
                idx,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
        paths = self.selected_paths()
        files = [p for p in paths if p.is_file()]
        menu = QMenu(self)

        def add(text: str, slot: Callable[[], None], shortcut: str = "") -> QAction:
            action = menu.addAction(text)
            assert action is not None
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            return action

        if not idx.isValid():
            add("Paste File", self.paste_files, "Ctrl+V")
            add("New Folder", self.create_folder)
            add("New Canvas", lambda: self.new_canvas_requested.emit(self._model.current_path))
            sort_menu = menu.addMenu("Sort By")
            if sort_menu is not None:
                for sort_id, label in SORT_OPTIONS:
                    act = sort_menu.addAction(label)
                    if act is not None:
                        act.setCheckable(True)
                        act.setChecked(sort_id == self._model.sort_id)
                        act.triggered.connect(lambda _c=False, s=sort_id: self.set_sort_id(s))
            menu.exec(global_pos)
            return

        if idx.isValid() and bool(idx.data(IS_FOLDER_ROLE)) and len(paths) == 1:
            add("Open", self.open_selected, "Enter")
            add("Rename", self.rename_selected, "F2")
            add("Delete", self.delete_selected, "Delete")
            add("New Folder", self.create_folder)
            add("Reveal in File Manager", self.reveal_selected_in_file_manager)
            menu.exec(global_pos)
            return

        n = len(files)
        add("Open" if n <= 1 else f"Open {n} Files", self.open_selected, "Enter")
        add(
            "Open in New Window",
            lambda: self._open_in_new_window(files),
        )
        menu.addSeparator()
        add("Rename", self.rename_selected, "F2")
        add("Delete" if n <= 1 else f"Delete {n} Files", self.delete_selected, "Delete")
        menu.addSeparator()
        add("Copy File" if n <= 1 else f"Copy {n} Files", self.copy_selected_files, "Ctrl+C")
        add("Paste File", self.paste_files, "Ctrl+V")
        add("Copy to Clipboard", self.copy_selected_png_to_clipboard, "Ctrl+Shift+C")
        menu.addSeparator()
        add("Export...", lambda: self._emit_export(files, quick=False))
        add("Export Quick (PNG)", lambda: self._emit_export(files, quick=True), "Ctrl+Shift+E")
        menu.addSeparator()
        add("Move to Folder...", self.move_selected_to_folder)
        add("New Folder", self.create_folder)
        menu.addSeparator()
        add("Reveal in File Manager", self.reveal_selected_in_file_manager)
        add("Properties", self.show_selected_properties)
        menu.exec(global_pos)

    # ------------------------------------------------------------------ internals

    def _icon(self, sp: QStyle.StandardPixmap) -> QIcon:
        style = self.style()
        return style.standardIcon(sp) if style is not None else QIcon()

    def _active_view(self) -> QAbstractItemView:
        return self._list if self._view_mode == "list" else self._grid

    def _update_stack(self) -> None:
        if self._model.rowCount() == 0 and not self._model.filter_text:
            self._stack.setCurrentWidget(self._empty)
        else:
            self._stack.setCurrentWidget(self._active_view())

    def _apply_size(self, size: int) -> None:
        self._model.set_thumb_size(size)
        self._grid.setIconSize(QSize(size, size))
        self._list.setIconSize(QSize(size, size))
        self._grid.setGridSize(QSize(size + 20, size + 50))
        self._grid.scheduleDelayedItemsLayout()

    def _on_size_changed(self, value: int) -> None:
        if self._view_mode == "grid":
            self._settings.set_library_thumbnail_size(value)
        else:
            self._settings.set_library_preview_size(value)
        self._apply_size(value)

    def set_sort_id(self, sort_id: str) -> None:
        self._model.set_sort_id(sort_id)
        self._settings.set_library_sort(sort_id)
        self._sync_sort_combo()

    def _sync_sort_combo(self) -> None:
        self._sort_combo.blockSignals(True)
        i = self._sort_combo.findData(self._model.sort_id)
        if i >= 0:
            self._sort_combo.setCurrentIndex(i)
        self._sort_combo.blockSignals(False)
        header = self._list.header()
        if header is not None:
            key, _, direction = self._model.sort_id.rpartition("_")
            for col, k in SORT_COLUMN_TO_KEY.items():
                if k == key:
                    header.setSortIndicator(
                        col,
                        Qt.SortOrder.DescendingOrder
                        if direction == "desc"
                        else Qt.SortOrder.AscendingOrder,
                    )

    def _on_sort_combo_changed(self, index: int) -> None:
        sort_id = self._sort_combo.itemData(index)
        if isinstance(sort_id, str):
            self.set_sort_id(sort_id)

    def _on_header_clicked(self, column: int) -> None:
        key = SORT_COLUMN_TO_KEY.get(column)
        if key is None:
            return
        cur_key, _, direction = self._model.sort_id.rpartition("_")
        descending = not (cur_key == key and direction == "desc")
        self.set_sort_id(f"{key}_{'desc' if descending else 'asc'}")

    def _update_path_label(self) -> None:
        text = str(self._manager.root)
        fm = QFontMetrics(self._path_label.font())
        available = max(120, self._path_label.width() - 4)
        self._path_label.setText(fm.elidedText(text, Qt.TextElideMode.ElideMiddle, available))
        self._path_label.setToolTip(text)

    def resizeEvent(self, e: object) -> None:  # noqa: N802
        super().resizeEvent(e)  # type: ignore[arg-type]
        self._update_path_label()

    def _on_path_changed(self) -> None:
        self._update_path_label()
        self._back_btn.setEnabled(self._model.can_go_up)
        # Rebuild breadcrumbs
        while self._crumbs.count():
            item = self._crumbs.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        crumbs = self._model.breadcrumbs()
        for i, (label, path) in enumerate(crumbs):
            btn = QToolButton()
            btn.setText(label if i == 0 else f"› {label}")
            btn.setAccessibleName(label)
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda _c=False, p=path: self._model.navigate_to(p))
            self._crumbs.addWidget(btn)
        self._update_footer()
        self._update_stack()

    def _on_model_reset(self) -> None:
        self._restore_selection()
        self._update_footer()
        self._update_stack()
        if self._pending_edit is not None:
            path = self._pending_edit
            self._pending_edit = None
            self._begin_edit(path)

    def _update_footer(self) -> None:
        shown = self._model.file_count
        total = self._model.total_file_count
        folders = self._model.folder_count
        if self._model.filter_text:
            text = f"{shown} of {total} files"
        else:
            text = f"{total} file{'s' if total != 1 else ''}"
        if folders:
            text += f" in {folders} folder{'s' if folders != 1 else ''}"
        self._count_label.setText(text)

    def _schedule_size(self) -> None:
        self._size_worker.start(self._manager)

    def _on_size_computed(self, size: int) -> None:
        self._size_label.setText(human_size(size))

    def _on_double_clicked(self, idx: QModelIndex) -> None:
        path = idx.data(PATH_ROLE)
        if not isinstance(path, Path):
            return
        if bool(idx.data(IS_FOLDER_ROLE)):
            self._model.navigate_to(path)
        else:
            self.open_requested.emit([path])

    def _begin_edit(self, path: Path) -> None:
        row = self._model.row_for_path(path)
        if row < 0:
            self._pending_edit = path
            return
        idx = self._model.index(row, COL_NAME)
        view = self._active_view()
        view.setCurrentIndex(idx)
        view.edit(idx)

    def _on_rename_requested(self, path: Path, new_name: str) -> None:
        try:
            if path.is_dir():
                self._manager.rename_folder(path, new_name)
            else:
                cmd = RenameLibraryFileCommand(self._manager, path, new_name)
                self._manager.command_stack.push(cmd)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Rename", str(e))

    def _on_move_requested(self, paths: list[Path], dest: Path) -> None:
        files = [p for p in paths if p.is_file()]
        folders = [p for p in paths if p.is_dir()]
        if files:
            self._manager.command_stack.push(MoveLibraryFileCommand(self._manager, files, dest))
        if folders:
            self._manager.move_files(folders, dest)

    def _import_paths(self, paths: list[Path], dest: Path) -> None:
        created: list[Path] = []
        for p in paths:
            result = self._manager.import_file(p, folder=dest)
            if result is not None:
                created.append(result)
        if created:
            self._model.refresh()

    def _emit_export(self, files: list[Path], *, quick: bool) -> None:
        if not files:
            self._explain("Select one or more files to export.")
            return
        if quick:
            self.export_quick_requested.emit(files)
        else:
            self.export_requested.emit(files)

    def _open_in_new_window(self, files: list[Path]) -> None:
        if not files:
            self._explain("Select a file to open.")
            return
        for p in files:
            self.open_in_new_window_requested.emit(p)

    def _explain(self, message: str) -> None:
        QMessageBox.information(self, "Library", message)

    # Drops anywhere on the dock body (outside the views) import into the current folder
    def dragEnterEvent(self, e: QDragEnterEvent | None) -> None:  # noqa: N802
        if e is None:
            return
        mime = e.mimeData()
        if mime is not None and (mime.hasUrls() or mime.hasFormat(LIBRARY_PATHS_MIME)):
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent | None) -> None:  # noqa: N802
        if e is None:
            return
        mime = e.mimeData()
        if mime is None or not mime.hasUrls():
            return
        paths = [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()]
        self._import_paths(paths, self._model.current_path)
        e.acceptProposedAction()
