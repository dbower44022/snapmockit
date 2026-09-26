"""MainWindow — primary application window."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QCursor,
    QDesktopServices,
    QKeyEvent,
    QKeySequence,
    QPageLayout,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressDialog,
    QSystemTrayIcon,
    QToolButton,
    QWidget,
    QWidgetAction,
)

if TYPE_CHECKING:
    from datetime import datetime

    from PyQt6.QtWidgets import QGraphicsItem

    from snapmock.tools.base_tool import BaseTool

from snapmock.capture.manager import CaptureManager
from snapmock.capture.models import (
    HOTKEY_ACTION_FULL_SCREEN,
    HOTKEY_ACTION_REGION,
    HOTKEY_ACTION_WINDOW,
    ORIGIN_COMMAND_LINE,
    ORIGIN_MENU,
    ORIGIN_TOOLBAR,
    ORIGIN_TRAY,
    CaptureMetadata,
    CaptureMode,
    CaptureRequest,
    CaptureResult,
)
from snapmock.capture.tray import make_tray_icon
from snapmock.config import desktop_entry
from snapmock.config.constants import (
    APP_NAME,
    DEFAULT_PANEL_WIDTH,
    DOCUMENTATION_URL,
    ISSUES_URL,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    PROJECT_EXTENSION,
    REPOSITORY_URL,
    SNAGIT_EXTENSION,
    ZOOM_MAX,
    ZOOM_MIN,
)
from snapmock.config.packaging import in_flatpak, upgrade_instruction
from snapmock.config.settings import AppSettings
from snapmock.config.shortcuts import SHORTCUTS, key_sequences
from snapmock.core.clipboard_manager import ClipboardManager
from snapmock.core.document import Document
from snapmock.core.document_manager import DocumentManager
from snapmock.core.layer import Layer
from snapmock.core.scene import SnapScene
from snapmock.core.selection_manager import SelectionManager
from snapmock.core.theme_manager import ThemeMode, theme_manager
from snapmock.core.tool_themes import ToolThemeManager
from snapmock.core.update_check import Outcome, UpdateChecker, UpdateCheckResult
from snapmock.core.view import SnapView
from snapmock.io.exporter import (
    ExportFormat,
    ExportSettings,
    export_scene,
    print_scene,
    resolve_region,
    selection_rect,
)
from snapmock.io.importer import import_image
from snapmock.io.project_serializer import (
    load_project,
    read_capture_metadata,
    read_library_metadata,
    save_project,
)
from snapmock.io.snagit_reader import load_snagx
from snapmock.io.snagit_writer import save_snagx
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.emoji_item import EmojiItem
from snapmock.items.numbered_step_item import NumberedStepItem
from snapmock.items.stamp_item import StampItem
from snapmock.library.manager import LibraryManager
from snapmock.library.render import export_file, export_target
from snapmock.tools.arc_tool import ArcTool
from snapmock.tools.arrow_tool import ArrowTool
from snapmock.tools.blur_tool import BlurTool
from snapmock.tools.border_tool import BorderTool
from snapmock.tools.callout_tool import CalloutTool
from snapmock.tools.crop_tool import CropTool
from snapmock.tools.ellipse_tool import EllipseTool
from snapmock.tools.emoji_tool import EmojiTool
from snapmock.tools.eyedropper_tool import EyedropperTool
from snapmock.tools.freehand_tool import FreehandTool
from snapmock.tools.highlight_tool import HighlightTool
from snapmock.tools.lasso_select_tool import LassoSelectTool
from snapmock.tools.line_tool import LineTool
from snapmock.tools.numbered_step_tool import NumberedStepTool
from snapmock.tools.pan_tool import PanTool
from snapmock.tools.polygon_tool import PolygonTool
from snapmock.tools.raster_select_tool import RasterSelectTool
from snapmock.tools.rectangle_tool import RectangleTool
from snapmock.tools.select_tool import SelectTool
from snapmock.tools.stamp_tool import StampTool
from snapmock.tools.text_tool import TextTool
from snapmock.tools.tool_manager import ToolManager
from snapmock.tools.zoom_tool import ZoomTool
from snapmock.ui.accessibility import apply_default_names, set_tab_order
from snapmock.ui.color_picker import ColorPicker
from snapmock.ui.document_tabs import DocumentTabs
from snapmock.ui.export_dialog import ExportDialog
from snapmock.ui.icons import apply_action_icons, apply_menu_bar_icons, apply_tool_action_icons
from snapmock.ui.layer_panel import LayerPanel
from snapmock.ui.library_panel import LibraryPanel
from snapmock.ui.panel_modes import PanelMode, mode_for_width, panel_width_for
from snapmock.ui.property_panel import PropertyPanel
from snapmock.ui.status_bar import SnapStatusBar
from snapmock.ui.toast import Toast
from snapmock.ui.tool_options_bar import ToolOptionsBar
from snapmock.ui.toolbar import MainToolBar, SnapToolBar
from snapmock.ui.unmet_requirements import check_requirements, show_unmet_requirements
from snapmock.ui.unsaved_changes_dialog import UnsavedChangesDialog
from snapmock.ui.welcome_panel import WelcomePanel

DELAY_CHOICES = (0, 3, 5, 10)
MODE_LABELS = {
    CaptureMode.REGION: "Capture &Region",
    CaptureMode.ACTIVE_WINDOW: "Capture Active &Window",
    CaptureMode.FULL_SCREEN: "Capture &Full Screen",
}
MODE_ACTIONS = {
    CaptureMode.REGION: HOTKEY_ACTION_REGION,
    CaptureMode.ACTIVE_WINDOW: HOTKEY_ACTION_WINDOW,
    CaptureMode.FULL_SCREEN: HOTKEY_ACTION_FULL_SCREEN,
}
MOMENTARY_PICK_KEYS: dict[str, str] = {
    "highlight": "highlight_color",
    "numbered_step": "badge_color",
    "text": "text_color",
}
"""Blur PRD 4.7's per-tool primary colour property for the momentary Alt mode; every other
tool takes the stroke colour."""


def momentary_pick_key(tool: BaseTool) -> str | None:
    """Which colour property a colour picked while Alt was held sets on *tool* (4.7).

    None when the tool carries no colour property at all, as the Select, Crop, Pan, and
    Zoom tools do not: nothing is applied and nothing is lost.
    """
    wanted = MOMENTARY_PICK_KEYS.get(tool.tool_id, "stroke_color")
    if wanted in tool.creation_defaults:
        return wanted
    for fallback in ("stroke_color", "text_color", "badge_color", "highlight_color"):
        if fallback in tool.creation_defaults:
            return fallback
    return None


# Tools that are held or momentary and never restored as the last-used tool.
TRANSIENT_TOOLS = frozenset({"pan", "zoom", "eyedropper"})
TRAY_UNAVAILABLE_MESSAGE = (
    "This desktop does not provide a system tray. Global hotkeys and the Capture menu still work."
)


_extra_windows: list[MainWindow] = []


def create_capture_manager(settings: AppSettings) -> CaptureManager:
    """Build the process-wide CaptureManager from the platform backends (PRD 6.2)."""
    from snapmock.capture import select_backends

    backend, hotkeys = select_backends()
    return CaptureManager(backend, hotkeys, settings)


def _as_color(value: object) -> QColor:
    """A QColor from a preference change value (QColor or colour text)."""
    return QColor(value) if isinstance(value, QColor) else QColor(str(value))


log = logging.getLogger("snapmock")


def _megabytes(path: Path) -> str:
    """A file's size for a sentence the user reads, in whole megabytes."""
    try:
        return f"{path.stat().st_size / 1_000_000:.0f} MB"
    except OSError:
        return "its size unknown"


