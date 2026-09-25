"""ToolOptionsBar — the shared control set and per-tool options (General UI PRD Section 5).

The bar composes each tool's options from the tool's :attr:`BaseTool.options_controls`
declaration: every shared control (colour swatches, stroke width, opacity, font
family and size, bold/italic/underline, smoothing, starting number) is built by one
factory here and bound to the key of the same name in the tool's ``creation_defaults``.
The tool's own :meth:`BaseTool.build_options_widgets` adds what only it has.

The Select tool's bar and the Eyedropper's bar are composed here too, because both
act on things a tool cannot reach: the Arrange actions and the other tools' defaults.

The leftmost control of every tool that has creation defaults is the preset dropdown of
PRD 5.2: a button naming the applied preset, the active theme, or "Custom", whose menu
lists the tool's presets and the Save as Preset, Update Preset, Manage Presets, and Reset
to Theme rows. It reads and writes through the :class:`ToolThemeManager`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from snapmock.commands.eyedropper_commands import ApplyEyedropperColorCommand
from snapmock.config.constants import (
    BADGE_SIZE_MAX,
    BADGE_SIZE_MIN,
    COLOR_HISTORY_MAX,
    CORNER_RADIUS_MAX,
    HEAD_SIZE_CUSTOM_MAX,
    HIGHLIGHT_WIDTH_MAX,
    HIGHLIGHT_WIDTH_MIN,
    SAMPLE_SIZES,
    ApplyTarget,
    BadgeShape,
    BorderStyle,
    ColorFormat,
    DisplayMode,
    FontWeight,
    HeadSize,
    HeadStyle,
)
from snapmock.core.emoji_data import EMOJI_SIZE_MAX, EMOJI_SIZE_MIN
from snapmock.core.stamp_library import STAMP_SIZE_MAX, STAMP_SIZE_MIN
from snapmock.core.theme_manager import current_theme, theme_manager
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.tools.eyedropper_tool import EyedropperTool, format_color_value
from snapmock.ui.accessibility import apply_default_names
from snapmock.ui.color_picker import ColorPicker
from snapmock.ui.unmet_requirements import check_requirements

if TYPE_CHECKING:
    from snapmock.core.selection_manager import SelectionManager
    from snapmock.core.tool_themes import ToolThemeManager
    from snapmock.tools.base_tool import BaseTool
    from snapmock.tools.tool_manager import ToolManager

TOOL_OPTIONS_BAR_HEIGHT = 36
SWATCH_SIZE = 24
_CONTROL_HEIGHT = 26
EYEDROPPER_SWATCH_SIZE = 32
"""Blur PRD 4.5's large sampled-colour swatch."""
HISTORY_SWATCH_SIZE = 16
"""Blur PRD 4.5's Color History swatches."""
_STRIP_HINT_WIDTH = 120
"""What the control strip asks for: enough to be visible, never the sum of the controls."""


class _ValueField(QLineEdit):
    """A read-only colour value that copies itself when clicked (Blur PRD 4.5)."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:  # noqa: N802
        super().mousePressEvent(event)
        self.clicked.emit()


def _color_pixmap(color: QColor, size: int) -> QPixmap:
    """*color* as a swatch, or an outlined checkerboard where there is no colour."""
    pixmap = QPixmap(size, size)
    if color.isValid() and color.alpha() > 0:
        pixmap.fill(color)
        return pixmap
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.fillRect(0, 0, size, size, QColor("#FFFFFF"))
    cell = max(2, size // 4)
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if (x // cell + y // cell) % 2:
                painter.fillRect(x, y, cell, cell, QColor("#CCCCCC"))
    painter.setPen(QColor("#808080"))
    painter.drawRect(0, 0, size - 1, size - 1)
    painter.end()
    return pixmap


def _sample_size_icon(size: int) -> QIcon:
    """4.5's small visual indicator of the sample area: a square that grows with it."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    side = {1: 3, 3: 6, 5: 9, 11: 13}.get(size, 3)
    offset = (16 - side) // 2
    painter.setPen(QColor(90, 90, 90))
    painter.setBrush(QColor(90, 90, 90, 60))
    painter.drawRect(offset, offset, side - 1, side - 1)
    painter.end()
    return QIcon(pixmap)


def _to_clipboard(text: str) -> None:
    clipboard = QGuiApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


@dataclass(frozen=True)
class ControlSpec:
    """One shared control: its widget kind, label, and range (PRD 5.2)."""

    key: str
    label: str
    kind: str  # color | double | int | slider | font | text_style | enum | check
    minimum: float = 0.0
    maximum: float = 100.0
    step: float = 1.0
    suffix: str = ""
    decimals: int = 0
    choices: tuple[tuple[str, Any], ...] = ()
    """The enum kind's rows as (label, value) pairs, in order."""
    icon: str = ""
    """The toggle kind's Tabler glyph."""
    scale: float = 1.0
    """The slider kind's widget units per stored unit: 100 for a 0.0 to 1.0 opacity."""


