"""Accessible names and the tab order of General UI PRD Section 14.

Every interactive control carries an accessible name. Most are named where they
are built; the helpers here name what a layout already labels (a form row's
field takes the row's label, a toolbar widget takes the label before it, a
button takes its own text), so a module names by hand only the controls no
label describes. :func:`unnamed_controls` is the audit the test suite runs over
the main window and every dialog.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QKeySequenceEdit,
    QLabel,
    QLayout,
    QLineEdit,
    QMenuBar,
    QPlainTextEdit,
    QScrollBar,
    QTabBar,
    QTextEdit,
    QToolBar,
    QToolButton,
    QWidget,
    QWidgetAction,
)

# Widget classes a user operates; a layout or a plain label is not one.
INTERACTIVE_TYPES: tuple[type[QWidget], ...] = (
    QAbstractButton,
    QComboBox,
    QAbstractSpinBox,
    QLineEdit,
    QAbstractSlider,
    QAbstractItemView,
    QTabBar,
    QTextEdit,
    QPlainTextEdit,
    QKeySequenceEdit,
)


def clean_label(text: str) -> str:
    """A label's text as a name: no accelerator ampersand, colon, or ellipsis."""
    text = text.replace("&", "").strip()
    for suffix in (":", "…", "..."):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return " ".join(text.split())


def is_internal(widget: QWidget) -> bool:
    """A part Qt builds inside a control (a spinbox's line edit, a combo's popup list)."""
    if widget.objectName().startswith("qt_"):
        return True
    parent = widget.parentWidget()
    if isinstance(parent, QComboBox | QAbstractSpinBox | QLineEdit | QAbstractItemView):
        return True
    return parent is not None and isinstance(parent.parentWidget(), QComboBox)


def is_interactive(widget: QWidget) -> bool:
    """Whether *widget* is a control the audit and the tab order consider."""
    if isinstance(widget, QScrollBar) or is_internal(widget):
        return False
    if isinstance(widget, QGroupBox):
        return widget.isCheckable()
    return isinstance(widget, INTERACTIVE_TYPES)


def _button_name(button: QAbstractButton) -> str:
    """A button's text, or its tooltip when the text is a glyph or a single letter."""
    text = clean_label(button.text())
    if len(text) >= 2 and any(c.isalpha() for c in text):
        return text
    tip = clean_label(button.toolTip())
    return tip or text


def _interactive_descendants(root: QWidget) -> list[QWidget]:
    return [w for w in root.findChildren(QWidget) if is_interactive(w)]


def _part_suffix(widget: QWidget) -> str:
    if isinstance(widget, QAbstractSlider):
        return "slider"
    if isinstance(widget, QAbstractSpinBox):
        return "value"
    if isinstance(widget, QKeySequenceEdit):
        return "key"
    if isinstance(widget, QAbstractButton):
        return _button_name(widget)
    if isinstance(widget, QComboBox):
        return "choice"
    if isinstance(widget, QLineEdit):
        return "text"
    return type(widget).__name__


def _name_field(field: QWidget, label: str) -> None:
    """Name *field* after *label*; a container's controls each take a part suffix."""
    if is_interactive(field):
        if not field.accessibleName():
            field.setAccessibleName(label)
        return
    parts = _interactive_descendants(field)
    if len(parts) == 1:
        if not parts[0].accessibleName():
            parts[0].setAccessibleName(label)
        return
    for part in parts:
        if not part.accessibleName():
            part.setAccessibleName(f"{label} {_part_suffix(part)}")


def name_form_fields(form: QFormLayout) -> None:
    """Give every field of *form* the accessible name of its row label."""
    for row in range(form.rowCount()):
        label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        field_item = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
        if field_item is None:
            continue
        label_widget = label_item.widget() if label_item is not None else None
        label = clean_label(label_widget.text()) if isinstance(label_widget, QLabel) else ""
        field = field_item.widget()
        if field is None:
            layout = field_item.layout()
            if layout is not None:
                _name_layout_controls(layout, label)
            continue
        if label:
            _name_field(field, label)
        elif isinstance(field, QAbstractButton) and not field.accessibleName():
            field.setAccessibleName(_button_name(field))


