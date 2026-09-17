"""Which installed form is running, and the command line that starts it.

On Linux the application ships in three forms (Technical Architecture PRD 7.3): from
source, as the AppImage, and as the Flatpak. Two things a user reads differ by form.
The command bound to a key for a capture is one (Screen Capture PRD 3.5 and 9.2): the
Wayland user's only route to a hotkey is a desktop shortcut, and the command that
starts the Flatpak is not the command that starts the AppImage. What Check for Updates
offers is the other (General UI PRD 3.8; Flatpak decision 5): the release page carries
one file per form.

Nothing here reads a setting or asks the user: the form is read from the environment the
process is already in.
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from collections.abc import Mapping
from enum import Enum
from pathlib import Path

from snapmock.config.constants import DESKTOP_ENTRY_ID

FLATPAK_MARKER = Path("/.flatpak-info")
"""Every Flatpak sandbox carries this file; nothing outside one does."""

APPIMAGE_VARIABLE = "APPIMAGE"
"""The AppImage runtime sets this to the sealed file's own path."""

DISTRIBUTION_COMMAND = "snapmockit"
"""The console name a packaged installation puts on the path."""


class Form(Enum):
    """The three ways the application is installed on Linux."""

    SOURCE = "source"
    APPIMAGE = "appimage"
    FLATPAK = "flatpak"


def current_form(environ: Mapping[str, str] | None = None, marker: Path = FLATPAK_MARKER) -> Form:
    """The form this process runs as."""
    env = os.environ if environ is None else environ
    if marker.exists():
        return Form.FLATPAK
    if env.get(APPIMAGE_VARIABLE):
        return Form.APPIMAGE
    return Form.SOURCE


def in_flatpak(marker: Path = FLATPAK_MARKER) -> bool:
    """Whether the process runs inside a Flatpak sandbox (decisions 4 and 5)."""
    return marker.exists()


def launch_command(
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    executable: str | None = None,
) -> str:
    """The command line that starts this form, ready to paste into a shortcut.

    The Flatpak is started through ``flatpak run``; the AppImage by its own path;
    a packaged installation by the console name where the path carries one, and a
    checkout by the interpreter that is running it.
    """
    env = os.environ if environ is None else environ
    form = current_form(env, marker)
    if form is Form.FLATPAK:
        return f"flatpak run {DESKTOP_ENTRY_ID}"
    if form is Form.APPIMAGE:
        return shlex.quote(env[APPIMAGE_VARIABLE])
    if shutil.which(DISTRIBUTION_COMMAND):
        return DISTRIBUTION_COMMAND
    return f"{shlex.quote(executable or sys.executable)} -m snapmock"


def capture_command(
    mode: str,
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    executable: str | None = None,
) -> str:
    """The capture command of *mode* for this form (Screen Capture PRD 3.5)."""
    return f"{launch_command(environ, marker, executable)} --capture {mode}"