SHARED_CONTROLS: dict[str, ControlSpec] = {
    "stroke_color": ControlSpec("stroke_color", "Stroke", "color"),
    "fill_color": ControlSpec("fill_color", "Fill", "color"),
    "stroke_width": ControlSpec(
        "stroke_width", "Width", "double", 0.5, 50.0, 0.5, " px", decimals=1
    ),
    "opacity_pct": ControlSpec("opacity_pct", "Opacity", "slider", 0, 100, 1, "%"),
    # The vector items' shared set (Basic Shape PRD 2.6; General UI PRD 5.2)
    "stroke_style": ControlSpec(
        "stroke_style",
        "Style",
        "enum",
        choices=tuple((s.value.replace("dashdot", "dash-dot").title(), s) for s in BorderStyle),
    ),
    "fill_opacity": ControlSpec(
        "fill_opacity", "Fill Opacity", "slider", 0, 100, 1, "%", scale=100.0
    ),
    "stroke_opacity": ControlSpec(
        "stroke_opacity", "Stroke Opacity", "slider", 0, 100, 1, "%", scale=100.0
    ),
    # The Highlighter (Blur PRD 3.5): its colour and width under their own names and
    # range, the four blend modes of 3.4 (the item takes every mode of ITEM_BLEND_MODES)
    "highlight_color": ControlSpec("highlight_color", "Highlight", "color"),
    "highlight_width": ControlSpec(
        "highlight_width", "Width", "slider", HIGHLIGHT_WIDTH_MIN, HIGHLIGHT_WIDTH_MAX, 1, " px"
    ),
    "blend_mode": ControlSpec(
        "blend_mode",
        "Blend",
        "enum",
        choices=(
            ("Multiply", "Multiply"),
            ("Overlay", "Overlay"),
            ("Soft Light", "Soft Light"),
            ("Normal", "Normal"),
        ),
    ),
    # The Rectangle tool (Basic Shape PRD 5.4): the uniform corner radius
    "corner_radius": ControlSpec(
        "corner_radius", "Corner Radius", "slider", 0, CORNER_RADIUS_MAX, 1, " px"
    ),
    # The Arrow tool (Basic Shape PRD 4.7): the head and tail styles with glyphs, the size
    "head_style": ControlSpec(
        "head_style",
        "Head",
        "enum",
        choices=tuple((s.value.title(), s) for s in HeadStyle),
    ),
    "tail_style": ControlSpec(
        "tail_style",
        "Tail",
        "enum",
        choices=tuple((s.value.title(), s) for s in HeadStyle),
    ),
    "head_size": ControlSpec(
        "head_size",
        "Head Size",
        "enum",
        choices=(
            ("Small", HeadSize.SMALL),
            ("Medium", HeadSize.MEDIUM),
            ("Large", HeadSize.LARGE),
            ("XLarge", HeadSize.XLARGE),
        ),
    ),
    "head_size_custom": ControlSpec(
        "head_size_custom",
        "Custom",
        "double",
        0.0,
        HEAD_SIZE_CUSTOM_MAX,
        1.0,
        " px",
        decimals=0,
    ),
    "font_family": ControlSpec("font_family", "Font", "font"),
    "font_size": ControlSpec("font_size", "Size", "int", 6, 200, 1, " pt"),
    "text_style": ControlSpec("text_style", "", "text_style"),
    "text_color": ControlSpec("text_color", "Text", "color"),
    "bg_color": ControlSpec("bg_color", "Background", "color"),
    "border_color": ControlSpec("border_color", "Border", "color"),
    "border_width": ControlSpec("border_width", "Border", "double", 0.0, 20.0, 0.5, " px", 1),
    "smoothing": ControlSpec("smoothing", "Smoothing", "slider", 0, 100, 1, "%"),
    "start_number": ControlSpec("start_number", "Start at", "int", 1, 999, 1),
    # The Numbered Step tool (Numbered Steps, Stamps & Emoji PRD 2.7)
    "badge_color": ControlSpec("badge_color", "Badge", "color"),
    "badge_shape": ControlSpec(
        "badge_shape",
        "Shape",
        "enum",
        choices=tuple((s.value.replace("_", " ").title(), s) for s in BadgeShape),
    ),
    "badge_size": ControlSpec(
        "badge_size", "Size", "slider", BADGE_SIZE_MIN, BADGE_SIZE_MAX, 1, " px"
    ),
    "display_mode": ControlSpec(
        "display_mode",
        "Mode",
        "enum",
        choices=(
            ("Number", DisplayMode.NUMBER),
            ("Letter", DisplayMode.LETTER),
            ("Roman", DisplayMode.ROMAN),
            ("Custom Text", DisplayMode.TEXT),
        ),
    ),
    "font_weight": ControlSpec(
        "font_weight",
        "Weight",
        "enum",
        choices=(("Normal", FontWeight.NORMAL), ("Bold", FontWeight.BOLD)),
    ),
    "border_style": ControlSpec(
        "border_style",
        "Style",
        "enum",
        choices=tuple((s.value.replace("dashdot", "dash-dot").title(), s) for s in BorderStyle),
    ),
    "shadow_enabled": ControlSpec("shadow_enabled", "Shadow", "check"),
    # The Stamp tool (PRD 3.6) and the Emoji tool (PRD 4.5)
    "stamp_size": ControlSpec(
        "stamp_size", "Size", "slider", STAMP_SIZE_MIN, STAMP_SIZE_MAX, 1, " px"
    ),
    "stamp_color": ControlSpec("stamp_color", "Color", "color"),
    "stamp_secondary_color": ControlSpec("stamp_secondary_color", "Secondary", "color"),
    "flip_horizontal": ControlSpec(
        "flip_horizontal", "Flip Horizontal", "toggle", icon="flip-horizontal"
    ),
    "flip_vertical": ControlSpec("flip_vertical", "Flip Vertical", "toggle", icon="flip-vertical"),
    "emoji_size": ControlSpec(
        "emoji_size", "Size", "slider", EMOJI_SIZE_MIN, EMOJI_SIZE_MAX, 1, " px"
    ),
}

_TEXT_STYLE_KEYS: tuple[tuple[str, str, str], ...] = (
    ("bold", "B", "Bold"),
    ("italic", "I", "Italic"),
    ("underline", "U", "Underline"),
)


def arrow_head_icon(style: HeadStyle, size: int = 20, *, tail: bool = False) -> QIcon:
    """A short arrow drawn with *style* at its head (or its tail), the dropdown's glyph
    (Basic Shape PRD 4.7, "visual icons")."""
    from PyQt6.QtCore import QLineF

    from snapmock.items.arrow_item import ArrowItem
    from snapmock.items.vector_item import with_alpha  # noqa: F401  (keeps the import graph)

    item = ArrowItem(line=QLineF(3.0, size / 2, size - 3.0, size / 2))
    item.stroke_width = 1.5
    item.stroke_color = QColor(90, 90, 90)
    item.head_size = HeadSize.SMALL
    item.head_size_custom = 6.0
    if tail:
        item.tail_style = style
        item.head_style = HeadStyle.NONE
    else:
        item.head_style = style
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    item.paint(painter, None)
    painter.end()
    return QIcon(pixmap)


def badge_shape_icon(shape: BadgeShape, size: int = 16) -> QIcon:
    """The badge shape drawn as a small filled glyph (PRD 2.7, "visual icons")."""
    from snapmock.items.numbered_step_item import NumberedStepItem

    item = NumberedStepItem(badge_size=float(size) - 2.0)
    item.badge_shape = shape
    item.shadow_enabled = False
    path = item.badge_path()
    bounds = path.boundingRect()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(size / 2 - bounds.center().x(), size / 2 - bounds.center().y())
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(90, 90, 90))
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class _OverflowPopover(QWidget):
    """The controls that do not fit the bar, stacked in a popover (General UI PRD 15.1).

    15.1 says the Tool Options Bar "collapses into an overflow menu" at the minimum window
    size. Qt's own toolbar extension button is what a `QToolBar` shows for that, and its
    popup never opens for the widget actions this bar is made of: at a 1024 px window the
    Blur tool's bar hid fifteen of its thirty controls, the blur radius among them, and no
    click could reach them (measured 09-12-26 after Doug's display run). This popover holds
    the real controls instead of copies, so whatever it shows is the control itself.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAccessibleName("More tool options")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        self._layout = layout

    @property
    def rows(self) -> QVBoxLayout:
        return self._layout

    def take(self, widgets: Sequence[QWidget], *, hidden: set[QWidget] | None = None) -> None:
        """Show *widgets* here, in the bar's own order, except those the tool has hidden."""
        for widget in widgets:
            self._layout.addWidget(widget)
            widget.setVisible(hidden is None or widget not in hidden)

    def release(self) -> list[QWidget]:
        """Give every control back, in order, for the bar to lay out again."""
        widgets = []
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widgets.append(widget)
        return widgets


class _Strip(QWidget):
    """The row the controls sit in.

    It wants the width the toolbar's row has and never demands more, so the Tool Options
    Bar spans its row as it always did while the overflow decides what fits: a widget
    whose size hint were the sum of its controls would make the toolbar ask for 1400 px
    and Qt would hide the tail behind an extension button whose popup does not open.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._wanted = _STRIP_HINT_WIDTH

    def set_wanted_width(self, width: int) -> None:
        """What the whole tool's controls need, whether they are in the strip or in the
        popover: the toolbar asks for this, so moving a control out never shrinks the row
        and the two cannot chase each other down."""
        wanted = max(_STRIP_HINT_WIDTH, width)
        if wanted == self._wanted:
            return
        self._wanted = wanted
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._wanted, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # Zero, so a narrow window squeezes the strip instead of widening the window;
        # what does not fit is moved to the popover rather than clipped.
        return QSize(0, super().minimumSizeHint().height())


class _Separator(QWidget):
    """The bar's group divider, as a widget rather than a toolbar separator, so it can
    move into the overflow popover with the controls around it."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(9)
        self.setAccessibleName("Separator")

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(current_theme().toolbar_separator)
        middle = self.width() // 2
        painter.drawLine(middle, 4, middle, self.height() - 5)
        painter.end()


