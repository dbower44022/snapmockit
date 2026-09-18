"""Which installed form is running, and the command line that starts it.

The application ships in four forms (Technical Architecture PRD 7.3): from source, as
the AppImage, as the Flatpak, and installed from the Python Package Index. Two things a
user reads differ by form.
The command bound to a key for a capture is one (Screen Capture PRD 3.5 and 9.2): the
Wayland user's only route to a hotkey is a desktop shortcut, and the command that
starts the Flatpak is not the command that starts the AppImage. What Check for Updates
offers is the other (General UI PRD 3.8; Flatpak decision 5; PyPI decision 5): the
release page carries one file per form, and an installation from the index is upgraded
by the tool that installed it.

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

PACKAGE_DIRECTORY = Path(__file__).resolve().parents[1]
"""Where the ``snapmock`` package was imported from."""

INSTALLED_PACKAGE_PARENTS = frozenset({"site-packages", "dist-packages"})
"""The directories an installer puts a distribution in; a checkout is neither."""


class Form(Enum):
    """The ways the application is installed."""

    SOURCE = "source"
    APPIMAGE = "appimage"
    FLATPAK = "flatpak"
    INDEX = "index"


class Installer(Enum):
    """The tool that installed the index's form, which is the tool that upgrades it."""

    PIPX = "pipx"
    UV_TOOL = "uv tool"
    PIP = "pip"


UPGRADE_INSTRUCTIONS = {
    Installer.PIPX: "Upgrade with pipx upgrade snapmockit.",
    Installer.UV_TOOL: "Upgrade with uv tool upgrade snapmockit.",
    Installer.PIP: "Upgrade with pip install --upgrade snapmockit.",
}
"""What a newer release means to an installation from the index (PyPI decision 5)."""


def current_form(
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    package_directory: Path = PACKAGE_DIRECTORY,
) -> Form:
    """The form this process runs as.

    The Flatpak and the AppImage both install the package into a ``site-packages`` of
    their own, so they are told apart first; a package found in one otherwise came from
    the index. A checkout, the editable install ``uv sync`` makes in one included,
    imports from the working tree.
    """
    env = os.environ if environ is None else environ
    if marker.exists():
        return Form.FLATPAK
    if env.get(APPIMAGE_VARIABLE):
        return Form.APPIMAGE
    if package_directory.parent.name in INSTALLED_PACKAGE_PARENTS:
        return Form.INDEX
    return Form.SOURCE


def installer(environ: Mapping[str, str] | None = None, prefix: str | None = None) -> Installer:
    """The tool that installed the environment at *prefix*, read from where it lies.

    pipx keeps each application in ``<PIPX_HOME>/venvs/<name>`` and uv in
    ``<UV_TOOL_DIR>/<name>``; their default homes end in ``pipx`` and in ``uv/tools``
    (``uv/data/tools`` on Windows). Any other environment is taken to be pip's.
    """
    env = os.environ if environ is None else environ
    root = Path(prefix if prefix is not None else sys.prefix)
    parent = root.parent
    pipx_home = env.get("PIPX_HOME")
    if parent.name == "venvs" and (
        (pipx_home and parent.parent == Path(pipx_home)) or parent.parent.name == "pipx"
    ):
        return Installer.PIPX
    uv_tool_dir = env.get("UV_TOOL_DIR")
    if (uv_tool_dir and parent == Path(uv_tool_dir)) or (
        parent.name == "tools" and "uv" in parent.parts[-3:-1]
    ):
        return Installer.UV_TOOL
    return Installer.PIP


def upgrade_instruction(
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    package_directory: Path = PACKAGE_DIRECTORY,
    prefix: str | None = None,
) -> str | None:
    """How an installation from the index takes a newer release; None for other forms."""
    if current_form(environ, marker, package_directory) is not Form.INDEX:
        return None
    return UPGRADE_INSTRUCTIONS[installer(environ, prefix)]


def in_flatpak(marker: Path = FLATPAK_MARKER) -> bool:
    """Whether the process runs inside a Flatpak sandbox (decisions 4 and 5)."""
    return marker.exists()


def launch_command(
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    executable: str | None = None,
    package_directory: Path = PACKAGE_DIRECTORY,
) -> str:
    """The command line that starts this form, ready to paste into a shortcut.

    The Flatpak is started through ``flatpak run``; the AppImage by its own path;
    an installation from the index by the console name where the path leads to the
    command beside the running interpreter, and by that command's full path where it
    does not (a virtual environment that is not activated); a checkout by the console
    name where the path carries one, and otherwise by the interpreter running it.
    """
    env = os.environ if environ is None else environ
    form = current_form(env, marker, package_directory)
    if form is Form.FLATPAK:
        return f"flatpak run {DESKTOP_ENTRY_ID}"
    if form is Form.APPIMAGE:
        return shlex.quote(env[APPIMAGE_VARIABLE])
    interpreter = executable or sys.executable
    on_path = shutil.which(DISTRIBUTION_COMMAND, path=env.get("PATH"))
    if form is Form.INDEX:
        beside = shutil.which(DISTRIBUTION_COMMAND, path=str(Path(interpreter).parent))
        if beside is not None:
            if on_path is not None and Path(on_path).resolve() == Path(beside).resolve():
                return DISTRIBUTION_COMMAND
            return shlex.quote(beside)
    elif on_path is not None:
        return DISTRIBUTION_COMMAND
    return f"{shlex.quote(interpreter)} -m snapmock"


def capture_command(
    mode: str,
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    executable: str | None = None,
    package_directory: Path = PACKAGE_DIRECTORY,
) -> str:
    """The capture command of *mode* for this form (Screen Capture PRD 3.5)."""
    command = launch_command(environ, marker, executable, package_directory)
    return f"{command} --capture {mode}"
