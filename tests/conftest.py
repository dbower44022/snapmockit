"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock import main_window as main_window_module
from snapmock.capture.backend import FakeCaptureBackend, FakeHotkeyBackend
from snapmock.capture.manager import CaptureManager
from snapmock.config import settings as settings_module
from snapmock.config.constants import PANEL_THRESHOLD_MIN
from snapmock.config.settings import AppSettings
from snapmock.core import tool_themes as tool_themes_module
from snapmock.core.scene import SnapScene
from snapmock.core.view import SnapView
from snapmock.main_window import MainWindow


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point AppSettings at a throwaway INI file, a temporary library, and a temporary
    application data directory.

    Keeps the test run from touching the real QSettings store, creating
    ``~/SnapMock/Library``, or writing presets and themes under ``~/.config``.
    """
    ini = tmp_path / "settings.ini"
    library_dir = tmp_path / "Library"

    def _init(self: settings_module.AppSettings) -> None:
        self._qs = QSettings(str(ini), QSettings.Format.IniFormat)

    monkeypatch.setattr(settings_module.AppSettings, "__init__", _init)
    settings_module.AppSettings().set_library_directory(library_dir)
    # The first run is over (General UI PRD 16): no Section 16.2 writes and no Welcome
    # panel in a test's MainWindow unless the test resets the flag itself.
    settings_module.AppSettings().set_first_run_done(True)
    # The offscreen screen is small, so a test window opens at the 1024 by 600 minimum.
    # Thresholds at their floor keep the right panels in full mode (General UI PRD 15.2);
    # the responsive tests set the real defaults back.
    settings_module.AppSettings().set_panel_narrow_threshold(PANEL_THRESHOLD_MIN)
    settings_module.AppSettings().set_panel_strip_threshold(PANEL_THRESHOLD_MIN)
    # Presets, themes, and the tool state (General UI PRD 11.8, 11.9, 15.4) go to a
    # throwaway application data directory, never to ~/.config/snapmock.
    monkeypatch.setattr(
        tool_themes_module, "application_data_directory", lambda: tmp_path / "snapmock-data"
    )
    return library_dir


@pytest.fixture(autouse=True)
def fake_capture_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every MainWindow gets a CaptureManager on the fake backends.

    Keeps the suite off the real platform backends, which would grab the
    developer's screen and register real global hotkeys.
    """

    def _create(settings: AppSettings) -> CaptureManager:
        return CaptureManager(FakeCaptureBackend(), FakeHotkeyBackend(), settings)

    monkeypatch.setattr(main_window_module, "create_capture_manager", _create)


@pytest.fixture(autouse=True)
def _delete_closed_windows(qapp: QApplication) -> Iterator[None]:
    """Delete every closed top-level widget after each test.

    pytest-qt closes the widgets a test registers but never deletes them, so they
    accumulate for the whole run, and every later change of the application style
    sheet, which Qt answers by re-polishing every live widget, grows with them: a
    theme switch cost 30 to 116 seconds on the CI runner by the end of a run
    (docs/Release-Engineering.md, Section 3). This fixture is set up before the
    test's own fixtures and torn down after them, so it runs once qtbot has closed
    the test's widgets, and deletes whatever is closed.
    """
    yield
    from PyQt6 import sip
    from PyQt6.QtCore import QEvent

    for widget in QApplication.topLevelWidgets():
        if not sip.isdeleted(widget) and not widget.isVisible():
            widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()


@pytest.fixture()
def main_window(qtbot: QtBot) -> MainWindow:
    """Create a MainWindow instance managed by qtbot.

    On teardown every open document is marked clean first so the
    unsaved-changes prompt in ``closeEvent`` never blocks the test run.
    """
    window = MainWindow()

    def _mark_all_clean(w: MainWindow) -> None:
        for doc in w.documents.documents:
            doc.scene.command_stack.mark_clean()

    qtbot.addWidget(window, before_close_func=_mark_all_clean)
    return window


@pytest.fixture()
def unmet_messages(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture the never-disabled unmet-requirement messages instead of showing them.

    Each entry is ``(title, text)`` as passed to the information box.
    """
    from snapmock.ui import unmet_requirements

    shown: list[tuple[str, str]] = []

    def _record(_parent: object, title: str, text: str, *_a: object, **_k: object) -> None:
        shown.append((title, text))

    monkeypatch.setattr(unmet_requirements.QMessageBox, "information", staticmethod(_record))
    return shown


@pytest.fixture()
def scene(qapp: QApplication) -> SnapScene:
    """Create a bare SnapScene (no view needed); a QGraphicsScene needs the application first."""
    return SnapScene()


@pytest.fixture()
def view(qtbot: QtBot, scene: SnapScene) -> SnapView:
    """Create a SnapView attached to a SnapScene."""
    v = SnapView(scene)
    qtbot.addWidget(v)
    return v
