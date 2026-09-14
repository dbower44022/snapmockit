"""First-run onboarding dialogs (PRD Section 9). Shown on the first capture attempt only."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from snapmock.config.constants import APP_NAME

CONSENT_TEXT = (
    f"Your desktop will ask whether {APP_NAME} may take a screenshot. This is the desktop's "
    "own dialog. Some desktops ask once; some ask every time."
)
HOTKEY_TEXT = (
    "Wayland desktops do not let applications register their own keyboard shortcuts. "
    "To capture with PrintScreen, bind a shortcut in your desktop's keyboard settings to "
    "this command:"
)
COMMANDS = (
    ("Region", "snapmock --capture region"),
    ("Active window", "snapmock --capture window"),
    ("Full screen", "snapmock --capture full"),
)
DESKTOP_NOTES = (
    "GNOME: Settings > Keyboard > View and Customize Shortcuts > Custom Shortcuts.",
    "KDE Plasma: System Settings > Shortcuts > Add Command.",
    "The desktop's own PrintScreen binding must be removed or changed first.",
)
MACOS_NOTE = (
    "macOS: the Shortcuts application, with a keyboard shortcut on a Run Shell Script action."
)


MACOS_PERMISSION_TEXT = (
    f"macOS asks you to allow {APP_NAME} to record the screen before it can take screenshots. "
    "Click Continue to see the system prompt. If you have already denied it, open System "
    f"Settings and enable {APP_NAME} under Privacy & Security > Screen Recording."
)
MACOS_RESTART_TEXT = f"Quit and reopen {APP_NAME} to finish."


def _copy_to_clipboard(text: str) -> None:
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


class DesktopShortcutPanel(QGroupBox):
    """Panel two of the Wayland onboarding: the commands to bind (PRD 9.2)."""

    def __init__(self, parent: QWidget | None = None, *, macos: bool = False) -> None:
        super().__init__("Keyboard shortcut", parent)
        layout = QVBoxLayout(self)
        intro = QLabel(HOTKEY_TEXT)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.fields: dict[str, QLineEdit] = {}
        for label, command in COMMANDS:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label}:"))
            field = QLineEdit(command)
            field.setReadOnly(True)
            row.addWidget(field, 1)
            copy = QPushButton("Copy")
            copy.clicked.connect(lambda _c=False, t=command: _copy_to_clipboard(t))
            row.addWidget(copy)
            layout.addLayout(row)
            self.fields[command] = field
        notes = (MACOS_NOTE,) if macos else DESKTOP_NOTES
        for note in notes:
            line = QLabel(note)
            line.setWordWrap(True)
            layout.addWidget(line)


class WaylandOnboardingDialog(QDialog):
    """Consent and desktop-shortcut guidance before the first Wayland capture (PRD 9.2).

    ``help_only`` shows the shortcut panel with a Close button, for the
    Preferences link.
    """

    def __init__(self, parent: QWidget | None = None, *, help_only: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set Up a Desktop Shortcut" if help_only else "Capturing on Wayland")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        if not help_only:
            consent = QGroupBox("Consent")
            consent_layout = QVBoxLayout(consent)
            text = QLabel(CONSENT_TEXT)
            text.setWordWrap(True)
            consent_layout.addWidget(text)
            layout.addWidget(consent)
        self.shortcut_panel = DesktopShortcutPanel(self)
        layout.addWidget(self.shortcut_panel)
        self.dont_show = QCheckBox("Don't show this again")
        self.dont_show.setVisible(not help_only)
        layout.addWidget(self.dont_show)
        if help_only:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(self.reject)
            buttons.accepted.connect(self.accept)
        else:
            buttons = QDialogButtonBox()
            cont = buttons.addButton("Continue", QDialogButtonBox.ButtonRole.AcceptRole)
            buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            if cont is not None:
                cont.setDefault(True)
        layout.addWidget(buttons)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)


class MacOSPermissionDialog(QDialog):
    """Screen Recording permission onboarding (PRD 9.1).

    ``request`` asks the platform for permission and returns True when granted.
    Continue calls it; if permission is still missing the dialog moves to its
    final state, which says to quit and reopen, with a Quit button.
    """

    def __init__(
        self,
        request: Callable[[], bool],
        *,
        settings_url: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._request = request
        self._settings_url = settings_url
        self.granted = False
        self.quit_requested = False
        self.setWindowTitle("Screen Recording Permission")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        self.text = QLabel(MACOS_PERMISSION_TEXT)
        self.text.setWordWrap(True)
        layout.addWidget(self.text)
        self.dont_show = QCheckBox("Don't show this again")
        layout.addWidget(self.dont_show)
        self.buttons = QDialogButtonBox()
        self.continue_button = QPushButton("Continue")
        self.buttons.addButton(self.continue_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self.settings_button = QPushButton("Open System Settings")
        self.buttons.addButton(self.settings_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.quit_button = QPushButton("Quit")
        self.buttons.addButton(self.quit_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.quit_button.setVisible(False)
        self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._on_continue)
        self.buttons.rejected.connect(self.reject)
        self.settings_button.clicked.connect(self._open_settings)
        self.quit_button.clicked.connect(self._on_quit)
        layout.addWidget(self.buttons)

    def _on_continue(self) -> None:
        if self._request():
            self.granted = True
            self.accept()
            return
        # macOS applies the permission only after a restart (PRD 9.1).
        self.text.setText(MACOS_RESTART_TEXT)
        self.continue_button.setVisible(False)
        self.quit_button.setVisible(True)

    def _open_settings(self) -> None:
        QDesktopServices.openUrl(QUrl(self._settings_url))

    def _on_quit(self) -> None:
        self.quit_requested = True
        self.reject()
