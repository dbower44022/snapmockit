"""QApplication bootstrap, the single-instance channel, and command-line capture (PRD 3.5)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from snapmock.capture.cli import CaptureCommand, parse_command_line
from snapmock.capture.single_instance import try_forward
from snapmock.config.constants import APP_NAME, APP_VERSION, DESKTOP_ENTRY_ID
from snapmock.main_window import MainWindow
from snapmock.ui.icons import application_icon

log = logging.getLogger("snapmock")


def version_text() -> str:
    """What ``--version`` prints: the product's name and version (packaging silence 6)."""
    return f"{APP_NAME} {APP_VERSION}"


def main(argv: list[str] | None = None) -> None:
    """Launch the application, or forward a capture request to the running instance.

    ``--version`` prints :func:`version_text` and exits before any Qt object exists,
    so a smoke test and a bug report can read it without a display.
    """
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv[1:]:
        print(version_text())
        sys.exit(0)
    command, files = parse_command_line(argv)
    # The names are set before the application exists: Qt registers the desktop
    # entry's id with the desktop portal when the first window shows, once, from
    # the name it holds then; a name set afterwards registers a second time and
    # the portal refuses it ("Connection already associated with an application
    # ID", seen from the AppImage on 09-14-26). On a host where the desktop entry
    # is not installed the portal answers "App info not found" once; it is a
    # warning, and it ends when the AppImage is integrated into the menu.
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(APP_VERSION)
    QApplication.setDesktopFileName(DESKTOP_ENTRY_ID)
    # The application is created before the forward because the write to the
    # channel completes only once an event loop is available to pump it, which
    # is how a Windows named pipe behaves (PRD 3.5).
    app = QApplication(argv)
    app.setWindowIcon(application_icon())
    if command is not None and try_forward(argv):
        sys.exit(0)

    window = MainWindow(restore_session=True)
    manager = window.capture_manager
    manager.listen_for_commands()
    manager.register_hotkeys()

    hide_until_done = command is not None and window.capture_manager.settings.capture_hide_window()
    if not hide_until_done:
        window.show()
        window.report_hotkey_failures()
    if files:
        window.open_paths([Path(name) for name in files])
    if command is not None:
        _capture_as_first_action(window, command, show_after=hide_until_done)
    sys.exit(app.exec())


def _capture_as_first_action(
    window: MainWindow, command: CaptureCommand, *, show_after: bool
) -> None:
    """Run ``--capture`` once the event loop starts; show the window when it is over."""
    manager = window.capture_manager

    def finish() -> None:
        if show_after and not window.isVisible():
            window.show()
            window.report_hotkey_failures()
        for signal in (
            manager.capture_completed,
            manager.capture_failed,
            manager.capture_cancelled,
        ):
            try:
                signal.disconnect(finish)
            except TypeError:
                pass

    if show_after:
        manager.capture_completed.connect(finish)
        manager.capture_failed.connect(finish)
        manager.capture_cancelled.connect(finish)

    def start() -> None:
        if not manager.start_from_command(command):
            finish()

    QTimer.singleShot(0, start)
