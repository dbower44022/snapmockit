"""Tests for the Wayland portal backend and onboarding (PRD 6.4, 9.2).

The whole module is Linux-only: the portal backend is selected nowhere else.
The D-Bus round trip runs against a fake portal registered on the session
bus by the test itself; it is skipped when no session bus is reachable.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

if not sys.platform.startswith("linux"):
    # select_backends() reaches the portal only on Linux. Elsewhere QtDBus is
    # missing from some wheels, and where it is present there is no session bus
    # and its event dispatcher faults on teardown, taking the interpreter with
    # it. Skip before the import so neither case can be hit.
    pytest.skip("the Wayland portal backend is Linux-only", allow_module_level=True)

from PyQt6.QtCore import QObject, QRect, QSize, pyqtSlot  # noqa: E402
from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusObjectPath  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402
from pytestqt.qtbot import QtBot  # noqa: E402

from snapmock.capture import wayland_portal as wp  # noqa: E402
from snapmock.capture.backend import (  # noqa: E402
    CaptureCancelledError,
    CaptureError,
    FakeHotkeyBackend,
)
from snapmock.capture.manager import CaptureManager, CaptureState  # noqa: E402
from snapmock.capture.models import CaptureMode, CaptureRequest, MonitorInfo  # noqa: E402
from snapmock.capture.onboarding import WaylandOnboardingDialog, commands  # noqa: E402
from snapmock.config.settings import AppSettings  # noqa: E402


def _desktop_image(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    for x in range(width):
        for y in range(height):
            image.setPixelColor(x, y, QColor(x % 256, y % 256, 0))
    return image


def test_split_per_monitor_crops_physical_rects(qapp: QApplication) -> None:
    monitors = [
        MonitorInfo("A", QRect(0, 0, 40, 20), QSize(40, 20), 1.0, True),
        MonitorInfo("B", QRect(40, 0, 20, 20), QSize(40, 40), 2.0),
    ]
    image = _desktop_image(120, 40)  # B's physical origin is 40 * 2.0 = 80
    parts = wp.split_per_monitor(image, monitors)
    assert parts["A"].size() == QSize(40, 20) and parts["B"].size() == QSize(40, 40)
    assert parts["B"].pixelColor(0, 0) == image.pixelColor(80, 0)
    assert parts["A"].pixelColor(39, 19) == image.pixelColor(39, 19)


def test_split_scales_when_sizes_differ(qapp: QApplication) -> None:
    monitors = [MonitorInfo("A", QRect(0, 0, 40, 20), QSize(80, 40), 2.0, True)]
    parts = wp.split_per_monitor(_desktop_image(40, 20), monitors)
    assert parts["A"].size() == QSize(80, 40)


def test_read_and_delete_removes_file(qapp: QApplication, tmp_path: Path) -> None:
    file = tmp_path / "shot.png"
    _desktop_image(4, 4).save(str(file))
    image = wp.read_and_delete(file.as_uri())
    assert image.size() == QSize(4, 4) and not file.exists()
    with pytest.raises(CaptureError):
        wp.read_and_delete("")


def test_backend_with_injected_screenshot(qapp: QApplication) -> None:
    calls: list[int] = []

    def shoot() -> QImage:
        calls.append(1)
        monitors = wp.qt_monitors()
        union = QRect()
        for m in monitors:
            union = union.united(m.physical_geometry)
        return _desktop_image(union.width(), union.height())

    backend = wp.WaylandPortalBackend(screenshot=shoot)
    caps = backend.capabilities()
    assert caps.full_screen and caps.region
    assert not caps.active_window and not caps.cursor and not caps.hotkeys
    grab = backend.grab_screens(include_cursor=True)
    assert calls == [1]
    assert set(grab.images) == {m.name for m in backend.monitors()}
    assert grab.cursor_image is None


def test_manager_treats_portal_cancel_as_silent_cancel(qtbot: QtBot) -> None:
    def cancelled() -> QImage:
        raise CaptureCancelledError(wp.MSG_PORTAL_CANCELLED)

    backend = wp.WaylandPortalBackend(screenshot=cancelled)
    manager = CaptureManager(backend, FakeHotkeyBackend(), AppSettings())
    failed: list[str] = []
    manager.capture_failed.connect(failed.append)
    with qtbot.waitSignal(manager.capture_cancelled, timeout=2000):
        manager.start(CaptureRequest(CaptureMode.FULL_SCREEN, hide_window=False))
    assert not failed and manager.state is CaptureState.IDLE


def test_active_window_degrades_to_region_on_portal(qtbot: QtBot) -> None:
    backend = wp.WaylandPortalBackend(screenshot=lambda: _desktop_image(8, 8))
    shown: list[str] = []

    class Sel(QObject):
        from PyQt6.QtCore import pyqtSignal

        region_selected = pyqtSignal(QRect, str)
        cancelled = pyqtSignal()
        failed = pyqtSignal(str)

        def show_selection(self, grab: object, *, hint: str, show_magnifier: bool) -> None:
            shown.append(hint)

        def hide_selection(self) -> None:
            pass

        def destroy(self) -> None:
            pass

    manager = CaptureManager(
        backend, FakeHotkeyBackend(), AppSettings(), overlay_factory=lambda: Sel()
    )
    assert manager.start(CaptureRequest(CaptureMode.ACTIVE_WINDOW, hide_window=False))
    assert shown and "not available on this desktop" in shown[0]
    manager.cancel()


# --- fake portal on the session bus ---


def _session_bus_ok() -> bool:
    return bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")) and (
        QDBusConnection.sessionBus().isConnected()
    )


class FakePortal(QObject):
    """A Screenshot portal that answers with a chosen response code and file."""

    def __init__(self, bus: QDBusConnection, code: int, file: Path | None) -> None:
        super().__init__()
        self._bus = bus
        self.code = code
        self.file = file
        self.calls: list[dict[str, object]] = []

    @pyqtSlot(str, "QVariantMap", result=QDBusObjectPath)
    def Screenshot(self, parent: str, options: dict[str, object]) -> QDBusObjectPath:  # noqa: N802
        self.calls.append(dict(options))
        token = str(options.get("handle_token", "t"))
        handle = wp.request_handle_path(self._bus, token)
        results: dict[str, object] = {}
        if self.file is not None:
            results["uri"] = self.file.as_uri()
        signal = QDBusMessage.createSignal(handle, wp.REQUEST_INTERFACE, "Response")
        signal.setArguments([self.code, results])
        self._bus.send(signal)
        return QDBusObjectPath(handle)


@pytest.fixture()
def fake_portal(qapp: QApplication, tmp_path: Path):  # type: ignore[no-untyped-def]
    if not _session_bus_ok():
        pytest.skip("no D-Bus session bus")
    bus = QDBusConnection.sessionBus()
    service = f"org.snapmock.FakePortal{uuid.uuid4().hex[:8]}"
    assert bus.registerService(service)
    file = tmp_path / "desktop.png"
    _desktop_image(16, 8).save(str(file))
    portal = FakePortal(bus, wp.RESPONSE_SUCCESS, file)
    assert bus.registerObject(
        wp.PORTAL_PATH,
        wp.SCREENSHOT_INTERFACE,
        portal,
        QDBusConnection.RegisterOption.ExportAllSlots,
    )
    yield service, portal, file
    bus.unregisterObject(wp.PORTAL_PATH)
    bus.unregisterService(service)


def test_portal_round_trip_success(fake_portal: tuple[str, FakePortal, Path]) -> None:
    service, portal, file = fake_portal
    client = wp.PortalScreenshotClient(service=service)
    assert client.is_available()
    image = client.screenshot(timeout_ms=5000)
    assert image.size() == QSize(16, 8)
    assert not file.exists()
    assert portal.calls and portal.calls[0]["interactive"] is False


def test_portal_round_trip_cancel_and_error(fake_portal: tuple[str, FakePortal, Path]) -> None:
    service, portal, _file = fake_portal
    client = wp.PortalScreenshotClient(service=service)
    portal.code = wp.RESPONSE_CANCELLED
    with pytest.raises(CaptureCancelledError):
        client.screenshot(timeout_ms=5000)
    portal.code = 2
    with pytest.raises(CaptureError, match=wp.MSG_PORTAL_FAILED):
        client.screenshot(timeout_ms=5000)


def test_missing_portal_reports_install_message(qapp: QApplication) -> None:
    client = wp.PortalScreenshotClient(service="org.snapmock.NoSuchPortal")
    assert not client.is_available()
    with pytest.raises(CaptureError, match="xdg-desktop-portal"):
        client.screenshot(timeout_ms=100)


# --- onboarding (PRD 9.2) ---


def test_onboarding_dialog_panels_and_copy(qtbot: QtBot, qapp: QApplication) -> None:
    dlg = WaylandOnboardingDialog()
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "Capturing on Wayland"
    assert set(dlg.shortcut_panel.fields) == {c for _l, c in commands()}
    assert dlg.dont_show.isVisible() is False  # dialog not shown yet; widget exists
    buttons = dlg.findChild(QDialogButtonBox)
    assert buttons is not None
    labels = [b.text() for b in buttons.buttons()]
    assert "Continue" in labels and any("Cancel" in t for t in labels)
    helper = WaylandOnboardingDialog(help_only=True)
    qtbot.addWidget(helper)
    assert helper.windowTitle() == "Set Up a Desktop Shortcut"
    assert helper.dont_show.isHidden()
