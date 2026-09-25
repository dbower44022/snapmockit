"""PropertyPanel — dock widget showing selected item properties (General UI PRD Section 8).

Every control edits the whole selection: one item gets a ``ModifyPropertyCommand``,
several get one ``ModifyPropertiesCommand`` (PRD 8.6), and a control whose values
differ across the selection shows a mixed indicator until it is changed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QPoint, QSizeF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFontComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from snapmock.commands.canvas_property_commands import (
    SetCanvasBorderCommand,
    SetCanvasPropertyCommand,
)
from snapmock.commands.macro_command import MacroCommand
from snapmock.commands.modify_property import ModifyPropertiesCommand, ModifyPropertyCommand
from snapmock.commands.move_item_layer import MoveItemToLayerCommand
from snapmock.commands.raster_commands import ResizeCanvasCommand
from snapmock.commands.scale_geometry_command import ScaleGeometryCommand
from snapmock.config.constants import (
    BADGE_SIZE_MAX,
    BADGE_SIZE_MIN,
    BLUR_BRUSH_SIZE_MAX,
    BLUR_BRUSH_SIZE_MIN,
    BLUR_FEATHER_MAX,
    BLUR_PIXEL_SIZE_MAX,
    BLUR_PIXEL_SIZE_MIN,
    BLUR_RADIUS_MAX,
    BLUR_RADIUS_MIN,
    BORDER_WIDTH_MAX,
    CORNER_KEYS,
    CORNER_RADIUS_MAX,
    DEFAULT_BLUR_BRUSH_SIZE,
    DEFAULT_BORDER_COLOR,
    DEFAULT_LINE_SPACING,
    DEFAULT_SHADOW_COLOR,
    DEFAULT_STRAIGHTEN_THRESHOLD,
    HEAD_SIZE_CUSTOM_MAX,
    LINE_SPACING_MAX,
    LINE_SPACING_MIN,
    STRAIGHTEN_THRESHOLD_MAX,
    STRAIGHTEN_THRESHOLD_MIN,
    ArcType,
    BadgeShape,
    BlurMode,
    BlurRegionShape,
    BlurSourceMode,
    BorderStyle,
    CornerRadiusMode,
    DisplayMode,
    FontWeight,
    HeadSize,
    HeadStyle,
    LabelPosition,
    LineStyle,
    PolygonMode,
    VerticalAlign,
)
from snapmock.config.settings import AppSettings
from snapmock.core.command_stack import BaseCommand
from snapmock.core.emoji_data import EMOJI_SIZE_MAX, EMOJI_SIZE_MIN, SkinTone
from snapmock.core.layer import ITEM_BLEND_MODES
from snapmock.core.stamp_library import STAMP_SIZE_MAX, STAMP_SIZE_MIN
from snapmock.core.theme_manager import current_theme, theme_manager
from snapmock.items.arc_item import ArcItem
from snapmock.items.arrow_item import ArrowItem
from snapmock.items.base_item import SnapGraphicsItem
from snapmock.items.blur_item import BlurItem
from snapmock.items.callout_item import CalloutItem
from snapmock.items.emoji_item import EmojiItem
from snapmock.items.freehand_item import FreehandItem
from snapmock.items.group_item import GroupItem
from snapmock.items.numbered_step_item import NumberedStepItem
from snapmock.items.polygon_item import (
    SIDES_MAX,
    SIDES_MIN,
    STAR_INDENT_MAX,
    STAR_INDENT_MIN,
    PolygonItem,
)
from snapmock.items.rectangle_item import RectangleItem
from snapmock.items.shadow import ShadowMixin
from snapmock.items.stamp_item import StampItem
from snapmock.items.text_item import TextItem
from snapmock.items.vector_item import VectorItem
from snapmock.ui.collapsible_section import CollapsibleSection
from snapmock.ui.color_picker import ColorPicker
from snapmock.ui.panel_modes import STRIP_PANEL_WIDTH, PanelMode

if TYPE_CHECKING:
    from snapmock.core.scene import SnapScene
    from snapmock.core.selection_manager import SelectionManager
    from snapmock.tools.tool_manager import ToolManager


_VECTOR_TOOL_IDS = {"rectangle", "ellipse", "line", "arrow", "freehand", "highlight"}

MIXED_TEXT = "—"
"""The dash a spinbox shows when the selection's values differ (PRD 8.6)."""

FONT_WEIGHTS: tuple[tuple[str, QFont.Weight], ...] = (
    ("Regular", QFont.Weight.Normal),
    ("Bold", QFont.Weight.Bold),
)
"""Font Weight dropdown entries (PRD 8.4; the Text PRD's weight table)."""

FONT_STYLES: tuple[tuple[str, bool], ...] = (("Normal", False), ("Italic", True))
"""Font Style dropdown entries (PRD 8.4)."""

CANVAS_DPI_RANGE = (1, 2400)

_TextLike = TextItem | CalloutItem


def _color_key(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexArgb)


def _uniform(values: list[Any], key: Callable[[Any], Any] = lambda v: v) -> tuple[Any, bool]:
    """The first value and whether every value matches it; ``(None, False)`` when empty."""
    if not values:
        return None, False
    first = values[0]
    first_key = key(first)
    return first, all(key(v) == first_key for v in values[1:])


