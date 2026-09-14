"""macOS backend stub (PRD 6.5, 9.1).

Implements the interfaces, reports the Screen Recording permission model,
and raises :class:`CaptureError` from every grab until the Core Graphics
paths through ctypes are written. Imports on every platform.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect

from snapmock.capture.backend import (
    CaptureBackend,
    CaptureError,
    HotkeyBackend,
    NullHotkeyBackend,
    QtScreenGrabBackend,
)
from snapmock.capture.models import BackendCapabilities, PermissionState, ScreenGrab
from snapmock.config.constants import APP_NAME

NOT_IMPLEMENTED = "not yet implemented on this platform"
PERMISSION_MESSAGE = (
    f"{APP_NAME} needs Screen Recording permission. Enable {APP_NAME} under System Settings > "
    f"Privacy & Security > Screen Recording, then quit and reopen {APP_NAME}."
)
SCREEN_RECORDING_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
)


class MacOSCaptureBackend(QtScreenGrabBackend):
    """Core Graphics grab through Qt; window list and cursor through ctypes (planned)."""

    name = "macos"
    permission_message = PERMISSION_MESSAGE
    settings_url = SCREEN_RECORDING_SETTINGS_URL

    def __init__(self) -> None:
        # The stub cannot preflight or request; it reports denied until implemented.
        self.permission_state = PermissionState.DENIED
        self.permission_requests = 0

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            full_screen=True,
            active_window=True,
            region=True,
            cursor=True,
            hotkeys=False,  # deferred past version 1 (PRD 6.7)
            tray=True,
            needs_permission=True,
        )

    def request_permission(self) -> PermissionState:
        self.permission_requests += 1
        return self.permission_state

    def grab_screens(self, include_cursor: bool) -> ScreenGrab:
        if self.permission_state is not PermissionState.GRANTED:
            raise CaptureError(PERMISSION_MESSAGE)
        raise CaptureError(NOT_IMPLEMENTED)

    def active_window_geometry(self) -> QRect | None:
        return None


def create_backends() -> tuple[CaptureBackend, HotkeyBackend]:
    return MacOSCaptureBackend(), NullHotkeyBackend()
