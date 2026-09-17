"""QApplication bootstrap, the single-instance channel, and command-line capture (PRD 3.5)."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from snapmock.capture.cli import CaptureCommand, parse_command_line
from snapmock.capture.single_instance import try_forward
from snapmock.config.constants import APP_NAME, APP_VERSION, DESKTOP_ENTRY_ID
from snapmock.config.migration import import_host_settings, migrate_storage
from snapmock.main_window import MainWindow
from snapmock.ui.icons import application_icon

log = logging.getLogger("snapmock")


def desktop_entry_installed(
    entry_id: str = DESKTOP_ENTRY_ID, environ: Mapping[str, str] | None = None
) -> bool:
    """Whether ``<entry_id>.desktop`` is in an applications directory of the XDG data path.

    ``$XDG_DATA_HOME`` (default ``~/.local/share``) and ``$XDG_DATA_DIRS``
    (default ``/usr/local/share:/usr/share``), as the desktop and its portal
    look the entry up. True from a package that installed the entry, or from an
    AppImage integrated into the menu; false from source and from a bare AppImage.
    """
    env = os.environ if environ is None else environ
    data_home = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    data_dirs = env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for base in [data_home, *data_dirs.split(":")]:
        if base and (Path(base) / "applications" / f"{entry_id}.desktop").is_file():
            return True
    return False


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
    # ID", seen from the AppImage on 09-14-26). The id is given to Qt only where
    # the desktop entry is installed, since the portal looks the entry up and
    # answers "App info not found" for an AppImage that is not in the menu.
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(APP_VERSION)
    if desktop_entry_installed():
        QApplication.setDesktopFileName(DESKTOP_ENTRY_ID)
    # The application is created before the forward because the write to the
    # channel completes only once an event loop is available to pump it, which
    # is how a Windows named pipe behaves (PRD 3.5).
    app = QApplication(argv)
    app.setWindowIcon(application_icon())
    if command is not None and try_forward(argv):
        sys.exit(0)

    # Before anything reads the settings or the library (packaging decision 4).
    migration = migrate_storage()
    # Inside a Flatpak, the store is the sandbox's own; fill it once from the home
    # directory's on the first start (Flatpak decision 4).
    imported = import_host_settings()
    window = MainWindow(restore_session=True)
    manager = window.capture_manager
    manager.listen_for_commands()
    manager.register_hotkeys()

    hide_until_done = command is not None and window.capture_manager.settings.capture_hide_window()
    if not hide_until_done:
        window.show()
        window.report_hotkey_failures()
    startup_messages = [text for text in (migration.message(), imported.message()) if text]
    if startup_messages:
        window.show_startup_message(" ".join(startup_messages))
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
