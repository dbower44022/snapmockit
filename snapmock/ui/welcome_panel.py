"""The Welcome panel of General UI PRD Section 16 and the canvas size dialog its card opens.

The panel takes the place of the empty canvas on the first launch and opens from
Help > Welcome / Getting Started at any time. It is a page the central widget
shows over the document stack (:meth:`DocumentTabs.show_page`); it owns no
document state and acts only through signals the main window routes to the
existing File > Import Image, Edit > Paste, and File > New paths.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from snapmock.config.constants import APP_NAME
from snapmock.config.settings import AppSettings
from snapmock.core.theme_manager import theme_manager

TAGLINE = f"{APP_NAME} - Screenshot Annotation & UI Mockup Tool"

CARD_OPEN_IMAGE = "Open an Image"
CARD_PASTE = "Paste from Clipboard"
CARD_NEW_CANVAS = "New Blank Canvas"

# Title, description, Tabler glyph (PRD 16.1, Quick Start).
CARDS: tuple[tuple[str, str, str], ...] = (
    (CARD_OPEN_IMAGE, "Choose an image file to annotate.", "photo-plus"),
    (CARD_PASTE, "Use the image on the clipboard.", "clipboard"),
    (CARD_NEW_CANVAS, "Start from an empty canvas of the size you choose.", "file-plus"),
)

# The four-step guide (PRD 16.1, Getting Started): text and glyph.
STEPS: tuple[tuple[str, str], ...] = (
    ("Import or paste a screenshot", "photo-plus"),
    ("Use annotation tools to mark up the image", "pencil"),
    ("Cut and rearrange screen regions for mockups", "scissors"),
    ("Export or save your work", "file-export"),
)

DONT_SHOW_AGAIN = "Don't show this again"
CLOSE_BUTTON = "Close"

CARD_ICON_SIZE = 48
STEP_ICON_SIZE = 24
LOGO_ICON_SIZE = 64
CONTENT_MAX_WIDTH = 760
CANVAS_SIZE_MAX = 32000


class CanvasSizeDialog(QDialog):
    """The size dialog the New Blank Canvas card opens (PRD 16.1).

    Width and height start at the Preferences default canvas size. Lock aspect
    ratio keeps their ratio while one is edited. Cancel creates nothing.
    """

    def __init__(self, width: int, height: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Blank Canvas")
        self._ratio = width / max(1, height)
        self._updating = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._width = QSpinBox()
        self._width.setRange(1, CANVAS_SIZE_MAX)
        self._width.setSuffix(" px")
        self._width.setValue(width)
        self._width.setAccessibleName("Canvas width")
        self._height = QSpinBox()
        self._height.setRange(1, CANVAS_SIZE_MAX)
        self._height.setSuffix(" px")
        self._height.setValue(height)
        self._height.setAccessibleName("Canvas height")
        form.addRow("Width:", self._width)
        form.addRow("Height:", self._height)
        self._lock = QCheckBox("Lock aspect ratio")
        self._lock.setAccessibleName("Lock aspect ratio")
        form.addRow("", self._lock)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setAccessibleName("Create canvas")
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel is not None:
            cancel.setAccessibleName("Cancel")
        layout.addWidget(buttons)

        self._width.valueChanged.connect(self._on_width_changed)
        self._height.valueChanged.connect(self._on_height_changed)

    @property
    def width_spin(self) -> QSpinBox:
        return self._width

    @property
    def height_spin(self) -> QSpinBox:
        return self._height

    @property
    def lock_checkbox(self) -> QCheckBox:
        return self._lock

    def size_value(self) -> tuple[int, int]:
        """The chosen width and height in pixels."""
        return self._width.value(), self._height.value()

    def _on_width_changed(self, value: int) -> None:
        if self._updating or not self._lock.isChecked():
            return
        self._updating = True
        self._height.setValue(max(1, round(value / self._ratio)))
        self._updating = False

    def _on_height_changed(self, value: int) -> None:
        if self._updating or not self._lock.isChecked():
            return
        self._updating = True
        self._width.setValue(max(1, round(value * self._ratio)))
        self._updating = False


class WelcomeCard(QPushButton):
    """One large Quick Start card: a glyph over a title and a one-line description."""

    def __init__(self, title: str, description: str, glyph: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._glyph = glyph
        self.setObjectName("WelcomeCard")
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.setToolTip(description)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._icon.setStyleSheet("background: transparent;")
        self._title = QLabel(title)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._title.setStyleSheet("background: transparent;")
        font = QFont(self._title.font())
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        self._title.setFont(font)
        self._description = QLabel(description)
        self._description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._description.setWordWrap(True)
        self._description.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._description.setObjectName("secondaryText")
        self._description.setStyleSheet("background: transparent;")
        layout.addStretch()
        layout.addWidget(self._icon)
        layout.addWidget(self._title)
        layout.addWidget(self._description)
        layout.addStretch()
        self.apply_theme()

    @property
    def title(self) -> str:
        return self._title.text()

    def apply_theme(self) -> None:
        """Re-render the glyph in the current theme's text colour."""
        icon = theme_manager().icon(self._glyph)
        self._icon.setPixmap(icon.pixmap(CARD_ICON_SIZE, CARD_ICON_SIZE))