def _name_layout_controls(layout: QLayout, label: str) -> None:
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        widget = item.widget()
        if widget is not None:
            if label:
                _name_field(widget, label)
            continue
        sub = item.layout()
        if sub is not None:
            _name_layout_controls(sub, label)


def name_buttons_from_text(root: QWidget) -> None:
    """Every unnamed button under *root* takes its text (or its tooltip for a glyph)."""
    for button in root.findChildren(QAbstractButton):
        if is_internal(button) or button.accessibleName():
            continue
        name = _button_name(button)
        if name:
            button.setAccessibleName(name)


def name_toolbar_widgets(toolbar: QToolBar) -> None:
    """An unnamed toolbar widget takes the text of the label placed before it."""
    label = ""
    for action in toolbar.actions():
        if not isinstance(action, QWidgetAction):
            label = ""
            continue
        widget = action.defaultWidget()
        if isinstance(widget, QLabel):
            label = clean_label(widget.text())
            continue
        if widget is None:
            continue
        if is_interactive(widget):
            if widget.accessibleName():
                continue
            own = _button_name(widget) if isinstance(widget, QAbstractButton) else ""
            if own or label:
                widget.setAccessibleName(own or label)
        else:
            for part in _interactive_descendants(widget):
                if not part.accessibleName() and label:
                    part.setAccessibleName(label)
    name_buttons_from_text(toolbar)


def apply_default_names(root: QWidget) -> None:
    """Name what the layouts under *root* already label, then the buttons by text."""
    for form in root.findChildren(QFormLayout):
        name_form_fields(form)
    for toolbar in root.findChildren(QToolBar):
        name_toolbar_widgets(toolbar)
    if isinstance(root, QToolBar):
        name_toolbar_widgets(root)
    name_buttons_from_text(root)


def unnamed_controls(root: QWidget) -> list[QWidget]:
    """The interactive controls under *root* without an accessible name (the audit).

    A toolbar button Qt builds for a QAction is named by the action's text and
    is not listed.
    """
    missing: list[QWidget] = []
    for widget in root.findChildren(QWidget):
        if not is_interactive(widget) or widget.accessibleName():
            continue
        if isinstance(widget, QToolButton):
            action = widget.defaultAction()
            if action is not None and action.text():
                continue
        missing.append(widget)
    return missing


def describe(widget: QWidget) -> str:
    """One line naming *widget* for an audit failure message."""
    text = getattr(widget, "text", lambda: "")()
    chain: list[str] = []
    w: QWidget | None = widget
    while w is not None and len(chain) < 4:
        chain.append(f"{type(w).__name__}({w.objectName()!r})")
        w = w.parentWidget()
    return f"{' < '.join(chain)} text={text!r}"


def focusable_controls(root: QWidget) -> list[QWidget]:
    """The Tab stops under *root* in construction order, *root* itself first if it is one.

    A control in another window is not one of them, even when *root* is its parent: a
    popup — the colour picker's popover, the Tool Options Bar's overflow — is its own
    surface with its own Tab order, and ``setTabOrder`` refuses a chain that crosses
    windows in any case.
    """
    stops: list[QWidget] = []
    window = root.window()
    candidates: Iterable[QWidget] = [root, *root.findChildren(QWidget)]
    for widget in candidates:
        if isinstance(widget, QMenuBar) or is_internal(widget):
            continue
        if widget.window() is not window:
            continue
        if widget.focusPolicy() & Qt.FocusPolicy.TabFocus:
            stops.append(widget)
    return stops


def set_tab_order(zones: Sequence[QWidget]) -> list[QWidget]:
    """Chain the Tab stops of *zones* in that order (PRD 14: Main Toolbar > Tool
    Options Bar > Left Tool Palette > Canvas > Layer Panel > Property Panel).

    Returns the chain, first stop first.
    """
    chain: list[QWidget] = []
    for zone in zones:
        chain.extend(focusable_controls(zone))
    for first, second in zip(chain, chain[1:], strict=False):
        QWidget.setTabOrder(first, second)
    return chain
