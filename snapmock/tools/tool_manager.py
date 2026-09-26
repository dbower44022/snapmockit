"""ToolManager — registry and active-tool switching."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent

from snapmock.tools.base_tool import BaseTool

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager


class ToolManager(QObject):
    """Manages the tool registry and delegates events to the active tool.

    Signals
    -------
    tool_changed(str)
        Emitted with the tool_id of the newly activated tool.
    tool_defaults_changed(str)
        Emitted with a tool_id after one of its ``creation_defaults`` was edited
        by a UI surface (Tool Options Bar, Property Panel, Preferences), so the
        other surfaces re-read it (General UI PRD 5.1, 8.5).
    """

    tool_changed = pyqtSignal(str)
    tool_defaults_changed = pyqtSignal(str)

    def __init__(
        self,
        scene: SnapScene,
        selection_manager: SelectionManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._selection_manager = selection_manager
        self._tools: dict[str, BaseTool] = {}
        self._active_tool: BaseTool | None = None
        self._previous_tool_id: str | None = None
        self._last_tool_id: str | None = None

    # --- registration ---

    def register(self, tool: BaseTool) -> None:
        """Register a tool by its tool_id."""
        self._tools[tool.tool_id] = tool

    def tool(self, tool_id: str) -> BaseTool | None:
        return self._tools.get(tool_id)

    @property
    def tool_ids(self) -> list[str]:
        return list(self._tools.keys())

    @property
    def selection_manager(self) -> SelectionManager:
        """The selection every tool is activated with."""
        return self._selection_manager

    # --- activation ---

    @property
    def active_tool(self) -> BaseTool | None:
        return self._active_tool

    @property
    def active_tool_id(self) -> str:
        if self._active_tool is not None:
            return self._active_tool.tool_id
        return ""

    @property
    def previous_tool_id(self) -> str | None:
        """The tool a temporary activation will return to: the Space-bar pan's and the
        momentary eyedropper's."""
        return self._previous_tool_id

    @property
    def last_tool_id(self) -> str | None:
        """The tool that was active before the current one, by whatever route — what Blur
        PRD 4.6 calls the previously active tool."""
        return self._last_tool_id

    def activate(self, tool_id: str) -> None:
        """Switch to the tool identified by *tool_id*."""
        tool = self._tools.get(tool_id)
        if tool is None:
            return
        if self._active_tool is not None and self._active_tool.tool_id != tool_id:
            self._last_tool_id = self._active_tool.tool_id
        if self._active_tool is not None:
            self._active_tool.cancel()
            self._active_tool.deactivate()
        self._active_tool = tool
        tool.activate(self._scene, self._selection_manager)
        self.tool_changed.emit(tool_id)

    def activate_temporary(self, tool_id: str) -> None:
        """Temporarily switch to *tool_id*, remembering the current tool.

        Used for Space-bar pan override.  Call :meth:`restore_previous` to
        return to the original tool.
        """
        if self._active_tool is not None:
            self._previous_tool_id = self._active_tool.tool_id
        self.activate(tool_id)

    def restore_previous(self) -> None:
        """Restore the tool that was active before :meth:`activate_temporary`."""
        if self._previous_tool_id is not None:
            self.activate(self._previous_tool_id)
            self._previous_tool_id = None

    # --- event delegation ---

    def handle_mouse_press(self, event: QMouseEvent) -> bool:
        if self._active_tool is not None:
            return self._active_tool.mouse_press(event)
        return False

    def handle_mouse_move(self, event: QMouseEvent) -> bool:
        if self._active_tool is not None:
            return self._active_tool.mouse_move(event)
        return False

    def handle_mouse_release(self, event: QMouseEvent) -> bool:
        if self._active_tool is not None:
            return self._active_tool.mouse_release(event)
        return False

    def handle_mouse_double_click(self, event: QMouseEvent) -> bool:
        if self._active_tool is not None:
            return self._active_tool.mouse_double_click(event)
        return False

    def handle_key_press(self, event: QKeyEvent) -> bool:
        """Delegate key press to the active tool."""
        if self._active_tool is not None:
            return self._active_tool.key_press(event)
        return False

    def handle_key_release(self, event: QKeyEvent) -> bool:
        """Delegate key release to the active tool."""
        if self._active_tool is not None:
            return self._active_tool.key_release(event)
        return False

    def handle_context_menu(self, event: QContextMenuEvent) -> bool:
        """Delegate context menu to the active tool."""
        if self._active_tool is not None:
            return self._active_tool.context_menu(event)
        return False