def _block_line_spacing(fmt: QTextBlockFormat) -> float:
    """A paragraph's line spacing multiplier; 1.0 when none is set (Qt's single)."""
    proportional = cast(int, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    if fmt.lineHeightType() == proportional and fmt.lineHeight() > 0:
        return round(fmt.lineHeight() / 100.0, 3)
    return 1.0


def _hex_text(color: QColor) -> str:
    fmt = QColor.NameFormat.HexArgb if color.alpha() < 255 else QColor.NameFormat.HexRgb
    return color.name(fmt).upper()


# Section title -> Tabler glyph for the icon-strip buttons (PRD 15.2).
SECTION_ICONS: dict[str, str] = {
    "Transform": "resize",
    "Appearance": "palette",
    "Arrow": "arrow-up-right",
    "Rectangle": "border-inner",
    "Text": "typography",
    "Text Box": "app-window",
    "Item Info": "info-circle",
    "Canvas": "aspect-ratio",
}
POPOVER_SIZE = (340, 480)


class _PropertyPopover(QWidget):
    """The popover an icon-strip button opens; it holds the panel's own scroll area."""

    closed = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAccessibleName("Properties")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._layout = layout

    def adopt(self, widget: QWidget) -> None:
        widget.setParent(self)
        self._layout.addWidget(widget)
        widget.show()

    def hideEvent(self, event: object) -> None:  # noqa: N802
        super().hideEvent(event)  # type: ignore[arg-type]
        self.closed.emit()


class PropertyPanel(QDockWidget):
    """Dockable panel showing properties of the selected item(s).

    :meth:`set_mode` gives the narrow mode of PRD 15.2 (sliders and hex inputs
    hidden, the spinboxes and swatches stay) and the icon strip (one button per
    section, each opening the panel in a popover).

    Signals
    -------
    canvas_setting_changed(str, object)
        A Canvas section control that edits a preference rather than the
        scene: ``pasteboard_color`` (QColor or None), ``grid_size`` (int),
        ``snap_to_grid`` (bool). The main window applies and persists it.
    """

    canvas_setting_changed = pyqtSignal(str, object)

    def __init__(
        self,
        selection_manager: SelectionManager,
        scene: SnapScene,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Properties", parent)
        self.setAccessibleName("Property Panel")
        self._selection_manager = selection_manager
        self._scene = scene
        self._settings = AppSettings()
        self._updating = False
        self._tool_manager: ToolManager | None = None
        self._active_tool_id: str = ""
        self._editor_connected: bool = False
        self._connected_editor: QWidget | None = None

        # Left, right, or bottom (General UI PRD 2.3); the acceptance pass found the
        # bottom edge missing (implementation notes Section 16, row 2).
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )

        # Scroll area wrapper
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(2)

        self._build_transform_section()
        self._build_appearance_section()
        self._build_arrow_section()
        self._build_arc_section()
        self._build_polygon_section()
        self._build_blur_section()
        self._build_highlight_section()
        self._build_rectangle_section()
        self._build_freehand_section()
        self._build_step_section()
        self._build_stamp_section()
        self._build_emoji_section()
        self._build_shadow_section()
        self._build_text_section()
        self._build_text_box_section()
        self._build_info_section()
        self._build_canvas_section()
        self._sections = (
            self._transform_section,
            self._appearance_section,
            self._arrow_section,
            self._arc_section,
            self._polygon_section,
            self._blur_section,
            self._highlight_section,
            self._rectangle_section,
            self._freehand_section,
            self._step_section,
            self._stamp_section,
            self._emoji_section,
            self._shadow_section,
            self._text_section,
            self._text_box_section,
            self._info_section,
            self._canvas_section,
        )
        for section in self._sections:
            section.set_expanded(self._settings.property_section_expanded(section.title))
            section.toggled.connect(self._on_section_toggled)

        self._main_layout.addStretch()
        self._scroll.setWidget(container)
        self.setWidget(self._scroll)
        self._mode = PanelMode.FULL
        self._abbreviated: list[QWidget] = [
            self._stroke_w_slider,
            self._opacity_slider,
            self._fill_opacity_slider,
            self._stroke_opacity_slider,
            self._text_fill_opacity_slider,
            self._text_stroke_opacity_slider,
            self._corner_radius_slider,
            self._stroke_hex,
            self._fill_hex,
        ]
        self._popover: _PropertyPopover | None = None
        self._strip_buttons: dict[str, QToolButton] = {}
        self._strip = self._build_strip()

        self._connect_edit_handlers()
        self._connect_selection_signals()
        self._connect_scene_signals()
        theme_manager().theme_changed.connect(self._on_theme_changed)

        # Initial state
        self._refresh_from_selection()

    # ---------------------------------------------------- collapse modes (PRD 15)

    def _build_strip(self) -> QWidget:
        strip = QWidget()
        strip.setAccessibleName("Property Panel sections")
        layout = QVBoxLayout(strip)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        for section in self._sections:
            button = QToolButton()
            button.setAutoRaise(True)
            button.setToolTip(section.title)
            button.setAccessibleName(f"{section.title} section")
            button.setAccessibleDescription(f"Opens the {section.title} properties.")
            button.setFixedSize(STRIP_PANEL_WIDTH - 8, STRIP_PANEL_WIDTH - 8)
            button.clicked.connect(lambda _c=False, s=section: self._open_section_popover(s))
            layout.addWidget(button)
            self._strip_buttons[section.title] = button
        layout.addStretch()
        self._apply_strip_icons()
        return strip

    def _apply_strip_icons(self) -> None:
        manager = theme_manager()
        for title, button in self._strip_buttons.items():
            button.setIcon(manager.icon(SECTION_ICONS.get(title, "settings")))
            button.setIconSize(manager.icon_qsize())

    @property
    def mode(self) -> PanelMode:
        return self._mode

    @property
    def strip(self) -> QWidget:
        return self._strip

    @property
    def popover(self) -> _PropertyPopover | None:
        return self._popover

    def set_mode(self, mode: PanelMode) -> None:
        """Full, narrow (abbreviated controls), or the icon strip with popovers."""
        if mode is self._mode:
            return
        self._mode = mode
        self._close_popover()
        for widget in self._abbreviated:
            widget.setVisible(mode is PanelMode.FULL)
        if mode is PanelMode.ICON_STRIP:
            self._scroll.setParent(self)
            self._scroll.hide()
            self.setWidget(self._strip)
            self._strip.show()
            self.setMinimumWidth(STRIP_PANEL_WIDTH)
            self.setMaximumWidth(STRIP_PANEL_WIDTH)
        else:
            if self.widget() is not self._scroll:
                self._strip.setParent(self)
                self._strip.hide()
                self.setWidget(self._scroll)
                self._scroll.show()
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)

    def _open_section_popover(self, section: CollapsibleSection) -> None:
        self._close_popover()
        popover = _PropertyPopover(self)
        popover.adopt(self._scroll)
        popover.resize(*POPOVER_SIZE)
        popover.closed.connect(self._on_popover_closed)
        section.set_expanded(True)
        self._refresh_from_selection()
        anchor = self.mapToGlobal(QPoint(0, 0))
        popover.move(anchor.x() - popover.width(), anchor.y())
        popover.show()
        self._scroll.ensureWidgetVisible(section)
        self._popover = popover

    def _close_popover(self) -> None:
        if self._popover is not None:
            popover = self._popover
            self._popover = None
            popover.hide()
            popover.deleteLater()

    def _on_popover_closed(self) -> None:
        if self._popover is None:
            return
        popover = self._popover
        self._popover = None
        self._scroll.setParent(self)
        self._scroll.hide()
        popover.deleteLater()

    # ------------------------------------------------------------------ build

    @staticmethod
    def _make_double_spin(
        minimum: float, maximum: float, decimals: int, suffix: str, name: str
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        spin.setSpecialValueText(MIXED_TEXT)
        spin.setAccessibleName(name)
        return spin

    @staticmethod
    def _slider_spin_row(spin: QSpinBox | QDoubleSpinBox, slider: QSlider, name: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        slider.setAccessibleName(f"{name} slider")
        spin.setAccessibleName(name)
        layout.addWidget(slider)
        layout.addWidget(spin)
        return row

    @staticmethod
    def _hex_edit(name: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setMaxLength(9)
        edit.setPlaceholderText("#RRGGBB")
        edit.setFixedWidth(84)
        edit.setAccessibleName(f"{name} hex")
        return edit

    @staticmethod
    def _color_row(picker: ColorPicker, edit: QLineEdit, name: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        picker.setAccessibleName(name)
        layout.addWidget(picker)
        layout.addWidget(edit)
        layout.addStretch()
        return row

    def _build_transform_section(self) -> None:
        self._transform_section = CollapsibleSection("Transform")
        # Spinbox minimums are one step below the real range: the minimum
        # shows the mixed dash (PRD 8.6) and is never a value the panel writes.
        self._x_spin = self._make_double_spin(-99999.0, 99999.0, 1, " px", "X position")
        self._y_spin = self._make_double_spin(-99999.0, 99999.0, 1, " px", "Y position")
        self._w_spin = self._make_double_spin(0.0, 99999.0, 1, " px", "Width")
        self._h_spin = self._make_double_spin(0.0, 99999.0, 1, " px", "Height")
        self._rot_spin = self._make_double_spin(-361.0, 360.0, 1, "°", "Rotation")
        self._transform_section.add_row("X:", self._x_spin)
        self._transform_section.add_row("Y:", self._y_spin)

        w_row = QWidget()
        w_layout = QHBoxLayout(w_row)
        w_layout.setContentsMargins(0, 0, 0, 0)
        w_layout.addWidget(self._w_spin)
        self._aspect_lock = QToolButton()
        self._aspect_lock.setCheckable(True)
        self._aspect_lock.setAutoRaise(True)
        self._aspect_lock.setToolTip("Lock aspect ratio")
        self._aspect_lock.setAccessibleName("Lock aspect ratio")
        w_layout.addWidget(self._aspect_lock)
        self._transform_section.add_row("W:", w_row)
        self._transform_section.add_row("H:", self._h_spin)
        self._transform_section.add_row("Rotation:", self._rot_spin)

        flip_container = QWidget()
        flip_layout = QHBoxLayout(flip_container)
        flip_layout.setContentsMargins(0, 0, 0, 0)
        self._flip_h_btn = QPushButton("Flip H")
        self._flip_h_btn.setCheckable(True)
        self._flip_h_btn.setAccessibleName("Flip horizontal")
        self._flip_v_btn = QPushButton("Flip V")
        self._flip_v_btn.setCheckable(True)
        self._flip_v_btn.setAccessibleName("Flip vertical")
        flip_layout.addWidget(self._flip_h_btn)
        flip_layout.addWidget(self._flip_v_btn)
        self._transform_section.add_row("Flip:", flip_container)
        self._main_layout.addWidget(self._transform_section)

    def _build_appearance_section(self) -> None:
        self._appearance_section = CollapsibleSection("Appearance")

        self._stroke_color_picker = ColorPicker(QColor("black"))
        self._stroke_hex = self._hex_edit("Stroke color")
        self._appearance_section.add_row(
            "Stroke:", self._color_row(self._stroke_color_picker, self._stroke_hex, "Stroke color")
        )

        self._stroke_w_slider = QSlider(Qt.Orientation.Horizontal)
        self._stroke_w_slider.setRange(0, 100)
        self._stroke_w_spin = QDoubleSpinBox()
        self._stroke_w_spin.setRange(-1.0, 100.0)
        self._stroke_w_spin.setDecimals(1)
        self._stroke_w_spin.setSpecialValueText(MIXED_TEXT)
        self._stroke_w_spin.setKeyboardTracking(False)
        self._appearance_section.add_row(
            "Width:",
            self._slider_spin_row(self._stroke_w_spin, self._stroke_w_slider, "Stroke width"),
        )

        self._stroke_style_combo = QComboBox()
        for style in BorderStyle:
            self._stroke_style_combo.addItem(
                style.value.replace("dashdot", "dash-dot").title(), style
            )
        self._stroke_style_combo.setAccessibleName("Stroke style")
        self._appearance_section.add_row("Style:", self._stroke_style_combo)

        self._fill_color_picker = ColorPicker(QColor("transparent"))
        self._fill_hex = self._hex_edit("Fill color")
        self._fill_row = self._color_row(self._fill_color_picker, self._fill_hex, "Fill color")
        self._appearance_section.add_row("Fill:", self._fill_row)

        # Fill Opacity and Stroke Opacity for vector items (PRD 8.3; Vector Item Properties
        # decision 2, option A: they replace the single Opacity for vector items).
        self._fill_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._fill_opacity_slider.setRange(0, 100)
        self._fill_opacity_spin = QSpinBox()
        self._fill_opacity_spin.setRange(-1, 100)
        self._fill_opacity_spin.setSuffix("%")
        self._fill_opacity_spin.setSpecialValueText(MIXED_TEXT)
        self._fill_opacity_spin.setKeyboardTracking(False)
        self._fill_opacity_row = self._slider_spin_row(
            self._fill_opacity_spin, self._fill_opacity_slider, "Fill opacity"
        )
        self._appearance_section.add_row("Fill opacity:", self._fill_opacity_row)
        self._stroke_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._stroke_opacity_slider.setRange(0, 100)
        self._stroke_opacity_spin = QSpinBox()
        self._stroke_opacity_spin.setRange(-1, 100)
        self._stroke_opacity_spin.setSuffix("%")
        self._stroke_opacity_spin.setSpecialValueText(MIXED_TEXT)
        self._stroke_opacity_spin.setKeyboardTracking(False)
        self._appearance_section.add_row(
            "Stroke opacity:",
            self._slider_spin_row(
                self._stroke_opacity_spin, self._stroke_opacity_slider, "Stroke opacity"
            ),
        )

        # The single Opacity of a group (its own, beside its members' two; decision 2's
        # follow-on detail); hidden for a selection of vector items alone.
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(-1, 100)
        self._opacity_spin.setSuffix("%")
        self._opacity_spin.setSpecialValueText(MIXED_TEXT)
        self._opacity_spin.setKeyboardTracking(False)
        self._opacity_row = self._slider_spin_row(
            self._opacity_spin, self._opacity_slider, "Opacity"
        )
        self._appearance_section.add_row("Opacity:", self._opacity_row)
        self._main_layout.addWidget(self._appearance_section)

    @staticmethod
    def _set_row_visible(section: CollapsibleSection, field: QWidget, visible: bool) -> None:
        """Show or hide one form row of *section*: the field and its label."""
        field.setVisible(visible)
        label = section.form_layout.labelForField(field)
        if label is not None:
            label.setVisible(visible)

    def _build_arrow_section(self) -> None:
        """The arrow's heads (Basic Shape PRD 4.3): where a placed arrow's head and tail
        styles and size are changed, since the bar edits creation defaults only."""
        from snapmock.ui.tool_options_bar import arrow_head_icon

        self._arrow_section = CollapsibleSection("Arrow")
        self._arrow_head_combo = QComboBox()
        self._arrow_tail_combo = QComboBox()
        for style in HeadStyle:
            self._arrow_head_combo.addItem(arrow_head_icon(style), style.value.title(), style)
            self._arrow_tail_combo.addItem(
                arrow_head_icon(style, tail=True), style.value.title(), style
            )
        self._arrow_head_combo.setAccessibleName("Head style")
        self._arrow_tail_combo.setAccessibleName("Tail style")
        self._arrow_section.add_row("Head:", self._arrow_head_combo)
        self._arrow_section.add_row("Tail:", self._arrow_tail_combo)
        self._arrow_size_combo = QComboBox()
        for label, size in (
            ("Small", HeadSize.SMALL),
            ("Medium", HeadSize.MEDIUM),
            ("Large", HeadSize.LARGE),
            ("XLarge", HeadSize.XLARGE),
        ):
            self._arrow_size_combo.addItem(label, size)
        self._arrow_size_combo.setAccessibleName("Head size")
        self._arrow_section.add_row("Head size:", self._arrow_size_combo)
        self._arrow_custom_spin = self._make_double_spin(
            -1.0, HEAD_SIZE_CUSTOM_MAX, 0, " px", "Custom head size"
        )
        self._arrow_custom_spin.setToolTip("0 uses the named size")
        self._arrow_section.add_row("Custom size:", self._arrow_custom_spin)
        # The line style of 4.3 for a placed arrow (Basic Shape remainder Phase 1 step 3)
        from snapmock.tools.arrow_tool import line_style_icon

        self._arrow_line_style_combo = QComboBox()
        for line_style in LineStyle:
            self._arrow_line_style_combo.addItem(
                line_style_icon(line_style), line_style.value.title(), line_style
            )
        self._arrow_line_style_combo.setAccessibleName("Line style")
        self._arrow_section.add_row("Line style:", self._arrow_line_style_combo)
        self._main_layout.addWidget(self._arrow_section)

    def _build_arc_section(self) -> None:
        """A placed arc's type and heads (Basic Shape PRD 7.3, 7.4), since the bar edits
        creation defaults only."""
        from snapmock.tools.arc_tool import arc_type_icon
        from snapmock.ui.tool_options_bar import arrow_head_icon

        self._arc_section = CollapsibleSection("Arc")
        self._arc_type_combo = QComboBox()
        for arc_type in ArcType:
            self._arc_type_combo.addItem(arc_type_icon(arc_type), arc_type.value.title(), arc_type)
        self._arc_type_combo.setAccessibleName("Arc type")
        self._arc_section.add_row("Type:", self._arc_type_combo)
        self._arc_head_combo = QComboBox()
        self._arc_tail_combo = QComboBox()
        for style in HeadStyle:
            self._arc_head_combo.addItem(arrow_head_icon(style), style.value.title(), style)
            self._arc_tail_combo.addItem(
                arrow_head_icon(style, tail=True), style.value.title(), style
            )
        self._arc_head_combo.setAccessibleName("Arc head style")
        self._arc_tail_combo.setAccessibleName("Arc tail style")
        self._arc_section.add_row("Head:", self._arc_head_combo)
        self._arc_section.add_row("Tail:", self._arc_tail_combo)
        self._arc_size_combo = QComboBox()
        for label, size in (
            ("Small", HeadSize.SMALL),
            ("Medium", HeadSize.MEDIUM),
            ("Large", HeadSize.LARGE),
            ("XLarge", HeadSize.XLARGE),
        ):
            self._arc_size_combo.addItem(label, size)
        self._arc_size_combo.setAccessibleName("Arc head size")
        self._arc_section.add_row("Head size:", self._arc_size_combo)
        self._main_layout.addWidget(self._arc_section)

    def _build_polygon_section(self) -> None:
        """A placed polygon's sides, star, and closure (Basic Shape PRD 8.3), since the bar
        edits creation defaults only: the first three for a regular polygon, Closed for a
        freeform one."""
        self._polygon_section = CollapsibleSection("Polygon")
        self._polygon_sides_spin = QSpinBox()
        self._polygon_sides_spin.setRange(SIDES_MIN - 1, SIDES_MAX)
        self._polygon_sides_spin.setSpecialValueText(MIXED_TEXT)
        self._polygon_sides_spin.setKeyboardTracking(False)
        self._polygon_sides_spin.setAccessibleName("Sides")
        self._polygon_section.add_row("Sides:", self._polygon_sides_spin)
        self._polygon_star_check = QCheckBox("Star")
        self._polygon_star_check.setAccessibleName("Star")
        self._polygon_section.add_row("Star:", self._polygon_star_check)
        self._polygon_indent_spin = self._make_double_spin(
            STAR_INDENT_MIN - 0.01, STAR_INDENT_MAX, 2, "", "Star indent"
        )
        self._polygon_indent_spin.setSingleStep(0.05)
        self._polygon_section.add_row("Indent:", self._polygon_indent_spin)
        self._polygon_closed_check = QCheckBox("Closed")
        self._polygon_closed_check.setAccessibleName("Closed polygon")
        self._polygon_section.add_row("Path:", self._polygon_closed_check)
        self._main_layout.addWidget(self._polygon_section)

    def _build_blur_section(self) -> None:
        """A placed blur region's properties (Blur PRD 2.5, 2.8), each change one command and
        shown on the canvas at once; the rows follow the mode and the shape."""
        self._blur_section = CollapsibleSection("Blur")
        self._blur_mode_combo = QComboBox()
        for mode, label in (
            (BlurMode.GAUSSIAN, "Gaussian Blur"),
            (BlurMode.PIXELATE, "Pixelate"),
            (BlurMode.SOLID, "Solid Fill"),
        ):
            self._blur_mode_combo.addItem(label, mode)
        self._blur_mode_combo.setAccessibleName("Blur mode")
        self._blur_section.add_row("Mode:", self._blur_mode_combo)
        self._blur_radius_spin = self._make_double_spin(
            BLUR_RADIUS_MIN - 1.0, BLUR_RADIUS_MAX, 1, " px", "Blur radius"
        )
        self._blur_section.add_row("Radius:", self._blur_radius_spin)
        self._blur_pixel_spin = QSpinBox()
        self._blur_pixel_spin.setRange(BLUR_PIXEL_SIZE_MIN - 1, BLUR_PIXEL_SIZE_MAX)
        self._blur_pixel_spin.setSuffix(" px")
        self._blur_pixel_spin.setSpecialValueText(MIXED_TEXT)
        self._blur_pixel_spin.setKeyboardTracking(False)
        self._blur_pixel_spin.setAccessibleName("Pixel size")
        self._blur_section.add_row("Pixel size:", self._blur_pixel_spin)
        self._blur_fill_picker = ColorPicker(QColor("black"))
        self._blur_fill_picker.setAccessibleName("Blur fill color")
        self._blur_section.add_row("Fill:", self._blur_fill_picker)
        self._blur_shape_combo = QComboBox()
        for shape, label in (
            (BlurRegionShape.RECTANGLE, "Rectangle"),
            (BlurRegionShape.ELLIPSE, "Ellipse"),
            (BlurRegionShape.FREEFORM, "Freeform"),
            (BlurRegionShape.WHOLE_LAYER, "Whole Layer"),
        ):
            self._blur_shape_combo.addItem(label, shape)
        self._blur_shape_combo.setAccessibleName("Region shape")
        self._blur_section.add_row("Shape:", self._blur_shape_combo)
        self._blur_corner_spin = self._make_double_spin(
            -1.0, CORNER_RADIUS_MAX, 0, " px", "Blur corner radius"
        )
        self._blur_section.add_row("Corner radius:", self._blur_corner_spin)
        self._blur_feather_spin = self._make_double_spin(
            -1.0, BLUR_FEATHER_MAX, 0, " px", "Feather"
        )
        self._blur_section.add_row("Feather:", self._blur_feather_spin)
        self._blur_brush_spin = QSpinBox()
        self._blur_brush_spin.setRange(int(BLUR_BRUSH_SIZE_MIN), int(BLUR_BRUSH_SIZE_MAX))
        self._blur_brush_spin.setSuffix(" px")
        self._blur_brush_spin.setKeyboardTracking(False)
        self._blur_brush_spin.setAccessibleName("Brush size")
        self._blur_brush_spin.setToolTip("The brush that paints a freeform region")
        self._blur_section.add_row("Brush size:", self._blur_brush_spin)
        self._blur_source_combo = QComboBox()
        for source, label in (
            (BlurSourceMode.ALL_BELOW, "All below"),
            (BlurSourceMode.ACTIVE_LAYER, "Active layer"),
            (BlurSourceMode.SPECIFIC_LAYER, "Specific layer"),
        ):
            self._blur_source_combo.addItem(label, source)
        self._blur_source_combo.setAccessibleName("Blur source")
        self._blur_section.add_row("Source:", self._blur_source_combo)
        self._blur_source_layer_combo = QComboBox()
        self._blur_source_layer_combo.setAccessibleName("Blur source layer")
        self._blur_section.add_row("Source layer:", self._blur_source_layer_combo)
        self._blur_invert_check = QCheckBox("Invert mask")
        self._blur_invert_check.setAccessibleName("Invert mask")
        self._blur_section.add_row("Mask:", self._blur_invert_check)
        self._blur_opacity_spin = QSpinBox()
        self._blur_opacity_spin.setRange(-1, 100)
        self._blur_opacity_spin.setSuffix("%")
        self._blur_opacity_spin.setSpecialValueText(MIXED_TEXT)
        self._blur_opacity_spin.setKeyboardTracking(False)
        self._blur_opacity_spin.setAccessibleName("Blur opacity")
        self._blur_section.add_row("Opacity:", self._blur_opacity_spin)
        self._blur_border_picker = ColorPicker(QColor(0, 0, 0, 0))
        self._blur_border_picker.setAccessibleName("Blur border color")
        self._blur_section.add_row("Border:", self._blur_border_picker)
        self._blur_border_spin = self._make_double_spin(-1.0, 50.0, 1, " px", "Border width")
        self._blur_section.add_row("Border width:", self._blur_border_spin)
        self._main_layout.addWidget(self._blur_section)

    def _build_highlight_section(self) -> None:
        """The Highlighter's straightening, shown for the tool's defaults only.

        Blur PRD 3.6: auto_straighten and snap_to_axis have no retroactive effect, so a
        placed stroke shows no row for them (freeform blur silence 5); the section appears
        while the Highlighter is active with nothing selected, as General UI PRD Section 8
        shows a creation tool's defaults. The rows are not undoable, since they are tool
        settings and not document state.
        """
        self._highlight_section = CollapsibleSection("Highlighter")
        self._highlight_straighten_check = QCheckBox("Auto-straighten")
        self._highlight_straighten_check.setAccessibleName("Auto-straighten")
        self._highlight_section.add_row("Straighten:", self._highlight_straighten_check)
        self._highlight_threshold_spin = QDoubleSpinBox()
        self._highlight_threshold_spin.setRange(STRAIGHTEN_THRESHOLD_MIN, STRAIGHTEN_THRESHOLD_MAX)
        self._highlight_threshold_spin.setSingleStep(0.01)
        self._highlight_threshold_spin.setDecimals(2)
        self._highlight_threshold_spin.setKeyboardTracking(False)
        self._highlight_threshold_spin.setAccessibleName("Straighten threshold")
        self._highlight_section.add_row("Threshold:", self._highlight_threshold_spin)
        self._highlight_snap_check = QCheckBox("Snap to axis")
        self._highlight_snap_check.setAccessibleName("Snap to axis")
        self._highlight_section.add_row("Snap:", self._highlight_snap_check)
        self._main_layout.addWidget(self._highlight_section)

    def _build_rectangle_section(self) -> None:
        """The rectangle's corner radius (Basic Shape PRD 5.3, 5.4), for a placed rectangle."""
        self._rectangle_section = CollapsibleSection("Rectangle")
        self._corner_radius_slider = QSlider(Qt.Orientation.Horizontal)
        self._corner_radius_slider.setRange(0, int(CORNER_RADIUS_MAX))
        self._corner_radius_spin = QDoubleSpinBox()
        self._corner_radius_spin.setRange(-1.0, CORNER_RADIUS_MAX)
        self._corner_radius_spin.setDecimals(0)
        self._corner_radius_spin.setSuffix(" px")
        self._corner_radius_spin.setSpecialValueText(MIXED_TEXT)
        self._corner_radius_spin.setKeyboardTracking(False)
        self._corner_radius_row = self._slider_spin_row(
            self._corner_radius_spin, self._corner_radius_slider, "Corner radius"
        )
        self._rectangle_section.add_row("Corner radius:", self._corner_radius_row)
        # Uniform / Individual and the four radii of 5.3 (Basic Shape remainder Phase 2)
        self._corner_mode_check = QCheckBox("Individual corners")
        self._corner_mode_check.setAccessibleName("Individual corner radii")
        self._rectangle_section.add_row("Corners:", self._corner_mode_check)
        self._corner_spins: dict[str, QDoubleSpinBox] = {}
        for key, label in zip(
            CORNER_KEYS, ("Top-left:", "Top-right:", "Bottom-left:", "Bottom-right:")
        ):
            spin = self._make_double_spin(
                -1.0, CORNER_RADIUS_MAX, 0, " px", f"{label[:-1]} corner radius"
            )
            self._rectangle_section.add_row(label, spin)
            self._corner_spins[key] = spin
        self._main_layout.addWidget(self._rectangle_section)

    def _build_freehand_section(self) -> None:
        """A placed freehand stroke's Smoothing and Close Path (Basic Shape PRD 9.6, 9.7):
        re-smoothing starts again from the raw points, as one undoable change, since the
        bar edits creation defaults only."""
        self._freehand_section = CollapsibleSection("Freehand")
        self._freehand_smoothing_slider = QSlider(Qt.Orientation.Horizontal)
        self._freehand_smoothing_slider.setRange(0, 100)
        self._freehand_smoothing_spin = QSpinBox()
        self._freehand_smoothing_spin.setRange(-1, 100)
        self._freehand_smoothing_spin.setSuffix("%")
        self._freehand_smoothing_spin.setSpecialValueText(MIXED_TEXT)
        self._freehand_smoothing_spin.setKeyboardTracking(False)
        self._freehand_section.add_row(
            "Smoothing:",
            self._slider_spin_row(
                self._freehand_smoothing_spin, self._freehand_smoothing_slider, "Smoothing"
            ),
        )
        self._freehand_closed_check = QCheckBox("Close path")
        self._freehand_closed_check.setAccessibleName("Close path")
        self._freehand_section.add_row("Path:", self._freehand_closed_check)
        self._main_layout.addWidget(self._freehand_section)

    def _build_step_section(self) -> None:
        """The numbered step's own properties (Numbered Steps, Stamps & Emoji PRD 2.4):
        everything the Appearance section does not already show as the stroke and fill."""
        from snapmock.ui.tool_options_bar import badge_shape_icon

        self._step_section = CollapsibleSection("Numbered Step")

        self._step_value_spin = QSpinBox()
        self._step_value_spin.setRange(-1, 9999)
        self._step_value_spin.setSpecialValueText(MIXED_TEXT)
        self._step_value_spin.setKeyboardTracking(False)
        self._step_value_spin.setAccessibleName("Step number")
        self._step_section.add_row("Number:", self._step_value_spin)

        self._step_mode_combo = QComboBox()
        for label, mode in (
            ("Number", DisplayMode.NUMBER),
            ("Letter", DisplayMode.LETTER),
            ("Roman", DisplayMode.ROMAN),
            ("Custom Text", DisplayMode.TEXT),
        ):
            self._step_mode_combo.addItem(label, mode)
        self._step_mode_combo.setAccessibleName("Display mode")
        self._step_section.add_row("Mode:", self._step_mode_combo)

        self._step_text_edit = QLineEdit()
        self._step_text_edit.setAccessibleName("Custom text")
        self._step_text_edit.setPlaceholderText("Text in Custom Text mode")
        self._step_section.add_row("Text:", self._step_text_edit)

        self._step_shape_combo = QComboBox()
        for shape in BadgeShape:
            self._step_shape_combo.addItem(
                badge_shape_icon(shape), shape.value.replace("_", " ").title(), shape
            )
        self._step_shape_combo.setAccessibleName("Badge shape")
        self._step_section.add_row("Shape:", self._step_shape_combo)

        self._step_size_spin = self._make_double_spin(
            BADGE_SIZE_MIN - 1.0, BADGE_SIZE_MAX, 1, " px", "Badge size"
        )
        self._step_section.add_row("Size:", self._step_size_spin)

        self._step_weight_combo = QComboBox()
        self._step_weight_combo.addItem("Normal", FontWeight.NORMAL)
        self._step_weight_combo.addItem("Bold", FontWeight.BOLD)
        self._step_weight_combo.setAccessibleName("Badge font weight")
        self._step_section.add_row("Weight:", self._step_weight_combo)

        self._step_border_style_combo = QComboBox()
        for style in BorderStyle:
            self._step_border_style_combo.addItem(
                style.value.replace("dashdot", "dash-dot").title(), style
            )
        self._step_border_style_combo.setAccessibleName("Border style")
        self._step_section.add_row("Border style:", self._step_border_style_combo)

        self._step_label_edit = QLineEdit()
        self._step_label_edit.setAccessibleName("Label text")
        self._step_label_edit.setPlaceholderText("No label")
        self._step_section.add_row("Label:", self._step_label_edit)

        self._step_label_pos_combo = QComboBox()
        for position in LabelPosition:
            self._step_label_pos_combo.addItem(position.value.title(), position)
        self._step_label_pos_combo.setAccessibleName("Label position")
        self._step_section.add_row("Label position:", self._step_label_pos_combo)

        self._step_label_size_spin = self._make_double_spin(
            0.0, 200.0, 1, " pt", "Label font size"
        )
        self._step_section.add_row("Label size:", self._step_label_size_spin)

        self._step_label_color_picker = ColorPicker(QColor("black"))
        self._step_label_color_picker.setAccessibleName("Label color")
        self._step_section.add_row("Label color:", self._step_label_color_picker)

        self._step_label_bg_picker = ColorPicker(QColor("white"))
        self._step_label_bg_picker.setAccessibleName("Label background")
        self._step_section.add_row("Label background:", self._step_label_bg_picker)

        self._step_label_pill_check = QCheckBox("Background pill")
        self._step_label_pill_check.setAccessibleName("Label background pill")
        self._step_section.add_row("", self._step_label_pill_check)
        self._main_layout.addWidget(self._step_section)

    def _build_stamp_section(self) -> None:
        """The stamp's own properties (Numbered Steps, Stamps & Emoji PRD 3.5): the stamp
        with a Change Stamp button, size, the two colours, and the single opacity of
        General UI PRD 8.3 for a non-vector item."""
        self._stamp_section = CollapsibleSection("Stamp")

        stamp_row = QWidget()
        stamp_layout = QHBoxLayout(stamp_row)
        stamp_layout.setContentsMargins(0, 0, 0, 0)
        self._stamp_name_label = QLabel("")
        self._stamp_name_label.setAccessibleName("Stamp name")
        stamp_layout.addWidget(self._stamp_name_label, 1)
        self._stamp_change_button = QPushButton("Change...")
        self._stamp_change_button.setAccessibleName("Change stamp")
        self._stamp_change_button.setToolTip("Choose another stamp from the library")
        stamp_layout.addWidget(self._stamp_change_button)
        self._stamp_section.add_row("Stamp:", stamp_row)

        self._stamp_size_spin = self._make_double_spin(
            STAMP_SIZE_MIN - 1.0, STAMP_SIZE_MAX, 1, " px", "Stamp size"
        )
        self._stamp_section.add_row("Size:", self._stamp_size_spin)

        self._stamp_color_picker = ColorPicker(QColor("#CC0000"))
        self._stamp_color_picker.setAccessibleName("Stamp color")
        self._stamp_section.add_row("Color:", self._stamp_color_picker)
        self._stamp_secondary_picker = ColorPicker(QColor("white"))
        self._stamp_secondary_picker.setAccessibleName("Stamp secondary color")
        self._stamp_section.add_row("Secondary:", self._stamp_secondary_picker)

        self._stamp_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._stamp_opacity_slider.setRange(0, 100)
        self._stamp_opacity_spin = QSpinBox()
        self._stamp_opacity_spin.setRange(-1, 100)
        self._stamp_opacity_spin.setSuffix("%")
        self._stamp_opacity_spin.setSpecialValueText(MIXED_TEXT)
        self._stamp_opacity_spin.setKeyboardTracking(False)
        self._stamp_section.add_row(
            "Opacity:",
            self._slider_spin_row(
                self._stamp_opacity_spin, self._stamp_opacity_slider, "Stamp opacity"
            ),
        )
        self._main_layout.addWidget(self._stamp_section)

    def _build_emoji_section(self) -> None:
        """The emoji's own properties (Numbered Steps, Stamps & Emoji PRD 4.4): the emoji with
        a Change Emoji button, size, skin tone, and the single opacity of General UI PRD 8.3."""
        self._emoji_section = CollapsibleSection("Emoji")

        emoji_row = QWidget()
        emoji_layout = QHBoxLayout(emoji_row)
        emoji_layout.setContentsMargins(0, 0, 0, 0)
        self._emoji_name_label = QLabel("")
        self._emoji_name_label.setAccessibleName("Emoji name")
        emoji_layout.addWidget(self._emoji_name_label, 1)
        self._emoji_change_button = QPushButton("Change...")
        self._emoji_change_button.setAccessibleName("Change emoji")
        self._emoji_change_button.setToolTip("Choose another emoji from the picker")
        emoji_layout.addWidget(self._emoji_change_button)
        self._emoji_section.add_row("Emoji:", emoji_row)

        self._emoji_size_spin = self._make_double_spin(
            EMOJI_SIZE_MIN - 1.0, EMOJI_SIZE_MAX, 1, " px", "Emoji size"
        )
        self._emoji_section.add_row("Size:", self._emoji_size_spin)

        self._emoji_tone_combo = QComboBox()
        for tone in SkinTone:
            self._emoji_tone_combo.addItem(tone.value.replace("_", " ").title(), tone)
        self._emoji_tone_combo.setAccessibleName("Skin tone")
        self._emoji_section.add_row("Skin tone:", self._emoji_tone_combo)

        self._emoji_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._emoji_opacity_slider.setRange(0, 100)
        self._emoji_opacity_spin = QSpinBox()
        self._emoji_opacity_spin.setRange(-1, 100)
        self._emoji_opacity_spin.setSuffix("%")
        self._emoji_opacity_spin.setSpecialValueText(MIXED_TEXT)
        self._emoji_opacity_spin.setKeyboardTracking(False)
        self._emoji_section.add_row(
            "Opacity:",
            self._slider_spin_row(
                self._emoji_opacity_spin, self._emoji_opacity_slider, "Emoji opacity"
            ),
        )
        self._main_layout.addWidget(self._emoji_section)

    def _build_shadow_section(self) -> None:
        """The Shadow section of General UI PRD 8.3, for the items that carry a shadow
        (Numbered Steps, Stamps, and Emoji decision 1)."""
        self._shadow_section = CollapsibleSection("Shadow")

        self._shadow_check = QCheckBox("Enabled")
        self._shadow_check.setAccessibleName("Shadow enabled")
        self._shadow_section.add_row("", self._shadow_check)

        self._shadow_color_picker = ColorPicker(QColor(0, 0, 0, 102))
        self._shadow_color_picker.setAccessibleName("Shadow color")
        self._shadow_section.add_row("Color:", self._shadow_color_picker)

        self._shadow_x_spin = self._make_double_spin(-101.0, 100.0, 1, " px", "Shadow offset X")
        self._shadow_section.add_row("Offset X:", self._shadow_x_spin)
        self._shadow_y_spin = self._make_double_spin(-101.0, 100.0, 1, " px", "Shadow offset Y")
        self._shadow_section.add_row("Offset Y:", self._shadow_y_spin)

        self._shadow_blur_slider = QSlider(Qt.Orientation.Horizontal)
        self._shadow_blur_slider.setRange(0, 50)
        self._shadow_blur_spin = QDoubleSpinBox()
        self._shadow_blur_spin.setRange(-1.0, 50.0)
        self._shadow_blur_spin.setDecimals(1)
        self._shadow_blur_spin.setSuffix(" px")
        self._shadow_blur_spin.setSpecialValueText(MIXED_TEXT)
        self._shadow_blur_spin.setKeyboardTracking(False)
        self._shadow_section.add_row(
            "Blur radius:",
            self._slider_spin_row(self._shadow_blur_spin, self._shadow_blur_slider, "Shadow blur"),
        )
        self._main_layout.addWidget(self._shadow_section)

    def _build_text_section(self) -> None:
        self._text_section = CollapsibleSection("Text")

        self._font_combo = QFontComboBox()
        self._font_combo.setAccessibleName("Font family")
        self._text_section.add_row("Font:", self._font_combo)

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(0, 200)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setSpecialValueText(MIXED_TEXT)
        self._font_size_spin.setKeyboardTracking(False)
        self._font_size_spin.setAccessibleName("Font size")
        self._text_section.add_row("Size:", self._font_size_spin)

        self._weight_combo = QComboBox()
        for label, weight in FONT_WEIGHTS:
            self._weight_combo.addItem(label, weight)
        self._weight_combo.setAccessibleName("Font weight")
        self._text_section.add_row("Weight:", self._weight_combo)

        self._style_combo = QComboBox()
        for label, italic in FONT_STYLES:
            self._style_combo.addItem(label, italic)
        self._style_combo.setAccessibleName("Font style")
        self._text_section.add_row("Style:", self._style_combo)

        self._underline_check = QCheckBox("Underline")
        self._underline_check.setAccessibleName("Underline")
        self._text_section.add_row("", self._underline_check)

        self._text_color_picker = ColorPicker(QColor("black"))
        self._text_color_picker.setAccessibleName("Text color")
        self._text_section.add_row("Color:", self._text_color_picker)

        self._text_align_combo = QComboBox()
        self._text_align_combo.addItem("Left", Qt.AlignmentFlag.AlignLeft)
        self._text_align_combo.addItem("Center", Qt.AlignmentFlag.AlignHCenter)
        self._text_align_combo.addItem("Right", Qt.AlignmentFlag.AlignRight)
        self._text_align_combo.addItem("Justify", Qt.AlignmentFlag.AlignJustify)
        self._text_align_combo.setAccessibleName("Text alignment")
        self._text_section.add_row("Align:", self._text_align_combo)

        # Line Spacing (PRD 8.4; Text PRD 2.2): a multiplier, 0.5 to 5.0 by 0.1
        self._line_spacing_spin = self._make_double_spin(
            LINE_SPACING_MIN - 0.1, LINE_SPACING_MAX, 1, "", "Line spacing"
        )
        self._line_spacing_spin.setSingleStep(0.1)
        self._line_spacing_spin.setSuffix(" ×")
        self._text_section.add_row("Line spacing:", self._line_spacing_spin)

        # Background Fill belongs to the Text section (PRD 8.4)
        self._text_bg_color_picker = ColorPicker(QColor("transparent"))
        self._text_bg_color_picker.setAccessibleName("Background fill")
        self._text_section.add_row("Background:", self._text_bg_color_picker)
        self._main_layout.addWidget(self._text_section)

    def _build_text_box_section(self) -> None:
        self._text_box_section = CollapsibleSection("Text Box")

        self._text_border_color_picker = ColorPicker(QColor("transparent"))
        self._text_border_color_picker.setAccessibleName("Border color")
        self._text_box_section.add_row("Border:", self._text_border_color_picker)

        self._text_border_w_spin = self._make_double_spin(-0.1, 20.0, 1, " px", "Border width")
        self._text_box_section.add_row("Border width:", self._text_border_w_spin)

        # Fill Opacity and Stroke Opacity for the text box and the callout (General UI PRD
        # 8.3; Vector Item Properties decision 1, option B: here rather than in Appearance)
        self._text_fill_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._text_fill_opacity_slider.setRange(0, 100)
        self._text_fill_opacity_spin = QSpinBox()
        self._text_fill_opacity_spin.setRange(-1, 100)
        self._text_fill_opacity_spin.setSuffix("%")
        self._text_fill_opacity_spin.setSpecialValueText(MIXED_TEXT)
        self._text_fill_opacity_spin.setKeyboardTracking(False)
        self._text_box_section.add_row(
            "Fill opacity:",
            self._slider_spin_row(
                self._text_fill_opacity_spin, self._text_fill_opacity_slider, "Text fill opacity"
            ),
        )
        self._text_stroke_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._text_stroke_opacity_slider.setRange(0, 100)
        self._text_stroke_opacity_spin = QSpinBox()
        self._text_stroke_opacity_spin.setRange(-1, 100)
        self._text_stroke_opacity_spin.setSuffix("%")
        self._text_stroke_opacity_spin.setSpecialValueText(MIXED_TEXT)
        self._text_stroke_opacity_spin.setKeyboardTracking(False)
        self._text_box_section.add_row(
            "Stroke opacity:",
            self._slider_spin_row(
                self._text_stroke_opacity_spin,
                self._text_stroke_opacity_slider,
                "Text stroke opacity",
            ),
        )

        self._text_corner_radius_spin = self._make_double_spin(
            -0.1, 50.0, 1, " px", "Corner radius"
        )
        self._text_box_section.add_row("Corner radius:", self._text_corner_radius_spin)

        self._text_padding_spin = self._make_double_spin(-0.1, 50.0, 1, " px", "Padding")
        self._text_box_section.add_row("Padding:", self._text_padding_spin)

        self._text_valign_combo = QComboBox()
        self._text_valign_combo.addItem("Top", VerticalAlign.TOP)
        self._text_valign_combo.addItem("Center", VerticalAlign.CENTER)
        self._text_valign_combo.addItem("Bottom", VerticalAlign.BOTTOM)
        self._text_valign_combo.setAccessibleName("Vertical alignment")
        self._text_box_section.add_row("Vertical align:", self._text_valign_combo)

        self._text_auto_size_check = QCheckBox("Auto-size height")
        self._text_auto_size_check.setAccessibleName("Auto-size height")
        self._text_box_section.add_row("", self._text_auto_size_check)
        self._main_layout.addWidget(self._text_box_section)

    def _build_info_section(self) -> None:
        self._info_section = CollapsibleSection("Item Info")
        self._type_label = QLabel("")
        self._layer_combo = QComboBox()
        self._layer_combo.setAccessibleName("Layer")
        self._locked_check = QCheckBox("Locked")
        self._locked_check.setAccessibleName("Item lock")
        # Blend Mode (PRD 8.3) sits here rather than in Appearance because every item
        # carries it (Vector Item Properties decision 4) and every selection shows Item Info.
        self._blend_combo = QComboBox()
        for mode in ITEM_BLEND_MODES:
            self._blend_combo.addItem(mode, mode)
        self._blend_combo.setAccessibleName("Blend mode")
        self._info_section.add_row("Type:", self._type_label)
        self._info_section.add_row("Layer:", self._layer_combo)
        self._info_section.add_row("Blend mode:", self._blend_combo)
        self._info_section.add_row("", self._locked_check)
        self._main_layout.addWidget(self._info_section)

    def _build_canvas_section(self) -> None:
        self._canvas_section = CollapsibleSection("Canvas")
        self._canvas_w_spin = QSpinBox()
        self._canvas_w_spin.setRange(1, 99999)
        self._canvas_w_spin.setSuffix(" px")
        self._canvas_w_spin.setKeyboardTracking(False)
        self._canvas_w_spin.setAccessibleName("Canvas width")
        self._canvas_h_spin = QSpinBox()
        self._canvas_h_spin.setRange(1, 99999)
        self._canvas_h_spin.setSuffix(" px")
        self._canvas_h_spin.setKeyboardTracking(False)
        self._canvas_h_spin.setAccessibleName("Canvas height")
        self._bg_color_picker = ColorPicker(QColor("white"))
        self._bg_color_picker.setAccessibleName("Canvas color")
        self._pasteboard_picker = ColorPicker(QColor("#E0E0E0"), allow_transparent=False)
        self._pasteboard_picker.setAccessibleName("Pasteboard color")
        self._grid_size_spin = QSpinBox()
        self._grid_size_spin.setRange(1, 100)
        self._grid_size_spin.setSuffix(" px")
        self._grid_size_spin.setKeyboardTracking(False)
        self._grid_size_spin.setAccessibleName("Grid size")
        self._snap_check = QCheckBox("Snap to grid")
        self._snap_check.setAccessibleName("Snap to grid")
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(*CANVAS_DPI_RANGE)
        self._dpi_spin.setKeyboardTracking(False)
        self._dpi_spin.setAccessibleName("Canvas DPI")
        # The canvas border (Navigation PRD 10.6): the same values the Border tool's bar
        # edits, reachable without activating the tool.
        self._border_w_spin = QSpinBox()
        self._border_w_spin.setRange(0, BORDER_WIDTH_MAX)
        self._border_w_spin.setSuffix(" px")
        self._border_w_spin.setKeyboardTracking(False)
        self._border_w_spin.setAccessibleName("Canvas border width")
        self._border_color_picker = ColorPicker(QColor(DEFAULT_BORDER_COLOR))
        self._border_color_picker.setAccessibleName("Canvas border color")
        self._border_opacity_spin = QSpinBox()
        self._border_opacity_spin.setRange(0, 100)
        self._border_opacity_spin.setSuffix("%")
        self._border_opacity_spin.setKeyboardTracking(False)
        self._border_opacity_spin.setAccessibleName("Canvas border opacity")
        self._border_style_combo = QComboBox()
        self._border_style_combo.setAccessibleName("Canvas border style")
        for style in BorderStyle:
            self._border_style_combo.addItem(
                style.value.replace("dashdot", "dash-dot").title(), style
            )
        self._canvas_section.add_row("Width:", self._canvas_w_spin)
        self._canvas_section.add_row("Height:", self._canvas_h_spin)
        self._canvas_section.add_row("Canvas color:", self._bg_color_picker)
        self._canvas_section.add_row("Border:", self._border_w_spin)
        self._canvas_section.add_row("Border color:", self._border_color_picker)
        self._canvas_section.add_row("Border opacity:", self._border_opacity_spin)
        self._canvas_section.add_row("Border style:", self._border_style_combo)
        self._border_shadow_check = QCheckBox("Border shadow")
        self._border_shadow_check.setAccessibleName("Canvas border shadow")
        self._border_shadow_color = ColorPicker(QColor(DEFAULT_SHADOW_COLOR))
        self._border_shadow_color.setAccessibleName("Canvas border shadow color")
        self._border_shadow_dx = QDoubleSpinBox()
        self._border_shadow_dx.setRange(-100.0, 100.0)
        self._border_shadow_dx.setSuffix(" px")
        self._border_shadow_dx.setKeyboardTracking(False)
        self._border_shadow_dx.setAccessibleName("Canvas border shadow offset X")
        self._border_shadow_dy = QDoubleSpinBox()
        self._border_shadow_dy.setRange(-100.0, 100.0)
        self._border_shadow_dy.setSuffix(" px")
        self._border_shadow_dy.setKeyboardTracking(False)
        self._border_shadow_dy.setAccessibleName("Canvas border shadow offset Y")
        self._border_shadow_blur = QDoubleSpinBox()
        self._border_shadow_blur.setRange(0.0, 100.0)
        self._border_shadow_blur.setSuffix(" px")
        self._border_shadow_blur.setKeyboardTracking(False)
        self._border_shadow_blur.setAccessibleName("Canvas border shadow blur")
        self._canvas_section.add_row("", self._border_shadow_check)
        self._canvas_section.add_row("Shadow color:", self._border_shadow_color)
        self._canvas_section.add_row("Shadow X:", self._border_shadow_dx)
        self._canvas_section.add_row("Shadow Y:", self._border_shadow_dy)
        self._canvas_section.add_row("Shadow blur:", self._border_shadow_blur)
        self._canvas_section.add_row("Pasteboard:", self._pasteboard_picker)
        self._canvas_section.add_row("Grid size:", self._grid_size_spin)
        self._canvas_section.add_row("", self._snap_check)
        self._canvas_section.add_row("DPI:", self._dpi_spin)
        self._main_layout.addWidget(self._canvas_section)

    def _connect_edit_handlers(self) -> None:
        self._x_spin.valueChanged.connect(self._on_x_changed)
        self._y_spin.valueChanged.connect(self._on_y_changed)
        self._w_spin.valueChanged.connect(self._on_w_changed)
        self._h_spin.valueChanged.connect(self._on_h_changed)
        self._rot_spin.valueChanged.connect(self._on_rotation_changed)
        self._aspect_lock.toggled.connect(self._on_aspect_lock_toggled)
        self._flip_h_btn.toggled.connect(self._on_flip_h_changed)
        self._flip_v_btn.toggled.connect(self._on_flip_v_changed)
        self._stroke_color_picker.color_changed.connect(self._on_stroke_color_changed)
        self._stroke_hex.editingFinished.connect(self._on_stroke_hex_edited)
        self._stroke_w_slider.valueChanged.connect(self._on_stroke_w_slider_changed)
        self._stroke_w_spin.valueChanged.connect(self._on_stroke_w_spin_changed)
        self._stroke_style_combo.currentIndexChanged.connect(self._on_stroke_style_changed)
        self._fill_color_picker.color_changed.connect(self._on_fill_color_changed)
        self._fill_hex.editingFinished.connect(self._on_fill_hex_edited)
        self._opacity_slider.valueChanged.connect(self._on_opacity_slider_changed)
        self._opacity_spin.valueChanged.connect(self._on_opacity_spin_changed)
        self._text_fill_opacity_slider.valueChanged.connect(
            self._on_text_fill_opacity_slider_changed
        )
        self._text_fill_opacity_spin.valueChanged.connect(self._on_text_fill_opacity_spin_changed)
        self._text_stroke_opacity_slider.valueChanged.connect(
            self._on_text_stroke_opacity_slider_changed
        )
        self._text_stroke_opacity_spin.valueChanged.connect(
            self._on_text_stroke_opacity_spin_changed
        )
        self._layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        self._locked_check.toggled.connect(self._on_locked_changed)
        self._blend_combo.currentIndexChanged.connect(self._on_blend_mode_changed)
        self._canvas_w_spin.valueChanged.connect(self._on_canvas_size_changed)
        self._canvas_h_spin.valueChanged.connect(self._on_canvas_size_changed)
        self._bg_color_picker.color_changed.connect(self._on_bg_color_changed)
        self._border_w_spin.valueChanged.connect(self._on_border_width_changed)
        self._border_color_picker.color_changed.connect(self._on_border_color_changed)
        self._border_opacity_spin.valueChanged.connect(self._on_border_opacity_changed)
        self._border_style_combo.currentIndexChanged.connect(self._on_border_style_changed)
        self._border_shadow_check.toggled.connect(self._on_border_shadow_changed)
        self._border_shadow_color.color_changed.connect(self._on_border_shadow_changed)
        self._border_shadow_dx.valueChanged.connect(self._on_border_shadow_changed)
        self._border_shadow_dy.valueChanged.connect(self._on_border_shadow_changed)
        self._border_shadow_blur.valueChanged.connect(self._on_border_shadow_changed)
        self._pasteboard_picker.color_changed.connect(self._on_pasteboard_color_changed)
        self._grid_size_spin.valueChanged.connect(self._on_grid_size_changed)
        self._snap_check.toggled.connect(self._on_snap_toggled)
        self._dpi_spin.valueChanged.connect(self._on_dpi_changed)
        self._font_combo.currentFontChanged.connect(self._on_font_family_changed)
        self._font_size_spin.valueChanged.connect(self._on_font_size_changed)
        self._weight_combo.currentIndexChanged.connect(self._on_weight_changed)
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)
        self._underline_check.toggled.connect(self._on_underline_changed)
        self._text_color_picker.color_changed.connect(self._on_text_color_changed)
        self._text_align_combo.currentIndexChanged.connect(self._on_text_align_changed)
        self._line_spacing_spin.valueChanged.connect(self._on_line_spacing_changed)
        self._text_bg_color_picker.color_changed.connect(self._on_text_bg_color_changed)
        self._text_border_color_picker.color_changed.connect(self._on_text_border_color_changed)
        self._text_border_w_spin.valueChanged.connect(self._on_text_border_w_changed)
        self._text_corner_radius_spin.valueChanged.connect(self._on_text_corner_radius_changed)
        self._text_padding_spin.valueChanged.connect(self._on_text_padding_changed)
        self._text_valign_combo.currentIndexChanged.connect(self._on_text_valign_changed)
        self._text_auto_size_check.toggled.connect(self._on_text_auto_size_changed)
        self._arrow_head_combo.currentIndexChanged.connect(self._on_arrow_head_changed)
        self._arrow_tail_combo.currentIndexChanged.connect(self._on_arrow_tail_changed)
        self._arrow_size_combo.currentIndexChanged.connect(self._on_arrow_size_changed)
        self._arrow_custom_spin.valueChanged.connect(self._on_arrow_custom_changed)
        self._arrow_line_style_combo.currentIndexChanged.connect(self._on_arrow_line_style_changed)
        self._corner_radius_slider.valueChanged.connect(self._on_corner_radius_slider_changed)
        self._corner_radius_spin.valueChanged.connect(self._on_corner_radius_spin_changed)
        self._corner_mode_check.toggled.connect(self._on_corner_mode_changed)
        for key, spin in self._corner_spins.items():
            spin.valueChanged.connect(lambda v, k=key: self._on_corner_spin_changed(k, v))
        self._freehand_smoothing_slider.valueChanged.connect(
            self._on_freehand_smoothing_slider_changed
        )
        self._freehand_smoothing_spin.valueChanged.connect(
            self._on_freehand_smoothing_spin_changed
        )
        self._freehand_closed_check.toggled.connect(self._on_freehand_closed_changed)
        self._polygon_sides_spin.valueChanged.connect(self._on_polygon_sides_changed)
        for combo, prop in (
            (self._blur_mode_combo, "blur_mode"),
            (self._blur_shape_combo, "region_shape"),
        ):
            combo.currentIndexChanged.connect(
                lambda index, c=combo, p=prop: self._on_blur_combo_changed(c, p, index)
            )
        blur_spins: list[tuple[QSpinBox | QDoubleSpinBox, str, float]] = [
            (self._blur_radius_spin, "blur_radius", BLUR_RADIUS_MIN),
            (self._blur_pixel_spin, "pixel_size", float(BLUR_PIXEL_SIZE_MIN)),
            (self._blur_corner_spin, "corner_radius", 0.0),
            (self._blur_feather_spin, "feather", 0.0),
            (self._blur_opacity_spin, "opacity_pct", 0.0),
            (self._blur_border_spin, "border_width", 0.0),
        ]
        for blur_spin, prop, low in blur_spins:
            blur_spin.valueChanged.connect(
                lambda value, p=prop, lo=low: self._on_blur_value_changed(p, value, lo)
            )
        self._blur_fill_picker.color_changed.connect(
            lambda color: self._on_blur_value_changed("fill_color", QColor(color), None)
        )
        self._blur_border_picker.color_changed.connect(
            lambda color: self._on_blur_value_changed("border_color", QColor(color), None)
        )
        self._blur_invert_check.toggled.connect(
            lambda checked: self._on_blur_value_changed("invert_mask", bool(checked), None)
        )
        self._blur_brush_spin.valueChanged.connect(self._on_blur_brush_size_changed)
        self._highlight_straighten_check.toggled.connect(
            lambda checked: self._on_highlight_default("auto_straighten", bool(checked))
        )
        self._highlight_snap_check.toggled.connect(
            lambda checked: self._on_highlight_default("snap_to_axis", bool(checked))
        )
        self._highlight_threshold_spin.valueChanged.connect(
            lambda value: self._on_highlight_default("straighten_threshold", float(value))
        )
        self._blur_source_combo.currentIndexChanged.connect(
            lambda index: self._on_blur_combo_changed(
                self._blur_source_combo, "source_mode", index
            )
        )
        self._blur_source_layer_combo.currentIndexChanged.connect(
            self._on_blur_source_layer_changed
        )
        self._polygon_star_check.toggled.connect(
            lambda checked: self._on_polygon_flag_changed("star_enabled", checked)
        )
        self._polygon_indent_spin.valueChanged.connect(self._on_polygon_indent_changed)
        self._polygon_closed_check.toggled.connect(
            lambda checked: self._on_polygon_flag_changed("closed", checked)
        )
        for combo, prop in (
            (self._arc_type_combo, "arc_type"),
            (self._arc_head_combo, "head_style"),
            (self._arc_tail_combo, "tail_style"),
            (self._arc_size_combo, "head_size"),
        ):
            combo.currentIndexChanged.connect(
                lambda index, c=combo, p=prop: self._on_arc_combo_changed(c, p, index)
            )
        self._step_value_spin.valueChanged.connect(self._on_step_value_changed)
        self._step_mode_combo.currentIndexChanged.connect(self._on_step_mode_changed)
        self._step_text_edit.editingFinished.connect(self._on_step_text_edited)
        self._step_shape_combo.currentIndexChanged.connect(self._on_step_shape_changed)
        self._step_size_spin.valueChanged.connect(self._on_step_size_changed)
        self._step_weight_combo.currentIndexChanged.connect(self._on_step_weight_changed)
        self._step_border_style_combo.currentIndexChanged.connect(
            self._on_step_border_style_changed
        )
        self._fill_opacity_slider.valueChanged.connect(self._on_fill_opacity_slider_changed)
        self._fill_opacity_spin.valueChanged.connect(self._on_fill_opacity_spin_changed)
        self._stroke_opacity_slider.valueChanged.connect(self._on_stroke_opacity_slider_changed)
        self._stroke_opacity_spin.valueChanged.connect(self._on_stroke_opacity_spin_changed)
        self._step_label_edit.editingFinished.connect(self._on_step_label_edited)
        self._step_label_pos_combo.currentIndexChanged.connect(self._on_step_label_pos_changed)
        self._step_label_size_spin.valueChanged.connect(self._on_step_label_size_changed)
        self._step_label_color_picker.color_changed.connect(self._on_step_label_color_changed)
        self._step_label_bg_picker.color_changed.connect(self._on_step_label_bg_changed)
        self._step_label_pill_check.toggled.connect(self._on_step_label_pill_changed)
        self._shadow_check.toggled.connect(self._on_shadow_enabled_changed)
        self._shadow_color_picker.color_changed.connect(self._on_shadow_color_changed)
        self._shadow_x_spin.valueChanged.connect(self._on_shadow_x_changed)
        self._shadow_y_spin.valueChanged.connect(self._on_shadow_y_changed)
        self._shadow_blur_slider.valueChanged.connect(self._on_shadow_blur_slider_changed)
        self._shadow_blur_spin.valueChanged.connect(self._on_shadow_blur_spin_changed)
        self._stamp_change_button.clicked.connect(self._on_stamp_change_clicked)
        self._stamp_size_spin.valueChanged.connect(self._on_stamp_size_changed)
        self._stamp_color_picker.color_changed.connect(self._on_stamp_color_changed)
        self._stamp_secondary_picker.color_changed.connect(self._on_stamp_secondary_changed)
        self._stamp_opacity_slider.valueChanged.connect(self._on_stamp_opacity_slider_changed)
        self._stamp_opacity_spin.valueChanged.connect(self._on_stamp_opacity_spin_changed)
        self._emoji_change_button.clicked.connect(self._on_emoji_change_clicked)
        self._emoji_size_spin.valueChanged.connect(self._on_emoji_size_changed)
        self._emoji_tone_combo.currentIndexChanged.connect(self._on_emoji_tone_changed)
        self._emoji_opacity_slider.valueChanged.connect(self._on_emoji_opacity_slider_changed)
        self._emoji_opacity_spin.valueChanged.connect(self._on_emoji_opacity_spin_changed)

    # ------------------------------------------------------------ wiring

    def _connect_selection_signals(self) -> None:
        self._selection_manager.selection_changed.connect(self._refresh_from_selection)
        self._selection_manager.selection_cleared.connect(self._refresh_from_selection)

    def _disconnect_selection_signals(self) -> None:
        for signal in (
            self._selection_manager.selection_changed,
            self._selection_manager.selection_cleared,
        ):
            try:
                signal.disconnect(self._refresh_from_selection)
            except (TypeError, RuntimeError):
                pass

    def _scene_signal_pairs(self) -> list[tuple[Any, Callable[..., None]]]:
        lm = self._scene.layer_manager
        return [
            (self._scene.command_stack.stack_changed, self._refresh_from_selection),
            (self._scene.canvas_size_changed, self._refresh_from_selection),
            (self._scene.background_changed, self._refresh_from_selection),
            (self._scene.canvas_dpi_changed, self._refresh_from_selection),
            (self._scene.border_changed, self._refresh_from_selection),
            (lm.layer_added, self._rebuild_layer_combo),
            (lm.layer_removed, self._rebuild_layer_combo),
            (lm.layer_renamed, self._rebuild_layer_combo),
        ]

    def _connect_scene_signals(self) -> None:
        for signal, slot in self._scene_signal_pairs():
            signal.connect(slot)

    def _disconnect_scene_signals(self) -> None:
        for signal, slot in self._scene_signal_pairs():
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _on_section_toggled(self, expanded: bool) -> None:
        section = self.sender()
        if isinstance(section, CollapsibleSection):
            self._settings.set_property_section_expanded(section.title, expanded)

    def _on_theme_changed(self, _name: str) -> None:
        self._apply_icons()
        self._apply_strip_icons()
        self._refresh_from_selection()

    def _apply_icons(self) -> None:
        manager = theme_manager()
        name = "link" if self._aspect_lock.isChecked() else "link-off"
        icon = manager.icon(name)
        if not icon.isNull():
            self._aspect_lock.setIcon(icon)

    # ---------------------------------------------------------- selection

    def _selected_items(self) -> list[SnapGraphicsItem]:
        return [i for i in self._selection_manager.items if isinstance(i, SnapGraphicsItem)]

    def _first_selected_item(self) -> SnapGraphicsItem | None:
        items = self._selected_items()
        return items[0] if items else None

    def _selected_vectors(self) -> list[VectorItem]:
        """The vector items an Appearance edit reaches: a group stands for its vector
        members, nested groups included (Group and Ungroup kickoff, silence 2)."""
        found: list[VectorItem] = []
        for item in self._selected_items():
            if isinstance(item, VectorItem):
                found.append(item)
            elif isinstance(item, GroupItem):
                found.extend(m for m in item.descendants() if isinstance(m, VectorItem))
        return found

    @staticmethod
    def _shows_appearance(item: SnapGraphicsItem) -> bool:
        """Whether *item* takes the Appearance section: a vector item, or a group with
        at least one vector item below it."""
        if isinstance(item, VectorItem):
            return True
        if isinstance(item, GroupItem):
            return any(isinstance(m, VectorItem) for m in item.descendants())
        return False

    def _selected_rectangles(self) -> list[RectangleItem]:
        return [i for i in self._selected_items() if isinstance(i, RectangleItem)]

    def _selected_freehand(self) -> list[FreehandItem]:
        return [i for i in self._selected_items() if isinstance(i, FreehandItem)]

    def _selected_blurs(self) -> list[BlurItem]:
        return [i for i in self._selected_items() if isinstance(i, BlurItem)]

    def _selected_polygons(self) -> list[PolygonItem]:
        return [i for i in self._selected_items() if isinstance(i, PolygonItem)]

    def _selected_arcs(self) -> list[ArcItem]:
        return [i for i in self._selected_items() if isinstance(i, ArcItem)]

    def _selected_arrows(self) -> list[ArrowItem]:
        return [i for i in self._selected_items() if isinstance(i, ArrowItem)]

    def _selected_steps(self) -> list[NumberedStepItem]:
        return [i for i in self._selected_items() if isinstance(i, NumberedStepItem)]

    def _selected_stamps(self) -> list[StampItem]:
        return [i for i in self._selected_items() if isinstance(i, StampItem)]

    def _selected_emoji(self) -> list[EmojiItem]:
        return [i for i in self._selected_items() if isinstance(i, EmojiItem)]

    @staticmethod
    def _shows_shadow(item: SnapGraphicsItem) -> bool:
        """Whether *item* takes the Shadow section: an item carrying the shadow helper, or
        a group with at least one such item below it (silence 12)."""
        if isinstance(item, ShadowMixin):
            return True
        if isinstance(item, GroupItem):
            return any(isinstance(m, ShadowMixin) for m in item.descendants())
        return False

    def _selected_shadowed(self) -> list[Any]:
        """The items a Shadow edit reaches: every selected item carrying the shadow helper,
        a group standing for its shadow-carrying members."""
        found: list[Any] = []
        for item in self._selected_items():
            if isinstance(item, ShadowMixin):
                found.append(item)
            elif isinstance(item, GroupItem):
                found.extend(m for m in item.descendants() if isinstance(m, ShadowMixin))
        return found

    def _selected_non_vectors(self) -> list[SnapGraphicsItem]:
        """The selected items with one opacity of their own: groups and non-vector items."""
        return [i for i in self._selected_items() if not isinstance(i, VectorItem)]

    def _selected_text_items(self) -> list[_TextLike]:
        return [i for i in self._selected_items() if isinstance(i, (TextItem, CalloutItem))]

    # ------------------------------------------------------------ refresh

    def _refresh_from_selection(self, *_args: object) -> None:  # noqa: C901
        self._updating = True
        try:
            items = self._selected_items()
            has_selection = bool(items)
            all_vector = has_selection and all(self._shows_appearance(i) for i in items)
            all_text = has_selection and all(isinstance(i, (TextItem, CalloutItem)) for i in items)
            all_text_items = has_selection and all(isinstance(i, TextItem) for i in items)
            all_arrows = has_selection and all(isinstance(i, ArrowItem) for i in items)
            all_arcs = has_selection and all(isinstance(i, ArcItem) for i in items)
            all_polygons = has_selection and all(isinstance(i, PolygonItem) for i in items)
            all_blurs = has_selection and all(isinstance(i, BlurItem) for i in items)
            all_rectangles = has_selection and all(isinstance(i, RectangleItem) for i in items)
            all_freehand = has_selection and all(isinstance(i, FreehandItem) for i in items)
            all_steps = has_selection and all(isinstance(i, NumberedStepItem) for i in items)
            all_shadow = has_selection and all(self._shows_shadow(i) for i in items)
            all_stamps = has_selection and all(isinstance(i, StampItem) for i in items)
            all_emoji = has_selection and all(isinstance(i, EmojiItem) for i in items)

            in_tool_defaults = not has_selection and self._active_tool_id in ("text", "callout")
            in_vector_defaults = not has_selection and self._active_tool_id in _VECTOR_TOOL_IDS

            # Section visibility (PRD 8.3 to 8.6)
            self._transform_section.setVisible(has_selection)
            self._appearance_section.setVisible(all_vector or in_vector_defaults)
            self._arrow_section.setVisible(all_arrows)
            self._arc_section.setVisible(all_arcs)
            self._polygon_section.setVisible(all_polygons)
            self._blur_section.setVisible(all_blurs)
            in_highlight_defaults = not has_selection and self._active_tool_id == "highlight"
            self._highlight_section.setVisible(in_highlight_defaults)
            if in_highlight_defaults:
                self._populate_highlight_defaults()
            self._rectangle_section.setVisible(all_rectangles)
            self._freehand_section.setVisible(all_freehand)
            self._step_section.setVisible(all_steps)
            self._stamp_section.setVisible(all_stamps)
            self._emoji_section.setVisible(all_emoji)
            self._shadow_section.setVisible(all_shadow)
            self._text_section.setVisible(all_text or in_tool_defaults)
            self._text_box_section.setVisible(all_text or in_tool_defaults)
            self._info_section.setVisible(has_selection)
            self._canvas_section.setVisible(
                not has_selection and not in_tool_defaults and not in_vector_defaults
            )

            # The single Opacity row is a group's own (decision 2); the fill rows are for
            # the tools and items that have a fill.
            self._set_row_visible(
                self._appearance_section, self._opacity_row, bool(self._selected_non_vectors())
            )
            defaults = self._active_tool_defaults() if in_vector_defaults else None
            has_fill = defaults is None or "fill_color" in defaults
            self._set_row_visible(self._appearance_section, self._fill_row, has_fill)
            self._set_row_visible(self._appearance_section, self._fill_opacity_row, has_fill)

            if in_vector_defaults:
                self._populate_appearance_from_tool_defaults()
            elif in_tool_defaults:
                self._populate_from_tool_defaults()
            elif items:
                self._populate_transform(items)
                if all_vector:
                    self._populate_appearance(self._selected_vectors())
                if all_text:
                    self._populate_text(self._selected_text_items(), all_text_items)
                if all_arrows:
                    self._populate_arrow(self._selected_arrows())
                if all_arcs:
                    self._populate_arc(self._selected_arcs())
                if all_polygons:
                    self._populate_polygon(self._selected_polygons())
                if all_blurs:
                    self._populate_blur(self._selected_blurs())
                if all_rectangles:
                    self._populate_rectangle(self._selected_rectangles())
                if all_freehand:
                    self._populate_freehand(self._selected_freehand())
                if all_steps:
                    self._populate_step(self._selected_steps())
                if all_stamps:
                    self._populate_stamp(self._selected_stamps())
                if all_emoji:
                    self._populate_emoji(self._selected_emoji())
                if all_shadow:
                    self._populate_shadow(self._selected_shadowed())
                self._populate_info(items)
            else:
                self._populate_canvas()
        finally:
            self._updating = False

    def _populate_transform(self, items: list[SnapGraphicsItem]) -> None:
        self._set_spin(self._x_spin, [i.pos_x for i in items])
        self._set_spin(self._y_spin, [i.pos_y for i in items])
        self._set_spin(self._w_spin, [i.boundingRect().width() for i in items])
        self._set_spin(self._h_spin, [i.boundingRect().height() for i in items])
        self._set_spin(self._rot_spin, [i.rotation_deg for i in items])
        self._set_toggle(self._flip_h_btn, [i.flip_horizontal for i in items])
        self._set_toggle(self._flip_v_btn, [i.flip_vertical for i in items])
        self._apply_icons()

    def _populate_appearance(self, items: list[VectorItem]) -> None:
        self._set_color(
            self._stroke_color_picker, self._stroke_hex, [i.stroke_color for i in items]
        )
        widths = [i.stroke_width for i in items]
        value, uniform = _uniform(widths)
        self._stroke_w_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._stroke_w_spin, widths)
        self._set_combo_data(self._stroke_style_combo, [i.stroke_style for i in items])
        self._set_color(self._fill_color_picker, self._fill_hex, [i.fill_color for i in items])
        fills = [int(round(i.fill_opacity * 100)) for i in items]
        value, uniform = _uniform(fills)
        self._fill_opacity_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._fill_opacity_spin, fills)
        strokes = [int(round(i.stroke_opacity * 100)) for i in items]
        value, uniform = _uniform(strokes)
        self._stroke_opacity_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._stroke_opacity_spin, strokes)
        # The single Opacity is a group's own, not its members'
        opacities = [int(i.opacity_pct) for i in self._selected_non_vectors()]
        if opacities:
            value, uniform = _uniform(opacities)
            self._opacity_slider.setValue(int(value) if uniform else 0)
            self._set_spin(self._opacity_spin, opacities)

    def _populate_text(self, items: list[_TextLike], all_text_items: bool) -> None:
        first = items[0]
        if len(items) == 1 and first.is_editing:
            self._ensure_editor_connected()
            self._refresh_text_from_cursor()
        else:
            self._disconnect_editor()
            fonts = [i.font for i in items]
            family, uniform = _uniform([f.family() for f in fonts])
            if uniform:
                self._font_combo.setCurrentFont(QFont(family))
            else:
                self._clear_font_combo()
            self._set_spin(self._font_size_spin, [f.pointSize() for f in fonts])
            self._set_combo_data(
                self._weight_combo,
                [QFont.Weight.Bold if f.bold() else QFont.Weight.Normal for f in fonts],
            )
            self._set_combo_data(self._style_combo, [f.italic() for f in fonts])
            self._set_check(self._underline_check, [f.underline() for f in fonts])
            self._set_color(self._text_color_picker, None, [i.text_color for i in items])
            alignments = [
                int(i.get_block_format().alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask)
                for i in items
            ]
            value, uniform = _uniform(alignments)
            if uniform:
                self._set_align_combo(Qt.AlignmentFlag(value))
            else:
                self._text_align_combo.setCurrentIndex(-1)
            spacings = [s for i in items for s in i.paragraph_line_spacings()]
            self._set_spin(self._line_spacing_spin, spacings)
        self._set_color(self._text_bg_color_picker, None, [i.bg_color for i in items])
        self._set_color(self._text_border_color_picker, None, [i.border_color for i in items])
        self._set_spin(self._text_border_w_spin, [i.border_width for i in items])
        fills = [int(round(i.fill_opacity * 100)) for i in items]
        value, uniform = _uniform(fills)
        self._text_fill_opacity_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._text_fill_opacity_spin, fills)
        strokes = [int(round(i.stroke_opacity * 100)) for i in items]
        value, uniform = _uniform(strokes)
        self._text_stroke_opacity_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._text_stroke_opacity_spin, strokes)
        self._set_spin(self._text_corner_radius_spin, [i.border_radius for i in items])
        self._set_spin(self._text_padding_spin, [i.padding for i in items])
        self._set_combo_data(self._text_valign_combo, [i.vertical_align for i in items])
        self._text_auto_size_check.setVisible(all_text_items)
        if all_text_items:
            self._set_check(
                self._text_auto_size_check,
                [i.auto_size for i in items if isinstance(i, TextItem)],
            )

    def _populate_rectangle(self, items: list[RectangleItem]) -> None:
        radii = [i.corner_radius for i in items]
        value, uniform = _uniform(radii)
        self._corner_radius_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._corner_radius_spin, radii)
        modes = [i.corner_radius_mode is CornerRadiusMode.INDIVIDUAL for i in items]
        self._set_check(self._corner_mode_check, modes)
        individual = all(modes)
        section = self._rectangle_section
        self._set_row_visible(section, self._corner_radius_row, not individual)
        for key, spin in self._corner_spins.items():
            self._set_row_visible(section, spin, individual)
            self._set_spin(spin, [getattr(i, key) for i in items])

    def _populate_freehand(self, items: list[FreehandItem]) -> None:
        percents = [int(round(i.smoothing * 100)) for i in items]
        value, uniform = _uniform(percents)
        self._freehand_smoothing_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._freehand_smoothing_spin, percents)
        self._set_check(self._freehand_closed_check, [i.is_closed for i in items])

    def _populate_blur(self, items: list[BlurItem]) -> None:
        section = self._blur_section
        modes = [i.blur_mode for i in items]
        self._set_combo_data(self._blur_mode_combo, modes)
        self._set_row_visible(section, self._blur_radius_spin, set(modes) == {BlurMode.GAUSSIAN})
        self._set_row_visible(section, self._blur_pixel_spin, set(modes) == {BlurMode.PIXELATE})
        self._set_row_visible(section, self._blur_fill_picker, set(modes) == {BlurMode.SOLID})
        shapes = [i.region_shape for i in items]
        self._set_combo_data(self._blur_shape_combo, shapes)
        rectangles = set(shapes) == {BlurRegionShape.RECTANGLE}
        self._set_row_visible(section, self._blur_corner_spin, rectangles)
        freeform = set(shapes) == {BlurRegionShape.FREEFORM}
        self._set_row_visible(section, self._blur_brush_spin, freeform)
        if freeform:
            self._blur_brush_spin.setValue(int(round(self._brush_size())))
        sources = [i.source_mode for i in items]
        self._set_combo_data(self._blur_source_combo, sources)
        specific = set(sources) == {BlurSourceMode.SPECIFIC_LAYER}
        self._set_row_visible(section, self._blur_source_layer_combo, specific)
        self._fill_source_layers([i.source_layer_id for i in items])
        self._set_spin(self._blur_radius_spin, [i.blur_radius for i in items])
        self._set_spin(self._blur_pixel_spin, [i.pixel_size for i in items])
        self._set_color(self._blur_fill_picker, None, [i.fill_color for i in items])
        self._set_spin(self._blur_corner_spin, [i.corner_radius for i in items])
        self._set_spin(self._blur_feather_spin, [i.feather for i in items])
        self._set_check(self._blur_invert_check, [i.invert_mask for i in items])
        self._set_spin(self._blur_opacity_spin, [int(round(i.opacity_pct)) for i in items])
        self._set_color(self._blur_border_picker, None, [i.border_color for i in items])
        self._set_spin(self._blur_border_spin, [i.border_width for i in items])

    def _populate_polygon(self, items: list[PolygonItem]) -> None:
        regular = all(i.polygon_mode is PolygonMode.REGULAR for i in items)
        section = self._polygon_section
        for widget in (
            self._polygon_sides_spin,
            self._polygon_star_check,
            self._polygon_indent_spin,
        ):
            self._set_row_visible(section, widget, regular)
        self._set_row_visible(section, self._polygon_closed_check, not regular)
        self._set_spin(self._polygon_sides_spin, [i.sides for i in items])
        self._set_check(self._polygon_star_check, [i.star_enabled for i in items])
        self._set_spin(self._polygon_indent_spin, [i.star_indent for i in items])
        self._set_check(self._polygon_closed_check, [i.closed for i in items])

    def _populate_arc(self, items: list[ArcItem]) -> None:
        self._set_combo_data(self._arc_type_combo, [i.arc_type for i in items])
        self._set_combo_data(self._arc_head_combo, [i.head_style for i in items])
        self._set_combo_data(self._arc_tail_combo, [i.tail_style for i in items])
        self._set_combo_data(self._arc_size_combo, [i.head_size for i in items])

    def _populate_arrow(self, items: list[ArrowItem]) -> None:
        self._set_combo_data(self._arrow_head_combo, [i.head_style for i in items])
        self._set_combo_data(self._arrow_tail_combo, [i.tail_style for i in items])
        self._set_combo_data(self._arrow_size_combo, [i.head_size for i in items])
        self._set_spin(self._arrow_custom_spin, [i.head_size_custom for i in items])
        self._set_combo_data(self._arrow_line_style_combo, [i.line_style for i in items])

    def _populate_step(self, items: list[NumberedStepItem]) -> None:
        self._set_spin(self._step_value_spin, [i.number_value for i in items])
        self._set_combo_data(self._step_mode_combo, [i.display_mode for i in items])
        text, uniform = _uniform([i.custom_text for i in items])
        self._step_text_edit.setText(str(text) if uniform else "")
        self._set_combo_data(self._step_shape_combo, [i.badge_shape for i in items])
        self._set_spin(self._step_size_spin, [i.badge_size for i in items])
        self._set_combo_data(self._step_weight_combo, [i.font_weight for i in items])
        self._set_combo_data(self._step_border_style_combo, [i.border_style for i in items])
        label, uniform = _uniform([i.label_text for i in items])
        self._step_label_edit.setText(str(label) if uniform else "")
        self._set_combo_data(self._step_label_pos_combo, [i.label_position for i in items])
        self._set_spin(self._step_label_size_spin, [i.label_font_size for i in items])
        self._set_color(self._step_label_color_picker, None, [i.label_color for i in items])
        self._set_color(self._step_label_bg_picker, None, [i.label_background for i in items])
        self._set_check(self._step_label_pill_check, [i.label_background_enabled for i in items])

    def _populate_stamp(self, items: list[StampItem]) -> None:
        names = [i.stamp_name for i in items]
        name, uniform = _uniform(names)
        self._stamp_name_label.setText(str(name) if uniform else f"{len(items)} stamps")
        self._set_spin(self._stamp_size_spin, [i.stamp_size for i in items])
        self._set_color(self._stamp_color_picker, None, [i.stamp_color for i in items])
        self._set_color(
            self._stamp_secondary_picker, None, [i.stamp_secondary_color for i in items]
        )
        opacities = [int(round(i.opacity_pct)) for i in items]
        value, uniform = _uniform(opacities)
        self._stamp_opacity_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._stamp_opacity_spin, opacities)

    def _populate_emoji(self, items: list[EmojiItem]) -> None:
        name, uniform = _uniform([i.emoji_name for i in items])
        self._emoji_name_label.setText(str(name) if uniform else f"{len(items)} emoji")
        self._set_spin(self._emoji_size_spin, [i.emoji_size for i in items])
        self._set_combo_data(self._emoji_tone_combo, [i.skin_tone for i in items])
        opacities = [int(round(i.opacity_pct)) for i in items]
        value, uniform = _uniform(opacities)
        self._emoji_opacity_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._emoji_opacity_spin, opacities)

    def _populate_shadow(self, items: list[Any]) -> None:
        self._set_check(self._shadow_check, [bool(i.shadow_enabled) for i in items])
        self._set_color(self._shadow_color_picker, None, [QColor(i.shadow_color) for i in items])
        self._set_spin(self._shadow_x_spin, [float(i.shadow_offset_x) for i in items])
        self._set_spin(self._shadow_y_spin, [float(i.shadow_offset_y) for i in items])
        blurs = [float(i.shadow_blur) for i in items]
        value, uniform = _uniform(blurs)
        self._shadow_blur_slider.setValue(int(value) if uniform else 0)
        self._set_spin(self._shadow_blur_spin, blurs)

    def _populate_info(self, items: list[SnapGraphicsItem]) -> None:
        self._set_combo_data(self._blend_combo, [i.blend_mode for i in items])
        value, uniform = _uniform([i.type_name for i in items])
        text = str(value) if uniform else f"{len(items)} items"
        if len(items) == 1 and isinstance(items[0], GroupItem):
            count = items[0].member_count
            text = f"Group ({count} item{'' if count == 1 else 's'})"
        self._type_label.setText(text)
        self._rebuild_layer_combo()
        self._set_check(self._locked_check, [i.locked for i in items])

    def _populate_canvas(self) -> None:
        cs = self._scene.canvas_size
        self._canvas_w_spin.setValue(int(cs.width()))
        self._canvas_h_spin.setValue(int(cs.height()))
        self._bg_color_picker.color = self._scene.background_color
        self._border_w_spin.setRange(0, max(1, self._scene.max_border_width()))
        self._border_w_spin.setValue(self._scene.border_width)
        border_color = self._scene.border_color
        self._border_color_picker.color = border_color
        self._border_opacity_spin.setValue(round(border_color.alpha() / 255 * 100))
        index = self._border_style_combo.findData(self._scene.border_style)
        if index >= 0:
            self._border_style_combo.setCurrentIndex(index)
        shadow = self._scene.border_shadow
        self._border_shadow_check.setChecked(bool(shadow.get("shadow_enabled", False)))
        self._border_shadow_color.color = QColor(str(shadow.get("shadow_color", "#66000000")))
        self._border_shadow_dx.setValue(float(shadow.get("shadow_offset_x", 0.0)))
        self._border_shadow_dy.setValue(float(shadow.get("shadow_offset_y", 0.0)))
        self._border_shadow_blur.setValue(float(shadow.get("shadow_blur", 0.0)))
        pasteboard = self._settings.pasteboard_color()
        self._pasteboard_picker.color = (
            pasteboard if pasteboard is not None else current_theme().pasteboard
        )
        self._grid_size_spin.setValue(self._settings.grid_size())
        self._snap_check.setChecked(self._settings.snap_to_grid())
        self._dpi_spin.setValue(self._scene.canvas_dpi)

    # mixed-value helpers (PRD 8.6)

    @staticmethod
    def _set_spin(spin: QSpinBox | QDoubleSpinBox, values: list[Any]) -> None:
        value, uniform = _uniform([round(float(v), 3) for v in values])
        if isinstance(spin, QSpinBox):
            spin.setValue(int(value) if uniform else spin.minimum())
        else:
            spin.setValue(float(value) if uniform else spin.minimum())

    @staticmethod
    def _set_color(picker: ColorPicker, edit: QLineEdit | None, values: list[QColor]) -> None:
        value, uniform = _uniform(values, _color_key)
        if uniform:
            picker.color = QColor(value)
            if edit is not None:
                edit.setText(_hex_text(QColor(value)))
        else:
            picker.mixed = True
            if edit is not None:
                edit.setText("")

    @staticmethod
    def _set_combo_data(combo: QComboBox, values: list[Any]) -> None:
        value, uniform = _uniform(values)
        if not uniform:
            combo.setCurrentIndex(-1)
            return
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(-1)

    @staticmethod
    def _set_check(check: QCheckBox, values: list[bool]) -> None:
        value, uniform = _uniform(values)
        if uniform:
            check.setTristate(False)
            check.setChecked(bool(value))
        else:
            check.setTristate(True)
            check.setCheckState(Qt.CheckState.PartiallyChecked)

    @staticmethod
    def _set_toggle(button: QPushButton, values: list[bool]) -> None:
        value, uniform = _uniform(values)
        button.setChecked(bool(value) if uniform else False)
        button.setToolTip("" if uniform else "Mixed")

    def _clear_font_combo(self) -> None:
        line_edit = self._font_combo.lineEdit()
        if line_edit is not None:
            line_edit.setText("")

    # tool defaults (PRD 8.5)

    def _in_tool_defaults_mode(self) -> bool:
        """Return True if showing tool defaults (no selection + text/callout tool)."""
        return self._first_selected_item() is None and self._active_tool_id in ("text", "callout")

    def _in_vector_defaults_mode(self) -> bool:
        """Return True if showing vector tool defaults (no selection + vector tool)."""
        return self._first_selected_item() is None and self._active_tool_id in _VECTOR_TOOL_IDS

    def _active_tool_defaults(self) -> dict[str, Any] | None:
        """Return the creation_defaults dict for the active tool, or None."""
        if self._tool_manager is None:
            return None
        tool = self._tool_manager.tool(self._active_tool_id)
        if tool is None:
            return None
        return tool.creation_defaults

    def _populate_from_tool_defaults(self) -> None:
        """Fill Text + Text Box widgets from the active tool's creation_defaults."""
        d = self._active_tool_defaults()
        if d is None:
            return
        font = QFont(str(d.get("font_family", "Sans Serif")))
        font.setPointSize(int(d.get("font_size", 14)))
        self._font_combo.setCurrentFont(font)
        self._font_size_spin.setValue(int(d.get("font_size", 14)))
        self._set_combo_data(
            self._weight_combo,
            [QFont.Weight.Bold if bool(d.get("bold", False)) else QFont.Weight.Normal],
        )
        self._set_combo_data(self._style_combo, [bool(d.get("italic", False))])
        self._set_check(self._underline_check, [bool(d.get("underline", False))])
        tc = d.get("text_color")
        self._text_color_picker.color = QColor(tc) if isinstance(tc, QColor) else QColor("black")

        ha = d.get("horizontal_align", Qt.AlignmentFlag.AlignLeft)
        if isinstance(ha, Qt.AlignmentFlag):
            self._set_align_combo(ha)
        self._line_spacing_spin.setValue(float(d.get("line_spacing", DEFAULT_LINE_SPACING)))

        bg = d.get("bg_color")
        self._text_bg_color_picker.color = (
            QColor(bg) if isinstance(bg, QColor) else QColor("#00000000")
        )
        bc = d.get("border_color")
        self._text_border_color_picker.color = (
            QColor(bc) if isinstance(bc, QColor) else QColor("#00000000")
        )
        self._text_border_w_spin.setValue(float(d.get("border_width", 0.0)))
        fill_pct = int(round(float(d.get("fill_opacity", 1.0)) * 100))
        self._text_fill_opacity_slider.setValue(fill_pct)
        self._text_fill_opacity_spin.setValue(fill_pct)
        stroke_pct = int(round(float(d.get("stroke_opacity", 1.0)) * 100))
        self._text_stroke_opacity_slider.setValue(stroke_pct)
        self._text_stroke_opacity_spin.setValue(stroke_pct)
        self._text_corner_radius_spin.setValue(float(d.get("border_radius", 0.0)))
        self._text_padding_spin.setValue(float(d.get("padding", 8.0)))
        self._set_combo_data(self._text_valign_combo, [d.get("vertical_align", VerticalAlign.TOP)])

        is_text_tool = self._active_tool_id == "text"
        self._text_auto_size_check.setVisible(is_text_tool)
        if is_text_tool:
            self._set_check(self._text_auto_size_check, [bool(d.get("auto_size", True))])

    def _populate_appearance_from_tool_defaults(self) -> None:
        """Fill Appearance widgets from the active vector tool's creation_defaults."""
        d = self._active_tool_defaults()
        if d is None:
            return
        sc = d.get("stroke_color")
        stroke = QColor(sc) if isinstance(sc, QColor) else QColor("black")
        self._set_color(self._stroke_color_picker, self._stroke_hex, [stroke])
        sw = float(d.get("stroke_width", 2.0))
        self._stroke_w_slider.setValue(int(sw))
        self._stroke_w_spin.setValue(sw)
        fc = d.get("fill_color")
        fill = QColor(fc) if isinstance(fc, QColor) else QColor("transparent")
        self._set_color(self._fill_color_picker, self._fill_hex, [fill])
        self._set_combo_data(self._stroke_style_combo, [d.get("stroke_style", BorderStyle.SOLID)])
        fill_pct = int(round(float(d.get("fill_opacity", 1.0)) * 100))
        self._fill_opacity_slider.setValue(fill_pct)
        self._fill_opacity_spin.setValue(fill_pct)
        stroke_pct = int(round(float(d.get("stroke_opacity", 1.0)) * 100))
        self._stroke_opacity_slider.setValue(stroke_pct)
        self._stroke_opacity_spin.setValue(stroke_pct)

    def _rebuild_layer_combo(self, *_args: object) -> None:
        was_updating = self._updating
        self._updating = True
        try:
            self._layer_combo.clear()
            layers = self._scene.layer_manager.layers
            items = self._selected_items()
            for layer in layers:
                self._layer_combo.addItem(layer.name, layer.layer_id)
            self._set_combo_data(self._layer_combo, [i.layer_id for i in items])
        finally:
            self._updating = was_updating

    # ------------------------------------------------------- commands

    def _push(self, command: BaseCommand) -> None:
        self._scene.command_stack.push(command)

    def _push_property(self, items: list[Any], prop: str, value: Any) -> None:
        """One undoable command that sets *prop* on every item (PRD 8.6)."""
        if not items:
            return
        if len(items) == 1:
            item = items[0]
            self._push(ModifyPropertyCommand(item, prop, getattr(item, prop), value))
        else:
            self._push(ModifyPropertiesCommand(items, prop, value))

    def _push_scale(self, items: list[SnapGraphicsItem], sx: float, sy: float) -> None:
        commands: list[BaseCommand] = [ScaleGeometryCommand(i, sx, sy) for i in items]
        if len(commands) == 1:
            self._push(commands[0])
        elif commands:
            self._push(MacroCommand(commands, "Resize items"))

    def _push_font(self, items: list[_TextLike], mutate: Callable[[QFont], None]) -> None:
        commands: list[BaseCommand] = []
        for item in items:
            new_font = QFont(item.font)
            mutate(new_font)
            commands.append(ModifyPropertyCommand(item, "font", item.font, new_font))
        if len(commands) == 1:
            self._push(commands[0])
        elif commands:
            self._push(MacroCommand(commands, "Change font"))

    def _set_default(self, key: str, value: object) -> bool:
        """Write a creation default when the panel shows tool defaults; True if it did."""
        if not (self._in_tool_defaults_mode() or self._in_vector_defaults_mode()):
            return False
        d = self._active_tool_defaults()
        if d is not None and key in d:
            d[key] = value
            self._notify_defaults_changed()
        return True

    # --- transform handlers ---

    def _on_x_changed(self, value: float) -> None:
        if self._updating or value == self._x_spin.minimum():
            return
        self._push_property(self._selected_items(), "pos_x", value)

    def _on_y_changed(self, value: float) -> None:
        if self._updating or value == self._y_spin.minimum():
            return
        self._push_property(self._selected_items(), "pos_y", value)

    def _on_w_changed(self, value: float) -> None:
        if self._updating or value <= 0:
            return
        commands: list[BaseCommand] = []
        for item in self._selected_items():
            old_w = item.boundingRect().width()
            if old_w <= 0:
                continue
            sx = value / old_w
            commands.append(ScaleGeometryCommand(item, sx, sx if self.aspect_locked else 1.0))
        self._push_commands(commands, "Resize items")

    def _on_h_changed(self, value: float) -> None:
        if self._updating or value <= 0:
            return
        commands: list[BaseCommand] = []
        for item in self._selected_items():
            old_h = item.boundingRect().height()
            if old_h <= 0:
                continue
            sy = value / old_h
            commands.append(ScaleGeometryCommand(item, sy if self.aspect_locked else 1.0, sy))
        self._push_commands(commands, "Resize items")

    def _push_commands(self, commands: list[BaseCommand], description: str) -> None:
        if len(commands) == 1:
            self._push(commands[0])
        elif commands:
            self._push(MacroCommand(commands, description))

    @property
    def aspect_locked(self) -> bool:
        """The chain-link toggle between Width and Height (PRD 8.3)."""
        return self._aspect_lock.isChecked()

    def _on_aspect_lock_toggled(self, _checked: bool) -> None:
        self._apply_icons()

    def _on_rotation_changed(self, value: float) -> None:
        if self._updating or value == self._rot_spin.minimum():
            return
        self._push_property(self._selected_items(), "rotation_deg", value)

    def _on_flip_h_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._push_property(self._selected_items(), "flip_horizontal", checked)

    def _on_flip_v_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._push_property(self._selected_items(), "flip_vertical", checked)

    # --- appearance handlers ---

    def _on_stroke_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._stroke_hex.setText(_hex_text(color))
        if self._set_default("stroke_color", QColor(color)):
            return
        self._push_property(self._selected_vectors(), "stroke_color", QColor(color))

    def _on_stroke_hex_edited(self) -> None:
        self._apply_hex(self._stroke_hex, self._stroke_color_picker)

    def _on_fill_hex_edited(self) -> None:
        self._apply_hex(self._fill_hex, self._fill_color_picker)

    def _apply_hex(self, edit: QLineEdit, picker: ColorPicker) -> None:
        """A valid hex in the input becomes the swatch colour and applies like a pick."""
        if self._updating:
            return
        color = QColor(edit.text().strip())
        if not color.isValid():
            edit.setText("" if picker.mixed else _hex_text(picker.color))
            return
        if not picker.mixed and _color_key(color) == _color_key(picker.color):
            edit.setText(_hex_text(color))
            return
        picker.color = color
        picker.color_changed.emit(QColor(color))

    def _on_stroke_w_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._stroke_w_spin.setValue(float(value))
        self._updating = False
        self._apply_stroke_width(float(value))

    def _on_stroke_w_spin_changed(self, value: float) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._stroke_w_slider.setValue(int(value))
        self._updating = False
        self._apply_stroke_width(value)

    def _apply_stroke_width(self, value: float) -> None:
        if self._set_default("stroke_width", value):
            return
        self._push_property(self._selected_vectors(), "stroke_width", value)

    def _on_fill_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._fill_hex.setText(_hex_text(color))
        if self._set_default("fill_color", QColor(color)):
            return
        self._push_property(self._selected_vectors(), "fill_color", QColor(color))

    def _on_stroke_style_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        style = self._stroke_style_combo.itemData(index)
        if not isinstance(style, BorderStyle):
            return
        if self._set_default("stroke_style", style):
            return
        self._push_property(self._selected_vectors(), "stroke_style", style)

    def _on_opacity_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._opacity_spin.setValue(value)
        self._updating = False
        self._apply_opacity(value)

    def _on_opacity_spin_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._opacity_slider.setValue(value)
        self._updating = False
        self._apply_opacity(value)

    def _apply_opacity(self, value: int) -> None:
        """The single Opacity: a group's own (decision 2); vector items keep their two."""
        self._push_property(self._selected_non_vectors(), "opacity_pct", float(value))

    # --- item info handlers ---

    def _on_layer_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        items = self._selected_items()
        target_layer_id = self._layer_combo.itemData(index)
        if not isinstance(target_layer_id, str):
            return
        moving = [i for i in items if i.layer_id != target_layer_id]
        if moving:
            self._push(MoveItemToLayerCommand(self._scene, moving, target_layer_id))

    def _on_blend_mode_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        mode = self._blend_combo.itemData(index)
        if isinstance(mode, str):
            self._push_property(self._selected_items(), "blend_mode", mode)

    def _on_locked_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._locked_check.setTristate(False)
        self._push_property(self._selected_items(), "locked", checked)

    # --- canvas handlers (PRD 8.5) ---

    def _on_canvas_size_changed(self, _value: int) -> None:
        if self._updating:
            return
        size = QSizeF(self._canvas_w_spin.value(), self._canvas_h_spin.value())
        if size == self._scene.canvas_size:
            return
        # Anchored top-left so existing content keeps its position.
        self._push(ResizeCanvasCommand(self._scene, size, 0, self._scene.background_color))

    def _on_bg_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._push(
            SetCanvasPropertyCommand(
                self._scene, "background_color", self._scene.background_color, QColor(color)
            )
        )

    def _on_border_width_changed(self, value: int) -> None:
        if self._updating or value == self._scene.border_width:
            return
        self._push(
            SetCanvasBorderCommand(
                self._scene, "border_width", self._scene.border_width, int(value)
            )
        )

    def _on_border_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        # The swatch carries no alpha of its own; the Border opacity row owns it (10.5)
        new_color = QColor(color)
        new_color.setAlpha(self._scene.border_color.alpha())
        if new_color == self._scene.border_color:
            return
        self._push(
            SetCanvasBorderCommand(
                self._scene, "border_color", self._scene.border_color, new_color
            )
        )

    def _on_border_opacity_changed(self, percent: int) -> None:
        if self._updating:
            return
        new_color = QColor(self._scene.border_color)
        new_color.setAlpha(round(max(0, min(100, percent)) / 100 * 255))
        if new_color == self._scene.border_color:
            return
        self._push(
            SetCanvasBorderCommand(
                self._scene, "border_color", self._scene.border_color, new_color
            )
        )

    def _on_border_style_changed(self, _index: int) -> None:
        if self._updating:
            return
        value = self._border_style_combo.currentData()
        if not isinstance(value, BorderStyle) or value == self._scene.border_style:
            return
        self._push(
            SetCanvasBorderCommand(self._scene, "border_style", self._scene.border_style, value)
        )

    def _on_border_shadow_changed(self, _value: object = None) -> None:
        """The border's five shadow keys, written as one command (Navigation PRD 10.6)."""
        if self._updating:
            return
        old = self._scene.border_shadow
        new = {
            "shadow_enabled": self._border_shadow_check.isChecked(),
            "shadow_color": self._border_shadow_color.color.name(QColor.NameFormat.HexArgb),
            "shadow_offset_x": self._border_shadow_dx.value(),
            "shadow_offset_y": self._border_shadow_dy.value(),
            "shadow_blur": self._border_shadow_blur.value(),
        }
        if new == old:
            return
        self._push(SetCanvasBorderCommand(self._scene, "border_shadow", old, new))

    def _on_pasteboard_color_changed(self, color: QColor) -> None:
        if not self._updating:
            self.canvas_setting_changed.emit("pasteboard_color", QColor(color))

    def _on_grid_size_changed(self, value: int) -> None:
        if not self._updating:
            self.canvas_setting_changed.emit("grid_size", value)

    def _on_snap_toggled(self, checked: bool) -> None:
        if not self._updating:
            self.canvas_setting_changed.emit("snap_to_grid", checked)

    def _on_dpi_changed(self, value: int) -> None:
        if self._updating or value == self._scene.canvas_dpi:
            return
        self._push(
            SetCanvasPropertyCommand(self._scene, "canvas_dpi", self._scene.canvas_dpi, value)
        )

    def show_canvas_section(self) -> None:
        """Expand the Canvas section and scroll to it (canvas context menu, PRD 10.1)."""
        self._canvas_section.set_expanded(True)
        self._refresh_from_selection()
        self._scroll.ensureWidgetVisible(self._canvas_section)

    # --- text handlers ---

    def _set_align_combo(self, alignment: Qt.AlignmentFlag) -> None:
        """Set the text align combo to match the given Qt alignment flag."""
        h_align = alignment & Qt.AlignmentFlag.AlignHorizontal_Mask
        for i in range(self._text_align_combo.count()):
            if self._text_align_combo.itemData(i) == h_align:
                self._text_align_combo.setCurrentIndex(i)
                return
        self._text_align_combo.setCurrentIndex(0)

    def _ensure_editor_connected(self) -> None:
        """Connect to the active editor's cursor/format signals for live updates."""
        editor = self._get_active_editor()
        if editor is None:
            return
        if self._editor_connected and self._connected_editor is editor:
            return
        self._disconnect_editor()
        self._connected_editor = editor
        self._editor_connected = True
        if hasattr(editor, "cursorPositionChanged"):
            editor.cursorPositionChanged.connect(self._on_editor_cursor_changed)
        if hasattr(editor, "selectionChanged"):
            editor.selectionChanged.connect(self._on_editor_cursor_changed)
        if hasattr(editor, "currentCharFormatChanged"):
            editor.currentCharFormatChanged.connect(self._on_editor_format_changed)

    def _disconnect_editor(self) -> None:
        """Safely disconnect from the previously connected editor."""
        if not self._editor_connected or self._connected_editor is None:
            self._editor_connected = False
            self._connected_editor = None
            return
        editor = self._connected_editor
        try:
            if hasattr(editor, "cursorPositionChanged"):
                editor.cursorPositionChanged.disconnect(self._on_editor_cursor_changed)
            if hasattr(editor, "selectionChanged"):
                editor.selectionChanged.disconnect(self._on_editor_cursor_changed)
            if hasattr(editor, "currentCharFormatChanged"):
                editor.currentCharFormatChanged.disconnect(self._on_editor_format_changed)
        except (TypeError, RuntimeError):
            pass
        self._editor_connected = False
        self._connected_editor = None

    def _on_editor_cursor_changed(self) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self._refresh_text_from_cursor()
        finally:
            self._updating = False

    def _on_editor_format_changed(self, _fmt: QTextCharFormat) -> None:
        self._on_editor_cursor_changed()

    def _refresh_text_from_cursor(self) -> None:  # noqa: C901
        """Refresh text widgets from the editor's current cursor/selection format."""
        editor = self._get_active_editor()
        if editor is None or not hasattr(editor, "textCursor"):
            return
        cursor: QTextCursor = editor.textCursor()

        if not cursor.hasSelection():
            fmt = cursor.charFormat()
            font = fmt.font()
            self._font_combo.setCurrentFont(font)
            self._font_size_spin.setValue(max(1, font.pointSize()))
            self._set_combo_data(
                self._weight_combo,
                [QFont.Weight.Bold if font.bold() else QFont.Weight.Normal],
            )
            self._set_combo_data(self._style_combo, [font.italic()])
            self._set_check(self._underline_check, [font.underline()])
            fg = fmt.foreground()
            if fg.style() != Qt.BrushStyle.NoBrush:
                self._text_color_picker.color = QColor(fg.color())
            self._set_align_combo(cursor.blockFormat().alignment())
            self._set_spin(self._line_spacing_spin, [_block_line_spacing(cursor.blockFormat())])
            return

        # Selection: analyse fragments for mixed state (Text PRD 3.6)
        families: list[str] = []
        sizes: list[int] = []
        bolds: list[bool] = []
        italics: list[bool] = []
        underlines: list[bool] = []
        colors: list[QColor] = []
        alignments: list[int] = []
        spacings: list[float] = []

        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        doc = cursor.document()
        if doc is None:
            return

        block = doc.begin()
        while block.isValid():
            block_start = block.position()
            block_end = block_start + block.length()
            if block_end > sel_start and block_start < sel_end:
                align = block.blockFormat().alignment()
                alignments.append(int(align & Qt.AlignmentFlag.AlignHorizontal_Mask))
                spacings.append(_block_line_spacing(block.blockFormat()))
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    frag_start = fragment.position()
                    frag_end = frag_start + fragment.length()
                    if frag_end > sel_start and frag_start < sel_end:
                        fmt = fragment.charFormat()
                        font = fmt.font()
                        families.append(font.family())
                        sizes.append(font.pointSize())
                        bolds.append(font.bold())
                        italics.append(font.italic())
                        underlines.append(font.underline())
                        fg = fmt.foreground()
                        if fg.style() != Qt.BrushStyle.NoBrush:
                            colors.append(QColor(fg.color()))
                it += 1
            block = block.next()

        family, uniform = _uniform(families)
        if uniform and family:
            self._font_combo.setCurrentFont(QFont(family))
        elif families:
            self._clear_font_combo()
        if sizes:
            self._set_spin(self._font_size_spin, [max(1, s) for s in sizes])
        if bolds:
            self._set_combo_data(
                self._weight_combo,
                [QFont.Weight.Bold if b else QFont.Weight.Normal for b in bolds],
            )
        if italics:
            self._set_combo_data(self._style_combo, italics)
        if underlines:
            self._set_check(self._underline_check, underlines)
        if colors:
            self._set_color(self._text_color_picker, None, colors)
        if alignments:
            value, uniform = _uniform(alignments)
            if uniform:
                self._set_align_combo(Qt.AlignmentFlag(value))
            else:
                self._text_align_combo.setCurrentIndex(-1)
        if spacings:
            self._set_spin(self._line_spacing_spin, spacings)

    def _editing_editor(self) -> QWidget | None:
        """The rich text editor when exactly one text item is being edited."""
        items = self._selected_text_items()
        if len(items) == 1 and items[0].is_editing:
            editor = self._get_active_editor()
            if editor is not None and hasattr(editor, "textCursor"):
                return editor
        return None

    def _get_active_editor(self) -> QWidget | None:
        """Return the active _RichTextEditor if a text item is being edited."""
        parent = self.parent()
        if parent is not None and hasattr(parent, "tool_manager"):
            text_tool = parent.tool_manager.tool("text")
            if text_tool is not None and hasattr(text_tool, "active_editor"):
                editor = text_tool.active_editor
                if isinstance(editor, QWidget):
                    return editor
        return None

    def _merge_char_format(self, editor: QWidget, fmt: QTextCharFormat) -> None:
        editor.textCursor().mergeCharFormat(fmt)  # type: ignore[attr-defined]

    def _on_font_family_changed(self, font: QFont) -> None:
        if self._updating:
            return
        if self._set_default("font_family", font.family()):
            return
        editor = self._editing_editor()
        if editor is not None:
            fmt = QTextCharFormat()
            fmt.setFontFamilies([font.family()])
            self._merge_char_format(editor, fmt)
            return
        self._push_font(self._selected_text_items(), lambda f: f.setFamily(font.family()))

    def _on_font_size_changed(self, value: int) -> None:
        if self._updating or value == 0:
            return
        if self._set_default("font_size", value):
            return
        editor = self._editing_editor()
        if editor is not None:
            fmt = QTextCharFormat()
            fmt.setFontPointSize(float(value))
            self._merge_char_format(editor, fmt)
            return
        self._push_font(self._selected_text_items(), lambda f: f.setPointSize(value))

    def _on_weight_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        weight = self._weight_combo.itemData(index)
        bold = weight == QFont.Weight.Bold
        if self._set_default("bold", bold):
            return
        editor = self._editing_editor()
        if editor is not None:
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
            self._merge_char_format(editor, fmt)
            return
        self._push_font(self._selected_text_items(), lambda f: f.setBold(bold))

    def _on_style_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        italic = bool(self._style_combo.itemData(index))
        if self._set_default("italic", italic):
            return
        editor = self._editing_editor()
        if editor is not None:
            fmt = QTextCharFormat()
            fmt.setFontItalic(italic)
            self._merge_char_format(editor, fmt)
            return
        self._push_font(self._selected_text_items(), lambda f: f.setItalic(italic))

    def _on_underline_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._underline_check.setTristate(False)
        if self._set_default("underline", checked):
            return
        editor = self._editing_editor()
        if editor is not None:
            fmt = QTextCharFormat()
            fmt.setFontUnderline(checked)
            self._merge_char_format(editor, fmt)
            return
        self._push_font(self._selected_text_items(), lambda f: f.setUnderline(checked))

    def _on_text_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        if self._set_default("text_color", QColor(color)):
            return
        editor = self._editing_editor()
        if editor is not None:
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self._merge_char_format(editor, fmt)
            return
        self._push_property(self._selected_text_items(), "text_color", QColor(color))

    def _on_text_align_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        alignment = self._text_align_combo.itemData(index)
        if not isinstance(alignment, Qt.AlignmentFlag):
            return
        if self._set_default("horizontal_align", alignment):
            return
        editor = self._editing_editor()
        if editor is not None and hasattr(editor, "setAlignment"):
            editor.setAlignment(alignment)
            return
        self._push_property(self._selected_text_items(), "horizontal_alignment", alignment)

    def _on_line_spacing_changed(self, value: float) -> None:
        """Line Spacing (PRD 8.4): the paragraph at the cursor or the selection's
        paragraphs while editing, as the alignment row does; every paragraph of the
        selected items otherwise, as one command (kickoff silence 8)."""
        if self._updating or value < LINE_SPACING_MIN:
            return
        value = round(value, 1)
        if self._set_default("line_spacing", value):
            return
        editor = self._editing_editor()
        if editor is not None:
            fmt = QTextBlockFormat()
            fmt.setLineHeight(
                value * 100.0,
                cast(int, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value),
            )
            editor.textCursor().mergeBlockFormat(fmt)  # type: ignore[attr-defined]
            return
        commands: list[BaseCommand] = []
        for item in self._selected_text_items():
            old = item.line_spacings
            commands.append(ModifyPropertyCommand(item, "line_spacings", old, [value] * len(old)))
        if len(commands) == 1:
            self._push(commands[0])
        elif commands:
            self._push(MacroCommand(commands, "Change line spacing"))

    def _on_text_bg_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        if self._set_default("bg_color", QColor(color)):
            return
        self._push_property(self._selected_text_items(), "bg_color", QColor(color))

    def _on_text_border_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        if self._set_default("border_color", QColor(color)):
            return
        self._push_property(self._selected_text_items(), "border_color", QColor(color))

    def _on_text_border_w_changed(self, value: float) -> None:
        if self._updating or value < 0:
            return
        if self._set_default("border_width", value):
            return
        self._push_property(self._selected_text_items(), "border_width", value)

    def _on_text_corner_radius_changed(self, value: float) -> None:
        if self._updating or value < 0:
            return
        if self._set_default("border_radius", value):
            return
        self._push_property(self._selected_text_items(), "border_radius", value)

    def _on_text_padding_changed(self, value: float) -> None:
        if self._updating or value < 0:
            return
        if self._set_default("padding", value):
            return
        self._push_property(self._selected_text_items(), "padding", value)

    def _on_text_valign_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        new_align = self._text_valign_combo.itemData(index)
        if not isinstance(new_align, VerticalAlign):
            return
        if self._set_default("vertical_align", new_align):
            return
        self._push_property(self._selected_text_items(), "vertical_align", new_align)

    def _on_text_auto_size_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._text_auto_size_check.setTristate(False)
        if self._set_default("auto_size", checked):
            return
        items = [i for i in self._selected_items() if isinstance(i, TextItem)]
        self._push_property(items, "auto_size", checked)

    # --- public API for scene/selection replacement ---

    def set_scene(self, scene: SnapScene) -> None:
        """Replace the scene reference (e.g. after File > New or Open)."""
        self._disconnect_scene_signals()
        self._scene = scene
        self._connect_scene_signals()
        self._refresh_from_selection()

    def set_selection(self, selection_manager: SelectionManager) -> None:
        """Replace the SelectionManager (e.g. after opening a new project)."""
        self._disconnect_selection_signals()
        self._selection_manager = selection_manager
        self._connect_selection_signals()
        self._refresh_from_selection()

    def set_tool_manager(self, tm: ToolManager) -> None:
        """Wire the property panel to the tool manager for tool-defaults mode."""
        self._tool_manager = tm
        tm.tool_changed.connect(self._on_tool_changed)
        tm.tool_defaults_changed.connect(self._on_tool_defaults_changed)

    def _notify_defaults_changed(self) -> None:
        """Tell the Tool Options Bar a creation default changed here (PRD 5.1, 8.5)."""
        if self._tool_manager is not None:
            self._tool_manager.tool_defaults_changed.emit(self._active_tool_id)

    def _on_tool_defaults_changed(self, tool_id: str) -> None:
        """Re-read the defaults another surface edited, when this panel is showing them."""
        if self._updating or tool_id != self._active_tool_id:
            return
        if self._in_tool_defaults_mode() or self._in_vector_defaults_mode():
            self._refresh_from_selection()

    # --- numbered step handlers (Numbered Steps, Stamps & Emoji PRD 2.4) ---

    def _on_corner_radius_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._corner_radius_spin.setValue(float(value))
        self._updating = False
        self._push_property(self._selected_rectangles(), "corner_radius", float(value))

    def _on_corner_radius_spin_changed(self, value: float) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._corner_radius_slider.setValue(int(value))
        self._updating = False
        self._push_property(self._selected_rectangles(), "corner_radius", float(value))

    def _on_corner_mode_changed(self, checked: bool) -> None:
        if self._updating:
            return
        mode = CornerRadiusMode.INDIVIDUAL if checked else CornerRadiusMode.UNIFORM
        self._push_property(self._selected_rectangles(), "corner_radius_mode", mode)

    def _on_corner_spin_changed(self, key: str, value: float) -> None:
        if self._updating or value < 0:
            return
        self._push_property(self._selected_rectangles(), key, float(value))

    def _on_freehand_smoothing_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._freehand_smoothing_spin.setValue(value)
        self._updating = False
        self._apply_freehand_smoothing(value)

    def _on_freehand_smoothing_spin_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._freehand_smoothing_slider.setValue(value)
        self._updating = False
        self._apply_freehand_smoothing(value)

    def _apply_freehand_smoothing(self, percent: int) -> None:
        """Re-smooth each selected stroke from its raw points (Basic Shape PRD 9.7): one
        command per stroke that restores the smoothing and the segments together."""
        fraction = percent / 100.0
        commands: list[BaseCommand] = [
            ModifyPropertyCommand(
                item, "smoothing_fit", item.smoothing_fit, (fraction, item.fit_segments(fraction))
            )
            for item in self._selected_freehand()
        ]
        self._push_commands(commands, "Re-smooth freehand strokes")

    def _on_freehand_closed_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._push_property(self._selected_freehand(), "is_closed", bool(checked))

    def _on_blur_combo_changed(self, combo: QComboBox, prop: str, index: int) -> None:
        if self._updating or index < 0:
            return
        self._push_property(self._selected_blurs(), prop, combo.itemData(index))

    def _on_blur_value_changed(self, prop: str, value: Any, low: float | None) -> None:
        if self._updating:
            return
        if low is not None and float(value) < low:
            return  # the mixed indicator, not a value
        self._push_property(self._selected_blurs(), prop, value)

    def _fill_source_layers(self, current: list[str | None]) -> None:
        """The layer list for Specific Layer, rebuilt each time so renames and deletions
        show at once; a layer that is gone reads as the mixed indicator (2.5)."""
        combo = self._blur_source_layer_combo
        combo.blockSignals(True)
        combo.clear()
        for layer in self._scene.layer_manager.layers:
            combo.addItem(layer.name, layer.layer_id)
        chosen = set(current)
        index = -1
        if len(chosen) == 1:
            wanted = next(iter(chosen))
            index = combo.findData(wanted) if wanted else -1
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _on_blur_source_layer_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        layer_id = self._blur_source_layer_combo.itemData(index)
        self._push_property(self._selected_blurs(), "source_layer_id", layer_id)

    def _populate_highlight_defaults(self) -> None:
        tool = self._tool_manager.tool("highlight") if self._tool_manager is not None else None
        defaults = getattr(tool, "creation_defaults", {}) or {}
        self._highlight_straighten_check.setChecked(bool(defaults.get("auto_straighten", True)))
        self._highlight_snap_check.setChecked(bool(defaults.get("snap_to_axis", True)))
        self._highlight_threshold_spin.setValue(
            float(defaults.get("straighten_threshold", DEFAULT_STRAIGHTEN_THRESHOLD))
        )

    def _on_highlight_default(self, key: str, value: object) -> None:
        """Set one of the Highlighter's straightening defaults (3.4). Not undoable: it is a
        tool setting, and 3.6 gives it no retroactive effect on a placed stroke."""
        if self._updating or self._tool_manager is None:
            return
        tool = self._tool_manager.tool("highlight")
        if tool is None:
            return
        tool.creation_defaults[key] = value
        tool.on_option_changed(key, value)
        self._tool_manager.tool_defaults_changed.emit("highlight")

    def _brush_size(self) -> float:
        """The brush the Blur tool paints with; the panel's row and the bar's share it."""
        session = getattr(self._active_brush_owner(), "brush_session", None)
        if session is not None:
            return float(session.brush_size)
        tool = self._tool_manager.tool("blur") if self._tool_manager is not None else None
        size = getattr(tool, "brush_size", None)
        return float(size) if isinstance(size, (int, float)) else DEFAULT_BLUR_BRUSH_SIZE

    def _active_brush_owner(self) -> object:
        """The Select tool, which owns brush-editing mode (Blur PRD 2.8)."""
        if self._tool_manager is None:
            return None
        return self._tool_manager.tool("select")

    def _on_blur_brush_size_changed(self, value: int) -> None:
        """The brush is not a stored property of the region (Section 5.1 gives it no key):
        the row sets the brush both brushes use, and is not undoable."""
        if self._updating or self._tool_manager is None:
            return
        session = getattr(self._active_brush_owner(), "brush_session", None)
        if session is not None:
            session.brush_size = float(value)
        blur_tool = self._tool_manager.tool("blur")
        if blur_tool is not None:
            blur_tool.creation_defaults["brush_size"] = float(value)
            blur_tool.on_option_changed("brush_size", float(value))
            self._tool_manager.tool_defaults_changed.emit("blur")

    def _on_polygon_sides_changed(self, value: int) -> None:
        if self._updating or value < SIDES_MIN:
            return
        self._push_property(self._selected_polygons(), "sides", int(value))

    def _on_polygon_indent_changed(self, value: float) -> None:
        if self._updating or value < STAR_INDENT_MIN:
            return
        self._push_property(self._selected_polygons(), "star_indent", float(value))

    def _on_polygon_flag_changed(self, prop: str, checked: bool) -> None:
        if self._updating:
            return
        self._push_property(self._selected_polygons(), prop, bool(checked))

    def _on_arc_combo_changed(self, combo: QComboBox, prop: str, index: int) -> None:
        if self._updating or index < 0:
            return
        self._push_property(self._selected_arcs(), prop, combo.itemData(index))

    def _on_arrow_head_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        style = self._arrow_head_combo.itemData(index)
        if isinstance(style, HeadStyle):
            self._push_property(self._selected_arrows(), "head_style", style)

    def _on_arrow_tail_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        style = self._arrow_tail_combo.itemData(index)
        if isinstance(style, HeadStyle):
            self._push_property(self._selected_arrows(), "tail_style", style)

    def _on_arrow_size_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        size = self._arrow_size_combo.itemData(index)
        if isinstance(size, HeadSize):
            self._push_property(self._selected_arrows(), "head_size", size)

    def _on_arrow_custom_changed(self, value: float) -> None:
        if self._updating or value < 0:
            return
        self._push_property(self._selected_arrows(), "head_size_custom", float(value))

    def _on_arrow_line_style_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        style = self._arrow_line_style_combo.itemData(index)
        if isinstance(style, LineStyle):
            self._push_property(self._selected_arrows(), "line_style", style)

    def _on_step_value_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._push_property(self._selected_steps(), "number_value", int(value))

    def _on_step_mode_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        mode = self._step_mode_combo.itemData(index)
        if isinstance(mode, DisplayMode):
            self._push_property(self._selected_steps(), "display_mode", mode)

    def _on_step_text_edited(self) -> None:
        if self._updating:
            return
        text = self._step_text_edit.text()
        items = [i for i in self._selected_steps() if i.custom_text != text]
        self._push_property(items, "custom_text", text)

    def _on_step_shape_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        shape = self._step_shape_combo.itemData(index)
        if isinstance(shape, BadgeShape):
            self._push_property(self._selected_steps(), "badge_shape", shape)

    def _on_step_size_changed(self, value: float) -> None:
        if self._updating or value < BADGE_SIZE_MIN:
            return
        self._push_property(self._selected_steps(), "badge_size", float(value))

    def _on_step_weight_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        weight = self._step_weight_combo.itemData(index)
        if isinstance(weight, FontWeight):
            self._push_property(self._selected_steps(), "font_weight", weight)

    def _on_step_border_style_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        style = self._step_border_style_combo.itemData(index)
        if isinstance(style, BorderStyle):
            self._push_property(self._selected_steps(), "border_style", style)

    def _on_fill_opacity_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._fill_opacity_spin.setValue(value)
        self._updating = False
        self._apply_vector_opacity("fill_opacity", value)

    def _on_fill_opacity_spin_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._fill_opacity_slider.setValue(value)
        self._updating = False
        self._apply_vector_opacity("fill_opacity", value)

    def _on_stroke_opacity_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._stroke_opacity_spin.setValue(value)
        self._updating = False
        self._apply_vector_opacity("stroke_opacity", value)

    def _on_stroke_opacity_spin_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._stroke_opacity_slider.setValue(value)
        self._updating = False
        self._apply_vector_opacity("stroke_opacity", value)

    def _apply_vector_opacity(self, prop: str, value: int) -> None:
        """Fill Opacity or Stroke Opacity over the vector items, groups expanded."""
        if self._set_default(prop, value / 100.0):
            return
        self._push_property(self._selected_vectors(), prop, value / 100.0)

    def _on_text_fill_opacity_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._text_fill_opacity_spin.setValue(value)
        self._updating = False
        self._apply_text_opacity("fill_opacity", value)

    def _on_text_fill_opacity_spin_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._text_fill_opacity_slider.setValue(value)
        self._updating = False
        self._apply_text_opacity("fill_opacity", value)

    def _on_text_stroke_opacity_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._text_stroke_opacity_spin.setValue(value)
        self._updating = False
        self._apply_text_opacity("stroke_opacity", value)

    def _on_text_stroke_opacity_spin_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._text_stroke_opacity_slider.setValue(value)
        self._updating = False
        self._apply_text_opacity("stroke_opacity", value)

    def _apply_text_opacity(self, prop: str, value: int) -> None:
        """Fill Opacity or Stroke Opacity of the Text Box section (decision 1)."""
        if self._set_default(prop, value / 100.0):
            return
        self._push_property(self._selected_text_items(), prop, value / 100.0)

    def _on_step_label_edited(self) -> None:
        if self._updating:
            return
        text = self._step_label_edit.text()
        items = [i for i in self._selected_steps() if i.label_text != text]
        self._push_property(items, "label_text", text)

    def _on_step_label_pos_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        position = self._step_label_pos_combo.itemData(index)
        if isinstance(position, LabelPosition):
            self._push_property(self._selected_steps(), "label_position", position)

    def _on_step_label_size_changed(self, value: float) -> None:
        if self._updating or value <= 0:
            return
        self._push_property(self._selected_steps(), "label_font_size", float(value))

    def _on_step_label_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._push_property(self._selected_steps(), "label_color", QColor(color))

    def _on_step_label_bg_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._push_property(self._selected_steps(), "label_background", QColor(color))

    def _on_step_label_pill_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._push_property(self._selected_steps(), "label_background_enabled", bool(checked))

    # --- stamp handlers (Numbered Steps, Stamps & Emoji PRD 3.5, 3.7) ---

    def _on_stamp_change_clicked(self) -> None:
        stamps = self._selected_stamps()
        window = self.window()
        open_editor = getattr(window, "open_marker_editor", None)
        if len(stamps) == 1 and callable(open_editor):
            open_editor(stamps[0])

    def _on_stamp_size_changed(self, value: float) -> None:
        if self._updating or value < STAMP_SIZE_MIN:
            return
        self._push_property(self._selected_stamps(), "stamp_size", float(value))

    def _on_stamp_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._push_property(self._selected_stamps(), "stamp_color", QColor(color))

    def _on_stamp_secondary_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._push_property(self._selected_stamps(), "stamp_secondary_color", QColor(color))

    def _on_stamp_opacity_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._stamp_opacity_spin.setValue(value)
        self._updating = False
        self._push_property(self._selected_stamps(), "opacity_pct", float(value))

    def _on_stamp_opacity_spin_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._stamp_opacity_slider.setValue(value)
        self._updating = False
        self._push_property(self._selected_stamps(), "opacity_pct", float(value))

    # --- emoji handlers (Numbered Steps, Stamps & Emoji PRD 4.4, 4.6) ---

    def _on_emoji_change_clicked(self) -> None:
        items = self._selected_emoji()
        open_editor = getattr(self.window(), "open_marker_editor", None)
        if len(items) == 1 and callable(open_editor):
            open_editor(items[0])

    def _on_emoji_size_changed(self, value: float) -> None:
        if self._updating or value < EMOJI_SIZE_MIN:
            return
        self._push_property(self._selected_emoji(), "emoji_size", float(value))

    def _on_emoji_tone_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        tone = self._emoji_tone_combo.itemData(index)
        if isinstance(tone, SkinTone):
            self._push_property(self._selected_emoji(), "skin_tone", tone)

    def _on_emoji_opacity_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._emoji_opacity_spin.setValue(value)
        self._updating = False
        self._push_property(self._selected_emoji(), "opacity_pct", float(value))

    def _on_emoji_opacity_spin_changed(self, value: int) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._emoji_opacity_slider.setValue(value)
        self._updating = False
        self._push_property(self._selected_emoji(), "opacity_pct", float(value))

    # --- shadow handlers (General UI PRD 8.3; decision 1) ---

    def _on_shadow_enabled_changed(self, checked: bool) -> None:
        if self._updating:
            return
        self._push_property(self._selected_shadowed(), "shadow_enabled", bool(checked))

    def _on_shadow_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._push_property(self._selected_shadowed(), "shadow_color", QColor(color))

    def _on_shadow_x_changed(self, value: float) -> None:
        if self._updating or value == self._shadow_x_spin.minimum():
            return
        self._push_property(self._selected_shadowed(), "shadow_offset_x", float(value))

    def _on_shadow_y_changed(self, value: float) -> None:
        if self._updating or value == self._shadow_y_spin.minimum():
            return
        self._push_property(self._selected_shadowed(), "shadow_offset_y", float(value))

    def _on_shadow_blur_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._shadow_blur_spin.setValue(float(value))
        self._updating = False
        self._push_property(self._selected_shadowed(), "shadow_blur", float(value))

    def _on_shadow_blur_spin_changed(self, value: float) -> None:
        if self._updating or value < 0:
            return
        self._updating = True
        self._shadow_blur_slider.setValue(int(value))
        self._updating = False
        self._push_property(self._selected_shadowed(), "shadow_blur", float(value))

    def refresh_tool_defaults(self) -> None:
        """Re-read the active tool's creation defaults (Preferences > Tools changed)."""
        self._refresh_from_selection()

    def refresh_canvas_settings(self) -> None:
        """Re-read the pasteboard, grid size, and snap state (View menu, Preferences)."""
        if not self._selected_items():
            self._refresh_from_selection()

    def _on_tool_changed(self, tool_id: str) -> None:
        """Track the active tool and refresh the panel."""
        self._active_tool_id = tool_id
        self._refresh_from_selection()