# The canvas's clipboard and Select All keys win over a field in the strip (PRD 5.1,
# 2.56): a width typed into a spin box leaves the keyboard focus there, and the field
# would otherwise take Ctrl+A as "select the digits" and Ctrl+C as "copy the digits".
_CANVAS_SEQUENCES = [
    QKeySequence("Ctrl+A"),
    QKeySequence("Ctrl+C"),
    QKeySequence("Ctrl+Shift+C"),
    QKeySequence("Ctrl+X"),
    QKeySequence("Ctrl+V"),
    QKeySequence("Ctrl+Shift+V"),
]


class _CanvasKeysFilter(QObject):
    """Refuse a strip field the ShortcutOverride for the canvas's clipboard keys.

    A focused line edit accepts the override for Ctrl+A, Ctrl+C, Ctrl+X and Ctrl+V and
    so keeps the window's Edit menu actions from firing. Swallowing the override event
    leaves it unaccepted, and Qt's shortcut map then fires the action as it does when
    the canvas has the focus. Every other key still reaches the field.
    """

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        if event is not None and event.type() == QEvent.Type.ShortcutOverride:
            assert isinstance(event, QKeyEvent)
            seq = QKeySequence(event.keyCombination())
            exact = QKeySequence.SequenceMatch.ExactMatch
            if any(seq.matches(s) == exact for s in _CANVAS_SEQUENCES):
                return True
        return super().eventFilter(watched, event)


