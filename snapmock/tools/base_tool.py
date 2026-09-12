"""BaseTool — abstract base class for all interactive tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QContextMenuEvent, QCursor, QKeyEvent, QMouseEvent

from snapmock.ui.unmet_requirements import check_requirements

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem, QToolBar

    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager
    from snapmock.core.view import SnapView


class BaseTool(ABC):
    """Abstract base for all drawing/editing tools.

    Subclasses override mouse/key handlers and return ``True`` if the
    event was consumed.
    """

    options_controls: tuple[str, ...] = ()
    """Shared Tool Options Bar controls, in order (General UI PRD 5.2, 5.3).

    Each entry names a control the bar builds once and binds to the key of the
    same name in :attr:`creation_defaults`; ``"tool"`` marks where the tool's
    own :meth:`build_options_widgets` widgets go (default: after the shared set).
    """

    def __init__(self) -> None:
        self._scene: SnapScene | None = None
        self._selection_manager: SelectionManager | None = None
        self._creation_defaults: dict[str, Any] = {}
        self._preview_item: QGraphicsItem | None = None

    @property
    def creation_defaults(self) -> dict[str, Any]:
        """Mutable dict of default property values applied to newly created items.

        PropertyPanel can read/write this dict to let users pre-configure
        properties before creating items.
        """
        return self._creation_defaults

    # --- identity ---

    @property
    @abstractmethod
    def tool_id(self) -> str:
        """Unique string identifier for this tool."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for toolbar/tooltip."""

    @property
    def cursor(self) -> Qt.CursorShape | QCursor:
        """Cursor to display when this tool is active (General UI PRD 6.6)."""
        return Qt.CursorShape.ArrowCursor

    # --- lifecycle ---

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        """Called when this tool becomes the active tool."""
        self._scene = scene
        self._selection_manager = selection_manager

    def deactivate(self) -> None:
        """Called when another tool replaces this one."""
        self._scene = None
        self._selection_manager = None

    def cancel(self) -> None:
        """Clean teardown of any in-progress operation.

        Called when the tool is switched away or when Escape is pressed.
        Drops the drawing preview, if there is one (Basic Shape PRD 2.3's Escape
        row); subclasses with an operation of their own override and extend this.
        """
        self._end_preview()

    # --- properties ---

    @property
    def is_active_operation(self) -> bool:
        """Whether the tool has an active drag/operation in progress.

        When True, Space-bar pan override is suppressed so the tool keeps
        receiving events, and the momentary Alt eyedropper stands down.
        True while a drawing preview is in the scene; subclasses whose operation
        is not a preview item override this.
        """
        return self._preview_item is not None

    # --- the shared drawing lifecycle (Basic Shape PRD 2.1, 2.3) ---

    def _window(self) -> Any:
        """The main window, for a message box or a status hint; None without a view."""
        view = self._view
        return view.window() if view is not None else None

    def layer_allows_drawing(self) -> bool:
        """Whether the active layer takes a new item (Basic Shape PRD 2.1).

        A press on a locked or a hidden layer is refused, and the never-disabled
        message of General UI PRD 1.3 names what is missing rather than any control
        being greyed out. Every drawing tool calls this from :meth:`mouse_press`, so
        the rule and its wording live in one place and not one copy per tool.
        """
        if self._scene is None:
            return False
        layer = self._scene.layer_manager.active_layer
        if layer is None:
            return False
        return check_requirements(
            self._window(),
            self.display_name,
            [
                (not layer.locked, "an unlocked active layer"),
                (layer.visible, "a visible active layer"),
            ],
        )

    def _start_preview(self, item: QGraphicsItem) -> None:
        """Put *item* in the scene as the drawing preview (Basic Shape PRD 2.1).

        The preview is a scene item and never joins the active layer's item list,
        which is what 2.1 calls the scene's item collection, so an abandoned drag
        leaves nothing behind an undo. It is dropped by :meth:`cancel` and taken by
        :meth:`_end_preview` when the drag finishes.
        """
        if self._scene is None:
            return
        self._preview_item = item
        self._scene.addItem(item)

    def _end_preview(self) -> None:
        """Take the drawing preview out of the scene, if there is one."""
        item = self._preview_item
        self._preview_item = None
        if item is not None and self._scene is not None and item.scene() is not None:
            self._scene.removeItem(item)

    @property
    def _view(self) -> SnapView | None:
        """Convenience accessor for the first view attached to the scene."""
        if self._scene is not None and self._scene.views():
            return self._scene.views()[0]  # type: ignore[return-value]
        return None

    def _snap_pos(self, pos: QPointF) -> QPointF:
        """*pos* snapped to the grid and guides as the View toggles say (PRD 6.5)."""
        view = self._view
        return view.snap_point(pos) if view is not None else pos

    def _switch_to_select(self) -> None:
        """Switch to the select tool via the view's tool manager."""
        view = self._view
        if view is not None:
            main_window = view.window()
            if main_window is not None and hasattr(main_window, "tool_manager"):
                main_window.tool_manager.activate("select")

    # --- event handlers (return True if consumed) ---

    def mouse_press(self, event: QMouseEvent) -> bool:
        return False

    def mouse_move(self, event: QMouseEvent) -> bool:
        return False

    def mouse_release(self, event: QMouseEvent) -> bool:
        return False

    def mouse_double_click(self, event: QMouseEvent) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        """Handle a key press event. Return True if consumed."""
        return False

    def key_release(self, event: QKeyEvent) -> bool:
        """Handle a key release event. Return True if consumed."""
        return False

    def handle_escape(self) -> bool:
        """Escape reached the window (the Edit > Deselect shortcut): end the tool's own
        operation in progress and return True, or return False to let Deselect run.

        A drawing operation is cancelled and its preview dropped (Basic Shape PRD 2.3).
        The Select tool leaves point-editing mode; the Arc and Polygon tools cancel the
        shape being drawn (Basic Shape PRD 7.2, 8.2)."""
        if self._preview_item is None:
            return False
        self.cancel()
        return True

    # --- context menu ---

    def context_menu(self, event: QContextMenuEvent) -> bool:
        """Handle a context menu event. Return True if consumed."""
        return False

    # --- status hint ---

    @property
    def status_hint(self) -> str:
        """Contextual hint for the status bar."""
        return ""

    # --- options bar ---

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """Populate *toolbar* with per-tool option widgets.

        Called each time this tool is activated.  Default does nothing.
        """

    def on_option_changed(self, key: str, value: Any) -> None:
        """A shared control wrote *value* to ``creation_defaults[key]``.

        Tools that also apply the value somewhere live (the text tool's editor,
        the numbered step counter) override this. Default does nothing.
        """