class WelcomePanel(QWidget):
    """The first-run Welcome panel (PRD 16.1).

    Signals
    -------
    open_image_requested()
        The Open an Image card.
    paste_requested()
        The Paste from Clipboard card.
    new_canvas_requested(int, int)
        The New Blank Canvas card, after its size dialog was accepted.
    closed()
        Close, or Escape: return to the canvas.
    """

    open_image_requested = pyqtSignal()
    paste_requested = pyqtSignal()
    new_canvas_requested = pyqtSignal(int, int)
    closed = pyqtSignal()

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setObjectName("WelcomePanel")
        self.setAccessibleName("Welcome")
        self.setAccessibleDescription(
            f"Quick Start cards and a four-step guide for new users of {APP_NAME}."
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        content_row = QHBoxLayout(content)
        column = QWidget()
        column.setMaximumWidth(CONTENT_MAX_WIDTH)
        content_row.addStretch()
        content_row.addWidget(column)
        content_row.addStretch()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(32, 32, 32, 24)
        layout.setSpacing(16)

        # Logo and tagline.
        self._logo = QLabel()
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setAccessibleName(f"{APP_NAME} logo")
        layout.addWidget(self._logo)
        name = QLabel(APP_NAME)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_font = QFont(name.font())
        name_font.setPointSize(name_font.pointSize() + 12)
        name_font.setBold(True)
        name.setFont(name_font)
        layout.addWidget(name)
        tagline = QLabel(TAGLINE)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setObjectName("secondaryText")
        layout.addWidget(tagline)

        # Quick Start cards.
        layout.addWidget(self._heading("Quick Start"))
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        self._cards: dict[str, WelcomeCard] = {}
        for title, description, glyph in CARDS:
            card = WelcomeCard(title, description, glyph)
            cards_row.addWidget(card)
            self._cards[title] = card
        layout.addLayout(cards_row)
        self._cards[CARD_OPEN_IMAGE].clicked.connect(self.open_image_requested)
        self._cards[CARD_PASTE].clicked.connect(self.paste_requested)
        self._cards[CARD_NEW_CANVAS].clicked.connect(self._on_new_canvas)

        # Getting Started guide.
        layout.addWidget(self._heading("Getting Started"))
        self._step_icons: list[tuple[QLabel, str]] = []
        for number, (text, glyph) in enumerate(STEPS, start=1):
            row = QHBoxLayout()
            row.setSpacing(12)
            badge = QLabel(str(number))
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setObjectName("stepBadge")
            badge_font = QFont(badge.font())
            badge_font.setBold(True)
            badge.setFont(badge_font)
            icon = QLabel()
            icon.setFixedSize(STEP_ICON_SIZE, STEP_ICON_SIZE)
            self._step_icons.append((icon, glyph))
            label = QLabel(text)
            label.setAccessibleName(f"Step {number}: {text}")
            row.addWidget(badge)
            row.addWidget(icon)
            row.addWidget(label, 1)
            layout.addLayout(row)

        # Bottom row: the checkbox and Close.
        layout.addStretch()
        bottom = QHBoxLayout()
        self._dont_show = QCheckBox(DONT_SHOW_AGAIN)
        self._dont_show.setAccessibleName(DONT_SHOW_AGAIN)
        self._dont_show.setAccessibleDescription(
            f"When checked, the Welcome panel no longer opens when {APP_NAME} starts."
        )
        self._dont_show.setChecked(not settings.show_welcome_at_startup())
        self._dont_show.toggled.connect(self._on_dont_show_toggled)
        self._close = QPushButton(CLOSE_BUTTON)
        self._close.setAccessibleName("Close the Welcome panel")
        self._close.setAccessibleDescription("Return to the canvas.")
        self._close.clicked.connect(self.closed)
        bottom.addWidget(self._dont_show)
        bottom.addStretch()
        bottom.addWidget(self._close)
        layout.addLayout(bottom)

        scroll.setWidget(content)
        self.apply_theme()
        theme_manager().theme_changed.connect(self._on_theme_changed)

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        font = QFont(label.font())
        font.setBold(True)
        font.setPointSize(font.pointSize() + 3)
        label.setFont(font)
        return label

    # ---- accessors ----

    def card(self, title: str) -> WelcomeCard:
        """The Quick Start card titled *title* (one of the ``CARD_`` constants)."""
        return self._cards[title]

    @property
    def dont_show_checkbox(self) -> QCheckBox:
        return self._dont_show

    @property
    def close_button(self) -> QPushButton:
        return self._close

    # ---- slots ----

    def _on_dont_show_toggled(self, checked: bool) -> None:
        self._settings.set_show_welcome_at_startup(not checked)

    def _on_new_canvas(self) -> None:
        width, height = self._settings.default_canvas_size()
        dialog = CanvasSizeDialog(width, height, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        size = dialog.size_value()
        dialog.deleteLater()
        if accepted:
            self.new_canvas_requested.emit(*size)

    def _on_theme_changed(self, _name: str) -> None:
        self.apply_theme()

    def apply_theme(self) -> None:
        """Re-render every glyph and the accent badges for the current theme."""
        theme = theme_manager()
        colors = theme.colors
        self._logo.setPixmap(theme.icon("screenshot").pixmap(LOGO_ICON_SIZE, LOGO_ICON_SIZE))
        for card in self._cards.values():
            card.apply_theme()
        for icon, glyph in self._step_icons:
            icon.setPixmap(theme.icon(glyph).pixmap(STEP_ICON_SIZE, STEP_ICON_SIZE))
        accent = colors.accent.name()
        accent_text = colors.accent_text.name()
        secondary = colors.text_secondary.name()
        border = colors.border.name()
        hover = colors.button_hover.name()
        panel = colors.panel_bg.name()
        self.setStyleSheet(
            f"QLabel#stepBadge {{ background-color: {accent}; color: {accent_text};"
            " border-radius: 14px; }"
            f"QLabel#secondaryText {{ color: {secondary}; }}"
            f"QPushButton#WelcomeCard {{ background-color: {panel}; border: 1px solid {border};"
            " border-radius: 8px; padding: 0; text-align: center; }"
            f"QPushButton#WelcomeCard:hover {{ background-color: {hover}; }}"
            f"QPushButton#WelcomeCard:focus {{ border: 2px solid {accent}; }}"
        )

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802
        if event is not None and event.key() == Qt.Key.Key_Escape:
            self.closed.emit()
            event.accept()
            return
        super().keyPressEvent(event)