class ToolOptionsBar(QToolBar):
    """Context-sensitive options for the active tool, 36 px tall (PRD 2.2)."""

    def __init__(self, tool_manager: ToolManager, parent: QWidget | None = None) -> None:
        super().__init__("Tool Options", parent)
        self._canvas_keys = _CanvasKeysFilter(self)
        self.setAccessibleName("Tool Options")
        self._tool_manager = tool_manager
        self._tool: BaseTool | None = None
        self._updating = False
        self._shared: dict[str, QWidget] = {}
        self._control_actions: dict[str, list[QAction]] = {}
        self._style_buttons: dict[str, QToolButton] = {}
        self._selection: SelectionManager | None = None
        self._selection_actions: list[QAction] = []
        self._selection_copies: list[QAction] = []
        self._selection_label: QLabel | None = None
        self._eyedropper_swatch: QLabel | None = None
        self._eyedropper_value: _ValueField | None = None
        self._eyedropper_format: QComboBox | None = None
        self._eyedropper_target: QComboBox | None = None
        self._eyedropper_clipboard: QToolButton | None = None
        self._eyedropper_sizes: dict[int, QToolButton] = {}
        self._eyedropper_history: list[QToolButton] = []
        self._eyedropper_history_actions: list[QAction] = []
        self._themes: ToolThemeManager | None = None
        self._preset_button: QToolButton | None = None
        self._preset_menu: QMenu | None = None
        # Every control lives in one strip inside the toolbar, so Qt never hides any of
        # them behind its own extension button, whose popup does not open for widget
        # actions (PRD 15.1; see _OverflowPopover). The strip takes whatever width the
        # toolbar gives it and the tail that does not fit moves into the popover.
        self._strip = _Strip()
        self._flow = QHBoxLayout(self._strip)
        self._flow.setContentsMargins(0, 0, 0, 0)
        self._flow.setSpacing(3)
        self._flow.addStretch()
        super().addWidget(self._strip)
        self._items: list[QWidget] = []
        """The controls in bar order, whether in the strip or in the popover."""
        self._proxies: list[QAction] = []
        """The actions this bar made for the controls in the strip, in order."""
        self._owned_actions: list[QAction] = []
        """Every action this bar put on itself, proxies and a tool's own alike, so that
        rebuilding for the next tool takes all of them off again."""
        self._action_widgets: dict[QAction, QWidget] = {}
        self._overflow = _OverflowPopover(self)
        self._more = QToolButton()
        self._more.setText("More…")
        self._more.setToolTip("The options that do not fit at this window width")
        self._more.setAccessibleName("More options")
        self._more.setMaximumHeight(_CONTROL_HEIGHT)
        self._more.clicked.connect(self._open_overflow)
        self._more_action = super().addWidget(self._more)
        if self._more_action is not None:
            self._more_action.setVisible(False)
        self._reflowing = False
        self._reflow_queued = False
        self._pinned: dict[QWidget, int] = {}
        """Each control's width, measured once while it sat in the strip."""
        self._tool_hidden: set[QWidget] = set()
        """The controls the active tool has hidden through the action it kept. Qt's own
        ``isHidden`` cannot answer that here: moving a control into the popover takes its
        parent away, which hides it, so the bar keeps the tool's intent itself."""
        self._label = QLabel("No tool selected")
        self.addWidget(self._label)
        self.setMovable(False)
        self.setFixedHeight(TOOL_OPTIONS_BAR_HEIGHT)

        tool_manager.tool_changed.connect(self._on_tool_changed)
        tool_manager.tool_defaults_changed.connect(self._on_tool_defaults_changed)
        self._on_tool_changed(tool_manager.active_tool_id)

    # ---- wiring from the window ----

    def set_selection_actions(self, actions: Sequence[QAction]) -> None:
        """The Arrange actions the Select tool's bar shows for two or more items (PRD 5.3)."""
        self._selection_actions = list(actions)
        if self._tool is not None and self._tool.tool_id == "select":
            self._on_tool_changed("select")

    def set_selection_manager(self, selection: SelectionManager) -> None:
        """Follow another document's selection (tab switch)."""
        if self._selection is selection:
            return
        if self._selection is not None:
            try:
                self._selection.selection_changed.disconnect(self._on_selection_changed)
            except (TypeError, RuntimeError):
                pass
        self._selection = selection
        selection.selection_changed.connect(self._on_selection_changed)
        self._update_selection_widgets()

    def set_theme_manager(self, themes: ToolThemeManager) -> None:
        """The presets and themes the dropdown reads and writes (PRD 5.2)."""
        self._themes = themes
        themes.state_changed.connect(self._refresh_preset_label)
        themes.presets_changed.connect(self._on_presets_changed)
        if self._tool is not None:
            self._on_tool_changed(self._tool.tool_id)

    def refresh(self) -> None:
        """Re-read the active tool's creation defaults into the shared controls."""
        if self._tool is not None:
            self._read_defaults(self._tool)
        self._refresh_preset_label()

    @property
    def preset_button(self) -> QToolButton | None:
        """The preset dropdown, when the active tool has creation defaults."""
        return self._preset_button

    @property
    def shared_widgets(self) -> dict[str, QWidget]:
        """The shared controls currently shown, keyed by creation-defaults key."""
        return dict(self._shared)

    @property
    def selection_action_copies(self) -> list[QAction]:
        return list(self._selection_copies)

    # ---- the strip and its overflow (PRD 15.1) ----

    def addWidget(self, widget: QWidget | None) -> QAction | None:  # noqa: N802
        """Put *widget* in the strip and return the action that shows and hides it.

        A tool keeps the returned action to show a control only in the mode it belongs to
        (the Blur tool's Fill colour, the Polygon tool's Sides), so it behaves as a
        toolbar's own widget action does.
        """
        if widget is None:
            return None
        self._yield_canvas_keys(widget)
        self._flow.insertWidget(self._flow.count() - 1, widget)
        self._items.append(widget)
        # Not added to the toolbar itself: a QToolBar builds a button for every action it
        # is given, and these actions exist only to show and hide the widget in the strip.
        action = QAction(self)
        action.changed.connect(lambda w=widget, a=action: self._on_proxy_changed(w, a))
        self._proxies.append(action)
        self._owned_actions.append(action)
        self._action_widgets[action] = widget
        self._schedule_reflow()
        return action

    def _yield_canvas_keys(self, widget: QWidget) -> None:
        """Let the canvas's clipboard keys pass a text field in the strip (2.56)."""
        # The override reaches the widget that holds the focus: a spin box or an editable
        # combo box, which forwards it to its line edit, so the filter sits on both
        editors: list[QWidget] = []
        if isinstance(widget, QAbstractSpinBox | QComboBox):
            line = widget.lineEdit()
            editors.append(widget)
            if line is not None:
                editors.append(line)
        elif isinstance(widget, QLineEdit):
            editors.append(widget)
        for editor in editors:
            editor.installEventFilter(self._canvas_keys)

    def addSeparator(self) -> QAction | None:  # noqa: N802
        """A group divider, as a widget so it travels with the controls it divides."""
        action = self.addWidget(_Separator())
        if action is not None:
            action.setSeparator(True)
        return action

    def addAction(self, action: QAction) -> None:  # type: ignore[override]  # noqa: N802
        """Show *action* as a button in the strip (the Select tool's Arrange copies)."""
        button = QToolButton()
        button.setDefaultAction(action)
        button.setMaximumHeight(_CONTROL_HEIGHT)
        self.addWidget(button)
        self._owned_actions.append(action)
        self._action_widgets[action] = button

    def widgetForAction(self, action: QAction | None) -> QWidget | None:  # noqa: N802
        if action is None:
            return None
        widget = self._action_widgets.get(action)
        return widget if widget is not None else super().widgetForAction(action)

    def clear(self) -> None:
        """Take every control out of the strip and the popover, for the next tool."""
        self._overflow.hide()
        for widget in self._overflow.release():
            widget.deleteLater()
        for widget in self._items:
            if widget.parent() is self._strip:
                self._flow.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        for action in self._owned_actions:
            self.removeAction(action)
        self._items = []
        self._proxies = []
        self._owned_actions = []
        self._action_widgets = {}
        self._tool_hidden = set()
        self._pinned = {}
        self._strip.set_wanted_width(0)
        if self._more_action is not None:
            self._more_action.setVisible(False)
        self._reflow_width = -1

    def _on_proxy_changed(self, widget: QWidget, action: QAction) -> None:
        """A tool hid or showed one of its controls through the action it kept."""
        hidden = not action.isVisible()
        if hidden == (widget in self._tool_hidden):
            return
        if hidden:
            self._tool_hidden.add(widget)
        else:
            self._tool_hidden.discard(widget)
        widget.setVisible(not hidden)
        self._schedule_reflow()

    @property
    def control_actions(self) -> list[QAction]:
        """One action per control in the strip, in order: what shows and hides each."""
        return list(self._proxies)

    @property
    def controls(self) -> list[QWidget]:
        """The controls the active tool put in the bar, in order, wherever they now sit."""
        return list(self._items)

    @property
    def more_button(self) -> QToolButton:
        """The overflow button, shown only while something does not fit (PRD 15.1)."""
        return self._more

    @property
    def overflow_popover(self) -> _OverflowPopover:
        return self._overflow

    @property
    def overflowing(self) -> list[QWidget]:
        """The controls in the popover rather than the strip, in bar order."""
        rows = self._overflow.rows
        widgets: list[QWidget] = []
        for index in range(rows.count()):
            item = rows.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widgets.append(widget)
        return widgets

    def _schedule_reflow(self) -> None:
        """Reflow once the toolbar has been given its width, after a rebuild.

        One pass however many controls were just added: building a tool's bar calls this
        for every one of them.
        """
        if self._reflow_queued:
            return
        self._reflow_queued = True
        QTimer.singleShot(0, self._run_queued_reflow)

    def _run_queued_reflow(self) -> None:
        self._reflow_queued = False
        self._reflow()

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._reflow()

    def _reflow(self) -> None:
        """Move the tail of the strip that does not fit into the popover, and back again.

        The arithmetic is on each control's own width rather than on the geometry Qt has
        given it, so the answer does not depend on when a layout pass has run: every
        control's minimum width is the width it asks for, pinned by :meth:`_pin_widths`,
        so the strip needs the sum of them plus the spacing between. The pass decides
        first and moves nothing when the decision has not changed, so the layout passes it
        causes cannot send it round again.
        """
        if self._reflowing:
            # The pass in flight is already moving widgets; whether another is needed is
            # decided at the end of it, by the width it then finds.
            return
        if not self._items:
            return
        available = self.contentsRect().width()
        if available <= 0:
            return
        self._reflowing = True
        grew = False
        try:
            grew = self._pin_widths()
            spacing = self._flow.spacing()
            shown = [w for w in self._items if w not in self._tool_hidden]
            needed = sum(self._pinned.get(w, w.sizeHint().width()) + spacing for w in shown)
            wanted_tail: list[QWidget] = []
            if needed > available:
                room = available - self._more.sizeHint().width() - spacing
                while shown and needed > room:
                    victim = shown.pop()
                    needed -= self._pinned.get(victim, victim.sizeHint().width()) + spacing
                    wanted_tail.insert(0, victim)
            wanted_tail = self._with_leading_labels(wanted_tail)
            if wanted_tail != self.overflowing:
                self._move(wanted_tail)
            if self._more_action is not None and self._more_action.isVisible() != bool(
                wanted_tail
            ):
                self._more_action.setVisible(bool(wanted_tail))
        finally:
            self._reflowing = False
        if grew or self.contentsRect().width() != available:
            # Either a control was measured for the first time, or the toolbar changed
            # width while this pass ran. Both settle in one more pass.
            self._schedule_reflow()

    def _with_leading_labels(self, tail: list[QWidget]) -> list[QWidget]:
        """Take the label of a control that is moving with it.

        ``_add_labelled`` puts a label immediately before the control it names, so a tail
        that starts at a control would leave its label behind in the strip, naming nothing.
        """
        if not tail:
            return tail
        first = self._items.index(tail[0])
        while first > 0 and isinstance(self._items[first - 1], QLabel):
            first -= 1
            tail.insert(0, self._items[first])
        return tail

    def _move(self, tail: Sequence[QWidget]) -> None:
        """Put every control back in the strip, then hand *tail* to the popover."""
        for widget in self._overflow.release():
            self._flow.insertWidget(self._items.index(widget), widget)
            # Reparenting hid it; the tool's own intent decides whether it shows.
            widget.setVisible(widget not in self._tool_hidden)
        self._overflow.hide()
        for widget in tail:
            self._flow.removeWidget(widget)
            widget.setParent(None)
        if tail:
            self._overflow.take(tail, hidden=self._tool_hidden)

    def _pin_widths(self) -> bool:
        """Hold every control at the width it asks for, measured once, in the strip.

        Pinned here rather than when the control joined the strip, because a widget's size
        hint before it has been shown and styled is smaller than the width it ends up
        wanting, and a minimum taken then let the layout squeeze the strip instead of
        overflowing it. Pinned once and then remembered, because a control sitting in the
        popover reports a different hint there and a width that followed it would never
        settle. Returns True when a control was measured for the first time, so the caller
        can run once more with the width it now knows.
        """
        measured = False
        for widget in self._items:
            if widget in self._tool_hidden or widget in self._pinned:
                continue
            if widget.parent() is not self._strip or not widget.isVisible():
                continue
            want = max(widget.sizeHint().width(), widget.minimumWidth())
            self._pinned[widget] = want
            widget.setMinimumWidth(want)
            measured = True
        total = sum(
            self._pinned.get(w, w.sizeHint().width()) + self._flow.spacing()
            for w in self._items
            if w not in self._tool_hidden
        )
        self._strip.set_wanted_width(total)
        return measured

    def _open_overflow(self) -> None:
        """Show the overflow popover under the More button (PRD 15.1)."""
        if not self.overflowing:
            return
        self._overflow.adjustSize()
        below = self._more.mapToGlobal(QPoint(0, self._more.height() + 2))
        size = self._overflow.sizeHint()
        x, y = below.x(), below.y()
        screen = QApplication.screenAt(below)
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left(), min(x, available.right() - size.width()))
            y = max(available.top(), min(y, available.bottom() - size.height()))
        self._overflow.move(x, y)
        self._overflow.show()
        self._overflow.raise_()

    # ---- composition ----

    def set_control_visible(self, key: str, visible: bool) -> None:
        """Show or hide one shared control with its label (the Rectangle bar's single
        Corner Radius slider, replaced by four spin boxes in Individual mode, PRD 5.4)."""
        for action in self._control_actions.get(key, []):
            action.setVisible(visible)

    def _on_tool_changed(self, tool_id: str) -> None:
        self.clear()
        self._shared.clear()
        self._control_actions.clear()
        self._style_buttons.clear()
        self._selection_copies.clear()
        self._selection_label = None
        self._eyedropper_swatch = self._eyedropper_value = None
        self._eyedropper_format = self._eyedropper_target = None
        self._eyedropper_clipboard = None
        self._eyedropper_sizes = {}
        self._eyedropper_history = []
        self._eyedropper_history_actions = []
        self._preset_button = self._preset_menu = None
        tool = self._tool_manager.tool(tool_id)
        self._tool = tool
        if tool is None:
            self._label = QLabel("No tool selected")
            self.addWidget(self._label)
            return
        if self._themes is not None and tool_id in self._themes.tool_ids:
            self._build_preset_dropdown(tool)
        self._label = QLabel(f"{tool.display_name} ")
        self.addWidget(self._label)

        keys = list(tool.options_controls)
        if "tool" not in keys:
            keys.append("tool")
        for key in keys:
            if key == "tool":
                if tool.tool_id == "select":
                    self._build_selection_controls()
                elif isinstance(tool, EyedropperTool):
                    self._build_eyedropper_controls(tool)
                tool.build_options_widgets(self)
                continue
            spec = SHARED_CONTROLS[key]
            if spec.key != "text_style" and spec.key not in tool.creation_defaults:
                continue
            before = len(self._proxies)
            self._build_control(spec)
            self._control_actions[spec.key] = list(self._proxies[before:])
        self._read_defaults(tool)
        self._update_selection_widgets()
        apply_default_names(self)
        self._reflow()
        self._schedule_reflow()

    def _add_labelled(self, label: str, widget: QWidget) -> None:
        if label:
            text = QLabel(f" {label}:")
            self.addWidget(text)
        widget.setMaximumHeight(_CONTROL_HEIGHT)
        self.addWidget(widget)

    def _build_control(self, spec: ControlSpec) -> None:
        if spec.kind == "color":
            picker = ColorPicker(swatch_size=SWATCH_SIZE)
            picker.setToolTip(f"{spec.label} colour")
            picker.setAccessibleName(f"{spec.label} color")
            picker.color_changed.connect(lambda c, k=spec.key: self._write(k, QColor(c)))
            self._add_labelled(spec.label, picker)
            self._shared[spec.key] = picker
        elif spec.kind == "double":
            dspin = QDoubleSpinBox()
            dspin.setRange(spec.minimum, spec.maximum)
            dspin.setSingleStep(spec.step)
            dspin.setDecimals(spec.decimals)
            dspin.setSuffix(spec.suffix)
            dspin.setMaximumWidth(80)
            dspin.setAccessibleName(spec.label)
            dspin.valueChanged.connect(lambda v, k=spec.key: self._write(k, float(v)))
            self._add_labelled(spec.label, dspin)
            self._shared[spec.key] = dspin
        elif spec.kind == "int":
            spin = QSpinBox()
            spin.setRange(int(spec.minimum), int(spec.maximum))
            spin.setSingleStep(int(spec.step))
            spin.setSuffix(spec.suffix)
            spin.setMaximumWidth(80)
            spin.setAccessibleName(spec.label)
            spin.valueChanged.connect(lambda v, k=spec.key: self._write(k, int(v)))
            self._add_labelled(spec.label, spin)
            self._shared[spec.key] = spin
        elif spec.kind == "slider":
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(int(spec.minimum), int(spec.maximum))
            slider.setFixedWidth(80)
            slider.setAccessibleName(f"{spec.label} slider")
            spin = QSpinBox()
            spin.setRange(int(spec.minimum), int(spec.maximum))
            spin.setSuffix(spec.suffix)
            spin.setMaximumWidth(64)
            spin.setAccessibleName(spec.label)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            if spec.scale != 1.0:
                spin.valueChanged.connect(
                    lambda v, k=spec.key, s=spec.scale: self._write(k, float(v) / s)
                )
            else:
                spin.valueChanged.connect(lambda v, k=spec.key: self._write(k, v))
            self._add_labelled(spec.label, slider)
            spin.setMaximumHeight(_CONTROL_HEIGHT)
            self.addWidget(spin)
            self._shared[spec.key] = spin
        elif spec.kind == "font":
            font_combo = QFontComboBox()
            font_combo.setMaximumWidth(160)
            font_combo.setAccessibleName(spec.label)
            font_combo.currentFontChanged.connect(
                lambda f, k=spec.key: self._write(k, str(f.family()))
            )
            self._add_labelled(spec.label, font_combo)
            self._shared[spec.key] = font_combo
        elif spec.kind == "enum":
            combo = QComboBox()
            combo.setMaximumWidth(130)
            combo.setAccessibleName(spec.label)
            for text, value in spec.choices:
                if spec.key == "badge_shape" and isinstance(value, BadgeShape):
                    combo.addItem(badge_shape_icon(value), text, value)
                elif spec.key in ("head_style", "tail_style") and isinstance(value, HeadStyle):
                    combo.addItem(
                        arrow_head_icon(value, tail=spec.key == "tail_style"), text, value
                    )
                else:
                    combo.addItem(text, value)
            combo.currentIndexChanged.connect(
                lambda index, k=spec.key, c=combo: self._write(k, c.itemData(index))
            )
            self._add_labelled(spec.label, combo)
            self._shared[spec.key] = combo
        elif spec.kind == "toggle":
            toggle = QToolButton()
            toggle.setCheckable(True)
            toggle.setToolTip(spec.label)
            toggle.setAccessibleName(spec.label)
            toggle.setFixedSize(_CONTROL_HEIGHT, _CONTROL_HEIGHT)
            icon = theme_manager().icon(spec.icon) if spec.icon else QIcon()
            if icon.isNull():
                toggle.setText(spec.label[:1])
            else:
                toggle.setIcon(icon)
            toggle.toggled.connect(lambda checked, k=spec.key: self._write(k, bool(checked)))
            self.addWidget(toggle)
            self._shared[spec.key] = toggle
        elif spec.kind == "check":
            check = QCheckBox(spec.label)
            check.setAccessibleName(spec.label)
            check.toggled.connect(lambda checked, k=spec.key: self._write(k, bool(checked)))
            check.setMaximumHeight(_CONTROL_HEIGHT)
            self.addWidget(check)
            self._shared[spec.key] = check
        elif spec.kind == "text_style":
            for key, text, tip in _TEXT_STYLE_KEYS:
                button = QToolButton()
                button.setText(text)
                button.setToolTip(tip)
                button.setAccessibleName(tip)
                button.setCheckable(True)
                button.setFixedSize(_CONTROL_HEIGHT, _CONTROL_HEIGHT)
                font = button.font()
                if key == "bold":
                    font.setBold(True)
                elif key == "italic":
                    font.setItalic(True)
                else:
                    font.setUnderline(True)
                button.setFont(font)
                button.toggled.connect(lambda checked, k=key: self._write(k, bool(checked)))
                self.addWidget(button)
                self._style_buttons[key] = button
                self._shared[key] = button

    # ---- the preset dropdown (PRD 5.2) ----

    def _build_preset_dropdown(self, tool: BaseTool) -> None:
        button = QToolButton()
        button.setObjectName("PresetDropdown")
        button.setAccessibleName(f"{tool.display_name} preset")
        button.setToolTip("Preset: the applied preset, the active theme, or Custom")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setMaximumHeight(_CONTROL_HEIGHT)
        menu = QMenu(button)
        menu.setObjectName("PresetMenu")
        menu.aboutToShow.connect(self._populate_preset_menu)
        button.setMenu(menu)
        self.addWidget(button)
        self._preset_button = button
        self._preset_menu = menu
        self._refresh_preset_label()

    def _refresh_preset_label(self) -> None:
        if self._preset_button is None or self._themes is None or self._tool is None:
            return
        self._preset_button.setText(f"{self._themes.current_label(self._tool.tool_id)} ▾")

    def _on_presets_changed(self, tool_id: str) -> None:
        if self._tool is not None and self._tool.tool_id == tool_id:
            self._refresh_preset_label()

    def _populate_preset_menu(self) -> None:
        """Rebuild the dropdown's rows from the tool's presets and state."""
        menu, themes, tool = self._preset_menu, self._themes, self._tool
        if menu is None or themes is None or tool is None:
            return
        menu.clear()
        tool_id = tool.tool_id
        label = themes.current_label(tool_id)
        for preset in themes.presets(tool_id):
            action = menu.addAction(preset.name)
            if action is None:
                continue
            action.setCheckable(True)
            action.setChecked(preset.name == label)
            action.triggered.connect(
                lambda _checked=False, name=preset.name: self._apply_preset(name)
            )
        if themes.presets(tool_id):
            menu.addSeparator()
        save = menu.addAction("Save as Preset...")
        if save is not None:
            save.triggered.connect(self._save_as_preset)
        if themes.preset_is_modified(tool_id):
            update = menu.addAction("Update Preset")
            if update is not None:
                update.triggered.connect(self._update_preset)
        manage = menu.addAction("Manage Presets...")
        if manage is not None:
            manage.triggered.connect(self._manage_presets)
        reset = menu.addAction("Reset to Theme")
        if reset is not None:
            reset.triggered.connect(self._reset_to_theme)

    def _ask_preset_name(self, initial: str = "") -> str | None:
        """Prompt for a preset name; None when cancelled."""
        text, ok = QInputDialog.getText(self, "Save as Preset", "Preset name:", text=initial)
        return text.strip() if ok else None

    def _confirm_replace(self, name: str) -> bool:
        answer = QMessageBox.question(
            self,
            "Save as Preset",
            f'A preset named "{name}" exists. Replace it with the current settings?',
        )
        return answer == QMessageBox.StandardButton.Yes

    def _apply_preset(self, name: str) -> None:
        if self._themes is not None and self._tool is not None:
            self._themes.apply_preset(self._tool.tool_id, name)

    def _save_as_preset(self) -> None:
        if self._themes is None or self._tool is None:
            return
        tool_id = self._tool.tool_id
        name = self._ask_preset_name()
        if name is None:
            return
        if not check_requirements(self, "Save as Preset", [(bool(name), "a preset name")]):
            return
        if name in self._themes.preset_names(tool_id) and not self._confirm_replace(name):
            return
        self._themes.save_preset(tool_id, name)

    def _update_preset(self) -> None:
        if self._themes is None or self._tool is None:
            return
        tool_id = self._tool.tool_id
        if check_requirements(
            self,
            "Update Preset",
            [(self._themes.applied_preset(tool_id) is not None, "an applied preset")],
        ):
            self._themes.update_preset(tool_id)

    def _manage_presets(self) -> None:
        """Manage Presets... (PRD 11.9): the dialog for the active tool's presets."""
        if self._themes is None or self._tool is None:
            return
        from snapmock.ui.manage_presets_dialog import ManagePresetsDialog

        tool = self._tool
        if not check_requirements(
            self,
            "Manage Presets",
            [
                (
                    bool(self._themes.preset_names(tool.tool_id)),
                    f"at least one saved preset for the {tool.display_name} tool",
                )
            ],
        ):
            return
        dialog = ManagePresetsDialog(
            self._themes, tool.tool_id, tool.display_name, tool.options_controls, self.window()
        )
        dialog.exec()

    def _reset_to_theme(self) -> None:
        if self._themes is None or self._tool is None:
            return
        tool_id = self._tool.tool_id
        if check_requirements(
            self,
            "Reset to Theme",
            [
                (
                    self._themes.is_overridden(tool_id),
                    "a setting that differs from the active theme",
                )
            ],
        ):
            self._themes.reset_to_theme(tool_id)

    # ---- the two-way binding ----

    def _write(self, key: str, value: Any) -> None:
        """A control changed: store the default and tell the other surfaces."""
        if self._updating or self._tool is None:
            return
        self._tool.creation_defaults[key] = value
        self._tool.on_option_changed(key, value)
        self._tool_manager.tool_defaults_changed.emit(self._tool.tool_id)

    def _on_tool_defaults_changed(self, tool_id: str) -> None:
        if self._tool is not None and self._tool.tool_id == tool_id:
            self._read_defaults(self._tool)
            if isinstance(self._tool, EyedropperTool):
                self._refresh_eyedropper()

    def _read_defaults(self, tool: BaseTool) -> None:
        """Show the tool's creation defaults in the shared controls without writing back."""
        d = tool.creation_defaults
        self._updating = True
        try:
            for key, widget in self._shared.items():
                if key not in d:
                    continue
                value = d[key]
                if isinstance(widget, ColorPicker):
                    widget.color = QColor(value) if isinstance(value, QColor) else QColor("black")
                elif isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
                elif isinstance(widget, QSpinBox):
                    spec = SHARED_CONTROLS.get(key)
                    scale = spec.scale if spec is not None else 1.0
                    widget.setValue(int(round(float(value) * scale)))
                elif isinstance(widget, QFontComboBox):
                    widget.setCurrentFont(QFont(str(value)))
                elif isinstance(widget, QComboBox):
                    index = widget.findData(value)
                    if index >= 0:
                        widget.setCurrentIndex(index)
                elif isinstance(widget, QCheckBox | QToolButton):
                    widget.setChecked(bool(value))
        finally:
            self._updating = False

    # ---- the Select tool's bar (PRD 5.3; Navigation PRD 2.5) ----

    def _build_selection_controls(self) -> None:
        self._selection_label = QLabel("No selection")
        self.addWidget(self._selection_label)
        if not self._selection_actions:
            return
        self.addSeparator()
        for action in self._selection_actions:
            copy = QAction(action.text(), self)
            copy.setIcon(action.icon())
            copy.setToolTip(action.toolTip() or action.text().replace("&", ""))
            copy.triggered.connect(action.trigger)
            self.addAction(copy)
            button = self.widgetForAction(copy)
            if isinstance(button, QToolButton):
                button.setFixedSize(_CONTROL_HEIGHT, _CONTROL_HEIGHT)
                button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self._selection_copies.append(copy)

    def _on_selection_changed(self, _items: list[object]) -> None:
        self._update_selection_widgets()

    def _update_selection_widgets(self) -> None:
        count = self._selection.count if self._selection is not None else 0
        if self._selection_label is not None:
            if count == 0 or self._selection is None:
                self._selection_label.setText("No selection")
            else:
                items = [i for i in self._selection.items if isinstance(i, SnapGraphicsItem)]
                noun = "item" if count == 1 else "items"
                text = f"Selection: {count} {noun}"
                if items:
                    rect = items[0].sceneBoundingRect()
                    for item in items[1:]:
                        rect = rect.united(item.sceneBoundingRect())
                    text += f"   W: {rect.width():.0f} H: {rect.height():.0f}"
                self._selection_label.setText(text)
        for copy in self._selection_copies:
            copy.setVisible(count >= 2)

    # ---- the Eyedropper's bar (Blur PRD 4.5; General UI PRD 5.3) ----

    def _build_eyedropper_controls(self, tool: EyedropperTool) -> None:
        """The seven controls of Blur PRD 4.5, in its order.

        Decision 3 of the Eyedropper and Blur performance work, option A: this is the
        Blur PRD's bar in full, and the Apply to Stroke and Apply to Fill buttons of
        General UI PRD 5.3 are gone, replaced by the Apply Target dropdown with the
        apply-on-sample rule of 4.6.
        """
        self._eyedropper_swatch = QLabel()
        self._eyedropper_swatch.setFixedSize(EYEDROPPER_SWATCH_SIZE, EYEDROPPER_SWATCH_SIZE)
        self._eyedropper_swatch.setToolTip("Last sampled colour")
        self._eyedropper_swatch.setAccessibleName("Sampled color")
        self.addWidget(self._eyedropper_swatch)

        value = _ValueField()
        value.setReadOnly(True)
        value.setMaximumHeight(_CONTROL_HEIGHT)
        value.setMinimumWidth(140)
        value.setToolTip("The sampled colour; click to copy it to the clipboard")
        value.setAccessibleName("Color value")
        value.clicked.connect(self._copy_value_to_clipboard)
        self.addWidget(value)
        self._eyedropper_value = value

        fmt = QComboBox()
        fmt.setMaximumHeight(_CONTROL_HEIGHT)
        fmt.setAccessibleName("Color format")
        for label, item in (
            ("Hex", ColorFormat.HEX),
            ("RGB", ColorFormat.RGB),
            ("HSL", ColorFormat.HSL),
        ):
            fmt.addItem(label, item)
        fmt.currentIndexChanged.connect(
            lambda _i: self._write_eyedropper("color_format", fmt.currentData())
        )
        self._add_labelled("Format", fmt)
        self._eyedropper_format = fmt

        self.addWidget(QLabel(" Sample:"))
        group = QButtonGroup(self)
        group.setExclusive(True)
        self._eyedropper_sizes = {}
        for size in SAMPLE_SIZES:
            button = QToolButton()
            button.setCheckable(True)
            button.setText(f"{size}x{size}")
            button.setIcon(_sample_size_icon(size))
            button.setToolTip(f"Average a {size} by {size} pixel area")
            button.setAccessibleName(f"{size}x{size} sample")
            button.setMaximumHeight(_CONTROL_HEIGHT)
            button.toggled.connect(
                lambda checked, s=size: (
                    self._write_eyedropper("sample_size", s) if checked else None
                )
            )
            group.addButton(button)
            self.addWidget(button)
            self._eyedropper_sizes[size] = button

        target = QComboBox()
        target.setMaximumHeight(_CONTROL_HEIGHT)
        target.setAccessibleName("Apply target")
        for name, choice in (
            ("Stroke Color", ApplyTarget.STROKE_COLOR),
            ("Fill Color", ApplyTarget.FILL_COLOR),
            ("Text Color", ApplyTarget.TEXT_COLOR),
        ):
            target.addItem(name, choice)
        target.currentIndexChanged.connect(
            lambda _i: self._write_eyedropper("apply_target", target.currentData())
        )
        self._add_labelled("Target", target)
        self._eyedropper_target = target

        clipboard = QToolButton()
        clipboard.setCheckable(True)
        clipboard.setIcon(theme_manager().icon("clipboard"))
        clipboard.setToolTip("Copy to Clipboard: every sample copies its hex value")
        clipboard.setAccessibleName("Copy to clipboard")
        clipboard.setMaximumHeight(_CONTROL_HEIGHT)
        clipboard.toggled.connect(
            lambda checked: self._write_eyedropper("copy_to_clipboard", bool(checked))
        )
        self.addWidget(clipboard)
        self._eyedropper_clipboard = clipboard

        self.addWidget(QLabel(" History:"))
        self._eyedropper_history = []
        self._eyedropper_history_actions = []
        for index in range(COLOR_HISTORY_MAX):
            swatch = QToolButton()
            swatch.setFixedSize(HISTORY_SWATCH_SIZE, HISTORY_SWATCH_SIZE)
            swatch.setAccessibleName(f"Color history {index + 1}")
            swatch.clicked.connect(lambda _c=False, i=index: self._reapply_history(i))
            action = self.addWidget(swatch)
            # The action, not only the widget: a hidden widget would leave its slot in the
            # bar, and this is the widest bar in the application already.
            if action is not None:
                action.setVisible(False)
                self._eyedropper_history_actions.append(action)
            self._eyedropper_history.append(swatch)

        tool.set_pick_callback(self._on_color_applied)
        # The colour display follows the cursor while a drag lasts (Blur PRD 4.2)
        tool.set_preview_callback(self._show_sampled_color)
        self._refresh_eyedropper()

    @property
    def eyedropper_value_text(self) -> str:
        """What the colour value field reads (4.5)."""
        return "" if self._eyedropper_value is None else self._eyedropper_value.text()

    @property
    def eyedropper_size_buttons(self) -> dict[int, QToolButton]:
        return dict(self._eyedropper_sizes)

    @property
    def eyedropper_history_swatches(self) -> list[QToolButton]:
        return list(self._eyedropper_history)

    def _eyedropper(self) -> EyedropperTool | None:
        return self._tool if isinstance(self._tool, EyedropperTool) else None

    def _write_eyedropper(self, key: str, value: Any) -> None:
        """A bar control wrote one of 4.4's properties; the tool keeps it as a creation
        default, so a preset and a theme capture it (General UI PRD 5.2)."""
        tool = self._eyedropper()
        if tool is None or self._updating or value is None:
            return
        tool.creation_defaults[key] = value
        self._tool_manager.tool_defaults_changed.emit(tool.tool_id)
        self._refresh_eyedropper()

    def _refresh_eyedropper(self) -> None:
        """Show the tool's properties in the bar without writing them back."""
        tool = self._eyedropper()
        if tool is None:
            return
        self._updating = True
        try:
            if self._eyedropper_format is not None:
                index = self._eyedropper_format.findData(tool.color_format)
                if index >= 0:
                    self._eyedropper_format.setCurrentIndex(index)
            if self._eyedropper_target is not None:
                index = self._eyedropper_target.findData(tool.apply_target)
                if index >= 0:
                    self._eyedropper_target.setCurrentIndex(index)
            for size, button in self._eyedropper_sizes.items():
                button.setChecked(size == tool.sample_size)
            if self._eyedropper_clipboard is not None:
                self._eyedropper_clipboard.setChecked(tool.copy_to_clipboard)
        finally:
            self._updating = False
        self._show_sampled_color(tool.picked_color)
        self._refresh_color_history()

    def _refresh_color_history(self) -> None:
        """4.5's row of the last eight sampled colours, newest first. A slot with nothing
        in it is hidden rather than shown doing nothing (General UI PRD 1.3)."""
        tool = self._eyedropper()
        history = tool.color_history if tool is not None else []
        for index, swatch in enumerate(self._eyedropper_history):
            shown = index < len(history)
            if shown:
                color = history[index]
                swatch.setIcon(QIcon(_color_pixmap(color, HISTORY_SWATCH_SIZE - 6)))
                swatch.setToolTip(f"Re-apply {color.name().upper()}")
            if index < len(self._eyedropper_history_actions):
                self._eyedropper_history_actions[index].setVisible(shown)

    def _show_sampled_color(self, color: QColor) -> None:
        """The swatch and the colour value field, for a preview or an applied sample."""
        if self._eyedropper_swatch is None:
            return
        tool = self._eyedropper()
        self._eyedropper_swatch.setPixmap(_color_pixmap(color, EYEDROPPER_SWATCH_SIZE))
        if self._eyedropper_value is not None and tool is not None:
            self._eyedropper_value.setText(format_color_value(color, tool.color_format))

    def _on_color_applied(self, color: QColor) -> None:
        """An applied sample (4.2): the display, the history, the clipboard, the target."""
        self.show_picked_color(color)
        tool = self._eyedropper()
        if tool is not None:
            self._apply_picked(tool.apply_target.value, color)

    def show_picked_color(self, color: QColor) -> None:
        """A sample landed: show it, put it in the history, and copy it if the toggle is
        on (4.4, 4.5). Used by the colour picker's route, which applies the colour itself."""
        tool = self._eyedropper()
        if tool is not None:
            # 4.4's last_sampled_color: a pick routed through the colour picker is a sample
            # too, and a later refresh of the bar reads it back from the tool.
            tool.set_last_sampled_color(color)
            tool.push_history(color)
            if tool.copy_to_clipboard:
                _to_clipboard(color.name().upper())
        self._show_sampled_color(color)
        self._refresh_color_history()

    def _copy_value_to_clipboard(self) -> None:
        """4.5: a click on the colour value field copies what it reads."""
        if self._eyedropper_value is not None and self._eyedropper_value.text():
            _to_clipboard(self._eyedropper_value.text())

    def _reapply_history(self, index: int) -> None:
        """4.5: a click on a history swatch re-applies that colour."""
        tool = self._eyedropper()
        if tool is None:
            return
        history = tool.color_history
        if index >= len(history):
            return
        tool.set_last_sampled_color(history[index])
        self._show_sampled_color(history[index])
        self._refresh_color_history()
        self._apply_picked(tool.apply_target.value, history[index])

    def _apply_picked(self, key: str, color: QColor) -> None:
        """Apply *color* to *key*, by the three routes of Blur PRD 4.6 in its order.

        The routes are not exclusive, because they answer different questions. The tool
        the Eyedropper was reached from takes the colour as its creation default, so it is
        ready when the user switches back (route 1); a selection takes it on the items
        themselves, as one undoable command (route 2, and ``ApplyEyedropperColorCommand``
        of 6.2); and when there is neither a previous tool nor a selection, every tool
        that carries the property takes the colour, which is the closest thing the
        application has to route 3's active stroke colour.
        """
        if not color.isValid() or color.alpha() == 0:
            return
        applied = self._apply_to_previous_tool(key, color)
        applied = self._apply_to_selection(key, color) or applied
        if not applied:
            self._apply_to_every_tool(key, color)

    def _apply_to_previous_tool(self, key: str, color: QColor) -> bool:
        """Route 1: the tool the Eyedropper was reached from takes the colour (4.6)."""
        tool_id = self._tool_manager.previous_tool_id or self._tool_manager.last_tool_id
        if tool_id is None:
            return False
        other = self._tool_manager.tool(tool_id)
        if other is None or key not in other.creation_defaults:
            return False
        other.creation_defaults[key] = QColor(color)
        self._tool_manager.tool_defaults_changed.emit(tool_id)
        return True

    def _apply_to_selection(self, key: str, color: QColor) -> bool:
        """Route 2: the selected items take the colour, undoably (4.6, 6.2)."""
        if self._selection is None or not self._selection.count:
            return False
        items = [
            item
            for item in self._selection.items
            if isinstance(item, SnapGraphicsItem) and hasattr(item, key)
        ]
        if not items:
            return False
        scene = items[0].scene()
        if scene is None or not hasattr(scene, "command_stack"):
            return False
        scene.command_stack.push(ApplyEyedropperColorCommand(items, key, color))
        return True

    def _apply_to_every_tool(self, key: str, color: QColor) -> None:
        """Route 3: with no previous tool and no selection, every tool that carries the
        property takes the colour (4.6)."""
        for tool_id in self._tool_manager.tool_ids:
            other = self._tool_manager.tool(tool_id)
            if other is not None and key in other.creation_defaults:
                other.creation_defaults[key] = QColor(color)
                self._tool_manager.tool_defaults_changed.emit(tool_id)