class MainWindow(QMainWindow):
    """Primary application window.

    Owns the DocumentManager (one Document per open tab, each with its own
    SnapScene, SnapView, SelectionManager and ClipboardManager), the shared
    ToolManager, and the UI panels.  ``_scene``, ``_view``,
    ``_selection_manager`` and ``_clipboard`` always refer to the active tab.
    """

    def __init__(
        self,
        *,
        restore_session: bool = False,
        capture_manager: CaptureManager | None = None,
        primary_capture: bool = True,
    ) -> None:
        super().__init__()
        self._settings = AppSettings()
        self._apply_first_run_defaults()
        self._panel_mode = PanelMode.FULL
        # Theme (General UI PRD 13): applied before any widget is built so the
        # first paint is already themed; live switches repaint through the signal.
        self._theme = theme_manager()
        self._theme.set_icon_size(self._settings.icon_size())
        self._theme.set_ui_font_size(self._settings.ui_font_size())
        self._theme.set_mode(ThemeMode.from_value(self._settings.theme_mode()))
        self._theme.apply()
        self._theme.theme_changed.connect(self._on_theme_changed)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.resize(self._default_window_size())

        # Screen capture (Screen Capture PRD): one manager per process. Only the
        # primary window connects its results, owns the tray icon, and quits.
        self._capture = capture_manager or create_capture_manager(self._settings)
        self._primary_capture = primary_capture
        # Help > Check for Updates (General UI PRD 3.8): one check at a time, on the
        # event loop; the result arrives as a signal (implementation notes Section 19).
        self._update_checker = UpdateChecker(self)
        self._marker_editor: QWidget | None = None
        self._update_checker.finished.connect(self._on_update_check_finished)
        self._tray: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        self._hidden_in_tray = False
        self._quit_requested = False
        self._pending_capture_clipboard = False
        self._capture_mode_actions: dict[CaptureMode, QAction] = {}
        self._toolbar_mode_actions: dict[CaptureMode, QAction] = {}
        self._delay_groups: list[QActionGroup] = []
        self._capture_toggle_actions: list[tuple[str, QAction]] = []
        self._capture_button: QToolButton | None = None
        self._momentary_tool: str | None = None
        self._momentary_pick_serial = 0
        self._picker_pick_active = False
        self._picker_bar_callback: Callable[[QColor], None] | None = None

        # Library: auto-saved capture workspace (Library PRD)
        self._library = LibraryManager(self._settings.library_directory(), parent=self)

        # Documents (tabs): each owns a scene, view, selection and clipboard.
        # There is always at least one document open.
        self._documents = DocumentManager(self)
        self._wired_docs: set[str] = set()
        first = Document(self._new_scene(), parent=self)
        self._documents.add(first)

        # The tool manager is shared and rebound to the active document.
        self._tool_manager = ToolManager(first.scene, first.selection_manager, parent=self)
        self._register_tools()
        # Presets and themes (PRD 5.2, 11.8, 11.9): built right after registration so the
        # factory defaults it captures are untouched.
        self._tool_themes = ToolThemeManager(self._tool_manager, self._settings, parent=self)
        self._tool_manager.activate("select")

        self._tabs = DocumentTabs(self._documents, self)
        self.setCentralWidget(self._tabs)
        self._welcome: WelcomePanel | None = None

        # UI panels
        # Object names let saveState / restoreState persist the layout (PRD 2.3, 15.4).
        self._main_toolbar = MainToolBar(self)
        self._main_toolbar.setObjectName("MainToolBar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._main_toolbar)
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)

        # The Left Tool Palette (PRD 2.1): a vertical toolbar on the left edge.
        self._toolbar = SnapToolBar(self._tool_manager, self)
        self._toolbar.setObjectName("ToolPalette")
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._toolbar)

        self._tool_options = ToolOptionsBar(self._tool_manager, self)
        self._tool_options.setObjectName("ToolOptionsBar")
        self._tool_options.set_theme_manager(self._tool_themes)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._tool_options)
        self._tool_options.set_selection_manager(self._selection_manager)

        self._layer_panel = LayerPanel(self._scene, self)
        self._layer_panel.setObjectName("LayerPanel")
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._layer_panel)

        self._property_panel = PropertyPanel(self._selection_manager, self._scene, self)
        self._property_panel.setObjectName("PropertyPanel")
        self._property_panel.set_tool_manager(self._tool_manager)
        self._load_tool_session()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._property_panel)

        self._library_panel = LibraryPanel(self._library, self._settings, self)
        self._library_panel.set_is_open_provider(
            lambda p: self._documents.find_by_path(p) is not None
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._library_panel)
        self._library_panel.open_requested.connect(self._open_library_files)
        self._library_panel.open_in_new_window_requested.connect(self._open_in_new_window)
        self._library_panel.files_about_to_be_deleted.connect(self._close_documents_for_paths)
        self._library_panel.export_requested.connect(self._export_library_files)
        self._library_panel.export_quick_requested.connect(self._export_library_files_quick)
        self._library_panel.new_canvas_requested.connect(self._library_new_canvas)
        self._library.file_created.connect(self._on_library_file_created)
        self._documents.document_added.connect(lambda _d: self._library_panel.refresh_open_state())
        self._documents.document_removed.connect(
            lambda _d: self._library_panel.refresh_open_state()
        )
        self._toast = Toast(self)
        # A start that owes the user a message keeps the toast; the desktop-entry
        # offer waits for the next start rather than replacing it (menu-entry
        # decision 1).
        self._startup_message_shown = False

        self._status_bar = SnapStatusBar(first)
        self.setStatusBar(self._status_bar)
        self._status_bar.setVisible(self._settings.status_bar_visible())
        self._configure_view(first.view)

        # Wire tool hint to status bar
        self._tool_manager.tool_changed.connect(self._on_tool_changed_for_hint)

        # Document / tab signals
        self._documents.active_changed.connect(self._on_active_document_changed)
        self._documents.document_title_changed.connect(lambda _d: self._update_title())
        self._tabs.close_requested.connect(self._close_document)
        self._tabs.close_others_requested.connect(self._close_other_documents)
        self._tabs.close_all_requested.connect(self._close_all_documents)
        self._tabs.close_right_requested.connect(self._close_documents_to_right)
        self._tabs.reveal_in_file_manager_requested.connect(self._reveal_document_in_file_manager)
        self._tabs.reveal_in_library_requested.connect(self._reveal_document_in_library)

        # Menu bar
        self._recent_menu: QMenu | None = None
        # Arrange action references (populated in _setup_arrange_menu)
        self._bring_front_action: QAction | None = None
        self._bring_forward_action: QAction | None = None
        self._send_backward_action: QAction | None = None
        self._send_to_back_action: QAction | None = None
        self._align_menu: QMenu | None = None
        self._distribute_menu: QMenu | None = None
        self._align_canvas_action: QAction | None = None
        self._flip_h_action: QAction | None = None
        self._flip_v_action: QAction | None = None
        # Layer action references (populated in _setup_layer_menu)
        self._layer_move_up_action: QAction | None = None
        self._layer_move_down_action: QAction | None = None
        self._layer_move_top_action: QAction | None = None
        self._layer_move_bottom_action: QAction | None = None
        self._layer_delete_action: QAction | None = None
        self._layer_merge_down_action: QAction | None = None
        # Merge Down and Merge Visible ask once per session (follow-up silence 1)
        self._merge_dont_ask: bool = False
        # Tools menu action map
        self._tool_actions: dict[str, QAction] = {}
        # Menu actions the Main Toolbar reuses, keyed like SHORTCUTS (PRD 4.2)
        self._actions: dict[str, QAction] = {}
        self._setup_menus()
        menu_bar = self.menuBar()
        if menu_bar is not None:
            menu_bar.setAccessibleName("Menu bar")
        self._populate_main_toolbar()
        bar_actions = {
            "New Layer": self._layer_new_action,
            "Delete Layer": self._layer_delete_action,
            "Duplicate Layer": self._layer_duplicate_action,
            "Merge Down": self._layer_merge_down_action,
        }
        self._layer_panel.set_actions({k: a for k, a in bar_actions.items() if a is not None})
        self._layer_panel.layer_hovered.connect(self._on_layer_hovered)
        self._property_panel.canvas_setting_changed.connect(self._on_canvas_setting_changed)
        ColorPicker.set_eyedropper_handler(self._pick_color_for_picker)
        self._tool_manager.tool_changed.connect(self._on_tool_changed_for_picker)
        self._setup_capture_toolbar()
        self._name_extension_buttons()
        self._status_bar_action.setChecked(self._settings.status_bar_visible())
        self._update_undo_redo_text()

        # Autosave timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        if self._settings.autosave_enabled():
            self._autosave_timer.start(self._settings.autosave_interval_minutes() * 60_000)

        # Per-document signal wiring (title, layer state, menu state)
        self._wire_document(first)

        # The default arrangement, kept for View > Reset Layout (PRD 2.3).
        self._apply_default_dock_sizes()
        self._default_layout_state = bytes(self.saveState().data())

        # Restore window geometry and layout
        geo = self._settings.window_geometry()
        if geo is not None:
            self.restoreGeometry(geo)
        state = self._settings.window_state()
        if state is not None:
            self.restoreState(state)
            self._enforce_toolbar_layout()
            self._recover_floating_panels()
        else:
            self._apply_default_dock_sizes()

        self._update_panel_modes(force=True)
        self._restore_last_tool()
        self._update_title()
        self._apply_tab_order()
        self._tool_manager.tool_changed.connect(self._on_tool_changed_for_tab_order)

        if self._primary_capture:
            self._capture.set_onboarding_gate(self._capture_onboarding_gate)
            self._capture.capture_completed.connect(self._on_capture_completed)
            self._capture.capture_failed.connect(self._on_capture_failed)
            self._capture.capture_refused.connect(self._on_capture_refused)
            self._capture.countdown_tick.connect(self._on_capture_countdown)
            self._capture.hotkeys_changed.connect(self._sync_capture_shortcuts)
            self._setup_tray()

        if restore_session:
            self._restore_session()
        if self._settings.show_welcome_at_startup():
            self.show_welcome()

    def _apply_first_run_defaults(self) -> None:
        """The first launch (PRD 16.2): snap on, the System theme, the Welcome panel on.

        Every other Section 16.2 line is already the settings default. Written once,
        so a later launch keeps whatever the user changed.
        """
        if self._settings.first_run_done():
            return
        self._settings.set_snap_to_grid(True)
        self._settings.set_theme_mode(ThemeMode.SYSTEM.value)
        self._settings.set_show_welcome_at_startup(True)
        self._settings.set_first_run_done(True)

    # ---- Welcome panel (PRD 16) ----

    def show_welcome(self) -> None:
        """Show the Welcome panel in place of the canvas (first launch, Help menu)."""
        if self._welcome is None:
            self._welcome = WelcomePanel(self._settings)
            self._welcome.open_image_requested.connect(self._welcome_open_image)
            self._welcome.paste_requested.connect(self._welcome_paste)
            self._welcome.new_canvas_requested.connect(self._welcome_new_canvas)
            self._welcome.closed.connect(self.hide_welcome)
        self._tabs.show_page(self._welcome)
        self._welcome.setFocus()

    def hide_welcome(self) -> None:
        """Return to the active document's canvas."""
        self._tabs.show_documents()
        self._view.setFocus()

    @property
    def welcome_panel(self) -> WelcomePanel | None:
        return self._welcome

    def welcome_is_showing(self) -> bool:
        return self._welcome is not None and self._tabs.current_page is self._welcome

    def _welcome_open_image(self) -> None:
        if self._file_import_image():
            self.hide_welcome()

    def _welcome_paste(self) -> None:
        if not check_requirements(
            self,
            "Paste from Clipboard",
            [(self._clipboard_has_content(), "content on the clipboard")],
        ):
            return
        self._edit_paste()
        self.hide_welcome()

    def _welcome_new_canvas(self, width: int, height: int) -> None:
        scene = SnapScene(width, height)
        scene.set_background_color(self._settings.default_canvas_color())
        self._add_document(Document(scene, parent=self))
        self.hide_welcome()

    @staticmethod
    def _default_window_size() -> QSize:
        """80 percent of the primary screen (PRD 17.1), never below the minimum size."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return QSize(1200, 800)
        available = screen.availableGeometry().size()
        return QSize(
            max(MIN_WINDOW_WIDTH, int(available.width() * 0.8)),
            max(MIN_WINDOW_HEIGHT, int(available.height() * 0.8)),
        )

    def _apply_default_dock_sizes(self) -> None:
        """The default proportions of PRD 2.2: 300 px right stack, Library 250 px tall."""
        self.resizeDocks(
            [self._layer_panel, self._property_panel],
            [DEFAULT_PANEL_WIDTH, DEFAULT_PANEL_WIDTH],
            Qt.Orientation.Horizontal,
        )
        self.resizeDocks([self._library_panel], [250], Qt.Orientation.Vertical)
        layer_h = self._layer_panel.preferred_height()
        self.resizeDocks([self._layer_panel], [layer_h], Qt.Orientation.Vertical)

    def _toggle_dark_mode(self, checked: bool) -> None:
        """View > Dark Mode (PRD 3.3): an explicit Light or Dark choice, persisted."""
        mode = ThemeMode.DARK if checked else ThemeMode.LIGHT
        if self._theme.mode is mode:
            return
        self._settings.set_theme_mode(mode.value)
        self._theme.set_mode(mode)

    def set_theme_mode(self, mode: ThemeMode) -> None:
        """Choose Light, Dark, or System (Preferences > Appearance) and persist it."""
        self._settings.set_theme_mode(mode.value)
        self._theme.set_mode(mode)

    def _on_theme_changed(self, resolved: str) -> None:
        """Repaint what reads theme colours outside the style sheet (PRD 13.4)."""
        self._dark_mode_action.blockSignals(True)
        self._dark_mode_action.setChecked(resolved == "dark")
        self._dark_mode_action.blockSignals(False)
        self._apply_menu_icons()
        for doc in self._documents.documents:
            doc.view.apply_theme()
        select_tool = self._tool_manager.tool("select")
        if isinstance(select_tool, SelectTool):
            select_tool.apply_theme()

    def _view_reset_layout(self) -> None:
        """Restore every panel and toolbar to its default position, size, and visibility."""
        self.restoreState(self._default_layout_state)
        self._enforce_toolbar_layout()
        for widget in (
            self._main_toolbar,
            self._toolbar,
            self._tool_options,
            self._layer_panel,
            self._property_panel,
            self._library_panel,
        ):
            widget.setVisible(True)
        if self._status_bar_action is not None:
            self._status_bar_action.setChecked(True)
        self._apply_default_dock_sizes()
        self._update_panel_modes(force=True)

    # ---- multi-monitor (PRD 15.3) ----

    def _recover_floating_panels(self) -> None:
        """Move a floating panel onto the primary screen when its saved position is on
        no connected screen (PRD 15.3). Docked panels and on-screen panels are untouched."""
        screens = QApplication.screens()
        primary = QApplication.primaryScreen()
        if primary is None:
            return
        for panel in (self._layer_panel, self._property_panel, self._library_panel):
            if not panel.isFloating():
                continue
            frame = panel.frameGeometry()
            if any(screen.geometry().intersects(frame) for screen in screens):
                continue
            available = primary.availableGeometry()
            panel.move(available.topLeft() + QPoint(40, 40))

    # ---- panel collapse modes (PRD 15.1, 15.2) ----

    @property
    def panel_mode(self) -> PanelMode:
        return self._panel_mode

    def _update_panel_modes(self, *, force: bool = False) -> None:
        """Pick the right panels' mode from the window width and the two thresholds."""
        mode = mode_for_width(
            self.width(),
            self._settings.panel_narrow_threshold(),
            self._settings.panel_strip_threshold(),
        )
        if mode is self._panel_mode and not force:
            return
        self._panel_mode = mode
        self._layer_panel.set_mode(mode)
        self._property_panel.set_mode(mode)
        width = panel_width_for(mode)
        self.resizeDocks(
            [self._layer_panel, self._property_panel], [width, width], Qt.Orientation.Horizontal
        )

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_property_panel"):
            self._update_panel_modes()

    def _name_extension_buttons(self) -> None:
        """The overflow button each toolbar opens when its widgets do not fit (PRD 15.1)."""
        for bar, name in (
            (self._tool_options, "More tool options"),
            (self._main_toolbar, "More toolbar buttons"),
            (self._toolbar, "More tools"),
        ):
            ext = bar.findChild(QToolButton, "qt_toolbar_ext_button")
            if ext is not None:
                ext.setAccessibleName(name)
                ext.setToolTip(name)

    def _restore_last_tool(self) -> None:
        """Reactivate the tool that was active when the last session ended (PRD 15.4)."""
        tool_id = self._settings.last_tool()
        if tool_id and tool_id not in TRANSIENT_TOOLS and self._tool_manager.tool(tool_id):
            self._tool_manager.activate(tool_id)

    def _register_tools(self) -> None:
        """Register all built-in tools with the ToolManager."""
        self._tool_manager.register(SelectTool())
        self._tool_manager.register(RectangleTool())
        self._tool_manager.register(EllipseTool())
        self._tool_manager.register(ArrowTool())
        self._tool_manager.register(LineTool())
        self._tool_manager.register(ArcTool())
        self._tool_manager.register(PolygonTool())
        self._tool_manager.register(TextTool())
        self._tool_manager.register(FreehandTool())
        self._tool_manager.register(BlurTool())
        self._tool_manager.register(HighlightTool())
        self._tool_manager.register(CalloutTool())
        self._tool_manager.register(NumberedStepTool())
        self._tool_manager.register(StampTool())
        self._tool_manager.register(EmojiTool())
        self._tool_manager.register(CropTool())
        self._tool_manager.register(BorderTool())
        self._tool_manager.register(RasterSelectTool())
        self._tool_manager.register(EyedropperTool())
        self._tool_manager.register(PanTool())
        self._tool_manager.register(ZoomTool())
        self._tool_manager.register(LassoSelectTool())

    # ---- menus ----

    def _register(self, key: str, action: QAction | None) -> None:
        """Remember a menu action the Main Toolbar reuses."""
        if action is not None:
            self._actions[key] = action

    def _populate_main_toolbar(self) -> None:
        """PRD 4.2's six groups over the menu actions; Group 0 arrives with the capture button."""
        a = self._actions
        bar = self._main_toolbar
        bar.add_group([a["file.new"], a["file.open"], a["file.save"], a["file.export_quick_png"]])
        bar.add_group(
            [a["edit.undo"], a["edit.redo"], a["edit.cut"], a["edit.copy"], a["edit.paste"]]
        )
        bar.add_group([a["edit.duplicate"], a["edit.delete"]])
        bar.add_group([a["arrange.bring_to_front"], a["arrange.send_to_back"]])
        bar.add_alignment_group(
            [
                a["arrange.align_left"],
                a["arrange.align_center"],
                a["arrange.align_right"],
                a["arrange.align_top"],
                a["arrange.align_middle"],
                a["arrange.align_bottom"],
            ]
        )
        bar.add_zoom_group(a["view.zoom_out"], a["view.zoom_in"], a["view.fit_window"], self._view)
        bar.set_selection_manager(self._selection_manager)
        # The Select tool's options bar shows the same alignment rows plus Distribute (PRD 5.3).
        self._tool_options.set_selection_actions(
            [
                a["arrange.align_left"],
                a["arrange.align_center"],
                a["arrange.align_right"],
                a["arrange.align_top"],
                a["arrange.align_middle"],
                a["arrange.align_bottom"],
                a["arrange.distribute_horizontal"],
                a["arrange.distribute_vertical"],
            ]
        )

    def _enforce_toolbar_layout(self) -> None:
        """The PRD 2.1 toolbar areas, whatever a saved state says (toolbars are not movable)."""
        if self.toolBarArea(self._main_toolbar) != Qt.ToolBarArea.TopToolBarArea:
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._main_toolbar)
        if self.toolBarArea(self._toolbar) != Qt.ToolBarArea.LeftToolBarArea:
            self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._toolbar)
        if self.toolBarArea(self._tool_options) != Qt.ToolBarArea.TopToolBarArea:
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._tool_options)
        if not self.toolBarBreak(self._tool_options):
            self.insertToolBarBreak(self._tool_options)

    def _setup_menus(self) -> None:
        """Create menu bar actions."""
        menu_bar = self.menuBar()
        if menu_bar is None:
            return

        self._setup_file_menu(menu_bar)
        self._setup_edit_menu(menu_bar)
        self._setup_view_menu(menu_bar)
        self._setup_layer_menu(menu_bar)
        self._setup_image_menu(menu_bar)
        self._setup_arrange_menu(menu_bar)
        self._setup_tools_menu(menu_bar)
        self._setup_library_menu(menu_bar)
        self._setup_capture_menu(menu_bar)
        self._setup_help_menu(menu_bar)
        self._apply_menu_icons()

    def _apply_menu_icons(self) -> None:
        """Themed icons on every menu row that has one (General UI PRD 13.4)."""
        apply_menu_bar_icons(self.menuBar())
        apply_tool_action_icons(self._tool_actions)
        if self._tray_menu is not None:
            apply_action_icons(self._tray_menu.actions())

    def _setup_file_menu(self, menu_bar: QMenuBar) -> None:  # noqa: C901
        file_menu = menu_bar.addMenu("&File")
        if file_menu is None:
            return

        new_action = file_menu.addAction("&New")
        if new_action is not None:
            new_action.setShortcut(QKeySequence(SHORTCUTS["file.new"]))
            new_action.triggered.connect(self._file_new)
        self._register("file.new", new_action)

        open_action = file_menu.addAction("&Open...")
        if open_action is not None:
            open_action.setShortcut(QKeySequence(SHORTCUTS["file.open"]))
            open_action.triggered.connect(self._file_open)
        self._register("file.open", open_action)

        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._update_recent_files_menu()

        close_action = file_menu.addAction("&Close")
        if close_action is not None:
            close_action.setShortcut(QKeySequence(SHORTCUTS["file.close_tab"]))
            close_action.triggered.connect(self._file_close_tab)

        file_menu.addSeparator()

        save_action = file_menu.addAction("&Save")
        if save_action is not None:
            save_action.setShortcut(QKeySequence(SHORTCUTS["file.save"]))
            save_action.triggered.connect(self._file_save)
        self._register("file.save", save_action)

        save_as_action = file_menu.addAction("Save &As...")
        if save_as_action is not None:
            save_as_action.setShortcut(QKeySequence(SHORTCUTS["file.save_as"]))
            save_as_action.triggered.connect(self._file_save_as)

        file_menu.addSeparator()

        import_action = file_menu.addAction("&Import Image...")
        if import_action is not None:
            import_action.setShortcut(QKeySequence(SHORTCUTS["file.import_image"]))
            import_action.triggered.connect(self._file_import_image)

        export_action = file_menu.addAction("&Export...")
        if export_action is not None:
            export_action.setShortcut(QKeySequence(SHORTCUTS["file.export"]))
            export_action.triggered.connect(self._file_export)

        export_png_action = file_menu.addAction("Export &Quick (PNG)")
        if export_png_action is not None:
            export_png_action.setShortcut(QKeySequence(SHORTCUTS["file.export_quick_png"]))
            export_png_action.triggered.connect(self._file_export_quick_png)
        self._register("file.export_quick_png", export_png_action)

        file_menu.addSeparator()

        print_action = file_menu.addAction("&Print...")
        if print_action is not None:
            print_action.setShortcut(QKeySequence(SHORTCUTS["file.print"]))
            print_action.triggered.connect(self._file_print)

        file_menu.addSeparator()

        prefs_action = file_menu.addAction("Pre&ferences...")
        if prefs_action is not None:
            prefs_action.setShortcut(QKeySequence(SHORTCUTS["file.preferences"]))
            prefs_action.triggered.connect(self._file_preferences)

        file_menu.addSeparator()

        quit_action = file_menu.addAction("&Quit")
        if quit_action is not None:
            quit_action.setShortcut(QKeySequence(SHORTCUTS["file.quit"]))
            quit_action.triggered.connect(self.close)

    def _setup_edit_menu(self, menu_bar: QMenuBar) -> None:
        edit_menu = menu_bar.addMenu("&Edit")
        if edit_menu is None:
            return

        self._undo_action = QAction("&Undo", self)
        self._undo_action.setShortcut(QKeySequence(SHORTCUTS["edit.undo"]))
        self._undo_action.triggered.connect(self._edit_undo)
        edit_menu.addAction(self._undo_action)
        self._register("edit.undo", self._undo_action)

        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcuts(key_sequences("edit.redo"))
        self._redo_action.triggered.connect(self._edit_redo)
        edit_menu.addAction(self._redo_action)
        self._register("edit.redo", self._redo_action)

        edit_menu.addSeparator()

        cut_action = edit_menu.addAction("Cu&t")
        if cut_action is not None:
            cut_action.setShortcut(QKeySequence(SHORTCUTS["edit.cut"]))
            cut_action.triggered.connect(self._edit_cut)
        self._register("edit.cut", cut_action)

        copy_action = edit_menu.addAction("&Copy")
        if copy_action is not None:
            copy_action.setShortcut(QKeySequence(SHORTCUTS["edit.copy"]))
            copy_action.triggered.connect(self._edit_copy)
        self._register("edit.copy", copy_action)

        copy_all_action = edit_menu.addAction("Copy Al&l")
        if copy_all_action is not None:
            copy_all_action.setShortcut(QKeySequence(SHORTCUTS["edit.copy_all"]))
            copy_all_action.triggered.connect(self._edit_copy_all)

        paste_action = edit_menu.addAction("&Paste")
        if paste_action is not None:
            paste_action.setShortcut(QKeySequence(SHORTCUTS["edit.paste"]))
            paste_action.triggered.connect(self._edit_paste)
        self._register("edit.paste", paste_action)

        paste_in_place_action = edit_menu.addAction("Paste in &Place")
        if paste_in_place_action is not None:
            paste_in_place_action.setShortcut(QKeySequence(SHORTCUTS["edit.paste_in_place"]))
            paste_in_place_action.triggered.connect(self._edit_paste_in_place)

        delete_action = edit_menu.addAction("&Delete")
        if delete_action is not None:
            delete_action.setShortcuts(key_sequences("edit.delete"))
            delete_action.triggered.connect(self._edit_delete)
        self._register("edit.delete", delete_action)

        edit_menu.addSeparator()

        duplicate_action = edit_menu.addAction("D&uplicate")
        if duplicate_action is not None:
            duplicate_action.setShortcut(QKeySequence(SHORTCUTS["edit.duplicate"]))
            duplicate_action.triggered.connect(self._edit_duplicate)
        self._register("edit.duplicate", duplicate_action)

        edit_menu.addSeparator()

        select_all_action = edit_menu.addAction("Select &All")
        if select_all_action is not None:
            select_all_action.setShortcut(QKeySequence(SHORTCUTS["edit.select_all"]))
            select_all_action.triggered.connect(self._edit_select_all)

        select_on_layer_action = edit_menu.addAction("Select All on La&yer")
        if select_on_layer_action is not None:
            select_on_layer_action.triggered.connect(self._edit_select_all_on_layer)

        select_all_layers_action = edit_menu.addAction("Select All Laye&rs")
        if select_all_layers_action is not None:
            select_all_layers_action.setShortcut(QKeySequence(SHORTCUTS["edit.select_all_layers"]))
            select_all_layers_action.triggered.connect(self._edit_select_all_layers)

        deselect_action = edit_menu.addAction("D&eselect")
        if deselect_action is not None:
            deselect_action.setShortcut(QKeySequence(SHORTCUTS["edit.deselect"]))
            deselect_action.triggered.connect(self._edit_deselect)

        select_all_text_action = edit_menu.addAction("Select All &Text")
        if select_all_text_action is not None:
            select_all_text_action.setShortcut(QKeySequence(SHORTCUTS["edit.select_all_text"]))
            select_all_text_action.triggered.connect(self._edit_select_all_text)

        edit_menu.addSeparator()

        find_color_action = edit_menu.addAction("&Find/Replace Color...")
        if find_color_action is not None:
            find_color_action.triggered.connect(self._edit_find_replace_color)

    def _setup_view_menu(self, menu_bar: QMenuBar) -> None:
        view_menu = menu_bar.addMenu("&View")
        if view_menu is None:
            return

        zoom_in = view_menu.addAction("Zoom &In")
        if zoom_in is not None:
            zoom_in.setShortcuts(key_sequences("view.zoom_in"))
            zoom_in.triggered.connect(self._view_zoom_in)
        self._register("view.zoom_in", zoom_in)

        zoom_out = view_menu.addAction("Zoom &Out")
        if zoom_out is not None:
            zoom_out.setShortcut(QKeySequence(SHORTCUTS["view.zoom_out"]))
            zoom_out.triggered.connect(self._view_zoom_out)
        self._register("view.zoom_out", zoom_out)

        fit_action = view_menu.addAction("&Fit to Window")
        if fit_action is not None:
            fit_action.setShortcut(QKeySequence(SHORTCUTS["view.fit_window"]))
            fit_action.triggered.connect(lambda: self._view.fit_in_view_all())
        self._register("view.fit_window", fit_action)

        actual_action = view_menu.addAction("Zoom to &100%")
        if actual_action is not None:
            actual_action.setShortcut(QKeySequence(SHORTCUTS["view.actual_size"]))
            actual_action.triggered.connect(lambda: self._view.set_zoom(100))

        zoom_sel_action = view_menu.addAction("Zoom to &Selection")
        if zoom_sel_action is not None:
            zoom_sel_action.setShortcut(QKeySequence(SHORTCUTS["view.zoom_to_selection"]))
            zoom_sel_action.triggered.connect(self._view_zoom_to_selection)

        view_menu.addSeparator()

        self._grid_action = QAction("Show &Grid", self)
        self._grid_action.setCheckable(True)
        self._grid_action.setShortcut(QKeySequence(SHORTCUTS["view.toggle_grid"]))
        grid_vis = self._settings.grid_visible()
        self._grid_action.setChecked(grid_vis)
        self._view.set_grid_visible(grid_vis)
        self._grid_action.toggled.connect(self._toggle_grid)
        view_menu.addAction(self._grid_action)

        self._snap_grid_action = QAction("&Snap to Grid", self)
        self._snap_grid_action.setCheckable(True)
        self._snap_grid_action.setShortcut(QKeySequence(SHORTCUTS["view.snap_to_grid"]))
        self._snap_grid_action.setChecked(self._settings.snap_to_grid())
        self._snap_grid_action.toggled.connect(self._toggle_snap_to_grid)
        view_menu.addAction(self._snap_grid_action)

        self._rulers_action = QAction("Show &Rulers", self)
        self._rulers_action.setCheckable(True)
        self._rulers_action.setShortcut(QKeySequence(SHORTCUTS["view.toggle_rulers"]))
        rulers_vis = self._settings.rulers_visible()
        self._rulers_action.setChecked(rulers_vis)
        self._view.set_rulers_visible(rulers_vis)
        self._rulers_action.toggled.connect(self._toggle_rulers)
        view_menu.addAction(self._rulers_action)

        self._crosshairs_action = QAction("Show &Crosshairs", self)
        self._crosshairs_action.setCheckable(True)
        self._crosshairs_action.setChecked(self._settings.crosshairs_visible())
        self._crosshairs_action.toggled.connect(self._toggle_crosshairs)
        view_menu.addAction(self._crosshairs_action)

        # Guides (PRD 3.3, 6.5)
        self._guides_action = QAction("Show G&uides", self)
        self._guides_action.setCheckable(True)
        self._guides_action.setShortcut(QKeySequence(SHORTCUTS["view.toggle_guides"]))
        self._guides_action.setChecked(self._settings.guides_visible())
        self._guides_action.toggled.connect(self._toggle_guides)
        view_menu.addAction(self._guides_action)
        self._register("view.toggle_guides", self._guides_action)

        self._snap_guides_action = QAction("Snap to Gu&ides", self)
        self._snap_guides_action.setCheckable(True)
        self._snap_guides_action.setChecked(self._settings.snap_to_guides())
        self._snap_guides_action.toggled.connect(self._toggle_snap_to_guides)
        view_menu.addAction(self._snap_guides_action)

        self._lock_guides_action = QAction("Loc&k Guides", self)
        self._lock_guides_action.setCheckable(True)
        self._lock_guides_action.setChecked(self._settings.guides_locked())
        self._lock_guides_action.toggled.connect(self._toggle_lock_guides)
        view_menu.addAction(self._lock_guides_action)

        clear_guides = view_menu.addAction("Clear &All Guides")
        if clear_guides is not None:
            clear_guides.triggered.connect(self._view_clear_guides)

        view_menu.addSeparator()

        # Panel visibility toggles
        main_toolbar_toggle = self._main_toolbar.toggleViewAction()
        if main_toolbar_toggle is not None:
            main_toolbar_toggle.setText("Show &Main Toolbar")
            view_menu.addAction(main_toolbar_toggle)

        toolbar_toggle = self._toolbar.toggleViewAction()
        if toolbar_toggle is not None:
            toolbar_toggle.setText("Show Tool &Palette")
            view_menu.addAction(toolbar_toggle)

        options_toggle = self._tool_options.toggleViewAction()
        if options_toggle is not None:
            options_toggle.setText("Show Tool &Options")
            view_menu.addAction(options_toggle)

        layer_toggle = self._layer_panel.toggleViewAction()
        if layer_toggle is not None:
            layer_toggle.setText("Show &Layer Panel")
            view_menu.addAction(layer_toggle)

        property_toggle = self._property_panel.toggleViewAction()
        if property_toggle is not None:
            property_toggle.setText("Show &Property Panel")
            view_menu.addAction(property_toggle)

        library_toggle = self._library_panel.toggleViewAction()
        if library_toggle is not None:
            view_menu.addAction(library_toggle)

        self._status_bar_action = QAction("Show &Status Bar", self)
        self._status_bar_action.setCheckable(True)
        self._status_bar_action.setChecked(True)
        self._status_bar_action.toggled.connect(self._toggle_status_bar)
        view_menu.addAction(self._status_bar_action)

        view_menu.addSeparator()

        reset_layout = view_menu.addAction("Reset &Layout")
        if reset_layout is not None:
            reset_layout.triggered.connect(self._view_reset_layout)

        self._dark_mode_action = QAction("&Dark Mode", self)
        self._dark_mode_action.setCheckable(True)
        self._dark_mode_action.setChecked(self._theme.resolved == "dark")
        self._dark_mode_action.toggled.connect(self._toggle_dark_mode)
        view_menu.addAction(self._dark_mode_action)

        view_menu.addSeparator()

        next_tab = view_menu.addAction("&Next Tab")
        if next_tab is not None:
            next_tab.setShortcut(QKeySequence(SHORTCUTS["view.next_tab"]))
            next_tab.triggered.connect(self._documents.activate_next)

        prev_tab = view_menu.addAction("Pre&vious Tab")
        if prev_tab is not None:
            prev_tab.setShortcut(QKeySequence(SHORTCUTS["view.previous_tab"]))
            prev_tab.triggered.connect(self._documents.activate_previous)

    def _setup_image_menu(self, menu_bar: QMenuBar) -> None:
        image_menu = menu_bar.addMenu("&Image")
        if image_menu is None:
            return

        crop_canvas_action = image_menu.addAction("Crop to C&anvas")
        if crop_canvas_action is not None:
            crop_canvas_action.setShortcut(QKeySequence(SHORTCUTS["image.crop_to_canvas"]))
            crop_canvas_action.triggered.connect(self._image_crop_to_canvas)

        resize_canvas_action = image_menu.addAction("Resize &Canvas...")
        if resize_canvas_action is not None:
            resize_canvas_action.triggered.connect(self._image_resize_canvas)

        resize_image_action = image_menu.addAction("Resize &Image...")
        if resize_image_action is not None:
            resize_image_action.triggered.connect(self._image_resize_image)

        image_menu.addSeparator()

        rotate_cw_action = image_menu.addAction("Rotate Canvas 90° C&W")
        if rotate_cw_action is not None:
            rotate_cw_action.triggered.connect(self._image_rotate_cw)

        rotate_ccw_action = image_menu.addAction("Rotate Canvas 90° CC&W")
        if rotate_ccw_action is not None:
            rotate_ccw_action.triggered.connect(self._image_rotate_ccw)

        image_menu.addSeparator()

        flip_h_action = image_menu.addAction("Flip Canvas &Horizontal")
        if flip_h_action is not None:
            flip_h_action.triggered.connect(self._image_flip_h)

        flip_v_action = image_menu.addAction("Flip Canvas &Vertical")
        if flip_v_action is not None:
            flip_v_action.triggered.connect(self._image_flip_v)

        image_menu.addSeparator()

        auto_trim_action = image_menu.addAction("Auto-&Trim")
        if auto_trim_action is not None:
            auto_trim_action.triggered.connect(self._image_auto_trim)

    # ---- new menus ----

    def _setup_layer_menu(self, menu_bar: QMenuBar) -> None:  # noqa: C901
        layer_menu = menu_bar.addMenu("&Layer")
        if layer_menu is None:
            return

        self._layer_new_action = QAction("&New Layer", self)
        self._layer_new_action.setShortcut(QKeySequence(SHORTCUTS["layer.new"]))
        self._layer_new_action.triggered.connect(self._layer_new)
        layer_menu.addAction(self._layer_new_action)

        self._layer_duplicate_action = QAction("&Duplicate Layer", self)
        self._layer_duplicate_action.triggered.connect(self._layer_duplicate)
        layer_menu.addAction(self._layer_duplicate_action)

        self._layer_delete_action = QAction("De&lete Layer", self)
        self._layer_delete_action.setShortcut(QKeySequence(SHORTCUTS["layer.delete"]))
        self._layer_delete_action.triggered.connect(self._layer_delete)
        layer_menu.addAction(self._layer_delete_action)

        layer_menu.addSeparator()

        self._layer_merge_down_action = QAction("&Merge Down", self)
        self._layer_merge_down_action.setShortcut(QKeySequence(SHORTCUTS["layer.merge_down"]))
        self._layer_merge_down_action.triggered.connect(self._layer_merge_down)
        layer_menu.addAction(self._layer_merge_down_action)

        merge_visible_action = layer_menu.addAction("Merge &Visible")
        if merge_visible_action is not None:
            merge_visible_action.triggered.connect(self._layer_merge_visible)

        flatten_action = layer_menu.addAction("&Flatten All")
        if flatten_action is not None:
            flatten_action.setShortcut(QKeySequence(SHORTCUTS["layer.flatten"]))
            flatten_action.triggered.connect(self._layer_flatten)

        layer_menu.addSeparator()

        rename_action = layer_menu.addAction("&Rename Layer")
        if rename_action is not None:
            rename_action.setShortcut(QKeySequence(SHORTCUTS["layer.rename"]))
            rename_action.triggered.connect(self._layer_rename)

        props_action = layer_menu.addAction("Layer &Properties...")
        if props_action is not None:
            props_action.triggered.connect(self._layer_properties)

        layer_menu.addSeparator()

        self._layer_move_up_action = QAction("Move &Up", self)
        self._layer_move_up_action.setShortcut(QKeySequence(SHORTCUTS["layer.move_up"]))
        self._layer_move_up_action.triggered.connect(self._layer_move_up)
        layer_menu.addAction(self._layer_move_up_action)

        self._layer_move_down_action = QAction("Move &Down", self)
        self._layer_move_down_action.setShortcut(QKeySequence(SHORTCUTS["layer.move_down"]))
        self._layer_move_down_action.triggered.connect(self._layer_move_down)
        layer_menu.addAction(self._layer_move_down_action)

        self._layer_move_top_action = QAction("Move to &Top", self)
        self._layer_move_top_action.setShortcut(QKeySequence(SHORTCUTS["layer.move_to_top"]))
        self._layer_move_top_action.triggered.connect(self._layer_move_to_top)
        layer_menu.addAction(self._layer_move_top_action)

        self._layer_move_bottom_action = QAction("Move to &Bottom", self)
        self._layer_move_bottom_action.setShortcut(QKeySequence(SHORTCUTS["layer.move_to_bottom"]))
        self._layer_move_bottom_action.triggered.connect(self._layer_move_to_bottom)
        layer_menu.addAction(self._layer_move_bottom_action)

    def _setup_arrange_menu(self, menu_bar: QMenuBar) -> None:
        arrange_menu = menu_bar.addMenu("&Arrange")
        if arrange_menu is None:
            return

        self._bring_front_action = QAction("Bring to &Front", self)
        self._bring_front_action.setShortcut(QKeySequence(SHORTCUTS["arrange.bring_to_front"]))
        self._bring_front_action.triggered.connect(self._arrange_bring_to_front)
        arrange_menu.addAction(self._bring_front_action)
        self._register("arrange.bring_to_front", self._bring_front_action)

        self._bring_forward_action = QAction("Bring For&ward", self)
        self._bring_forward_action.setShortcut(QKeySequence(SHORTCUTS["arrange.bring_forward"]))
        self._bring_forward_action.triggered.connect(self._arrange_bring_forward)
        arrange_menu.addAction(self._bring_forward_action)

        self._send_backward_action = QAction("Send &Backward", self)
        self._send_backward_action.setShortcut(QKeySequence(SHORTCUTS["arrange.send_backward"]))
        self._send_backward_action.triggered.connect(self._arrange_send_backward)
        arrange_menu.addAction(self._send_backward_action)

        self._send_to_back_action = QAction("Send to Bac&k", self)
        self._send_to_back_action.setShortcut(QKeySequence(SHORTCUTS["arrange.send_to_back"]))
        self._send_to_back_action.triggered.connect(self._arrange_send_to_back)
        arrange_menu.addAction(self._send_to_back_action)
        self._register("arrange.send_to_back", self._send_to_back_action)

        arrange_menu.addSeparator()

        # Align submenu
        self._align_menu = arrange_menu.addMenu("Ali&gn")
        if self._align_menu is not None:
            for label, alignment, key in [
                ("Align &Left", "left", "align_left"),
                ("Align Center (&H)", "center_h", "align_center"),
                ("Align &Right", "right", "align_right"),
                ("Align &Top", "top", "align_top"),
                ("Align &Middle (V)", "middle_v", "align_middle"),
                ("Align &Bottom", "bottom", "align_bottom"),
            ]:
                action = self._align_menu.addAction(label)
                if action is not None:
                    action.triggered.connect(
                        lambda _checked=False, a=alignment: self._arrange_align(a)
                    )
                self._register(f"arrange.{key}", action)

        arrange_menu.addSeparator()

        # Distribute submenu
        self._distribute_menu = arrange_menu.addMenu("&Distribute")
        if self._distribute_menu is not None:
            dist_h = self._distribute_menu.addAction("Distribute &Horizontally")
            if dist_h is not None:
                dist_h.triggered.connect(
                    lambda _checked=False: self._arrange_distribute("horizontal")
                )
            self._register("arrange.distribute_horizontal", dist_h)
            dist_v = self._distribute_menu.addAction("Distribute &Vertically")
            if dist_v is not None:
                dist_v.triggered.connect(
                    lambda _checked=False: self._arrange_distribute("vertical")
                )
            self._register("arrange.distribute_vertical", dist_v)

        arrange_menu.addSeparator()

        self._align_canvas_action = QAction("Align to Canvas &Center", self)
        self._align_canvas_action.triggered.connect(self._arrange_align_canvas_center)
        arrange_menu.addAction(self._align_canvas_action)

        arrange_menu.addSeparator()

        group_action = QAction("&Group", self)
        group_action.setShortcut(QKeySequence(SHORTCUTS["arrange.group"]))
        group_action.triggered.connect(self._arrange_group)
        arrange_menu.addAction(group_action)

        ungroup_action = QAction("&Ungroup", self)
        ungroup_action.setShortcut(QKeySequence(SHORTCUTS["arrange.ungroup"]))
        ungroup_action.triggered.connect(self._arrange_ungroup)
        arrange_menu.addAction(ungroup_action)

        arrange_menu.addSeparator()

        self._flip_h_action = QAction("Flip &Horizontal", self)
        self._flip_h_action.triggered.connect(self._arrange_flip_horizontal)
        arrange_menu.addAction(self._flip_h_action)

        self._flip_v_action = QAction("Flip &Vertical", self)
        self._flip_v_action.triggered.connect(self._arrange_flip_vertical)
        arrange_menu.addAction(self._flip_v_action)

    def _setup_tools_menu(self, menu_bar: QMenuBar) -> None:
        tools_menu = menu_bar.addMenu("&Tools")
        if tools_menu is None:
            return

        # Tool groups for separator placement
        tool_groups: list[list[tuple[str, str]]] = [
            # Selection tools
            [("tool.select", "select"), ("tool.lasso_select", "lasso_select")],
            # Shape tools
            [
                ("tool.rectangle", "rectangle"),
                ("tool.ellipse", "ellipse"),
                ("tool.line", "line"),
                ("tool.arrow", "arrow"),
                ("tool.arc", "arc"),
                ("tool.polygon", "polygon"),
                ("tool.freehand", "freehand"),
            ],
            # Text & annotation
            [
                ("tool.text", "text"),
                ("tool.callout", "callout"),
                ("tool.numbered_step", "numbered_step"),
                ("tool.stamp", "stamp"),
                ("tool.emoji", "emoji"),
            ],
            # Effects
            [("tool.highlight", "highlight"), ("tool.blur", "blur")],
            # Region tools
            [
                ("tool.crop", "crop"),
                ("tool.border", "border"),
                ("tool.raster_select", "raster_select"),
                ("tool.eyedropper", "eyedropper"),
            ],
            # Navigation
            [("tool.pan", "pan"), ("tool.zoom", "zoom")],
        ]

        first_group = True
        for group in tool_groups:
            if not first_group:
                tools_menu.addSeparator()
            first_group = False
            for shortcut_key, tool_id in group:
                tool = self._tool_manager.tool(tool_id)
                if tool is None:
                    continue
                key_seq = SHORTCUTS.get(shortcut_key, "")
                action = QAction(tool.display_name, self)
                action.setCheckable(True)
                if key_seq:
                    action.setShortcut(QKeySequence(key_seq))
                action.triggered.connect(
                    lambda _checked=False, tid=tool_id: self._tool_manager.activate(tid)
                )
                tools_menu.addAction(action)
                self._tool_actions[tool_id] = action

        # Wire tool_changed signal to update checkmarks
        self._tool_manager.tool_changed.connect(self._update_tools_menu_check)
        # Set initial checkmark
        self._update_tools_menu_check(self._tool_manager.active_tool_id)

        # Below the tool list (PRD 3.7): Tool Themes... and the read-only Active Theme label.
        tools_menu.addSeparator()
        themes_action = QAction("Tool Themes...", self)
        themes_action.triggered.connect(self._tools_tool_themes)
        tools_menu.addAction(themes_action)
        self._register("tools.themes", themes_action)
        self._active_theme_label = QLabel()
        self._active_theme_label.setObjectName("ActiveThemeLabel")
        self._active_theme_label.setAccessibleName("Active tool theme")
        self._active_theme_label.setContentsMargins(28, 4, 12, 4)
        label_action = QWidgetAction(self)
        label_action.setDefaultWidget(self._active_theme_label)
        tools_menu.addAction(label_action)
        self._tool_themes.state_changed.connect(self._update_active_theme_label)
        self._tool_themes.active_theme_changed.connect(self._on_active_theme_changed)
        self._update_active_theme_label()

    def _on_active_theme_changed(self, _name: str) -> None:
        self._update_active_theme_label()

    def _update_active_theme_label(self) -> None:
        """Active Theme: [name], with "(modified)" once any tool is overridden (PRD 3.7)."""
        text = f"Active Theme: {self._tool_themes.active_theme_name}"
        if self._tool_themes.is_modified():
            text += " (modified)"
        self._active_theme_label.setText(text)

    @property
    def active_theme_text(self) -> str:
        """The Tools menu's Active Theme row as shown."""
        return self._active_theme_label.text()

    def _tools_tool_themes(self) -> None:
        """Tools > Tool Themes... (PRD 11.8)."""
        from snapmock.ui.tool_themes_dialog import ToolThemesDialog

        dialog = ToolThemesDialog(self._tool_themes, self._tool_manager, self)
        dialog.exec()

    def _setup_library_menu(self, menu_bar: QMenuBar) -> None:
        """Library menu (Library PRD Section 5)."""
        library_menu = menu_bar.addMenu("Li&brary")
        if library_menu is None:
            return

        self._library_toggle_action = self._library_panel.toggleViewAction()
        if self._library_toggle_action is not None:
            self._library_toggle_action.setText("Show &Library Panel")
            self._library_toggle_action.setShortcut(
                QKeySequence(SHORTCUTS["library.toggle_panel"])
            )
            library_menu.addAction(self._library_toggle_action)

        library_menu.addSeparator()

        open_lib = library_menu.addAction("&Open Library...")
        if open_lib is not None:
            open_lib.triggered.connect(self._library_panel.choose_library_directory)

        move_lib = library_menu.addAction("&Move Library...")
        if move_lib is not None:
            move_lib.triggered.connect(self._library_move)

        library_menu.addSeparator()

        new_folder = library_menu.addAction("New &Folder")
        if new_folder is not None:
            new_folder.triggered.connect(self._library_panel.create_folder)

        new_canvas = library_menu.addAction("New &Canvas")
        if new_canvas is not None:
            new_canvas.triggered.connect(
                lambda: self._library_new_canvas(self._library_panel.current_path)
            )

        library_menu.addSeparator()

        reveal = library_menu.addAction("&Reveal in File Manager")
        if reveal is not None:
            reveal.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._library.root)))
            )

        library_menu.addSeparator()

        prefs = library_menu.addAction("Library &Preferences...")
        if prefs is not None:
            prefs.triggered.connect(lambda: self._file_preferences(focus_library=True))

    # ---- capture (Screen Capture PRD 3.2 to 3.4, 7) ----

    def _setup_capture_menu(self, menu_bar: QMenuBar) -> None:
        """Capture menu after Library and before Help (PRD 3.4)."""
        capture_menu = menu_bar.addMenu("&Capture")
        if capture_menu is None:
            return
        self._capture_menu = capture_menu
        for mode in (CaptureMode.REGION, CaptureMode.ACTIVE_WINDOW, CaptureMode.FULL_SCREEN):
            action = QAction(MODE_LABELS[mode], self)
            action.triggered.connect(
                lambda _checked=False, m=mode: self._start_capture(m, ORIGIN_MENU)
            )
            capture_menu.addAction(action)
            self._capture_mode_actions[mode] = action
        capture_menu.addSeparator()
        capture_menu.addMenu(self._build_delay_menu(capture_menu))
        self._add_capture_toggle(
            capture_menu,
            "Include Mouse &Cursor",
            "include_cursor",
            self._settings.capture_include_cursor,
            self._settings.set_capture_include_cursor,
        )
        self._add_capture_toggle(
            capture_menu,
            "Copy to Clip&board",
            "copy_to_clipboard",
            self._settings.capture_copy_to_clipboard,
            self._settings.set_capture_copy_to_clipboard,
        )
        self._add_capture_toggle(
            capture_menu,
            f"&Hide {APP_NAME} During Capture",
            "hide_window",
            self._settings.capture_hide_window,
            self._settings.set_capture_hide_window,
        )
        capture_menu.addSeparator()
        prefs = capture_menu.addAction("Capture &Preferences...")
        if prefs is not None:
            prefs.triggered.connect(lambda: self._file_preferences(focus_capture=True))
        self._sync_capture_shortcuts()

    def _build_delay_menu(self, parent: QMenu) -> QMenu:
        """Delay: None / 3 s / 5 s / 10 s radio submenu bound to the preference (PRD 3.2)."""
        menu = QMenu("&Delay", parent)
        group = QActionGroup(menu)
        group.setExclusive(True)
        current = self._settings.capture_delay_seconds()
        for seconds in DELAY_CHOICES:
            label = "&None" if seconds == 0 else f"&{seconds} seconds"
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setData(seconds)
            action.setChecked(seconds == current)
            action.triggered.connect(lambda _c=False, s=seconds: self._set_capture_delay(s))
            group.addAction(action)
            menu.addAction(action)
        self._delay_groups.append(group)
        return menu

    def _set_capture_delay(self, seconds: int) -> None:
        self._settings.set_capture_delay_seconds(seconds)
        self._sync_capture_toggles()

    def _add_capture_toggle(
        self,
        menu: QMenu,
        label: str,
        key: str,
        getter: Callable[[], bool],
        setter: Callable[[bool], None],
    ) -> QAction:
        action = QAction(label, menu)
        action.setCheckable(True)
        action.setChecked(getter())
        action.toggled.connect(lambda checked: self._on_capture_toggle(setter, checked))
        menu.addAction(action)
        self._capture_toggle_actions.append((key, action))
        return action

    def _on_capture_toggle(self, setter: Callable[[bool], None], checked: bool) -> None:
        setter(checked)
        self._sync_capture_toggles()

    def _sync_capture_toggles(self) -> None:
        """Reflect the delay and checkbox preferences in every menu that shows them."""
        getters: dict[str, Callable[[], bool]] = {
            "include_cursor": self._settings.capture_include_cursor,
            "copy_to_clipboard": self._settings.capture_copy_to_clipboard,
            "hide_window": self._settings.capture_hide_window,
        }
        for key, action in self._capture_toggle_actions:
            value = getters[key]()
            if action.isChecked() != value:
                action.blockSignals(True)
                action.setChecked(value)
                action.blockSignals(False)
        delay = self._settings.capture_delay_seconds()
        for group in self._delay_groups:
            for action in group.actions():
                action.setChecked(action.data() == delay)

    def _sync_capture_shortcuts(self) -> None:
        """Menu shortcuts and the toolbar tooltip follow the hotkey preferences (PRD 3.4)."""
        for mode, action in self._capture_mode_actions.items():
            binding = self._capture.binding(MODE_ACTIONS[mode])
            action.setShortcut(binding.key_sequence if binding else QKeySequence())
        for mode, action in self._toolbar_mode_actions.items():
            binding = self._capture.binding(MODE_ACTIONS[mode])
            action.setShortcut(QKeySequence())  # toolbar copies never own the shortcut
            action.setText(
                MODE_LABELS[mode].replace("&", "")
                + (f"\t{binding.display_text}" if binding and binding.is_bound else "")
            )
        if self._capture_button is not None:
            default_mode = CaptureMode.from_string(self._settings.capture_default_mode())
            binding = self._capture.binding(MODE_ACTIONS[default_mode])
            key = binding.display_text if binding and binding.is_bound else ""
            self._capture_button.setToolTip(f"Capture ({key})" if key else "Capture")

    def _setup_capture_toolbar(self) -> None:
        """Group 0 Capture: a menu-button control at the left end (PRD 3.3)."""
        button = QToolButton()
        button.setText("Capture")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button.clicked.connect(lambda: self._start_capture(None, ORIGIN_TOOLBAR))
        menu = QMenu(button)
        for mode in (CaptureMode.REGION, CaptureMode.ACTIVE_WINDOW, CaptureMode.FULL_SCREEN):
            action = QAction(MODE_LABELS[mode], menu)
            action.triggered.connect(
                lambda _checked=False, m=mode: self._start_capture(m, ORIGIN_TOOLBAR)
            )
            menu.addAction(action)
            self._toolbar_mode_actions[mode] = action
        menu.addSeparator()
        menu.addMenu(self._build_delay_menu(menu))
        button.setMenu(menu)
        self._capture_button = button
        self._main_toolbar.set_capture_button(button)
        self._sync_capture_shortcuts()

    def _setup_tray(self) -> None:
        """The system tray icon and menu (PRD 3.2); created only when available."""
        if not self._settings.capture_tray_enabled():
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(make_tray_icon(), self)
        tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        for mode in (CaptureMode.REGION, CaptureMode.ACTIVE_WINDOW, CaptureMode.FULL_SCREEN):
            action = QAction(MODE_LABELS[mode], menu)
            action.triggered.connect(
                lambda _checked=False, m=mode: self._start_capture(m, ORIGIN_TRAY)
            )
            menu.addAction(action)
        menu.addSeparator()
        menu.addMenu(self._build_delay_menu(menu))
        self._add_capture_toggle(
            menu,
            "Include Mouse &Cursor",
            "include_cursor",
            self._settings.capture_include_cursor,
            self._settings.set_capture_include_cursor,
        )
        self._add_capture_toggle(
            menu,
            "Copy to Clip&board",
            "copy_to_clipboard",
            self._settings.capture_copy_to_clipboard,
            self._settings.set_capture_copy_to_clipboard,
        )
        menu.addSeparator()
        show = menu.addAction(f"&Show {APP_NAME}")
        if show is not None:
            show.triggered.connect(self.show_from_tray)
        prefs = menu.addAction("&Preferences...")
        if prefs is not None:
            prefs.triggered.connect(lambda: self._file_preferences(focus_capture=True))
        menu.addSeparator()
        quit_action = menu.addAction(f"&Quit {APP_NAME}")
        if quit_action is not None:
            quit_action.triggered.connect(self.quit_application)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.messageClicked.connect(self.show_from_tray)
        tray.show()
        self._tray = tray
        self._tray_menu = menu
        self._apply_quit_policy()

    def _teardown_tray(self) -> None:
        if self._tray is not None:
            self._tray.hide()
            self._tray.deleteLater()
            self._tray = None
        if self._tray_menu is not None:
            self._capture_toggle_actions = [
                (k, a)
                for k, a in self._capture_toggle_actions
                if a.parent() is not self._tray_menu
            ]
            self._delay_groups = [
                g for g in self._delay_groups if g.parent() is not self._tray_menu
            ]
            self._tray_menu.deleteLater()
            self._tray_menu = None
        self._apply_quit_policy()

    def _apply_quit_policy(self) -> None:
        """Keep the process alive without windows only while the tray keeps it running."""
        keep = self._tray is not None and self._settings.capture_keep_running_in_tray()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setQuitOnLastWindowClosed(not keep)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger and self._capture.platform != (
            "darwin"
        ):
            self.show_from_tray()

    def show_from_tray(self) -> None:
        """Show, restore, and activate the main window (tray: Show SnapMock)."""
        self._hidden_in_tray = False
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_application(self) -> None:
        """Quit from the tray, prompting for unsaved non-library documents."""
        self._quit_requested = True
        if not self.isVisible():
            self.show()
        self.close()
        if self.isVisible():
            self._quit_requested = False  # the user cancelled the close prompt

    @property
    def hidden_in_tray(self) -> bool:
        return self._hidden_in_tray

    @property
    def tray_icon(self) -> QSystemTrayIcon | None:
        return self._tray

    def _capture_onboarding_gate(self, request: CaptureRequest) -> bool:
        """First-run onboarding on platforms that need setup (PRD 9). Runs once."""
        backend = self._capture.backend
        if backend.name == "macos" and self._capture.capabilities.needs_permission:
            return self._macos_permission_gate()
        if self._settings.capture_onboarding_shown():
            return True
        if backend.name != "wayland_portal":
            return True
        from snapmock.capture.onboarding import WaylandOnboardingDialog

        dlg = WaylandOnboardingDialog(self if self.isVisible() else None)
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        if dlg.dont_show.isChecked():
            self._settings.set_capture_onboarding_shown(True)
        dlg.deleteLater()
        return accepted

    def _macos_permission_gate(self) -> bool:
        """Screen Recording onboarding (PRD 9.1): preflight, then the dialog if not granted."""
        from snapmock.capture.models import PermissionState
        from snapmock.capture.onboarding import MacOSPermissionDialog

        backend = self._capture.backend
        if backend.request_permission() is PermissionState.GRANTED:
            return True
        if self._settings.capture_onboarding_shown():
            return True  # the capture then fails with the Section 6.5 message
        dlg = MacOSPermissionDialog(
            lambda: backend.request_permission() is PermissionState.GRANTED,
            settings_url=str(getattr(backend, "settings_url", "")),
            parent=self if self.isVisible() else None,
        )
        dlg.exec()
        if dlg.dont_show.isChecked():
            self._settings.set_capture_onboarding_shown(True)
        granted, quit_requested = dlg.granted, dlg.quit_requested
        dlg.deleteLater()
        if quit_requested:
            QTimer.singleShot(0, self.quit_application)
        return granted

    def _start_capture(self, mode: CaptureMode | None, origin: str) -> None:
        self._capture.start(self._capture.request_from_settings(mode, origin))

    def _on_capture_completed(self, result: CaptureResult) -> None:
        """Hand the image to the Library (PRD 7.1). The manager restores windows after this."""
        self._pending_capture_clipboard = self._settings.capture_copy_to_clipboard()
        try:
            self.add_to_library(
                result.image,
                source="capture",
                capture_metadata=result.metadata,
                when=result.taken_at,
            )
        finally:
            self._pending_capture_clipboard = False

    def _on_capture_failed(self, reason: str) -> None:
        self._notify("Capture failed", reason)

    def _on_capture_refused(self, reason: str, origin: str) -> None:
        self._notify(
            "Capture", reason, force_notification=origin in (ORIGIN_TRAY, ORIGIN_COMMAND_LINE)
        )

    def _on_capture_countdown(self, remaining: int) -> None:
        if self._tray is not None:
            self._tray.setToolTip(
                f"{APP_NAME}: capturing in {remaining} s" if remaining > 0 else APP_NAME
            )

    def _notify(self, title: str, text: str, *, force_notification: bool = False) -> None:
        """A toast in the window, or a system notification while it is in the tray (PRD 7.4).

        The window may be hidden for the grab when this runs; the manager
        restores it right after, so the toast is still the right channel then.
        """
        if not self._hidden_in_tray:
            self._toast.show_message(text)
        if self._tray is not None and (force_notification or self._hidden_in_tray):
            self._tray.showMessage(title, text)

    def report_hotkey_failures(self) -> None:
        """One toast naming every hotkey the desktop refused (PRD 9.3)."""
        failed = [b for b in self._capture.bindings if b.is_bound and not b.registered]
        if not failed or not self._capture.hotkey_backend.supported:
            return
        keys = ", ".join(b.display_text for b in failed)
        verb = "is" if len(failed) == 1 else "are"
        self._notify(
            "Capture hotkeys",
            f"{keys} {verb} in use by another application. Change it in Preferences > Capture.",
        )

    @property
    def capture_manager(self) -> CaptureManager:
        return self._capture

    def _setup_help_menu(self, menu_bar: QMenuBar) -> None:
        help_menu = menu_bar.addMenu("&Help")
        if help_menu is None:
            return

        welcome_action = help_menu.addAction("&Welcome / Getting Started")
        if welcome_action is not None:
            welcome_action.triggered.connect(self._help_welcome)

        docs_action = help_menu.addAction("&Documentation")
        if docs_action is not None:
            docs_action.triggered.connect(self._help_docs)

        shortcuts_action = help_menu.addAction("&Keyboard Shortcuts")
        if shortcuts_action is not None:
            shortcuts_action.triggered.connect(self._help_shortcuts)

        bug_action = help_menu.addAction("Report a &Bug")
        if bug_action is not None:
            bug_action.triggered.connect(self._help_report_bug)

        # The permanent route into the desktop's menu and back out of it
        # (menu-entry decision 1, option C); its label follows the entry's state,
        # refreshed each time the menu opens, since another form can install one.
        self._menu_entry_action = None
        entry_action = help_menu.addAction(self._menu_entry_label())
        if entry_action is not None:
            entry_action.triggered.connect(self._help_menu_entry)
            self._menu_entry_action = entry_action
            help_menu.aboutToShow.connect(self._refresh_menu_entry_label)

        help_menu.addSeparator()

        updates_action = help_menu.addAction("Check for &Updates")
        if updates_action is not None:
            updates_action.triggered.connect(self._help_check_updates)

        about_action = help_menu.addAction(f"&About {APP_NAME}")
        if about_action is not None:
            about_action.triggered.connect(self._help_about)

    # ---- view toggles ----

    def _toggle_grid(self, checked: bool) -> None:
        self._view.set_grid_visible(checked)
        self._settings.set_grid_visible(checked)

    def _toggle_rulers(self, checked: bool) -> None:
        self._view.set_rulers_visible(checked)
        self._settings.set_rulers_visible(checked)

    def _toggle_crosshairs(self, checked: bool) -> None:
        """View > Show Crosshairs applies to every open document (PRD 3.3)."""
        for doc in self._documents.documents:
            doc.view.set_crosshairs_visible(checked)
        self._settings.set_crosshairs_visible(checked)

    def _toggle_snap_to_grid(self, checked: bool) -> None:
        self._settings.set_snap_to_grid(checked)
        for doc in self._documents.documents:
            doc.view.set_snap_to_grid(checked)
        if hasattr(self, "_property_panel"):
            self._property_panel.refresh_canvas_settings()

    def _toggle_guides(self, checked: bool) -> None:
        """View > Show Guides (PRD 3.3): guides stay in place when hidden."""
        self._settings.set_guides_visible(checked)
        for doc in self._documents.documents:
            doc.view.set_guides_visible(checked)

    def _toggle_snap_to_guides(self, checked: bool) -> None:
        self._settings.set_snap_to_guides(checked)
        for doc in self._documents.documents:
            doc.view.set_snap_to_guides(checked)

    def _toggle_lock_guides(self, checked: bool) -> None:
        self._settings.set_guides_locked(checked)
        for doc in self._documents.documents:
            doc.view.set_guides_locked(checked)

    def _view_clear_guides(self) -> None:
        """View > Clear All Guides (PRD 3.3): confirms, then one undoable command."""
        from snapmock.commands.guide_commands import ClearGuidesCommand

        guides = self._scene.guides
        if not self._require("Clear All Guides", (bool(guides), "at least one guide")):
            return
        count = len(guides)
        noun = "guide" if count == 1 else "guides"
        answer = QMessageBox.question(
            self,
            "Clear All Guides",
            f"Remove all {count} {noun} from the canvas?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._scene.command_stack.push(ClearGuidesCommand(self._scene))

    def _toggle_status_bar(self, checked: bool) -> None:
        self._status_bar.setVisible(checked)
        self._settings.set_status_bar_visible(checked)

    def _show_loupe_at_cursor(self, eyedropper: EyedropperTool) -> None:
        """Put the loupe where the pointer is, without waiting for a move (4.7)."""
        viewport = self._view.viewport()
        if viewport is None:
            return
        local = viewport.mapFromGlobal(QCursor.pos())
        if viewport.rect().contains(local):
            eyedropper.update_loupe(local)

    def _apply_momentary_pick(self) -> None:
        """A colour picked while Alt was held becomes the returned-to tool's primary colour.

        Blur PRD 4.7 names the property per tool: the stroke colour for a shape tool, the
        highlight colour for the Highlighter, the text colour for the Text tool, and the
        badge colour for the Numbered Step tool. The Eyedropper's own Apply Target (4.4)
        is not consulted here: the momentary mode is about the tool being used.
        """
        eyedropper = self._tool_manager.tool("eyedropper")
        if not isinstance(eyedropper, EyedropperTool):
            return
        if eyedropper.pick_serial == self._momentary_pick_serial:
            return
        tool = self._tool_manager.active_tool
        if tool is None:
            return
        key = momentary_pick_key(tool)
        if key is None:
            return
        tool.creation_defaults[key] = eyedropper.picked_color
        self._tool_manager.tool_defaults_changed.emit(tool.tool_id)

    def _apply_tab_order(self) -> None:
        """PRD 14: Main Toolbar > Tool Options Bar > Left Tool Palette > Canvas > Layer
        Panel > Property Panel, then the Library Panel and the status bar.

        Re-run when the Tool Options Bar rebuilds or the active document changes,
        since both replace Tab stops. The menu bar is reached with Alt or F10, as
        on every platform, and is not a Tab stop.
        """
        set_tab_order(
            [
                self._main_toolbar,
                self._tool_options,
                self._toolbar,
                self._view,
                self._layer_panel,
                self._property_panel,
                self._library_panel,
                self._status_bar,
            ]
        )

    def _on_tool_changed_for_tab_order(self, _tool_id: str) -> None:
        self._apply_tab_order()

    def show_status_hint(self, text: str) -> None:
        """Put *text* in the status bar's hint zone (General UI PRD 9)."""
        self._status_bar.set_hint(text)

    def _on_tool_changed_for_hint(self, _tool_id: str) -> None:
        tool = self._tool_manager.active_tool
        if tool is not None:
            self._status_bar.set_hint(tool.status_hint)
        else:
            self._status_bar.set_hint("")

    def _update_tools_menu_check(self, tool_id: str) -> None:
        """Update checkmarks in the Tools menu to reflect the active tool."""
        for tid, action in self._tool_actions.items():
            action.setChecked(tid == tool_id)

    # ---- signals ----

    # ---- never-disabled controls (General UI PRD 1.3) ----

    def _require(self, action: str, *requirements: tuple[bool, str]) -> bool:
        """Show the unmet-requirement message and return False unless every requirement holds."""
        return check_requirements(self, action, list(requirements))

    def _require_selection(self, action: str, minimum: int = 1) -> list[SnapGraphicsItem]:
        """The selected items, or an empty list after the message when fewer than *minimum*."""
        items = self._selected_snap_items()
        words = {1: "at least one item selected", 2: "at least two items selected"}
        need = words.get(minimum, f"at least {minimum} items selected")
        if not self._require(action, (len(items) >= minimum, need)):
            return []
        return items

    def _require_active_layer(self, action: str) -> Layer | None:
        active = self._scene.layer_manager.active_layer
        if not self._require(action, (active is not None, "an active layer")):
            return None
        return active

    def _clipboard_has_content(self) -> bool:
        if self._clipboard.has_internal or self._clipboard.has_raster:
            return True
        cb = QApplication.clipboard()
        if cb is None:
            return False
        mime = cb.mimeData()
        return mime is not None and (mime.hasImage() or bool(cb.text()))

    def _on_layer_lock_changed(self, layer_id: str, locked: bool) -> None:
        if locked:
            self._deselect_items_on_layer(layer_id)

    def _on_layer_type_changed(self, layer_id: str, _layer_type: str) -> None:
        """A layer made Background lets go of its image (end-to-end pass finding 11)."""
        for item in self._selection_manager.items:
            if self._scene.is_fixed_in_place(item):
                self._selection_manager.toggle(item)

    def _on_layer_visibility_changed(self, layer_id: str, visible: bool) -> None:
        if not visible:
            self._deselect_items_on_layer(layer_id)

    def _on_active_layer_changed(self, _layer_id: str) -> None:
        # Cancel active raster/lasso selection when layer changes
        active = self._tool_manager.active_tool
        if active is not None and active.is_active_operation:
            if isinstance(active, (RasterSelectTool, LassoSelectTool)):
                active.cancel()

    def _deselect_items_on_layer(self, layer_id: str) -> None:
        """Deselect any selected items on the given layer."""
        affected = [
            i
            for i in self._selection_manager.items
            if isinstance(i, SnapGraphicsItem) and i.layer_id == layer_id
        ]
        if affected:
            for item in affected:
                self._selection_manager.toggle(item)

    def _view_zoom_in(self) -> None:
        if self._require(
            "Zoom In", (self._view.zoom_percent < ZOOM_MAX, f"a zoom below {ZOOM_MAX}%")
        ):
            self._view.zoom_in()

    def _view_zoom_out(self) -> None:
        if self._require(
            "Zoom Out", (self._view.zoom_percent > ZOOM_MIN, f"a zoom above {ZOOM_MIN}%")
        ):
            self._view.zoom_out()

    def _view_zoom_to_selection(self) -> None:
        """Zoom to fit the current selection in the viewport."""
        items = self._require_selection("Zoom to Selection")
        if not items:
            return
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        pad = 20
        self._view.zoom_to_rect(rect.adjusted(-pad, -pad, pad, pad))

    # ---- file operations ----

    def _new_scene(self) -> SnapScene:
        """An empty scene at the default canvas size and colour (Preferences > General)."""
        width, height = self._settings.default_canvas_size()
        scene = SnapScene(width, height)
        scene.set_background_color(self._settings.default_canvas_color())
        return scene

    def _file_new(self) -> None:
        """Open a new, empty, unsaved document in a new tab."""
        self._add_document(Document(self._new_scene(), parent=self))

    def _file_open(self) -> None:
        """Open an existing .smk or .snagx project in a new tab."""
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            f"All Supported (*{PROJECT_EXTENSION} *{SNAGIT_EXTENSION})"
            f";;{APP_NAME} Projects (*{PROJECT_EXTENSION})"
            f";;Snagit Files (*{SNAGIT_EXTENSION})"
            ";;All Files (*)",
        )
        if not path_str:
            return
        self._open_project(Path(path_str))

    def show_startup_message(self, text: str) -> None:
        """A message the entry point owes the user at start, as a toast and in the log.

        The storage migration of packaging decision 4 reports its moves this way:
        a message, never a dialog that blocks (General UI PRD 1.3).
        """
        log.info("%s", text)
        self._startup_message_shown = True
        self._toast.show_message(text)

    def open_paths(self, paths: Iterable[Path]) -> None:
        """Open every project or Snagit file in *paths*, as the command line names them.

        The desktop entry's ``%F`` and a shell both reach here (packaging silence 2);
        a file that cannot be opened reports through the Open Error message.
        """
        for path in paths:
            self._open_project(path)

    def _open_project(self, path: Path) -> Document | None:
        """Open *path* in a new tab, or activate its tab if already open."""
        existing = self._documents.find_by_path(path)
        if existing is not None:
            self._documents.set_active(existing)
            return existing
        try:
            if path.suffix.lower() == SNAGIT_EXTENSION:
                scene = load_snagx(path)
                metadata = None
                capture_metadata = None
            else:
                scene = load_project(path)
                metadata = read_library_metadata(path)
                capture_metadata = read_capture_metadata(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Open Error", f"Could not open project:\n{e}")
            return None
        is_library = self._library.is_library_path(path)
        doc = Document(
            scene,
            file_path=path,
            is_library_file=is_library,
            display_name=(metadata or {}).get("display_name"),
            library_metadata=metadata,
            capture_metadata=capture_metadata,
            parent=self,
        )
        self._add_document(doc)
        if is_library:
            self._library.attach_document(doc)
        else:
            self._add_recent_file(path)
        zoom = self._settings.recent_file_zoom(path)
        if zoom is not None:
            doc.view.set_zoom(zoom)
        return doc

    def _file_save(self) -> None:
        """Save the current project (library files are written back immediately)."""
        doc = self._active_document
        if doc.is_library_file:
            self._library.write_back(doc)
            return
        if self._current_file is None:
            self._file_save_as()
            return
        self._save_to(self._current_file)

    def _file_save_as(self) -> None:
        """Save the current project to a new path."""
        path_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Project",
            "",
            f"{APP_NAME} Projects (*{PROJECT_EXTENSION});;Snagit Files (*{SNAGIT_EXTENSION})",
        )
        if not path_str:
            return
        path = Path(path_str)
        if SNAGIT_EXTENSION in selected_filter or path.suffix.lower() == SNAGIT_EXTENSION:
            if path.suffix.lower() != SNAGIT_EXTENSION:
                path = path.with_suffix(SNAGIT_EXTENSION)
        elif path.suffix.lower() != PROJECT_EXTENSION:
            path = path.with_suffix(PROJECT_EXTENSION)
        doc = self._active_document
        if doc.is_library_file and not self._library.is_library_path(path):
            # Library files stay bound to the library; Save As writes a copy.
            self._save_copy_to(path)
            return
        self._save_to(path)

    def _save_copy_to(self, path: Path) -> None:
        try:
            if path.suffix.lower() == SNAGIT_EXTENSION:
                save_snagx(self._scene, path)
            else:
                save_project(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Save Error", f"Could not save copy:\n{e}")
            return
        self._add_recent_file(path)
        self._status_bar.set_hint(f"Saved copy to {path.name}")

    def _save_to(self, path: Path) -> None:
        try:
            if path.suffix.lower() == SNAGIT_EXTENSION:
                warnings = save_snagx(self._scene, path)
                if warnings:
                    QMessageBox.warning(
                        self,
                        "Snagit Export Warnings",
                        "Some items could not be saved:\n\n" + "\n".join(warnings),
                    )
            else:
                save_project(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Save Error", f"Could not save project:\n{e}")
            return
        doc = self._active_document
        doc.file_path = path
        doc.display_name = None
        if self._library.is_library_path(path):
            doc.is_library_file = True
            self._library.attach_document(doc)
        self._scene.command_stack.mark_clean()
        self._add_recent_file(path)
        self._update_title()

    def _file_import_image(self) -> bool:
        """Import an image file into the scene; True when one was imported."""
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Import Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)"
        )
        if not path_str:
            return False
        return import_image(self._scene, Path(path_str)) is not None

    def _visible_scene_rect(self) -> QRectF:
        view = self._view
        viewport = view.viewport()
        if viewport is None:  # pragma: no cover - a QGraphicsView always has one
            return QRectF()
        return view.mapToScene(viewport.rect()).boundingRect()

    def _export_dialog(self) -> ExportDialog:
        """The Export dialog for the active document (General UI PRD 11.2)."""
        doc = self._active_document
        directory = None
        if doc.file_path is not None and not doc.is_library_file:
            directory = doc.file_path.parent
        return ExportDialog(
            self._scene,
            self._settings,
            self,
            document_name=doc.display_name,
            document_directory=directory,
            selection=selection_rect(self._selection_manager.items),
            visible=self._visible_scene_rect(),
        )

    def _file_export(self) -> None:
        """File > Export: the Export dialog, then write the active document."""
        dialog = self._export_dialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._write_export(dialog.output_path(), dialog.settings(), dialog.region_rect())

    def _write_export(self, path: Path, settings: ExportSettings, region: QRectF) -> bool:
        try:
            export_scene(self._scene, path, settings, region)
        except OSError as exc:
            QMessageBox.warning(self, "Export", f"Could not write {path}:\n{exc}")
            return False
        self._status_bar.set_hint(f"Exported {path}")
        return True

    def _file_export_quick_png(self) -> None:
        """Export Quick (PNG): the last-used PNG settings; the dialog on first use (PRD 3.1)."""
        stored = self._settings.export_settings(ExportFormat.PNG.value)
        if stored is None:
            self._file_export()
            return
        settings = ExportSettings.from_dict(stored).with_format(ExportFormat.PNG)
        doc = self._active_document
        if doc.file_path is not None and not doc.is_library_file:
            path = doc.file_path.with_suffix(".png")
        else:
            directory = self._settings.export_last_directory(ExportFormat.PNG.value) or Path.home()
            path = directory / f"{doc.display_name}.png"
        region = resolve_region(
            self._scene,
            settings.region,
            selection=selection_rect(self._selection_manager.items),
            visible=self._visible_scene_rect(),
        )
        self._write_export(path, settings, region)

    def _file_print(self) -> None:
        """System print dialog with the flattened canvas, fitted to the page (PRD 3.1)."""
        from PyQt6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        canvas = self._scene.canvas_size
        orientation = (
            QPageLayout.Orientation.Landscape
            if canvas.width() > canvas.height()
            else QPageLayout.Orientation.Portrait
        )
        printer.setPageOrientation(orientation)
        printer.setDocName(self._active_document.display_name)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Print")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        print_scene(self._scene, printer)

    def _file_preferences(
        self, *, focus_library: bool = False, focus_capture: bool = False
    ) -> None:
        from snapmock.ui.preferences_dialog import PreferencesDialog

        dlg = PreferencesDialog(
            self._settings,
            self,
            capture=self._capture,
            active_theme=self._tool_themes.active_theme_name,
        )
        if focus_library:
            dlg.focus_library_section()
        if focus_capture:
            dlg.focus_capture_section()
        if dlg.exec() == PreferencesDialog.DialogCode.Accepted:
            self._apply_preference_changes(dlg.get_changes())

    def _apply_preference_changes(self, changes: dict[str, tuple[object, object]]) -> None:
        """Write changed preferences to settings and sync live UI state."""
        if not changes:
            return

        def _int(val: object) -> int:
            return val if isinstance(val, int) else int(str(val))

        if "grid_visible" in changes:
            visible = bool(changes["grid_visible"][1])
            self._settings.set_grid_visible(visible)
            self._grid_action.blockSignals(True)
            self._grid_action.setChecked(visible)
            self._grid_action.blockSignals(False)
            self._view.set_grid_visible(visible)

        if "grid_size" in changes:
            size = _int(changes["grid_size"][1])
            self._settings.set_grid_size(size)
            self._view.set_grid_size(size)

        if "rulers_visible" in changes:
            visible = bool(changes["rulers_visible"][1])
            self._settings.set_rulers_visible(visible)
            self._rulers_action.blockSignals(True)
            self._rulers_action.setChecked(visible)
            self._rulers_action.blockSignals(False)
            self._view.set_rulers_visible(visible)

        if "snap_to_grid" in changes:
            enabled = bool(changes["snap_to_grid"][1])
            self._settings.set_snap_to_grid(enabled)
            self._snap_grid_action.blockSignals(True)
            self._snap_grid_action.setChecked(enabled)
            self._snap_grid_action.blockSignals(False)
            for doc in self._documents.documents:
                doc.view.set_snap_to_grid(enabled)

        if "autosave_interval" in changes:
            # 0 means disabled (PRD 11.3); the timer keeps its last positive interval.
            minutes = _int(changes["autosave_interval"][1])
            self._settings.set_autosave_enabled(minutes > 0)
            if minutes > 0:
                self._settings.set_autosave_interval_minutes(minutes)

        if "autosave_enabled" in changes:
            enabled = bool(changes["autosave_enabled"][1])
            self._settings.set_autosave_enabled(enabled)

        # Restart or stop autosave timer based on current settings
        if "autosave_enabled" in changes or "autosave_interval" in changes:
            self._autosave_timer.stop()
            if self._settings.autosave_enabled():
                ms = self._settings.autosave_interval_minutes() * 60_000
                self._autosave_timer.start(ms)

        # Library preferences (Library PRD 8.1) take effect immediately
        if "library_directory" in changes:
            new_dir = Path(str(changes["library_directory"][1])).expanduser()
            self._library_panel.set_library_directory(new_dir)
        if "library_auto_open" in changes:
            self._settings.set_library_auto_open(bool(changes["library_auto_open"][1]))
        if "library_toast_enabled" in changes:
            self._settings.set_library_toast_enabled(bool(changes["library_toast_enabled"][1]))
        if "library_default_view_mode" in changes:
            mode = str(changes["library_default_view_mode"][1])
            self._settings.set_library_default_view_mode(mode)
            self._library_panel.set_view_mode(mode)
        if "library_default_thumbnail_size" in changes:
            size = _int(changes["library_default_thumbnail_size"][1])
            self._settings.set_library_default_thumbnail_size(size)
            self._settings.set_library_thumbnail_size(size)
            self._library_panel.set_view_mode(self._library_panel.view_mode)
        if "library_default_sort" in changes:
            sort_id = str(changes["library_default_sort"][1])
            self._settings.set_library_default_sort(sort_id)
            self._library_panel.set_sort_id(sort_id)

        self._apply_general_preference_changes(changes)
        self._apply_appearance_preference_changes(changes)
        self._apply_tool_preference_changes(changes)
        self._apply_capture_preference_changes(changes)

    def _apply_general_preference_changes(self, changes: dict[str, tuple[object, object]]) -> None:
        """Preferences > General and Performance (General UI PRD 11.3)."""
        s = self._settings
        if "language" in changes:
            s.set_language(str(changes["language"][1]))
        if "recent_files_count" in changes:
            s.set_recent_files_count(int(str(changes["recent_files_count"][1])))
            s.set_recent_files(s.recent_files()[: s.recent_files_count()])
            self._update_recent_files_menu()
        if "default_canvas_size" in changes:
            size = changes["default_canvas_size"][1]
            if isinstance(size, tuple) and len(size) == 2:
                s.set_default_canvas_size(int(size[0]), int(size[1]))
        if "default_canvas_color" in changes:
            s.set_default_canvas_color(_as_color(changes["default_canvas_color"][1]))
        if "confirm_delete_layers" in changes:
            s.set_confirm_delete_layers(bool(changes["confirm_delete_layers"][1]))
        if "undo_limit" in changes:
            s.set_undo_limit(int(str(changes["undo_limit"][1])))
            for doc in self._documents.documents:
                doc.scene.command_stack.set_limit(s.undo_limit())
        if "thumbnail_delay_ms" in changes:
            s.set_thumbnail_delay_ms(int(str(changes["thumbnail_delay_ms"][1])))

    def _apply_appearance_preference_changes(
        self, changes: dict[str, tuple[object, object]]
    ) -> None:
        """Preferences > Appearance and Canvas & Grid, applied live (PRD 11.3, 13.4)."""
        s = self._settings
        if "theme_mode" in changes:
            self.set_theme_mode(ThemeMode.from_value(str(changes["theme_mode"][1])))
        if "icon_size" in changes:
            s.set_icon_size(int(str(changes["icon_size"][1])))
            self._theme.set_icon_size(s.icon_size())
        if "ui_font_size" in changes:
            s.set_ui_font_size(str(changes["ui_font_size"][1]))
            self._theme.set_ui_font_size(s.ui_font_size())
        if "checkerboard_size" in changes:
            s.set_checkerboard_size(int(str(changes["checkerboard_size"][1])))
        if "checkerboard_colors" in changes:
            colors = changes["checkerboard_colors"][1]
            if isinstance(colors, tuple) and len(colors) == 2:
                s.set_checkerboard_colors((_as_color(colors[0]), _as_color(colors[1])))
            else:
                s.set_checkerboard_colors(None)
        if "pasteboard_color" in changes:
            value = changes["pasteboard_color"][1]
            s.set_pasteboard_color(_as_color(value) if value is not None else None)
        if "grid_color" in changes:
            value = changes["grid_color"][1]
            s.set_grid_color(_as_color(value) if value is not None else None)
        if "grid_opacity" in changes:
            value = changes["grid_opacity"][1]
            s.set_grid_opacity(int(str(value)) if value is not None else None)
        if "snap_tolerance" in changes:
            s.set_snap_tolerance(int(str(changes["snap_tolerance"][1])))
        if "pixel_grid_zoom" in changes:
            s.set_pixel_grid_zoom(int(str(changes["pixel_grid_zoom"][1])))
        if "guide_color" in changes:
            s.set_guide_color(_as_color(changes["guide_color"][1]))
        if "guide_opacity" in changes:
            s.set_guide_opacity(int(str(changes["guide_opacity"][1])))
        if "layer_hover_highlight" in changes:
            s.set_layer_hover_highlight(bool(changes["layer_hover_highlight"][1]))
        if "panel_narrow_threshold" in changes:
            s.set_panel_narrow_threshold(int(str(changes["panel_narrow_threshold"][1])))
        if "panel_strip_threshold" in changes:
            s.set_panel_strip_threshold(int(str(changes["panel_strip_threshold"][1])))
        if "panel_narrow_threshold" in changes or "panel_strip_threshold" in changes:
            self._update_panel_modes(force=True)
        view_keys = (
            "checkerboard_size",
            "checkerboard_colors",
            "pasteboard_color",
            "grid_color",
            "grid_opacity",
            "pixel_grid_zoom",
            "snap_tolerance",
            "guide_color",
            "guide_opacity",
        )
        if any(key in changes for key in view_keys):
            for doc in self._documents.documents:
                self._apply_view_preferences(doc.view)
        if hasattr(self, "_property_panel"):
            self._property_panel.refresh_canvas_settings()

    def _apply_tool_preference_changes(self, changes: dict[str, tuple[object, object]]) -> None:
        """Preferences > Tools: the defaults every tool starts a new item with."""
        s = self._settings
        touched = False
        if "default_stroke_color" in changes:
            s.set_default_stroke_color(_as_color(changes["default_stroke_color"][1]))
            touched = True
        if "default_stroke_width" in changes:
            s.set_default_stroke_width(float(str(changes["default_stroke_width"][1])))
            touched = True
        if "default_fill_color" in changes:
            s.set_default_fill_color(_as_color(changes["default_fill_color"][1]))
            touched = True
        if "default_font_family" in changes:
            s.set_default_font_family(str(changes["default_font_family"][1]))
            touched = True
        if "default_font_size" in changes:
            s.set_default_font_size(int(str(changes["default_font_size"][1])))
            touched = True
        if "freehand_smoothing" in changes:
            s.set_freehand_smoothing(int(str(changes["freehand_smoothing"][1])))
            touched = True
        if "numbered_step_start" in changes:
            s.set_numbered_step_start(int(str(changes["numbered_step_start"][1])))
            touched = True
        if touched:
            self._apply_tool_defaults()

    def _apply_capture_preference_changes(self, changes: dict[str, tuple[object, object]]) -> None:
        """Capture preferences (Screen Capture PRD 8.1) take effect immediately."""

        def _int(val: object) -> int:
            return val if isinstance(val, int) else int(str(val))

        s = self._settings
        if "capture_default_mode" in changes:
            s.set_capture_default_mode(str(changes["capture_default_mode"][1]))
        if "capture_delay_seconds" in changes:
            s.set_capture_delay_seconds(_int(changes["capture_delay_seconds"][1]))
        if "capture_include_cursor" in changes:
            s.set_capture_include_cursor(bool(changes["capture_include_cursor"][1]))
        if "capture_play_sound" in changes:
            s.set_capture_play_sound(bool(changes["capture_play_sound"][1]))
        if "capture_hide_window" in changes:
            s.set_capture_hide_window(bool(changes["capture_hide_window"][1]))
        if "capture_copy_to_clipboard" in changes:
            s.set_capture_copy_to_clipboard(bool(changes["capture_copy_to_clipboard"][1]))
        if "capture_full_screen_scope" in changes:
            s.set_capture_full_screen_scope(str(changes["capture_full_screen_scope"][1]))
        if "capture_show_magnifier" in changes:
            s.set_capture_show_magnifier(bool(changes["capture_show_magnifier"][1]))
        if "capture_keep_running_in_tray" in changes:
            s.set_capture_keep_running_in_tray(bool(changes["capture_keep_running_in_tray"][1]))
        if "capture_tray_enabled" in changes:
            enabled = bool(changes["capture_tray_enabled"][1])
            s.set_capture_tray_enabled(enabled)
            if self._primary_capture:
                if enabled and self._tray is None:
                    self._setup_tray()
                    if self._tray is None:
                        self._toast.show_message(TRAY_UNAVAILABLE_MESSAGE)
                elif not enabled and self._tray is not None:
                    self._teardown_tray()
        self._apply_quit_policy()
        self._sync_capture_toggles()
        self._sync_capture_shortcuts()

    # ---- library ----

    def _open_library_files(self, paths: list[Path]) -> None:
        opened = None
        for p in paths:
            opened = self._open_project(p) or opened
        # The keyboard focus follows the file to its canvas (Library PRD 1.6): the grid
        # claims Ctrl+A, Ctrl+C and Ctrl+V for the files while it keeps the focus
        if opened is not None:
            self._view.setFocus()

    def _open_in_new_window(self, path: Path) -> None:
        window = MainWindow(capture_manager=self._capture, primary_capture=False)
        window.show()
        window._open_project(path)  # noqa: SLF001
        _extra_windows.append(window)

    def _close_documents_for_paths(self, paths: list[Path]) -> None:
        """Close tabs for library files that are about to be deleted (no prompt)."""
        for p in paths:
            doc = self._documents.find_by_path(p)
            if doc is None:
                continue
            self._library.detach_document(doc)
            if self._documents.count == 1:
                self._documents.add(Document(self._new_scene(), parent=self))
                self._configure_view(self._active_document.view)
                self._wire_document(self._active_document)
            self._documents.remove(doc)
            self._wired_docs.discard(doc.tab_id)
            doc.dispose()

    def _library_new_canvas(self, folder: Path) -> None:
        width, height = self._settings.default_canvas_size()
        path = self._library.create_blank(
            width, height, folder=folder, color=self._settings.default_canvas_color()
        )
        self._open_project(path)

    def add_to_library(
        self,
        image: object,
        *,
        source: str = "capture",
        capture_metadata: CaptureMetadata | None = None,
        when: datetime | None = None,
    ) -> Path | None:
        """Store *image* (QImage or QPixmap) as a new library file (Library PRD 6.1).

        Opens it in a tab when the Auto-open preference is on. Screen capture
        passes *capture_metadata* (written to the manifest, Screen Capture PRD
        12.1) and *when*, the grab time, which becomes ``captured_at``.
        """
        from PyQt6.QtGui import QImage, QPixmap

        if not isinstance(image, (QImage, QPixmap)):
            return None
        path = self._library.create_from_image(
            image,
            source=source,
            folder=self._library_panel.current_path,
            when=when,
            capture_metadata=capture_metadata.to_dict() if capture_metadata else None,
        )
        if self._settings.library_auto_open():
            self._open_project(path)
        return path

    def _on_library_file_created(self, path: Path) -> None:
        if not self._settings.library_toast_enabled():
            return
        where = "Library and clipboard" if self._pending_capture_clipboard else "Library"
        text = f"Captured to {where}: {path.stem}"
        if self._hidden_in_tray and self._tray is not None:
            # No window to show a toast in: a system notification instead (PRD 7.2).
            self._tray.showMessage(APP_NAME, text)
            return
        self._toast.show_message(text, "Open", lambda: self._open_library_files([path]))

    def _library_export_dialog(self, paths: list[Path]) -> tuple[ExportDialog, SnapScene] | None:
        """The Library variant of the Export dialog, previewing the first of *paths*."""
        try:
            scene = load_project(paths[0])
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Export", f"Could not open {paths[0].name}:\n{exc}")
            return None
        dialog = ExportDialog(
            scene,
            self._settings,
            self,
            document_name=export_target(paths[0], Path(), ExportSettings()).stem,
            library_files=paths,
        )
        return dialog, scene

    def _export_library_files(self, paths: list[Path]) -> None:
        """Library panel > Export...: the dialog for one file or a batch (Library PRD 7.2)."""
        if not paths:
            return
        opened = self._library_export_dialog(paths)
        if opened is None:
            return
        dialog, scene = opened
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            settings = dialog.settings()
            if len(paths) == 1:
                error = export_file(paths[0], dialog.output_path(), settings)
                if error:
                    QMessageBox.warning(self, "Export", error)
                else:
                    self._status_bar.set_hint(f"Exported {dialog.output_path()}")
                return
            out_dir = dialog.output_directory()
            apply_to_all = dialog.apply_to_all()
        finally:
            scene.deleteLater()
        self._export_library_batch(paths, out_dir, settings, per_file_dialog=not apply_to_all)

    def _export_library_files_quick(self, paths: list[Path]) -> None:
        """Library panel > Export Quick (PNG): last-used PNG settings into a chosen directory."""
        if not paths:
            return
        stored = self._settings.export_settings(ExportFormat.PNG.value)
        if stored is None:
            self._export_library_files(paths)
            return
        settings = ExportSettings.from_dict(stored).with_format(ExportFormat.PNG)
        start = self._settings.export_last_directory(ExportFormat.PNG.value) or Path.home()
        out = QFileDialog.getExistingDirectory(self, "Export PNGs To", str(start))
        if not out:
            return
        self._settings.set_export_last_directory(ExportFormat.PNG.value, Path(out))
        self._export_library_batch(paths, Path(out), settings)

    def _export_library_batch(
        self,
        paths: list[Path],
        out_dir: Path,
        settings: ExportSettings,
        *,
        per_file_dialog: bool = False,
    ) -> None:
        """Export *paths* into *out_dir* with a cancellable progress dialog and a summary.

        With *per_file_dialog* (Apply to All unchecked) the Export dialog reopens
        for every file after the first so each can take its own settings.
        """
        progress = QProgressDialog("Exporting…", "Cancel", 0, len(paths), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(400)
        written: list[Path] = []
        errors: list[str] = []
        for i, p in enumerate(paths):
            if progress.wasCanceled():
                break
            progress.setValue(i)
            QApplication.processEvents()
            file_settings = settings
            if per_file_dialog and i > 0:
                opened = self._library_export_dialog([p])
                if opened is None:
                    errors.append(f"{p.name}: could not be opened")
                    continue
                dialog, scene = opened
                try:
                    dialog.set_output_directory(out_dir)
                    if dialog.exec() != QDialog.DialogCode.Accepted:
                        break
                    file_settings = dialog.settings()
                    out_dir = dialog.output_directory()
                finally:
                    scene.deleteLater()
            target = export_target(p, out_dir, file_settings)
            error = export_file(p, target, file_settings)
            if error:
                errors.append(error)
            else:
                written.append(target)
        progress.setValue(len(paths))
        summary = f"Exported {len(written)} of {len(paths)} file(s) to {out_dir}"
        if errors:
            summary += "\n\nErrors:\n" + "\n".join(errors)
            QMessageBox.warning(self, "Export", summary)
        else:
            self._status_bar.set_hint(summary)

    def _library_move(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Move Library To", str(self._library.root))
        if not chosen:
            return
        new_root = Path(chosen)
        if new_root.resolve() == self._library.root.resolve():
            return
        progress = QProgressDialog("Moving library…", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        def report(done: int, total: int) -> bool:
            progress.setMaximum(max(1, total))
            progress.setValue(done)
            QApplication.processEvents()
            return not progress.wasCanceled()

        old_root = self._library.root
        try:
            self._library.move_library(new_root, report)
        except OSError as e:
            QMessageBox.critical(self, "Move Library", f"Could not move library:\n{e}")
            return
        finally:
            progress.close()
        self._settings.set_library_directory(self._library.root)
        # Re-point open library tabs at their new locations
        for doc in self._documents.documents:
            if doc.is_library_file and doc.file_path is not None:
                try:
                    rel = doc.file_path.resolve().relative_to(old_root.resolve())
                except ValueError:
                    continue
                doc.file_path = self._library.root / rel

    def _reveal_document_in_library(self, doc: Document) -> None:
        if doc.file_path is None or not self._library.is_library_path(doc.file_path):
            QMessageBox.information(
                self, "Reveal in Library", "This document is not a library file."
            )
            return
        self._library_panel.show()
        self._library_panel.raise_()
        self._library_panel.select_path(doc.file_path)

    def _restore_session(self) -> None:
        """Reopen the tabs from the previous session (Library PRD 11.2)."""
        paths = [Path(p) for p in self._settings.session_open_files()]
        paths = [p for p in paths if p.is_file()]
        for p in paths:
            self._open_project(p)
        idx = self._settings.session_active_index()
        if paths and 0 <= idx < self._documents.count:
            self._documents.set_active_index(idx)

    def _save_window_state(self) -> None:
        self._settings.save_window_geometry(self.saveGeometry().data())
        self._settings.save_window_state(self.saveState().data())
        tool_id = self._tool_manager.active_tool_id
        if tool_id and tool_id not in TRANSIENT_TOOLS:
            self._settings.set_last_tool(tool_id)
        self._tool_themes.save_session()

    def _remember_zoom(self, doc: Document) -> None:
        """Record the zoom a file-backed document is viewed at (PRD 15.4)."""
        if doc.file_path is not None:
            self._settings.set_recent_file_zoom(doc.file_path, doc.view.zoom_percent)

    def _save_session(self) -> None:
        for doc in self._documents.documents:
            self._remember_zoom(doc)
        open_files = [str(d.file_path) for d in self._documents.documents if d.file_path]
        self._settings.set_session_open_files(open_files)
        self._settings.set_session_active_index(max(0, self._documents.active_index))

    # ---- edit operations ----

    def _edit_undo(self) -> None:
        """Undo — first cancel any active tool operation, then undo."""
        active = self._tool_manager.active_tool
        if active is not None and active.is_active_operation:
            active.cancel()
            return  # first Ctrl+Z cancels active operation
        stack = self._scene.command_stack
        if self._require("Undo", (stack.can_undo, "something to undo")):
            stack.undo()

    def _edit_redo(self) -> None:
        stack = self._scene.command_stack
        if self._require("Redo", (stack.can_redo, "something to redo")):
            stack.redo()

    def _edit_deselect(self) -> None:
        """Escape, a ladder of three rungs (General UI PRD 2.58; Doug's decision C of
        09-25-26): end the active tool's own operation, else leave any other tool for the
        Select tool with the item last added to the document selected, else deselect all,
        silently when there is nothing to deselect (2.59).

        The first rung is the tool's: point-editing mode leaves and keeps the selection
        (Basic Shape PRD 3.5); an arc or a polygon in progress is cancelled (7.2, 8.2); a
        raster selection or a crop is dropped. The second gets a shape just drawn under
        the pointer's handles one key after the draw, while the Basic Shape PRD's 2.5
        still leaves it unselected until asked.
        """
        active = self._tool_manager.active_tool
        if active is not None and active.handle_escape():
            return
        if active is not None and active.tool_id != "select":
            self._tool_manager.activate("select")
            item = self._scene.last_added_item
            if item is not None and self._selectable(item):
                self._selection_manager.select(item)
            return
        # The third rung with nothing selected is silent, not a message: Escape is the
        # key a user presses to make sure nothing is going on (2.59, Doug's 09-25-26)
        self._selection_manager.deselect_all()

    def _selectable(self, item: QGraphicsItem) -> bool:
        """Whether a selection may take *item*: on a visible, unlocked layer and not the
        Background image (General UI PRD 6.2)."""
        if self._scene.is_fixed_in_place(item):
            return False
        layer_id = getattr(item, "layer_id", None)
        layer = self._scene.layer_manager.layer_by_id(layer_id) if layer_id else None
        return layer is not None and layer.visible and not layer.locked

    def _edit_cut(self) -> None:
        active = self._tool_manager.active_tool
        if (
            isinstance(active, (RasterSelectTool, LassoSelectTool))
            and hasattr(active, "has_active_selection")
            and active.has_active_selection
        ):
            # Cut erases the pixels the user sees: the topmost visible layer with an image
            # under the selection, whose lock refuses it (pass findings 10 and 16)
            source = self._raster_cut_source(active.selection_rect)
            if not self._require(
                "Cut",
                (source is not None, "an image under the selection"),
                (source is None or not source.locked, "an unlocked layer under the selection"),
            ):
                return
            assert source is not None
            self._copy_raster_selection(active)
            self._cut_raster_selection(active, source.layer_id)
            return
        if not self._require_selection("Cut"):
            return
        self._edit_copy()
        self._edit_delete()

    def _edit_copy(self) -> None:
        active = self._tool_manager.active_tool
        if (
            isinstance(active, (RasterSelectTool, LassoSelectTool))
            and hasattr(active, "has_active_selection")
            and active.has_active_selection
        ):
            self._copy_raster_selection(active)
            return
        items = self._selected_snap_items()
        if items:
            self._clipboard.copy_items(items)
            return
        # Nothing selected: the whole canvas, flattened, so a capture is one key from a
        # document (Raster PRD 9.1, Doug's decision A of 09-24-26)
        self._copy_whole_canvas()

    def _edit_copy_all(self) -> None:
        """Copy the whole canvas, flattened, whatever is selected (Raster PRD 9.1)."""
        self._copy_whole_canvas()

    def _copy_whole_canvas(self) -> None:
        """The flattened document, the capture plus every visible annotation and the
        canvas border when there is one, to both clipboards, as the PNG export renders it."""
        from snapmock.core.render_engine import RenderEngine

        rect = self._scene.output_rect
        if rect.isEmpty():
            return
        image = RenderEngine(self._scene).render_region(
            rect, background=self._scene.background_color
        )
        self._clipboard.copy_raster_region(image, rect)

    def _copy_raster_selection(self, tool: RasterSelectTool | LassoSelectTool) -> None:
        """Copy pixels from a raster/lasso selection to the clipboard."""
        from snapmock.core.render_engine import RenderEngine

        rect = tool.selection_rect
        if rect.isEmpty():
            return
        engine = RenderEngine(self._scene)
        image = engine.render_region(rect)
        self._clipboard.copy_raster_region(image, rect)

    def _raster_cut_source(self, rect: QRectF) -> Layer | None:
        """The topmost visible layer holding an image under *rect*, or None (Doug's
        decision A of 09-17-26, end-to-end pass finding 16: a capture leaves an empty
        annotation layer active, and the image the user selected is on the Background
        layer below it)."""
        from snapmock.items.raster_region_item import RasterRegionItem

        if rect.isEmpty():
            return None
        lm = self._scene.layer_manager
        for gitem in self._scene.items(rect):  # topmost first
            if not isinstance(gitem, RasterRegionItem):
                continue
            layer = lm.layer_by_id(gitem.layer_id)
            if layer is not None and layer.visible:
                return layer
        return None

    def _cut_raster_selection(
        self, tool: RasterSelectTool | LassoSelectTool, layer_id: str
    ) -> None:
        """Cut pixels from a raster/lasso selection (erase after copy) on *layer_id*."""
        from PyQt6.QtGui import QImage

        from snapmock.commands.raster_commands import RasterCutCommand

        rect = tool.selection_rect
        if not rect.isEmpty():
            cmd = RasterCutCommand(self._scene, rect, QImage(), layer_id)
            self._scene.command_stack.push(cmd)
        tool.cancel()

    def _edit_paste(self, *, at: QPointF | None = None) -> None:
        """Paste at the pointer (Raster PRD 5.5.3, 9.3.1, 9.3.3, 9.3.4).

        *at* is an explicit scene point, the right-click point of a context menu. It is
        keyword-only because the menu action's triggered signal passes its checked flag
        as the first positional argument.
        Otherwise the content goes where the pointer is over the canvas, and, when it is
        elsewhere (the Edit menu, the Welcome card, a shortcut pressed with the pointer
        off the viewport), at the viewport centre.
        """
        if not self._require("Paste", (self._clipboard_has_content(), "content on the clipboard")):
            return
        anchor = self._paste_anchor(at)
        # Smart paste routing: internal items → internal raster → system image → system text
        # 1. Internal vector items
        data = self._clipboard.paste_items()
        if data:
            self._paste_internal_items(data, anchor=anchor)
            return
        # 2. Internal raster data
        raster, _source_rect = self._clipboard.paste_raster()
        if raster is not None:
            self._paste_raster_image(raster, anchor)
            return
        # 3. System clipboard image
        sys_image = self._clipboard.paste_image_from_system()
        if sys_image is not None:
            self._paste_system_image(sys_image, anchor)
            return
        # 4. System clipboard text
        clipboard = QApplication.clipboard()
        if clipboard and clipboard.text():
            self._paste_system_text(clipboard.text(), anchor)

    def _paste_anchor(self, at: QPointF | None = None) -> QPointF:
        """Where a paste lands: *at*, else the pointer over the viewport, else its centre."""
        if at is not None:
            return QPointF(at)
        view = self._view
        viewport = view.viewport()
        pointer = view.pointer_scene_pos
        if pointer is not None and viewport is not None and viewport.isVisible():
            return pointer
        if viewport is None:
            return QPointF(0, 0)
        return view.mapToScene(viewport.rect().center())

    def _paste_internal_items(
        self,
        data: list[dict],  # type: ignore[type-arg]
        *,
        anchor: QPointF | None,
    ) -> None:
        """Add the copied items to the active layer and select them (PRD 9.3.1).

        With *anchor*, the top-left corner of the items' joint bounding box goes there and
        their arrangement is kept; without it (Paste in Place) each keeps its position.
        """
        from snapmock.commands.add_item import AddItemCommand
        from snapmock.io.project_serializer import ITEM_REGISTRY

        layer = self._scene.layer_manager.active_layer
        if layer is None:
            return
        items: list[SnapGraphicsItem] = []
        for item_data in data:
            item_type = item_data.get("type", "")
            cls = ITEM_REGISTRY.get(item_type)
            if cls is not None:
                item = cls.deserialize(item_data)
                # A pasted copy is a new item: the original keeps its id
                item.renew_ids()
                items.append(item)
        if not items:
            return
        if anchor is not None:
            bounds = items[0].sceneBoundingRect()
            for item in items[1:]:
                bounds = bounds.united(item.sceneBoundingRect())
            shift = anchor - bounds.topLeft()
            for item in items:
                item.setPos(item.pos() + shift)
        selected: list[QGraphicsItem] = []
        for item in items:
            self._scene.command_stack.push(AddItemCommand(self._scene, item, layer.layer_id))
            selected.append(item)
        self._tool_manager.activate("select")
        self._selection_manager.select_items(selected)

    def _paste_raster_image(self, image: object, top_left: QPointF) -> None:
        """Paste a raster image with its top-left corner at *top_left*."""
        from PyQt6.QtGui import QImage, QPixmap

        from snapmock.commands.add_item import AddItemCommand
        from snapmock.items.raster_region_item import RasterRegionItem

        if not isinstance(image, QImage):
            return
        pixmap = QPixmap.fromImage(image)
        item = RasterRegionItem(pixmap=pixmap)
        item.setPos(top_left)
        layer = self._scene.layer_manager.active_layer
        if layer is not None:
            self._scene.command_stack.push(AddItemCommand(self._scene, item, layer.layer_id))
            # Switch to select tool and select the new item
            self._tool_manager.activate("select")
            self._selection_manager.select(item)

    def _paste_system_text(self, text: str, top_left: QPointF) -> None:
        """Paste system clipboard text as a TextItem with its top-left corner at *top_left*."""
        from snapmock.commands.add_item import AddItemCommand
        from snapmock.items.text_item import TextItem

        item = TextItem(text=text)
        item.setPos(top_left)
        layer = self._scene.layer_manager.active_layer
        if layer is not None:
            self._scene.command_stack.push(AddItemCommand(self._scene, item, layer.layer_id))
            self._tool_manager.activate("select")
            self._selection_manager.select(item)

    def _paste_system_image(self, image: object, top_left: QPointF) -> None:
        """A system-clipboard image (Navigation PRD 9.3.3; Welcome card of General UI PRD
        16.1): the background layer on an empty project, else a region on the active layer
        with its top-left corner at *top_left*."""
        from PyQt6.QtGui import QPixmap

        from snapmock.io.importer import place_image

        pixmap = QPixmap.fromImage(image)  # type: ignore[arg-type]
        place_image(self._scene, pixmap, top_left)

    def _edit_paste_in_place(self) -> None:
        """Paste items at their original positions (no offset).

        Content with no original position, a raster copied without a source rectangle or
        a system-clipboard image, lands where Paste would put it (PRD 9.3, Paste in Place).
        """
        if not self._require(
            "Paste in Place", (self._clipboard_has_content(), "content on the clipboard")
        ):
            return
        data = self._clipboard.paste_items()
        if data:
            self._paste_internal_items(data, anchor=None)
            return
        raster, source_rect = self._clipboard.paste_raster()
        if raster is not None:
            if source_rect is not None and not source_rect.isEmpty():
                self._paste_raster_image(raster, source_rect.topLeft())
            else:
                self._paste_raster_image(raster, self._paste_anchor())
            return
        sys_image = self._clipboard.paste_image_from_system()
        if sys_image is not None:
            self._paste_system_image(sys_image, self._paste_anchor())

    def _edit_delete(self) -> None:
        items = self._require_selection("Delete")
        if not items:
            return
        from snapmock.commands.remove_item import RemoveItemCommand

        for item in items:
            self._scene.command_stack.push(RemoveItemCommand(self._scene, item))
        self._selection_manager.deselect_all()

    def _edit_duplicate(self) -> None:
        """Clone selected items with +10,+10 offset."""
        items = self._require_selection("Duplicate")
        if not items:
            return
        from snapmock.commands.add_item import AddItemCommand

        layer = self._scene.layer_manager.active_layer
        if layer is None:
            return
        clones: list[QGraphicsItem] = []
        for item in items:
            clone = item.clone()
            clone.setPos(clone.pos().x() + 10, clone.pos().y() + 10)
            self._scene.command_stack.push(AddItemCommand(self._scene, clone, layer.layer_id))
            clones.append(clone)
        self._selection_manager.select_items(clones)

    def _edit_select_all(self) -> None:
        """Select the whole document as a raster selection (PRD 3.2, 2.57).

        Ctrl+A means one thing, the picture to take away, whether or not the active layer
        holds items (Doug's decision B of 09-25-26); Ctrl+C then copies it. The items are
        deselected first so no handles sit under the marching ants. Selecting a layer's
        items is Select All on Layer, without a key.
        """
        self._selection_manager.deselect_all()
        self._select_whole_canvas()

    def _edit_select_all_on_layer(self) -> None:
        """Select every unlocked item on the active layer (PRD 3.2; Ctrl+A until 2.57)."""
        lm = self._scene.layer_manager
        active = lm.active_layer
        # Top-level items: a group is selected as one, never its members
        items: list[QGraphicsItem] = [
            i
            for i in self._scene.annotation_items()
            if active is not None
            and i.layer_id == active.layer_id
            and not i.locked
            and not self._scene.is_fixed_in_place(i)
        ]
        if self._require(
            "Select All on Layer", (bool(items), "at least one item on the active layer")
        ):
            self._selection_manager.select_items(items)

    def _select_whole_canvas(self) -> None:
        """A raster selection of the whole document, the border included, marching ants
        and all."""
        rect = self._scene.output_rect
        if rect.isEmpty():
            return
        self._tool_manager.activate("raster_select")
        tool = self._tool_manager.active_tool
        if isinstance(tool, RasterSelectTool):
            tool.select_rect(rect)

    def _edit_select_all_layers(self) -> None:
        """Select every unlocked item on every visible, unlocked layer."""
        lm = self._scene.layer_manager
        usable = {layer.layer_id for layer in lm.layers if layer.visible and not layer.locked}
        items: list[QGraphicsItem] = [
            i
            for i in self._scene.annotation_items()
            if i.layer_id in usable and not i.locked and not self._scene.is_fixed_in_place(i)
        ]
        if self._require("Select All Layers", (bool(items), "at least one item on the canvas")):
            self._selection_manager.select_items(items)

    def _edit_select_all_text(self) -> None:
        """Select every text-containing item on visible, unlocked layers (PRD 3.2).

        Batch changes to the selection's font, size, and colour arrive with the
        Property Panel's multi-selection behaviour (PRD 8.6, Phase 6). A group's text
        members are included, so the batch reaches text inside groups (Group and
        Ungroup kickoff, step 5).
        """
        from snapmock.items.callout_item import CalloutItem
        from snapmock.items.text_item import TextItem

        lm = self._scene.layer_manager
        usable = {layer.layer_id for layer in lm.layers if layer.visible and not layer.locked}
        items: list[QGraphicsItem] = [
            i
            for i in self._scene.all_annotation_items()
            if isinstance(i, (TextItem, CalloutItem)) and i.layer_id in usable and not i.locked
        ]
        if self._require("Select All Text", (bool(items), "at least one text-containing item")):
            self._tool_manager.activate("select")
            self._selection_manager.select_items(items)

    def _edit_find_replace_color(self) -> None:
        from snapmock.ui.find_replace_color_dialog import FindReplaceColorDialog

        has_items = bool(self._scene.annotation_items())
        if not self._require("Find/Replace Color", (has_items, "at least one item on the canvas")):
            return
        dlg = FindReplaceColorDialog(self._scene, self)
        dlg.exec()
        dlg.deleteLater()

    # ---- image operations ----

    def _image_resize_canvas(self) -> None:
        from snapmock.commands.raster_commands import ResizeCanvasCommand
        from snapmock.ui.resize_canvas_dialog import ResizeCanvasDialog

        dlg = ResizeCanvasDialog(self._scene.canvas_size, self)
        if dlg.exec():
            cmd = ResizeCanvasCommand(
                self._scene,
                dlg.new_size(),
                dlg.anchor(),
                dlg.fill_color(),
            )
            self._scene.command_stack.push(cmd)

    def _image_resize_image(self) -> None:
        from snapmock.commands.raster_commands import ResizeImageCommand
        from snapmock.ui.resize_image_dialog import ResizeImageDialog

        dlg = ResizeImageDialog(self._scene.canvas_size, self)
        if dlg.exec():
            cmd = ResizeImageCommand(self._scene, dlg.new_size())
            self._scene.command_stack.push(cmd)

    def _image_crop_to_canvas(self) -> None:
        """Activate the crop tool to resize the canvas (General UI PRD 3.5)."""
        self._tool_manager.activate("crop")

    def _image_rotate_cw(self) -> None:
        from snapmock.commands.canvas_transform_commands import RotateCanvasCommand

        cmd = RotateCanvasCommand(self._scene, clockwise=True)
        self._scene.command_stack.push(cmd)

    def _image_rotate_ccw(self) -> None:
        from snapmock.commands.canvas_transform_commands import RotateCanvasCommand

        cmd = RotateCanvasCommand(self._scene, clockwise=False)
        self._scene.command_stack.push(cmd)

    def _image_flip_h(self) -> None:
        from snapmock.commands.canvas_transform_commands import FlipCanvasCommand

        cmd = FlipCanvasCommand(self._scene, horizontal=True)
        self._scene.command_stack.push(cmd)

    def _image_flip_v(self) -> None:
        from snapmock.commands.canvas_transform_commands import FlipCanvasCommand

        cmd = FlipCanvasCommand(self._scene, horizontal=False)
        self._scene.command_stack.push(cmd)

    def _visible_content_bounds(self) -> QRectF:
        """Union of the bounds of every item on a visible layer, clipped to the canvas."""
        lm = self._scene.layer_manager
        visible = {layer.layer_id for layer in lm.layers if layer.visible}
        bounds = QRectF()
        for item in self._scene.annotation_items():
            if item.layer_id in visible:
                bounds = bounds.united(item.sceneBoundingRect())
        return bounds.intersected(self._scene.canvas_rect)

    def _image_auto_trim(self) -> None:
        """Crop the canvas to the bounding box of all visible content (PRD 3.5)."""
        from snapmock.commands.raster_commands import CropCanvasCommand

        bounds = self._visible_content_bounds()
        if not self._require("Auto-Trim", (not bounds.isEmpty(), "visible content on the canvas")):
            return
        rect = QRectF(
            math.floor(bounds.left()),
            math.floor(bounds.top()),
            math.ceil(bounds.right()) - math.floor(bounds.left()),
            math.ceil(bounds.bottom()) - math.floor(bounds.top()),
        )
        if not self._require(
            "Auto-Trim", (rect != self._scene.canvas_rect, "empty borders to remove")
        ):
            return
        self._scene.command_stack.push(CropCanvasCommand(self._scene, rect))

    # ---- layer operations ----

    def _layer_new(self) -> None:
        from snapmock.commands.layer_commands import AddLayerCommand

        lm = self._scene.layer_manager
        name = f"Layer {lm.count + 1}"
        cmd = AddLayerCommand(lm, name)
        self._scene.command_stack.push(cmd)

    def _layer_duplicate(self) -> None:
        lm = self._scene.layer_manager
        active = self._require_active_layer("Duplicate Layer")
        if active is None:
            return
        from snapmock.commands.layer_commands import DuplicateLayerCommand

        del lm
        self._scene.command_stack.push(DuplicateLayerCommand(self._scene, active.layer_id))

    def _layer_delete(self) -> None:
        """Delete the active layer, or every Ctrl+click-selected layer, as one command."""
        lm = self._scene.layer_manager
        active = lm.active_layer
        targets = [
            layer
            for layer in (lm.layer_by_id(lid) for lid in self._layer_panel.selected_layer_ids())
            if layer is not None
        ]
        if active is not None and not targets:
            targets = [active]
        if not self._require(
            "Delete Layer",
            (active is not None, "an active layer"),
            (
                lm.count > len(targets),
                "more than one layer" if len(targets) == 1 else "at least one layer left",
            ),
        ):
            return
        from snapmock.commands.layer_commands import RemoveLayerCommand
        from snapmock.commands.macro_command import MacroCommand
        from snapmock.commands.remove_item import RemoveItemCommand
        from snapmock.core.command_stack import BaseCommand

        ids = {layer.layer_id for layer in targets}
        # Top-level items: a group is removed with its members and counts once
        items = [i for i in self._scene.annotation_items() if i.layer_id in ids]
        if items and self._settings.confirm_delete_layers():
            count = len(items)
            noun = "item" if count == 1 else "items"
            what = f'layer "{targets[0].name}"' if len(targets) == 1 else f"{len(targets)} layers"
            pronoun = "it" if len(targets) == 1 else "them"
            answer = QMessageBox.question(
                self,
                "Delete Layer",
                f"Delete {what} and the {count} {noun} on {pronoun}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        cmds: list[BaseCommand] = [RemoveItemCommand(self._scene, i) for i in items]
        cmds.extend(RemoveLayerCommand(lm, layer.layer_id) for layer in targets)
        description = (
            f'Delete layer "{targets[0].name}"'
            if len(targets) == 1
            else f"Delete {len(targets)} layers"
        )
        self._scene.command_stack.push(MacroCommand(cmds, description))

    # ---- Merge Down, Merge Visible, Flatten All (PRD 3.4; follow-up decision 1) ----

    MERGE_DONT_ASK_TEXT = "Don't ask again this session"

    def _build_merge_question(self, title: str, text: str) -> QMessageBox:
        """The once-per-session question a merge asks before rasterizing (silence 1)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setInformativeText(
            "The items on the merged layers become one image and stop being editable."
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        check = QCheckBox(self.MERGE_DONT_ASK_TEXT, box)
        check.setAccessibleName(self.MERGE_DONT_ASK_TEXT)
        box.setCheckBox(check)
        return box

    def _ask_merge(self, title: str, text: str) -> bool:
        """True when the merge may go ahead; asks unless told not to this session or the
        Preferences setting "Confirm before deleting layers" is off."""
        if self._merge_dont_ask or not self._settings.confirm_delete_layers():
            return True
        box = self._build_merge_question(title, text)
        answer = box.exec()
        check = box.checkBox()
        if check is not None and check.isChecked():
            self._merge_dont_ask = True
        return answer == QMessageBox.StandardButton.Yes

    def _merge(self, layer_ids: list[str], target_id: str | None, description: str) -> None:
        from snapmock.commands.merge_commands import MergeLayersCommand

        self._scene.command_stack.push(
            MergeLayersCommand(self._scene, layer_ids, target_id, description=description)
        )

    def _layer_merge_down(self) -> None:
        """The active layer into the layer below it; a Ctrl+click selection that includes
        the active layer merges the selected layers into the lowest of them (PRD 7.3)."""
        lm = self._scene.layer_manager
        active = lm.active_layer
        idx = lm.index_of(active.layer_id) if active is not None else -1
        selected = self._layer_panel.selected_layer_ids()
        batch = active is not None and len(selected) > 1 and active.layer_id in selected
        if batch:
            layers = sorted(
                (layer for layer in (lm.layer_by_id(lid) for lid in selected) if layer),
                key=lambda layer: lm.index_of(layer.layer_id),
            )
        elif active is not None and idx > 0:
            layers = [lm.layers[idx - 1], active]
        else:
            layers = []
        if not self._require(
            "Merge Down",
            (active is not None, "an active layer"),
            (idx > 0 or batch, "a layer below the active layer"),
            (all(layer.visible for layer in layers), "the merged layers visible"),
        ):
            return
        target = layers[0]
        upper = ", ".join(f'"{layer.name}"' for layer in layers[1:])
        if not self._ask_merge("Merge Down", f'Merge {upper} into "{target.name}"?'):
            return
        self._merge([layer.layer_id for layer in layers], target.layer_id, "Merge Down")

    def _layer_merge_visible(self) -> None:
        """Every visible layer into the lowest visible one; hidden layers stay (silence 3)."""
        lm = self._scene.layer_manager
        visible = [layer for layer in lm.layers if layer.visible]
        if not self._require("Merge Visible", (len(visible) >= 2, "at least two visible layers")):
            return
        target = visible[0]
        if not self._ask_merge(
            "Merge Visible", f'Merge the {len(visible)} visible layers into "{target.name}"?'
        ):
            return
        self._merge([layer.layer_id for layer in visible], target.layer_id, "Merge Visible")

    def _layer_flatten(self) -> None:
        """Every layer into one Background layer holding one raster region (silence 2).

        Asks first, as the merges do, and names the hidden content it discards
        (end-to-end pass finding 12, General UI PRD 2.47)."""
        lm = self._scene.layer_manager
        count = lm.count
        if not self._require("Flatten All", (count >= 2, "at least two layers")):
            return
        text = f"Flatten all {count} layers into one image?"
        hidden = sum(1 for layer in lm.layers if not layer.visible)
        if hidden:
            noun = "layer's" if hidden == 1 else "layers'"
            text += f" {hidden} hidden {noun} content will be discarded."
        if not self._ask_merge("Flatten All", text):
            return
        self._merge(
            [layer.layer_id for layer in self._scene.layer_manager.layers], None, "Flatten All"
        )

    def _layer_rename(self) -> None:
        """Rename Layer (F2) opens the Layer Panel's inline editor (General UI PRD 7.2)."""
        active = self._require_active_layer("Rename Layer")
        if active is None:
            return
        if not self._layer_panel.isVisible():
            self._layer_panel.show()
        self._layer_panel.begin_rename(active.layer_id)

    def _layer_properties(self) -> None:
        active = self._require_active_layer("Layer Properties")
        if active is not None:
            self._show_layer_properties(active.layer_id)

    def _show_item_properties(self) -> None:
        """Show the item properties dialog for the first selected item."""
        items = self._selected_snap_items()
        if not items:
            return
        item = items[0]

        from snapmock.ui.item_properties_dialog import ItemPropertiesDialog

        dlg = ItemPropertiesDialog(item, self._scene, self)
        if dlg.exec() == ItemPropertiesDialog.DialogCode.Accepted:
            from snapmock.commands.modify_property import ModifyPropertyCommand

            for prop_name, (old_val, new_val) in dlg.get_changes().items():
                cmd = ModifyPropertyCommand(item, prop_name, old_val, new_val)
                self._scene.command_stack.push(cmd)

    def _show_layer_properties(self, layer_id: str) -> None:
        """Show the layer properties dialog for the given layer."""
        lm = self._scene.layer_manager
        layer = lm.layer_by_id(layer_id)
        if layer is None:
            return

        from snapmock.ui.layer_properties_dialog import LayerPropertiesDialog

        dlg = LayerPropertiesDialog(layer, self)
        if dlg.exec() == LayerPropertiesDialog.DialogCode.Accepted:
            from snapmock.commands.layer_commands import ChangeLayerPropertyCommand

            for prop_name, (old_val, new_val) in dlg.get_changes().items():
                cmd = ChangeLayerPropertyCommand(lm, layer_id, prop_name, old_val, new_val)
                self._scene.command_stack.push(cmd)

    def _layer_move_up(self) -> None:
        lm = self._scene.layer_manager
        active = self._require_active_layer("Move Layer Up")
        if active is None:
            return
        idx = lm.index_of(active.layer_id)
        if self._require(
            "Move Layer Up",
            (idx < lm.count - 1, "a layer above the active layer"),
            (not active.is_background, "a layer that is not the Background layer"),
        ):
            from snapmock.commands.layer_commands import ReorderLayerCommand

            cmd = ReorderLayerCommand(lm, active.layer_id, idx + 1)
            self._scene.command_stack.push(cmd)

    def _layer_move_down(self) -> None:
        lm = self._scene.layer_manager
        active = self._require_active_layer("Move Layer Down")
        if active is None:
            return
        idx = lm.index_of(active.layer_id)
        if self._require(
            "Move Layer Down",
            (idx > 0, "a layer below the active layer"),
            (
                idx <= 0 or not lm.layers[idx - 1].is_background,
                "a layer below that is not the Background layer",
            ),
        ):
            from snapmock.commands.layer_commands import ReorderLayerCommand

            cmd = ReorderLayerCommand(lm, active.layer_id, idx - 1)
            self._scene.command_stack.push(cmd)

    def _layer_move_to_top(self) -> None:
        lm = self._scene.layer_manager
        active = self._require_active_layer("Move Layer to Top")
        if active is None:
            return
        idx = lm.index_of(active.layer_id)
        if self._require(
            "Move Layer to Top",
            (idx < lm.count - 1, "a layer above the active layer"),
            (not active.is_background, "a layer that is not the Background layer"),
        ):
            from snapmock.commands.layer_commands import ReorderLayerCommand

            cmd = ReorderLayerCommand(lm, active.layer_id, lm.count - 1)
            self._scene.command_stack.push(cmd)

    def _layer_move_to_bottom(self) -> None:
        lm = self._scene.layer_manager
        active = self._require_active_layer("Move Layer to Bottom")
        if active is None:
            return
        idx = lm.index_of(active.layer_id)
        if self._require(
            "Move Layer to Bottom",
            (idx > 0, "a layer below the active layer"),
            (
                idx <= 0 or not lm.layers[idx - 1].is_background,
                "a layer below that is not the Background layer",
            ),
        ):
            from snapmock.commands.layer_commands import ReorderLayerCommand

            cmd = ReorderLayerCommand(lm, active.layer_id, 0)
            self._scene.command_stack.push(cmd)

    # ---- context menu helpers ----

    def _move_items_to_layer(self, target_layer_id: str) -> None:
        """Move selected items to the specified layer."""
        items = self._selected_snap_items()
        if not items:
            return
        from snapmock.commands.move_item_layer import MoveItemToLayerCommand

        cmd = MoveItemToLayerCommand(self._scene, items, target_layer_id)
        self._scene.command_stack.push(cmd)

    def _toggle_item_lock(self) -> None:
        """Toggle the locked flag on all selected items."""
        items = self._require_selection("Lock Item")
        if not items:
            return
        # Use the first item's state to determine the toggle direction
        new_locked = not items[0].locked
        for item in items:
            item.locked = new_locked

    def _layer_new_relative(self, reference_layer_id: str, *, above: bool) -> None:
        """Add a new layer above or below the referenced layer."""
        from snapmock.commands.layer_commands import AddLayerCommand

        lm = self._scene.layer_manager
        idx = lm.index_of(reference_layer_id)
        if idx < 0:
            return
        insert_idx = idx + 1 if above else idx
        name = f"Layer {lm.count + 1}"
        cmd = AddLayerCommand(lm, name, insert_idx)
        self._scene.command_stack.push(cmd)

    def _toggle_layer_lock(self, layer_id: str) -> None:
        """Toggle lock on a layer, and on its Ctrl+click selection, as one command."""
        self._layer_panel.toggle_lock(layer_id)

    def _toggle_layer_visibility(self, layer_id: str) -> None:
        """Toggle visibility on a layer, and on its Ctrl+click selection, as one command."""
        self._layer_panel.toggle_visibility(layer_id)

    def _pick_color_for_picker(self, deliver: Callable[[QColor], None]) -> bool:
        """A colour picker's eyedropper button (General UI PRD 11.1, Blur PRD 4.6).

        Activates the eyedropper as a temporary tool; the first pick goes to the
        picker as well as to the Tool Options Bar, and the previous tool returns.
        """
        eyedropper = self._tool_manager.tool("eyedropper")
        if not isinstance(eyedropper, EyedropperTool) or self._active_document is None:
            return False
        self._tool_manager.activate_temporary("eyedropper")
        bar_callback = eyedropper.pick_callback

        def _picked(color: QColor) -> None:
            eyedropper.set_pick_callback(bar_callback)
            self._picker_pick_active = False
            # The bar shows the sample and remembers it; the colour is applied by the
            # picker the user opened, not by the Eyedropper's Apply Target (Blur PRD 4.6).
            self._tool_options.show_picked_color(color)
            self._tool_manager.restore_previous()
            deliver(color)

        self._picker_pick_active = True
        self._picker_bar_callback = bar_callback
        eyedropper.set_pick_callback(_picked)
        return True

    def _on_tool_changed_for_picker(self, tool_id: str) -> None:
        """Leaving the eyedropper before a pick drops the picker's claim on it."""
        if tool_id != "eyedropper" and self._picker_pick_active:
            self._picker_pick_active = False
            eyedropper = self._tool_manager.tool("eyedropper")
            if isinstance(eyedropper, EyedropperTool):
                eyedropper.set_pick_callback(self._picker_bar_callback)

    def _on_canvas_setting_changed(self, key: str, value: object) -> None:
        """A Property Panel Canvas section control that edits a preference (PRD 8.5)."""
        if key == "snap_to_grid":
            self._snap_grid_action.setChecked(bool(value))
            return
        if key in ("pasteboard_color", "grid_size"):
            self._apply_preference_changes({key: (None, value)})

    def _show_canvas_properties(self) -> None:
        """Canvas context menu > Canvas Properties opens the Canvas section (PRD 10.1)."""
        self._selection_manager.deselect_all()
        self._property_panel.show()
        self._property_panel.raise_()
        self._property_panel.show_canvas_section()

    def _on_layer_hovered(self, layer_id: str) -> None:
        """Outline the hovered layer's items on the canvas (General UI PRD 7.3, Preferences)."""
        if layer_id and self._settings.layer_hover_highlight():
            self._view.set_highlighted_layer(layer_id)
        else:
            self._view.set_highlighted_layer(None)

    # ---- arrange operations ----

    def _selected_snap_items(self) -> list[SnapGraphicsItem]:
        return [i for i in self._selection_manager.items if isinstance(i, SnapGraphicsItem)]

    def _arrange_bring_to_front(self) -> None:
        items = self._require_selection("Bring to Front")
        if not items:
            return
        from snapmock.commands.arrange_commands import ChangeZOrderCommand

        cmd = ChangeZOrderCommand(self._scene, items, "front")
        self._scene.command_stack.push(cmd)

    def _arrange_bring_forward(self) -> None:
        items = self._require_selection("Bring Forward")
        if not items:
            return
        from snapmock.commands.arrange_commands import ChangeZOrderCommand

        cmd = ChangeZOrderCommand(self._scene, items, "forward")
        self._scene.command_stack.push(cmd)

    def _arrange_send_backward(self) -> None:
        items = self._require_selection("Send Backward")
        if not items:
            return
        from snapmock.commands.arrange_commands import ChangeZOrderCommand

        cmd = ChangeZOrderCommand(self._scene, items, "backward")
        self._scene.command_stack.push(cmd)

    def _arrange_send_to_back(self) -> None:
        items = self._require_selection("Send to Back")
        if not items:
            return
        from snapmock.commands.arrange_commands import ChangeZOrderCommand

        cmd = ChangeZOrderCommand(self._scene, items, "back")
        self._scene.command_stack.push(cmd)

    def _arrange_flip_horizontal(self) -> None:
        items = self._require_selection("Flip Horizontal")
        if not items:
            return
        from snapmock.commands.macro_command import MacroCommand
        from snapmock.commands.modify_property import ModifyPropertyCommand
        from snapmock.core.command_stack import BaseCommand

        cmds: list[BaseCommand] = [
            ModifyPropertyCommand(
                item, "flip_horizontal", item.flip_horizontal, not item.flip_horizontal
            )
            for item in items
        ]
        self._scene.command_stack.push(MacroCommand(cmds, "Flip Horizontal"))

    # ---- marker editing (Numbered Steps, Stamps, and Emoji PRD 2.8; kickoff silence 9) ----

    def open_marker_editor(self, item: SnapGraphicsItem) -> bool:
        """Enter *item*'s edit: the inline editor for a numbered step. One editor at a
        time; a double-click from the Select tool or the placing tool both land here.
        Returns False for an item with no editor."""
        from snapmock.items.numbered_step_item import NumberedStepItem

        self.close_marker_editor()
        if isinstance(item, EmojiItem):
            emoji_tool = self._tool_manager.tool("emoji")
            if not isinstance(emoji_tool, EmojiTool):
                return False
            self._selection_manager.select(item)
            anchor = self._view.mapFromScene(item.sceneBoundingRect().bottomLeft())
            emoji_target: EmojiItem = item

            def _emoji_chosen(chars: str) -> None:
                self._change_emoji(emoji_target, chars)

            emoji_tool.choose_emoji(
                None,
                _emoji_chosen,
                item.emoji_char,
                self._view.viewport().mapToGlobal(anchor),  # type: ignore[union-attr]
            )
            return True
        if isinstance(item, StampItem):
            tool = self._tool_manager.tool("stamp")
            if not isinstance(tool, StampTool):
                return False
            self._selection_manager.select(item)
            anchor = self._view.mapFromScene(item.sceneBoundingRect().bottomLeft())
            target: StampItem = item

            def _chosen(stamp_id: str) -> None:
                self._change_stamp(target, stamp_id)

            tool.choose_stamp(
                None,
                _chosen,
                item.stamp_id,
                self._view.viewport().mapToGlobal(anchor),  # type: ignore[union-attr]
            )
            return True
        if isinstance(item, NumberedStepItem):
            from snapmock.ui.step_inline_editor import EDIT_HINT, StepInlineEditor

            self._selection_manager.select(item)
            self._marker_editor = StepInlineEditor(
                item, self._view, self._scene, self._on_marker_editor_finished
            )
            self.show_status_hint(EDIT_HINT)
            return True
        return False

    @property
    def marker_editor(self) -> QWidget | None:
        """The open inline editor, if any."""
        return self._marker_editor

    def close_marker_editor(self) -> None:
        """Finish the open editor, applying its edit."""
        editor = self._marker_editor
        if editor is not None:
            finish = getattr(editor, "finish", None)
            if callable(finish):
                finish()
            self._marker_editor = None

    def _on_marker_editor_finished(self) -> None:
        self._marker_editor = None
        self._on_tool_changed_for_hint(self._tool_manager.active_tool_id)

    def _change_stamp(self, item: StampItem, stamp_id: str) -> None:
        """Change Stamp (PRD 3.7, 6.2): one undoable command replacing the stamp."""
        from snapmock.commands.marker_commands import ChangeStampCommand
        from snapmock.core.stamp_library import stamp_library

        info = stamp_library().stamp(stamp_id)
        if info is None or info.id == item.stamp_id:
            return
        self._scene.command_stack.push(
            ChangeStampCommand(item, info, stamp_library().svg_data(info.id))
        )

    def _change_emoji(self, item: EmojiItem, chars: str) -> None:
        """Change Emoji (PRD 4.6, 6.3): one undoable command replacing the emoji."""
        from snapmock.commands.marker_commands import ChangeEmojiCommand

        if not chars or chars == item.emoji_char:
            return
        self._scene.command_stack.push(ChangeEmojiCommand(item, chars))

    def _emoji_change(self) -> None:
        """Change Emoji... (PRD 4.6): the picker for the one selected emoji."""
        emoji = self._selected_marker(EmojiItem)
        if not self._require("Change Emoji", (emoji is not None, "one emoji")):
            return
        assert emoji is not None
        self.open_marker_editor(emoji)

    def _emoji_reset_size(self) -> None:
        """Reset Size (PRD 4.6; kickoff silence 13): back to 48 px."""
        from snapmock.commands.modify_property import ModifyPropertyCommand
        from snapmock.core.emoji_data import DEFAULT_EMOJI_SIZE

        emoji = self._selected_marker(EmojiItem)
        if not self._require("Reset Size", (emoji is not None, "one emoji")):
            return
        assert isinstance(emoji, EmojiItem)
        if emoji.emoji_size != DEFAULT_EMOJI_SIZE:
            self._scene.command_stack.push(
                ModifyPropertyCommand(emoji, "emoji_size", emoji.emoji_size, DEFAULT_EMOJI_SIZE)
            )

    def _selected_marker(self, kind: type[SnapGraphicsItem]) -> SnapGraphicsItem | None:
        items = self._selected_snap_items()
        if len(items) == 1 and isinstance(items[0], kind):
            return items[0]
        return None

    def _stamp_change(self) -> None:
        """Change Stamp... (PRD 3.7): the library for the one selected stamp."""
        stamp = self._selected_marker(StampItem)
        if not self._require("Change Stamp", (stamp is not None, "one stamp")):
            return
        assert stamp is not None
        self.open_marker_editor(stamp)

    def _stamp_reset_size(self) -> None:
        """Reset Size (PRD 3.7; kickoff silence 13): the index's default size."""
        from snapmock.commands.modify_property import ModifyPropertyCommand

        stamp = self._selected_marker(StampItem)
        if not self._require("Reset Size", (stamp is not None, "one stamp")):
            return
        assert isinstance(stamp, StampItem)
        if stamp.stamp_size != stamp.default_size:
            self._scene.command_stack.push(
                ModifyPropertyCommand(stamp, "stamp_size", stamp.stamp_size, stamp.default_size)
            )

    def _selected_step(self) -> NumberedStepItem | None:
        """The one selected numbered step, or None."""
        from snapmock.items.numbered_step_item import NumberedStepItem

        items = self._selected_snap_items()
        if len(items) == 1 and isinstance(items[0], NumberedStepItem):
            return items[0]
        return None

    def _step_set_as_starting_number(self) -> None:
        """Set as Starting Number (PRD 2.8): the Starting Number control takes this step's
        number, so the next placed step follows it."""
        step = self._selected_step()
        if not self._require("Set as Starting Number", (step is not None, "one numbered step")):
            return
        assert step is not None
        tool = self._tool_manager.tool("numbered_step")
        if isinstance(tool, NumberedStepTool):
            tool.creation_defaults["start_number"] = step.number_value
            tool.on_option_changed("start_number", step.number_value)
            self._tool_manager.tool_defaults_changed.emit("numbered_step")

    def _step_toggle_text_mode(self) -> None:
        """Convert to Text Mode / Convert to Number Mode (PRD 2.8), one undo entry."""
        from snapmock.commands.modify_property import ModifyPropertyCommand
        from snapmock.config.constants import DisplayMode

        step = self._selected_step()
        if not self._require("Convert Display Mode", (step is not None, "one numbered step")):
            return
        assert step is not None
        new_mode = (
            DisplayMode.NUMBER if step.display_mode is DisplayMode.TEXT else DisplayMode.TEXT
        )
        self._scene.command_stack.push(
            ModifyPropertyCommand(step, "display_mode", step.display_mode, new_mode)
        )

    def renumber_all_steps(self) -> None:
        """Renumber All Steps (Numbered Steps PRD 2.3, 6.1): every step top to bottom, then
        left to right, from the Numbered Step tool's Starting Number; one undo entry."""
        from snapmock.commands.marker_commands import RenumberStepsCommand

        tool = self._tool_manager.tool("numbered_step")
        start = int(tool.creation_defaults.get("start_number", 1)) if tool is not None else 1
        command = RenumberStepsCommand(self._scene, start)
        if not self._require(
            "Renumber All Steps", (command.count > 0, "at least one numbered step")
        ):
            return
        self._scene.command_stack.push(command)
        if isinstance(tool, NumberedStepTool) and self._tool_manager.active_tool is tool:
            tool.set_next_number(start + command.count)

    def _arrange_flip_vertical(self) -> None:
        items = self._require_selection("Flip Vertical")
        if not items:
            return
        from snapmock.commands.macro_command import MacroCommand
        from snapmock.commands.modify_property import ModifyPropertyCommand
        from snapmock.core.command_stack import BaseCommand

        cmds: list[BaseCommand] = [
            ModifyPropertyCommand(
                item, "flip_vertical", item.flip_vertical, not item.flip_vertical
            )
            for item in items
        ]
        self._scene.command_stack.push(MacroCommand(cmds, "Flip Vertical"))

    def _arrange_group(self) -> None:
        """Arrange > Group (PRD 3.6): the selected items become one group on their layer.

        Group and Ungroup kickoff decision 2 (option A): a selection that spans layers is
        refused with the Section 1.3 message rather than gathered onto one layer.
        """
        items = self._require_selection("Group", 2)
        if not items:
            return
        on_one_layer = len({item.layer_id for item in items}) == 1
        if not self._require("Group", (on_one_layer, "the selected items on one layer")):
            return
        from snapmock.commands.group_commands import GroupItemsCommand

        self._scene.command_stack.push(
            GroupItemsCommand(self._scene, items, self._selection_manager)
        )

    def _arrange_ungroup(self) -> None:
        """Arrange > Ungroup (PRD 3.6): every selected group dissolves into its members."""
        from snapmock.items.group_item import GroupItem

        groups = [item for item in self._selected_snap_items() if isinstance(item, GroupItem)]
        if not self._require("Ungroup", (bool(groups), "a group selected")):
            return
        from snapmock.commands.group_commands import UngroupItemsCommand

        self._scene.command_stack.push(
            UngroupItemsCommand(self._scene, groups, self._selection_manager)
        )

    def _arrange_align(self, alignment: str) -> None:
        items = self._require_selection("Align", 2)
        if not items:
            return
        from snapmock.commands.arrange_commands import AlignItemsCommand

        cmd = AlignItemsCommand(items, alignment)
        self._scene.command_stack.push(cmd)

    def _arrange_distribute(self, direction: str) -> None:
        items = self._require_selection("Distribute", 3)
        if not items:
            return
        from snapmock.commands.arrange_commands import DistributeItemsCommand

        cmd = DistributeItemsCommand(items, direction)
        self._scene.command_stack.push(cmd)

    def _arrange_align_canvas_center(self) -> None:
        items = self._require_selection("Align to Canvas Center")
        if not items:
            return
        from snapmock.commands.arrange_commands import AlignToCanvasCommand

        cmd = AlignToCanvasCommand(self._scene, items)
        self._scene.command_stack.push(cmd)

    # ---- help operations ----

    def _help_welcome(self) -> None:
        """Help > Welcome / Getting Started (PRD 3.8, 16.1)."""
        self.show_welcome()

    def _help_docs(self) -> None:
        QDesktopServices.openUrl(QUrl(DOCUMENTATION_URL))

    def _help_shortcuts(self) -> None:
        """The searchable shortcut reference (PRD 3.8), with the live capture hotkeys."""
        from snapmock.ui.shortcuts_dialog import KeyboardShortcutsDialog

        bindings = {b.action: b.key_text for b in self._capture.bindings}
        dlg = KeyboardShortcutsDialog(self, capture_bindings=bindings)
        dlg.exec()
        dlg.deleteLater()

    def _help_report_bug(self) -> None:
        QDesktopServices.openUrl(QUrl(ISSUES_URL))

    # ---- Help > Add to Menu / Remove from Menu (menu-entry decisions 1 to 4) ----

    ADD_TO_MENU_TITLE = "Add to Menu"
    REMOVE_FROM_MENU_TITLE = "Remove from Menu"
    ICON_RESCAN_NOTE = (
        "If the icon is missing, the desktop has not rescanned its icon folders yet: "
        "it appears after the desktop shell restarts or at your next login."
    )

    def _menu_entry_label(self) -> str:
        """The row's text, which follows whether our own entry is in place."""
        return "&Remove from Menu" if desktop_entry.installed() else "Add to &Menu"

    def _refresh_menu_entry_label(self) -> None:
        """Read the entry's state each time the Help menu opens, not once at start."""
        if self._menu_entry_action is not None:
            self._menu_entry_action.setText(self._menu_entry_label())

    def _help_menu_entry(self) -> None:
        """Write the desktop entry, the icons, and the file type, or take them away.

        A form that needs nothing says so rather than showing a disabled row
        (General UI PRD 1.3).
        """
        installed = desktop_entry.installed()
        title = self.REMOVE_FROM_MENU_TITLE if installed else self.ADD_TO_MENU_TITLE
        reason = desktop_entry.unsupported_reason()
        if reason is not None:
            QMessageBox.information(self, title, reason)
            return
        if installed:
            self._remove_desktop_entry(title)
        else:
            self._add_desktop_entry(title)
        self._refresh_menu_entry_label()

    def _add_desktop_entry(self, title: str) -> None:
        """Ask the AppImage's question if there is one, write, and report the outcome."""
        proceed, program = self._appimage_copy_choice(title)
        if not proceed:
            return
        outcome = desktop_entry.install(program=program)
        text = outcome.message()
        if outcome.changed:
            text = f"{text} {self.ICON_RESCAN_NOTE}"
        log.info("%s: %s", title, text)
        QMessageBox.information(self, title, text)

    def _remove_desktop_entry(self, title: str) -> None:
        """Delete what was written, then offer the AppImage's copy separately (decision 3)."""
        outcome = desktop_entry.remove()
        log.info("%s: %s", title, outcome.message())
        QMessageBox.information(self, title, outcome.message())
        self._offer_to_delete_appimage_copy(title)

    def _appimage_copy_choice(self, title: str) -> tuple[bool, str | None]:
        """Decision 3: where the AppImage's entry points, asked once, with a default.

        Returns whether to go on, and the ``Exec`` path to use in place of the running
        file. Every other form, and an AppImage already at the fixed name, is asked
        nothing.
        """
        running = desktop_entry.running_appimage()
        if running is None:
            return True, None
        destination = desktop_entry.appimage_destination()
        if running == destination:
            return True, None

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(
            f"{APP_NAME} can copy itself to {destination} ({_megabytes(running)}) and point "
            "the menu entry at the copy, so the entry keeps working if the file you are "
            "running now is moved or deleted."
        )
        copy_button = box.addButton("Copy and Add", QMessageBox.ButtonRole.AcceptRole)
        here_button = box.addButton("Add Without Copying", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(copy_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is here_button:
            return True, str(running)
        if clicked is not copy_button:
            return False, None
        try:
            copied = desktop_entry.copy_appimage(running, destination)
        except (OSError, ValueError) as error:
            QMessageBox.information(
                self, title, f"{destination} could not be written ({error}); nothing was copied."
            )
            return False, None
        return True, str(copied)

    def _offer_to_delete_appimage_copy(self, title: str) -> None:
        """The copy is named and deleted only on request, never silently (decision 3).

        Only the AppImage is asked: a copy at that path under any other form was put
        there by the user, not by this action, and is not ours to offer. The file the
        session is running from is named as left in place rather than offered, since
        deleting a mounted AppImage takes the running application's own files away.
        """
        running = desktop_entry.running_appimage()
        if running is None:
            return
        destination = desktop_entry.appimage_destination()
        if not destination.is_file():
            return
        if running == destination:
            QMessageBox.information(
                self,
                title,
                f"The copy at {destination} is the file you are running, so it is left "
                "in place. Delete it yourself, once Snapmockit is closed, if you no "
                "longer want it.",
            )
            return
        answer = QMessageBox.question(
            self,
            title,
            f"The copy at {destination} ({_megabytes(destination)}) is left in place. "
            "Delete it as well?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        try:
            destination.unlink()
        except OSError as error:
            QMessageBox.information(self, title, f"{destination} could not be deleted ({error}).")

    def offer_desktop_entry_once(self) -> None:
        """The one offer of menu-entry decision 1, on a first start with no entry.

        A message that does not block, with the action on it (General UI PRD 1.3); the
        Help menu row is the permanent route, so the offer is never made twice. A start
        that has already shown a startup message keeps that message and leaves the offer
        to the next start, since both use the one toast.
        """
        if self._startup_message_shown or self._settings.desktop_entry_offer_shown():
            return
        if desktop_entry.installed() or desktop_entry.unsupported_reason() is not None:
            return
        self._settings.set_desktop_entry_offer_shown(True)
        self._toast.show_message(
            f"{APP_NAME} is not in your desktop's menu.",
            "Add to Menu",
            self._help_menu_entry,
        )

    # ---- Help > Check for Updates (PRD 3.8; implementation notes Section 19) ----

    UPDATE_CHECK_TITLE = "Check for Updates"
    UPDATE_CHECK_HINT = "Checking for updates…"

    def _help_check_updates(self) -> None:
        """Query the GitHub releases API; the result comes back through the checker's signal."""
        if not self._require(
            self.UPDATE_CHECK_TITLE,
            (not self._update_checker.running, "the running check to finish"),
        ):
            return
        self.show_status_hint(self.UPDATE_CHECK_HINT)
        self._update_checker.start()

    def _on_update_check_finished(self, result: UpdateCheckResult) -> None:
        """Show one message for the outcome, then return the hint to the active tool's."""
        if result.outcome is Outcome.NETWORK_UNAVAILABLE:
            show_unmet_requirements(self, self.UPDATE_CHECK_TITLE, ["a network connection"])
        else:
            box = self._build_update_message(result)
            box.exec()
            box.deleteLater()
        self._on_tool_changed_for_hint("")

    FLATPAK_UPDATE_INSTRUCTION = (
        "Download the new .flatpak bundle from the release page and install it with "
        "flatpak install."
    )
    """What a newer release means inside a Flatpak (Flatpak decision 5): the release page
    carries one file per form, and a Flatpak user told to download the AppImage is sent to
    the wrong one. It becomes ``flatpak update`` once the Flathub step of decision 2 exists."""

    def update_message_text(self, result: UpdateCheckResult) -> str:
        """The message body for every outcome but network unavailable."""
        running = f"{APP_NAME} {result.running_version}"
        if result.outcome is Outcome.NEWER:
            found = f"{APP_NAME} {result.tag} is available. You are running {running}."
            if in_flatpak():
                return f"{found} {self.FLATPAK_UPDATE_INSTRUCTION}"
            # An installation from the index is upgraded by the tool that installed it,
            # not from the release page's files (PyPI decision 5).
            upgrade = upgrade_instruction()
            if upgrade is not None:
                return f"{found} {upgrade}"
            return found
        if result.outcome is Outcome.UP_TO_DATE:
            return f"{running} is up to date. The latest release is {result.tag}."
        if result.outcome is Outcome.NO_RELEASE:
            return f"No release has been published yet. You are running {running}."
        if result.outcome is Outcome.RATE_LIMITED:
            return "GitHub declined the request; try again later."
        return "The latest release could not be read. Try again later."

    def update_message_link(self, result: UpdateCheckResult) -> tuple[str, str] | None:
        """The button label and URL the message offers beside Close, if any."""
        if result.outcome is Outcome.NEWER and result.release_url:
            return "Open Release Page", result.release_url
        if result.outcome is Outcome.NO_RELEASE:
            return "Open Repository Page", REPOSITORY_URL
        return None

    def _build_update_message(self, result: UpdateCheckResult) -> QMessageBox:
        """An information box with Close and, for a release or none, a page button."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(self.UPDATE_CHECK_TITLE)
        box.setText(self.update_message_text(result))
        link = self.update_message_link(result)
        if link is not None:
            label, url = link
            button = box.addButton(label, QMessageBox.ButtonRole.ActionRole)
            if button is not None:
                button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        close = box.addButton(QMessageBox.StandardButton.Close)
        if close is not None:
            box.setDefaultButton(close)
            box.setEscapeButton(close)
        apply_default_names(box)
        return box

    def _help_about(self) -> None:
        from snapmock.ui.about_dialog import AboutDialog

        dlg = AboutDialog(self)
        dlg.exec()
        dlg.deleteLater()

    # ---- recent files ----

    def _add_recent_file(self, path: Path) -> None:
        recent = self._settings.recent_files()
        path_str = str(path.resolve())
        if path_str in recent:
            recent.remove(path_str)
        recent.insert(0, path_str)
        self._settings.set_recent_files(recent[: self._settings.recent_files_count()])
        self._update_recent_files_menu()

    def _update_recent_files_menu(self) -> None:
        if self._recent_menu is None:
            return
        self._recent_menu.clear()
        recent = self._settings.recent_files()
        if not recent:
            no_action = self._recent_menu.addAction("(No recent files)")
            if no_action is not None:
                no_action.triggered.connect(
                    lambda: self._require("Open Recent", (False, "a recently opened file"))
                )
            return
        for path_str in recent:
            action = self._recent_menu.addAction(Path(path_str).name)
            if action is not None:
                action.setToolTip(path_str)
                action.triggered.connect(
                    lambda _checked=False, p=path_str: self._open_project(Path(p))
                )
        self._recent_menu.addSeparator()
        clear = self._recent_menu.addAction("Clear Recent")
        if clear is not None:
            clear.triggered.connect(self._clear_recent_files)

    def _clear_recent_files(self) -> None:
        self._settings.set_recent_files([])
        self._update_recent_files_menu()

    # ---- autosave ----

    def _autosave(self) -> None:
        """Autosave every dirty non-library document that has a file."""
        for doc in self._documents.documents:
            if doc.is_library_file or doc.file_path is None or not doc.is_dirty:
                continue
            if doc.file_path.suffix.lower() != PROJECT_EXTENSION:
                continue
            try:
                save_project(doc.scene, doc.file_path)
            except Exception:  # noqa: BLE001
                pass  # Silent failure for autosave

    # ---- documents & tabs ----

    @property
    def _active_document(self) -> Document:
        doc = self._documents.active
        if doc is None:  # pragma: no cover - invariant: one document always open
            doc = Document(self._new_scene(), parent=self)
            self._documents.add(doc)
        return doc

    @property
    def _scene(self) -> SnapScene:
        return self._active_document.scene

    @property
    def _view(self) -> SnapView:
        return self._active_document.view

    @property
    def _selection_manager(self) -> SelectionManager:
        return self._active_document.selection_manager

    @property
    def _clipboard(self) -> ClipboardManager:
        return self._active_document.clipboard

    @property
    def _current_file(self) -> Path | None:
        return self._active_document.file_path

    def _configure_view(self, view: SnapView) -> None:
        """Apply shared UI state to a document's view."""
        view.set_tool_manager(self._tool_manager)
        view.cursor_moved.connect(self._status_bar.update_cursor_pos)
        view.set_grid_visible(self._settings.grid_visible())
        view.set_grid_size(self._settings.grid_size())
        view.set_rulers_visible(self._settings.rulers_visible())
        view.set_crosshairs_visible(self._settings.crosshairs_visible())
        view.set_guides_visible(self._settings.guides_visible())
        view.set_snap_to_guides(self._settings.snap_to_guides())
        view.set_guides_locked(self._settings.guides_locked())
        view.set_snap_to_grid(self._settings.snap_to_grid())
        self._apply_view_preferences(view)

    def _apply_view_preferences(self, view: SnapView) -> None:
        """Canvas appearance from Preferences > General, Appearance, Canvas & Grid."""
        s = self._settings
        view.set_pasteboard_color(s.pasteboard_color())
        view.set_checkerboard(s.checkerboard_size(), s.checkerboard_colors())
        view.set_grid_style(s.grid_color(), s.grid_opacity())
        view.set_pixel_grid_threshold(s.pixel_grid_zoom())
        view.set_snap_tolerance(s.snap_tolerance())
        view.set_guide_style(s.guide_color(), s.guide_opacity())

    def _load_tool_session(self) -> None:
        """Startup: the active theme into every tool, then the last-used values (PRD 15.4)."""
        self._tool_themes.load_session()
        self._property_panel.refresh_tool_defaults()
        self._tool_options.refresh()

    def _apply_tool_defaults(self) -> None:
        """Preferences > Tools changed: the Default theme's values (PRD 11.3, decision 7.2).

        The theme manager reaches the tools that are not overridden while Default is the
        active theme; a preset or a Custom edit is left alone.
        """
        self._tool_themes.preferences_changed()
        self._property_panel.refresh_tool_defaults()
        self._tool_options.refresh()

    def _wire_document(self, doc: Document) -> None:
        """Connect a document's signals to the window (once per document)."""
        if doc.tab_id in self._wired_docs:
            return
        self._wired_docs.add(doc.tab_id)
        doc.scene.command_stack.set_limit(self._settings.undo_limit())
        doc.scene.command_stack.stack_changed.connect(self._on_stack_changed)
        lm = doc.scene.layer_manager
        lm.layer_lock_changed.connect(self._on_layer_lock_changed)
        lm.layer_type_changed.connect(self._on_layer_type_changed)
        lm.layer_visibility_changed.connect(self._on_layer_visibility_changed)
        lm.active_layer_changed.connect(self._on_active_layer_changed)

    def _add_document(self, doc: Document, *, activate: bool = True) -> None:
        """Register a new document, replacing a pristine Untitled tab if present."""
        pristine = self._documents.active if self._is_pristine(self._documents.active) else None
        self._configure_view(doc.view)
        self._wire_document(doc)
        self._documents.add(doc, activate=activate)
        if pristine is not None and pristine is not doc and self._documents.count > 1:
            self._documents.remove(pristine)
            pristine.dispose()

    @staticmethod
    def _is_pristine(doc: Document | None) -> bool:
        """An unsaved, untouched Untitled document that can be replaced silently."""
        if doc is None:
            return False
        return (
            doc.file_path is None
            and not doc.is_library_file
            and doc.scene.command_stack.count == 0
            and not doc.scene.command_stack.is_dirty
        )

    def _on_active_document_changed(self, doc: Document | None) -> None:
        """Rebind the shared tool manager, panels and status bar to *doc*."""
        if doc is None:
            return
        prev_tool_id = self._tool_manager.active_tool_id or "select"
        active_tool = self._tool_manager.active_tool
        if active_tool is not None:
            active_tool.cancel()
            active_tool.deactivate()
        self._tool_manager._scene = doc.scene  # noqa: SLF001
        self._tool_manager._selection_manager = doc.selection_manager  # noqa: SLF001
        self._tool_manager.activate(prev_tool_id)
        # Panels are created after the first document; guard for construction order.
        if hasattr(self, "_layer_panel"):
            self._layer_panel.set_scene(doc.scene)
        if hasattr(self, "_property_panel"):
            self._property_panel.set_scene(doc.scene)
            self._property_panel.set_selection(doc.selection_manager)
        if hasattr(self, "_status_bar"):
            self._status_bar.set_document(doc)
        if hasattr(self, "_main_toolbar"):
            self._main_toolbar.set_view(doc.view)
            self._main_toolbar.set_selection_manager(doc.selection_manager)
        if hasattr(self, "_tool_options"):
            self._tool_options.set_selection_manager(doc.selection_manager)
        self._update_title()
        if hasattr(self, "_undo_action"):
            self._update_undo_redo_text()
        if hasattr(self, "_status_bar"):
            self._apply_tab_order()

    def _file_close_tab(self) -> None:
        self._close_document(self._active_document)

    def _close_document(self, doc: Document) -> bool:
        """Close *doc*, prompting to save if it has unsaved changes.

        Returns False if the user cancelled.
        """
        if not self._maybe_save_before_close(doc):
            return False
        self._remember_zoom(doc)
        self._library.detach_document(doc)
        if self._documents.count == 1:
            # Keep one document open at all times
            self._documents.add(Document(self._new_scene(), parent=self))
            self._configure_view(self._active_document.view)
            self._wire_document(self._active_document)
        self._documents.remove(doc)
        self._wired_docs.discard(doc.tab_id)
        doc.dispose()
        return True

    def _close_other_documents(self, keep: Document) -> None:
        for doc in self._documents.documents:
            if doc is not keep and not self._close_document(doc):
                return

    def _close_all_documents(self) -> None:
        for doc in self._documents.documents:
            if not self._close_document(doc):
                return

    def _close_documents_to_right(self, doc: Document) -> None:
        docs = self._documents.documents
        idx = self._documents.index_of(doc)
        for other in docs[idx + 1 :]:
            if not self._close_document(other):
                return

    def _maybe_save_before_close(self, doc: Document) -> bool:
        """The Unsaved Changes dialog (PRD 11.7): Save, Don't Save, Cancel."""
        if not doc.is_dirty:
            return True
        result = self._ask_unsaved_changes(doc.display_name, doc.scene)
        if result == QMessageBox.StandardButton.Cancel:
            return False
        if result == QMessageBox.StandardButton.Save:
            self._documents.set_active(doc)
            self._file_save()
            return not doc.is_dirty
        return True

    def _ask_unsaved_changes(
        self, name: str, scene: SnapScene | None = None
    ) -> QMessageBox.StandardButton:
        """The Section 11.7 dialog with the canvas preview; Cancel unless Save or Don't
        Save was clicked."""
        dialog = UnsavedChangesDialog(name, scene, self)
        dialog.exec()
        result = dialog.result_button()
        dialog.deleteLater()
        return result

    def _reveal_document_in_file_manager(self, doc: Document) -> None:
        if doc.file_path is None:
            QMessageBox.information(self, "Reveal", "This document has not been saved yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(doc.file_path.parent)))

    # ---- helpers ----

    def _on_stack_changed(self) -> None:
        self._update_title()
        self._update_undo_redo_text()

    def _update_undo_redo_text(self) -> None:
        """Undo [action] / Redo [action] follow the active document's stack (PRD 3.2)."""
        stack = self._scene.command_stack
        undo = stack.undo_text
        redo = stack.redo_text
        self._undo_action.setText(f"&Undo {undo}" if undo else "&Undo")
        self._redo_action.setText(f"&Redo {redo}" if redo else "&Redo")

    def _update_title(self) -> None:
        doc = self._active_document
        dirty = "*" if doc.is_dirty else ""
        self.setWindowTitle(f"{dirty}{doc.display_name} - {APP_NAME}")

    # ---- key event routing ----

    def _pan_to_corner(self, *, top_left: bool) -> None:
        """Home scrolls the canvas origin to the viewport corner; End its bottom-right corner."""
        view = self._view
        viewport = view.viewport()
        if viewport is None:
            return
        scale = view.zoom_percent / 100.0
        half_w = viewport.width() / 2.0 / scale
        half_h = viewport.height() / 2.0 / scale
        if top_left:
            view.centerOn(half_w, half_h)
        else:
            canvas = self._scene.canvas_size
            view.centerOn(canvas.width() - half_w, canvas.height() - half_h)

    def _space_held(self) -> bool:
        """Whether Space is currently held for temporary pan."""
        return self._tool_manager.previous_tool_id is not None

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802
        if event is None:
            super().keyPressEvent(event)
            return
        # Space-bar temporary pan override
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and not self._space_held():
            active = self._tool_manager.active_tool
            if active is None or not active.is_active_operation:
                self._tool_manager.activate_temporary("pan")
                event.accept()
                return

        # Alt held: momentary eyedropper (PRD 12.2), unless a drag is in progress
        if (
            event.key() == Qt.Key.Key_Alt
            and not event.isAutoRepeat()
            and self._momentary_tool is None
            and self._tool_manager.active_tool_id not in ("eyedropper", "pan", "zoom")
            # Alt+drag breaks a curve's continuity in point-editing mode (Basic Shape 9.7)
            and getattr(self._tool_manager.active_tool, "point_session", None) is None
            # Alt+paint erases in brush-editing mode (Blur PRD 2.8)
            and getattr(self._tool_manager.active_tool, "brush_session", None) is None
        ):
            active = self._tool_manager.active_tool
            if active is None or not active.is_active_operation:
                self._momentary_tool = "eyedropper"
                from_name = active.display_name if active is not None else None
                eyedropper = self._tool_manager.tool("eyedropper")
                if isinstance(eyedropper, EyedropperTool):
                    self._momentary_pick_serial = eyedropper.pick_serial
                self._tool_manager.activate_temporary("eyedropper")
                if isinstance(eyedropper, EyedropperTool):
                    # 4.7: the loupe appears on the key press, before any click, and the
                    # hint names the tool the colour is being picked for
                    eyedropper.set_momentary_from(from_name)
                    self._show_loupe_at_cursor(eyedropper)
                    eyedropper.show_hint()
                event.accept()
                return

        # Delegate to active tool
        if self._tool_manager.handle_key_press(event):
            event.accept()
            return

        key = event.key()

        # Home / End pan to the canvas corners (PRD 12.3)
        if key == Qt.Key.Key_Home:
            self._pan_to_corner(top_left=True)
            event.accept()
            return
        if key == Qt.Key.Key_End:
            self._pan_to_corner(top_left=False)
            event.accept()
            return

        # Arrow key viewport pan when no selection
        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            step = 100 if shift else 20
            h_bar = self._view.horizontalScrollBar()
            v_bar = self._view.verticalScrollBar()
            if key == Qt.Key.Key_Left and h_bar is not None:
                h_bar.setValue(h_bar.value() - step)
            elif key == Qt.Key.Key_Right and h_bar is not None:
                h_bar.setValue(h_bar.value() + step)
            elif key == Qt.Key.Key_Up and v_bar is not None:
                v_bar.setValue(v_bar.value() - step)
            elif key == Qt.Key.Key_Down and v_bar is not None:
                v_bar.setValue(v_bar.value() + step)
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            super().keyReleaseEvent(event)
            return
        # Space-bar release → restore previous tool
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self._space_held():
            self._tool_manager.restore_previous()
            event.accept()
            return
        # Alt release → back from the momentary eyedropper
        if event.key() == Qt.Key.Key_Alt and not event.isAutoRepeat() and self._momentary_tool:
            self._momentary_tool = None
            eyedropper = self._tool_manager.tool("eyedropper")
            if isinstance(eyedropper, EyedropperTool):
                # 4.7: a preview with no click leaves everything as it was
                eyedropper.set_momentary_from(None)
                eyedropper.hide_loupe()
            self._tool_manager.restore_previous()
            self._apply_momentary_pick()
            event.accept()
            return

        # Delegate to active tool
        if self._tool_manager.handle_key_release(event):
            event.accept()
            return

        super().keyReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Prompt for unsaved documents, then save window geometry and state.

        With Keep Running in Tray on and a tray icon present, closing hides the
        window instead and global hotkeys keep working (PRD 3.2).
        """
        keep_running = (
            self._primary_capture
            and self._tray is not None
            and self._settings.capture_keep_running_in_tray()
            and not self._quit_requested
        )
        if keep_running:
            self._save_window_state()
            self._hidden_in_tray = True
            self.hide()
            if event is not None:
                event.ignore()
            return
        for doc in self._documents.documents:
            if doc.is_dirty:
                self._documents.set_active(doc)
                if not self._maybe_save_before_close(doc):
                    if event is not None:
                        event.ignore()
                    return
        self._library.flush()
        self._library.purge_session_trash()
        self._save_session()
        self._save_window_state()
        if self._primary_capture:
            self._teardown_tray()
            self._capture.shutdown()
        super().closeEvent(event)

    # ---- properties ----

    @property
    def scene(self) -> SnapScene:
        return self._scene

    @property
    def view(self) -> SnapView:
        return self._view

    @property
    def selection_manager(self) -> SelectionManager:
        return self._selection_manager

    @property
    def tool_manager(self) -> ToolManager:
        return self._tool_manager

    @property
    def clipboard(self) -> ClipboardManager:
        return self._clipboard

    @property
    def documents(self) -> DocumentManager:
        return self._documents

    @property
    def library(self) -> LibraryManager:
        return self._library

    @property
    def library_panel(self) -> LibraryPanel:
        return self._library_panel

    @property
    def active_document(self) -> Document:
        return self._active_document
