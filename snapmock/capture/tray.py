"""The system tray icon image (PRD 3.2): the application icon, rendered at the tray's size."""

from __future__ import annotations

from PyQt6.QtGui import QIcon

from snapmock.ui.icons import render_application_icon


def make_tray_icon(size: int = 64) -> QIcon:
    """The application icon at *size* pixels (packaging decision 3: one face everywhere)."""
    return QIcon(render_application_icon(size))
