"""TextTool — click to place or drag to define a text box, click existing text to edit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QGraphicsRectItem,
    QTextEdit,
    QToolBar,
    QToolButton,
)

from snapmock.commands.add_item import AddItemCommand
from snapmock.commands.remove_item import RemoveItemCommand
from snapmock.commands.text_edit_command import TextEditCommand
from snapmock.config.constants import (
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_LINE_SPACING,
    DEFAULT_TEXT_BG_COLOR,
    DEFAULT_TEXT_BORDER_COLOR,
    DEFAULT_TEXT_BORDER_RADIUS,
    DEFAULT_TEXT_BORDER_WIDTH,
    DEFAULT_TEXT_PADDING,
    DEFAULT_TEXT_WIDTH,
    MIN_DRAG_TEXT_BOX,
    BorderStyle,
    VerticalAlign,
)
from snapmock.core.theme_manager import current_theme
from snapmock.items.callout_item import CalloutItem
from snapmock.items.text_item import TextItem
from snapmock.tools.base_tool import BaseTool
from snapmock.ui.cursors import text_hover_cursor
from snapmock.ui.find_replace_bar import FindReplaceBar

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager

# Items that support inline text editing
_TextLike = TextItem | CalloutItem


class _RichTextEditor(QTextEdit):
    """QTextEdit subclass that intercepts formatting shortcuts during editing."""

    editing_finished = pyqtSignal()
    find_requested = pyqtSignal()
    replace_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return

        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        if key == Qt.Key.Key_Escape:
            self.editing_finished.emit()
            return

        if ctrl and not shift:
            if key == Qt.Key.Key_B:
                self._toggle_bold()
                return
            if key == Qt.Key.Key_I:
                self._toggle_italic()
                return
            if key == Qt.Key.Key_U:
                self._toggle_underline()
                return
            if key == Qt.Key.Key_L:
                self._set_alignment(Qt.AlignmentFlag.AlignLeft)
                return
            if key == Qt.Key.Key_E:
                self._set_alignment(Qt.AlignmentFlag.AlignCenter)
                return
            if key == Qt.Key.Key_R:
                self._set_alignment(Qt.AlignmentFlag.AlignRight)
                return
            if key == Qt.Key.Key_J:
                self._set_alignment(Qt.AlignmentFlag.AlignJustify)
                return
            if key == Qt.Key.Key_V:
                # Plain-text paste (strip formatting)
                self._paste_plain()
                return
            if key == Qt.Key.Key_F:
                self.find_requested.emit()
                return
            if key == Qt.Key.Key_H:
                self.replace_requested.emit()
                return

        if ctrl and shift:
            if key == Qt.Key.Key_X:
                self._toggle_strikethrough()
                return
            if key == Qt.Key.Key_Period:
                self._change_font_size(1)
                return
            if key == Qt.Key.Key_Comma:
                self._change_font_size(-1)
                return
            if key == Qt.Key.Key_Equal:
                self._toggle_superscript()
                return
            if key == Qt.Key.Key_V:
                # Rich-text paste (preserve formatting)
                self._paste_rich()
                return

        if ctrl and not shift and key == Qt.Key.Key_Equal:
            self._toggle_subscript()
            return

        if key == Qt.Key.Key_Tab:
            self.textCursor().insertText("    ")
            return

        # Shift+Enter → soft line break
        if shift and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.textCursor().insertText("\n")
            return

        super().keyPressEvent(event)

    def _toggle_bold(self) -> None:
        fmt = QTextCharFormat()
        cur = self.textCursor().charFormat()
        is_bold = cur.fontWeight() >= QFont.Weight.Bold
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self.textCursor().mergeCharFormat(fmt)

    def _toggle_italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.textCursor().charFormat().fontItalic())
        self.textCursor().mergeCharFormat(fmt)

    def _toggle_underline(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self.textCursor().charFormat().fontUnderline())
        self.textCursor().mergeCharFormat(fmt)

    def _toggle_strikethrough(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not self.textCursor().charFormat().fontStrikeOut())
        self.textCursor().mergeCharFormat(fmt)

    def _set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        self.setAlignment(alignment)

    def _change_font_size(self, delta: int) -> None:
        fmt = QTextCharFormat()
        cur_size = self.textCursor().charFormat().font().pointSize()
        new_size = max(1, cur_size + delta)
        fmt.setFontPointSize(float(new_size))
        self.textCursor().mergeCharFormat(fmt)

    def _toggle_superscript(self) -> None:
        fmt = QTextCharFormat()
        cur = self.textCursor().charFormat()
        if cur.verticalAlignment() == QTextCharFormat.VerticalAlignment.AlignSuperScript:
            fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
        else:
            fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
        self.textCursor().mergeCharFormat(fmt)

    def _toggle_subscript(self) -> None:
        fmt = QTextCharFormat()
        cur = self.textCursor().charFormat()
        if cur.verticalAlignment() == QTextCharFormat.VerticalAlignment.AlignSubScript:
            fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
        else:
            fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
        self.textCursor().mergeCharFormat(fmt)

    def _paste_plain(self) -> None:
        """Paste clipboard content as plain text, using current cursor format."""
        from PyQt6.QtWidgets import QApplication as QApp

        clipboard = QApp.clipboard()
        if clipboard is None:
            return
        text = clipboard.text()
        if text:
            self.textCursor().insertText(text)

    def _paste_rich(self) -> None:
        """Paste clipboard content preserving rich-text formatting."""
        from PyQt6.QtWidgets import QApplication as QApp

        clipboard = QApp.clipboard()
        if clipboard is None:
            return
        mime = clipboard.mimeData()
        if mime is None:
            return
        if mime.hasHtml():
            html = mime.html()
            # Sanitize: strip scripts and iframes
            import re

            html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r"<iframe[^>]*>.*?</iframe>", "", html, flags=re.DOTALL | re.IGNORECASE)
            self.textCursor().insertHtml(html)
        elif mime.hasText():
            self.textCursor().insertText(mime.text())


class TextTool(BaseTool):
    """Click to place text, drag to define a text box, or click existing text to edit."""

    # Tool Options Bar (General UI PRD 5.3, Text PRD 3.5): shared controls, with the
    # tool's own alignment buttons ("tool") between the text colour and the box controls.
    options_controls = (
        "font_family",
        "font_size",
        "text_style",
        "text_color",
        "tool",
        "bg_color",
        "border_color",
        "border_width",
        "border_style",
    )

    def __init__(self) -> None:
        super().__init__()
        self._editing_item: _TextLike | None = None
        self._editor: _RichTextEditor | None = None
        self._find_bar: FindReplaceBar | None = None
        self._old_html: str = ""
        # Drag-to-create state
        self._drag_start: QPointF | None = None
        self._drag_preview: QGraphicsRectItem | None = None
        self._is_dragging: bool = False
        # Creation defaults (pre-configurable via PropertyPanel)
        self._creation_defaults = {
            "font_family": DEFAULT_FONT_FAMILY,
            "font_size": DEFAULT_FONT_SIZE,
            "bold": False,
            "italic": False,
            "underline": False,
            "text_color": QColor(Qt.GlobalColor.black),
            "bg_color": QColor(DEFAULT_TEXT_BG_COLOR),
            "border_color": QColor(DEFAULT_TEXT_BORDER_COLOR),
            "border_width": DEFAULT_TEXT_BORDER_WIDTH,
            "border_style": BorderStyle.SOLID,
            "fill_opacity": 1.0,
            "stroke_opacity": 1.0,
            "line_spacing": DEFAULT_LINE_SPACING,
            "border_radius": DEFAULT_TEXT_BORDER_RADIUS,
            "padding": DEFAULT_TEXT_PADDING,
            "vertical_align": VerticalAlign.TOP,
            "horizontal_align": Qt.AlignmentFlag.AlignLeft,
            "auto_size": True,
        }

    @property
    def tool_id(self) -> str:
        return "text"

    @property
    def display_name(self) -> str:
        return "Text"

    @property
    def cursor(self) -> Qt.CursorShape:
        return Qt.CursorShape.IBeamCursor

    @property
    def status_hint(self) -> str:
        if self._editing_item is not None:
            return (
                "Type to edit | Ctrl+B/I/U: format | Escape to finish | Click elsewhere to finish"
            )
        return "Click to place text | Drag to define text box | Click existing text to edit"

    @property
    def active_editor(self) -> _RichTextEditor | None:
        """The active editor widget, if currently editing. Used by PropertyPanel."""
        return self._editor

    @property
    def editing_item(self) -> _TextLike | None:
        """The item currently being edited, if any."""
        return self._editing_item

    @property
    def is_active_operation(self) -> bool:
        """True when dragging or editing."""
        return self._is_dragging or self._editing_item is not None

    def build_options_widgets(self, toolbar: QToolBar) -> None:
        """Text Alignment (Text PRD 3.5); the font, style, colour and box controls are shared."""
        self._opt_align_buttons: dict[Qt.AlignmentFlag, QToolButton] = {}
        for align, label, tip in (
            (Qt.AlignmentFlag.AlignLeft, "L", "Align Left (Ctrl+L)"),
            (Qt.AlignmentFlag.AlignCenter, "C", "Align Center (Ctrl+E)"),
            (Qt.AlignmentFlag.AlignRight, "R", "Align Right (Ctrl+R)"),
            (Qt.AlignmentFlag.AlignJustify, "J", "Justify (Ctrl+J)"),
        ):
            btn = QToolButton()
            btn.setText(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setToolTip(tip)
            btn.setFixedSize(26, 26)
            btn.clicked.connect(lambda checked, a=align: self._on_opt_align(a))
            toolbar.addWidget(btn)
            self._opt_align_buttons[align] = btn
        current = self._creation_defaults.get("horizontal_align", Qt.AlignmentFlag.AlignLeft)
        if isinstance(current, Qt.AlignmentFlag) and current in self._opt_align_buttons:
            self._opt_align_buttons[current].setChecked(True)

    def on_option_changed(self, key: str, value: object) -> None:
        """A shared control changed: while editing, apply it to the selection too (PRD 3.5)."""
        if self._editor is None:
            return
        fmt = QTextCharFormat()
        if key == "font_family":
            fmt.setFontFamilies([str(value)])
        elif key == "font_size":
            fmt.setFontPointSize(float(value))  # type: ignore[arg-type]
        elif key == "bold":
            fmt.setFontWeight(QFont.Weight.Bold if value else QFont.Weight.Normal)
        elif key == "italic":
            fmt.setFontItalic(bool(value))
        elif key == "underline":
            fmt.setFontUnderline(bool(value))
        elif key == "text_color" and isinstance(value, QColor):
            fmt.setForeground(value)
        else:
            return
        self._editor.textCursor().mergeCharFormat(fmt)

    def _on_opt_align(self, alignment: Qt.AlignmentFlag) -> None:
        if self._editor is not None:
            self._editor.setAlignment(alignment)
        else:
            self._creation_defaults["horizontal_align"] = alignment

    def activate(self, scene: SnapScene, selection_manager: SelectionManager) -> None:
        super().activate(scene, selection_manager)
        # If activated with a text item already selected (e.g. double-click from select tool),
        # start editing it immediately.
        if self._selection_manager is not None:
            for item in self._selection_manager.items:
                if isinstance(item, (TextItem, CalloutItem)):
                    self._start_editing(item)
                    break

    def deactivate(self) -> None:
        self._cleanup_drag()
        self._finish_editing()
        view = self._view
        if view is not None:
            view.set_hover_cursor(None)
        super().deactivate()

    def cancel(self) -> None:
        self._cleanup_drag()
        self._finish_editing()

    def mouse_press(self, event: QMouseEvent) -> bool:
        if self._scene is None or event.button() != Qt.MouseButton.LeftButton:
            return False

        view = self._view
        if view is None:
            return False

        scene_pos = view.mapToScene(event.pos())

        # Check if clicking on an existing text-like item
        clicked_item = self._text_item_at(scene_pos)

        if clicked_item is not None and clicked_item is self._editing_item:
            # Clicking inside the item we're already editing — let the editor handle it
            return False

        # Finish any current editing first
        self._finish_editing()

        if clicked_item is not None:
            # Edit existing text item
            self._start_editing(clicked_item)
        else:
            # Start potential drag-to-create
            self._drag_start = scene_pos
            self._is_dragging = False
            # Create a dashed-blue preview rectangle
            preview = QGraphicsRectItem()
            pen = QPen(QColor("#0078d7"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview.setPen(pen)
            preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            preview.setRect(QRectF(scene_pos, scene_pos))
            self._scene.addItem(preview)
            self._drag_preview = preview
        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        view = self._view
        if view is None or self._scene is None:
            return False
        if self._drag_start is None or self._drag_preview is None:
            if self._editing_item is None:
                self._update_hover_cursor(view.mapToScene(event.pos()))
            return False

        current = view.mapToScene(event.pos())
        rect = QRectF(self._drag_start, current).normalized()
        self._drag_preview.setRect(rect)

        # Set _is_dragging once past threshold
        if not self._is_dragging:
            dx = abs(current.x() - self._drag_start.x())
            dy = abs(current.y() - self._drag_start.y())
            if dx > MIN_DRAG_TEXT_BOX or dy > MIN_DRAG_TEXT_BOX:
                self._is_dragging = True

        return True

    def _apply_creation_defaults(self, item: TextItem) -> None:
        """Apply user-configured creation defaults to a newly constructed item."""
        d = self._creation_defaults
        font = QFont(d.get("font_family", DEFAULT_FONT_FAMILY))
        font.setPointSize(d.get("font_size", DEFAULT_FONT_SIZE))
        font.setBold(d.get("bold", False))
        font.setItalic(d.get("italic", False))
        font.setUnderline(d.get("underline", False))
        item.font = font
        item.text_color = QColor(d.get("text_color", QColor(Qt.GlobalColor.black)))
        item.bg_color = QColor(d.get("bg_color", QColor(DEFAULT_TEXT_BG_COLOR)))
        item.border_color = QColor(d.get("border_color", QColor(DEFAULT_TEXT_BORDER_COLOR)))
        item.border_width = d.get("border_width", DEFAULT_TEXT_BORDER_WIDTH)
        style = d.get("border_style", BorderStyle.SOLID)
        item.border_style = style if isinstance(style, BorderStyle) else BorderStyle.SOLID
        item.border_radius = d.get("border_radius", DEFAULT_TEXT_BORDER_RADIUS)
        item.fill_opacity = float(d.get("fill_opacity", 1.0))
        item.stroke_opacity = float(d.get("stroke_opacity", 1.0))
        item.line_spacing = float(d.get("line_spacing", DEFAULT_LINE_SPACING))
        item.padding = d.get("padding", DEFAULT_TEXT_PADDING)
        item.vertical_align = d.get("vertical_align", VerticalAlign.TOP)
        ha = d.get("horizontal_align", Qt.AlignmentFlag.AlignLeft)
        if isinstance(ha, Qt.AlignmentFlag):
            item.set_alignment(ha)
        item.auto_size = d.get("auto_size", True)

    def mouse_release(self, event: QMouseEvent) -> bool:
        if self._drag_start is None or self._scene is None:
            return False

        view = self._view
        if view is None:
            self._cleanup_drag()
            return False

        scene_pos = view.mapToScene(event.pos())

        # Remove preview
        self._cleanup_drag_preview()

        if (
            self._is_dragging
            and abs(scene_pos.x() - self._drag_start.x()) >= MIN_DRAG_TEXT_BOX
            and abs(scene_pos.y() - self._drag_start.y()) >= MIN_DRAG_TEXT_BOX
        ):
            # Drag-to-create: set drawn dimensions as minimums, auto-size enabled
            rect = QRectF(self._drag_start, scene_pos).normalized()
            item = TextItem(text="", pos_x=rect.x(), pos_y=rect.y())
            self._apply_creation_defaults(item)
            item._width = rect.width()
            item._auto_size = True
            item._auto_width = True
            item._min_width = rect.width()
            item._min_height = rect.height()
            layer = self._scene.layer_manager.active_layer
            if layer is not None:
                cmd = AddItemCommand(self._scene, item, layer.layer_id)
                self._scene.command_stack.push(cmd)
                self._start_editing(item)
        else:
            # Simple click: place new text item with auto-size
            click_pos = self._drag_start
            item = TextItem(text="", pos_x=click_pos.x(), pos_y=click_pos.y())
            self._apply_creation_defaults(item)
            item._min_width = DEFAULT_TEXT_WIDTH
            layer = self._scene.layer_manager.active_layer
            if layer is not None:
                cmd = AddItemCommand(self._scene, item, layer.layer_id)
                self._scene.command_stack.push(cmd)
                self._start_editing(item)

        # Reset drag state
        self._drag_start = None
        self._is_dragging = False
        return True

    def handle_escape(self) -> bool:
        """Escape reaches the window as Edit > Deselect's shortcut before the editor sees
        it, so editing ends here (Text PRD 2.4; end-to-end pass finding 15)."""
        if self._editor is None:
            return super().handle_escape()
        self._finish_editing()
        return True

    def key_press(self, event: QKeyEvent) -> bool:
        if self._editor is not None:
            if event.key() == Qt.Key.Key_Escape:
                self._finish_editing()
                return True
            # Let the editor widget handle all other keys
            return False
        return False

    def _update_hover_cursor(self, scene_pos: QPointF) -> None:
        """PRD 6.6: the highlighted I-beam over an existing text item, forbidden over one
        on a locked layer, the plain I-beam elsewhere."""
        view = self._view
        if view is None or self._scene is None:
            return
        if self._text_item_at(scene_pos) is not None:
            view.set_hover_cursor(text_hover_cursor())
            return
        for gitem in self._scene.items(scene_pos):
            if isinstance(gitem, (TextItem, CalloutItem)) and gitem.parentItem() is None:
                layer = self._scene.layer_manager.layer_by_id(gitem.layer_id)
                if layer is not None and layer.locked and layer.visible:
                    view.set_hover_cursor(Qt.CursorShape.ForbiddenCursor)
                    return
        view.set_hover_cursor(None)

    def _text_item_at(self, scene_pos: QPointF) -> _TextLike | None:
        """Find a top-level TextItem or CalloutItem under the given scene position.

        A group's member is not found: its text is edited after Ungroup (General UI
        PRD 3.6, Group and Ungroup kickoff silence 1).
        """
        if self._scene is None:
            return None
        for gitem in self._scene.items(scene_pos):
            if isinstance(gitem, (TextItem, CalloutItem)) and gitem.parentItem() is None:
                layer = self._scene.layer_manager.layer_by_id(gitem.layer_id)
                if layer is not None and (layer.locked or not layer.visible):
                    continue
                return gitem
        return None

    def _cleanup_drag_preview(self) -> None:
        """Remove the drag preview rect from the scene."""
        if self._drag_preview is not None:
            if self._scene is not None:
                self._scene.removeItem(self._drag_preview)
            self._drag_preview = None

    def _cleanup_drag(self) -> None:
        """Clean up all drag state."""
        self._cleanup_drag_preview()
        self._drag_start = None
        self._is_dragging = False

    def _start_editing(self, item: _TextLike) -> None:
        """Show a rich text editor overlay on the item."""
        view = self._view
        if view is None:
            return
        viewport = view.viewport()
        if viewport is None:
            return

        self._editing_item = item
        self._old_html = item.html()
        item.is_editing = True

        # Ensure the item is selected so PropertyPanel can show/edit its properties
        if self._selection_manager is not None:
            self._selection_manager.select_items([item])

        # Hide the item's painted text by making it invisible during editing
        item.setOpacity(0.0)

        # Create the editor as a child of the viewport
        editor = _RichTextEditor(viewport)
        self._editor = editor

        # Hide scrollbars — the text box auto-sizes, so scrollbars are never needed
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Share the item's document — edits go directly to the item
        editor.setDocument(item.text_document)

        # Disable word wrapping in the editor during edit mode (auto_width)
        if isinstance(item, TextItem) and item.auto_width:
            editor.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        # Enable document undo for per-keystroke Ctrl+Z during editing
        item.text_document.setUndoRedoEnabled(True)
        item.text_document.clearUndoRedoStacks()

        # Connect contentsChanged for auto-size
        item.text_document.contentsChanged.connect(self._on_document_changed)

        # Style the editor
        editor.setStyleSheet(
            "_RichTextEditor {"
            "  background: rgba(255, 255, 255, 200);"
            f"  border: 1px solid {current_theme().accent.name()};"
            "  padding: 0px;"
            "}"
        )

        # Position and size the editor to match the item in viewport coordinates
        self._reposition_editor()

        # Select all text
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        editor.setTextCursor(cursor)

        editor.editing_finished.connect(self._finish_editing)
        editor.find_requested.connect(self._show_find)
        editor.replace_requested.connect(self._show_find_replace)
        editor.show()
        editor.setFocus()

    def _reposition_editor(self) -> None:
        """Position the editor widget over the text item in viewport coordinates."""
        if self._editor is None or self._editing_item is None:
            return
        view = self._view
        if view is None:
            return
        item = self._editing_item

        # Map item bounding rect to viewport coordinates
        scene_rect = item.mapToScene(item.boundingRect())
        view_polygon = view.mapFromScene(scene_rect)
        view_rect = view_polygon.boundingRect()

        # Ensure minimum size for the editor
        min_w = max(int(view_rect.width()), 120)
        min_h = max(int(view_rect.height()) + 10, 40)

        self._editor.setGeometry(
            int(view_rect.x()),
            int(view_rect.y()),
            min_w,
            min_h,
        )

    def _on_document_changed(self) -> None:
        """Auto-resize the text item when the document content changes."""
        item = self._editing_item
        if item is None:
            return
        if isinstance(item, TextItem):
            changed = False
            if item.auto_size:
                item._height = None
                changed = True
            if item.auto_width:
                # Recalculate width from document ideal width
                item._document.setTextWidth(-1)
                ideal = item._document.idealWidth() + 2 * item._padding
                new_width = max(ideal, item._min_width)
                item._width = new_width
                changed = True
            if changed:
                item.prepareGeometryChange()
                item.update()
                self._reposition_editor()

    def _finish_editing(self) -> None:
        """Commit the edited text and remove the editor overlay."""
        if self._editor is None or self._editing_item is None:
            return

        item = self._editing_item
        new_html = item.html()

        # Disconnect contentsChanged before detaching editor
        try:
            item.text_document.contentsChanged.disconnect(self._on_document_changed)
        except (TypeError, RuntimeError):
            pass

        # Close find bar if open
        if self._find_bar is not None:
            self._find_bar.detach()
            self._find_bar.hide()
            self._find_bar.setParent(None)
            self._find_bar.deleteLater()
            self._find_bar = None

        # Detach editor from the item's document BEFORE destroying it
        # to prevent Qt from deleting the item's document
        self._editor.setDocument(QTextDocument())

        # Disconnect and remove editor
        try:
            self._editor.editing_finished.disconnect(self._finish_editing)
        except (TypeError, RuntimeError):
            pass
        self._editor.hide()
        self._editor.setParent(None)
        self._editor.deleteLater()
        self._editor = None

        # Disable document undo and clear stacks
        item.text_document.setUndoRedoEnabled(False)
        item.text_document.clearUndoRedoStacks()

        # Restore item visibility and editing state
        item.setOpacity(1.0)
        item.is_editing = False

        # Lock in the current dimensions — auto_width is only active during editing.
        # Must call prepareGeometryChange() since we bypass the property setter.
        if isinstance(item, TextItem) and item.auto_width:
            item.prepareGeometryChange()
            item._auto_width = False
            item.update()

        if self._scene is not None:
            # If text is empty, remove the item
            if not item.plain_text().strip():
                remove_cmd = RemoveItemCommand(self._scene, item)
                self._scene.command_stack.push(remove_cmd)
            elif new_html != self._old_html:
                # Push undo command for the entire editing session
                # First revert to old state, then let the command's redo() apply new state
                item.set_html(self._old_html)
                edit_cmd = TextEditCommand(item, self._old_html, new_html)
                self._scene.command_stack.push(edit_cmd)

        self._editing_item = None
        self._old_html = ""

    def _show_find(self) -> None:
        """Open the inline find bar."""
        if self._editor is None or self._editing_item is None:
            return
        bar = self._ensure_find_bar()
        bar.show_find()

    def _show_find_replace(self) -> None:
        """Open the inline find+replace bar."""
        if self._editor is None or self._editing_item is None:
            return
        bar = self._ensure_find_bar()
        bar.show_find_replace()

    def _ensure_find_bar(self) -> FindReplaceBar:
        """Create the find bar if it doesn't exist, attach to current document."""
        if self._find_bar is None:
            viewport = self._editor.parent() if self._editor else None
            self._find_bar = FindReplaceBar(viewport)  # type: ignore[arg-type]
            self._find_bar.closed.connect(self._on_find_bar_closed)
            self._find_bar.replace_all_requested.connect(self._on_replace_all)
        if self._editing_item is not None:
            self._find_bar.attach(self._editing_item.text_document)
        # Position at the top of the editor
        if self._editor is not None:
            self._find_bar.setGeometry(
                self._editor.x(),
                self._editor.y() - 30,
                self._editor.width(),
                28,
            )
        return self._find_bar

    def _on_find_bar_closed(self) -> None:
        """Return focus to the editor when the find bar is closed."""
        if self._editor is not None:
            self._editor.setFocus()

    def _on_replace_all(self, old_html: str, new_html: str) -> None:
        """Push a TextEditCommand for a Replace All operation."""
        if self._scene is None or self._editing_item is None:
            return
        if old_html != new_html:
            cmd = TextEditCommand(
                self._editing_item,
                old_html,
                new_html,
                is_clipboard_op=True,  # Prevents merge — treat like a batch op
            )
            self._scene.command_stack.push(cmd)
