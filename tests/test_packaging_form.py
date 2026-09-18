"""The installed form and the command that starts it (`snapmock/config/packaging.py`).

Flatpak decisions 4 and 5 and the Flatpak notes' correction 5.3: the command a user
binds to a key, and what Check for Updates offers, differ by form. Nothing here runs
a Flatpak: the sandbox's marker file is a temporary path and the AppImage's variable
is an environment mapping.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

from snapmock.capture.models import (
    HOTKEY_ACTION_FULL_SCREEN,
    HOTKEY_ACTION_REGION,
    HOTKEY_ACTION_WINDOW,
)
from snapmock.capture.onboarding import commands
from snapmock.config.constants import DESKTOP_ENTRY_ID
from snapmock.config.packaging import (
    PACKAGE_DIRECTORY,
    Form,
    Installer,
    capture_command,
    current_form,
    in_flatpak,
    installer,
    launch_command,
    upgrade_instruction,
)
from snapmock.ui.preferences_dialog import command_line_for_action


@pytest.fixture()
def marker(tmp_path: Path) -> Path:
    """A path standing in for ``/.flatpak-info``; it does not exist yet."""
    return tmp_path / "flatpak-info"


def test_a_checkout_is_the_source_form(marker: Path) -> None:
    assert current_form({}, marker) is Form.SOURCE
    assert in_flatpak(marker) is False


def test_the_sandbox_marker_makes_it_the_flatpak_form(marker: Path) -> None:
    marker.write_text("[Application]\n", encoding="utf-8")
    assert current_form({"APPIMAGE": "/tmp/Snapmockit.AppImage"}, marker) is Form.FLATPAK
    assert in_flatpak(marker) is True


def test_the_appimage_variable_makes_it_the_appimage_form(marker: Path) -> None:
    assert current_form({"APPIMAGE": "/tmp/Snapmockit.AppImage"}, marker) is Form.APPIMAGE


def test_the_flatpak_is_started_through_flatpak_run(marker: Path) -> None:
    marker.write_text("[Application]\n", encoding="utf-8")
    assert launch_command({}, marker) == f"flatpak run {DESKTOP_ENTRY_ID}"
    assert capture_command("region", {}, marker) == (
        f"flatpak run {DESKTOP_ENTRY_ID} --capture region"
    )


def test_the_appimage_is_started_by_its_own_path(marker: Path) -> None:
    env = {"APPIMAGE": "/home/someone/Apps/Snapmockit-1.0.0-x86_64.AppImage"}
    assert launch_command(env, marker) == env["APPIMAGE"]
    assert capture_command("full", env, marker).endswith(" --capture full")


def test_a_path_with_a_space_is_quoted_for_the_shell(marker: Path) -> None:
    env = {"APPIMAGE": "/home/someone/My Apps/Snapmockit.AppImage"}
    assert launch_command(env, marker) == shlex.quote(env["APPIMAGE"])


def test_a_checkout_names_the_interpreter_that_runs_it(marker: Path, tmp_path: Path) -> None:
    """No console script is installed from a checkout, so the module is named."""
    command = launch_command({"PATH": str(tmp_path)}, marker)
    assert command in (f"{shlex.quote(sys.executable)} -m snapmock", "snapmockit")


def test_the_onboarding_page_shows_the_running_form_s_three_commands() -> None:
    labels = [label for label, _command in commands()]
    assert labels == ["Region", "Active window", "Full screen"]
    for mode, (_label, command) in zip(("region", "window", "full"), commands(), strict=True):
        assert command == capture_command(mode)
        assert not command.startswith("snapmock --capture")  # the command that never existed


def test_the_preferences_dialog_shows_the_same_command() -> None:
    assert command_line_for_action(HOTKEY_ACTION_REGION) == capture_command("region")
    assert command_line_for_action(HOTKEY_ACTION_WINDOW) == capture_command("window")
    assert command_line_for_action(HOTKEY_ACTION_FULL_SCREEN) == capture_command("full")


# The installation from the Python Package Index (PyPI decisions 3 and 5).


def _installed(root: Path) -> Path:
    """A package directory laid out as an installer lays it out under *root*."""
    package = root / "lib" / "python3.12" / "site-packages" / "snapmock"
    package.mkdir(parents=True)
    return package


def _command(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    command = bin_dir / "snapmockit"
    command.write_text("#! /bin/sh\n", encoding="utf-8")
    command.chmod(0o755)
    return command


def test_the_suite_runs_from_a_checkout() -> None:
    """The editable install uv sync makes imports from the working tree."""
    assert current_form() is Form.SOURCE
    assert PACKAGE_DIRECTORY.parent.name not in {"site-packages", "dist-packages"}
    assert upgrade_instruction() is None


def test_a_package_in_site_packages_is_the_index_form(marker: Path, tmp_path: Path) -> None:
    package = _installed(tmp_path / "venv")
    assert current_form({}, marker, package) is Form.INDEX
    debian = tmp_path / "usr" / "lib" / "python3" / "dist-packages" / "snapmock"
    debian.mkdir(parents=True)
    assert current_form({}, marker, debian) is Form.INDEX


def test_the_flatpak_and_the_appimage_win_over_their_own_site_packages(
    marker: Path, tmp_path: Path
) -> None:
    package = _installed(tmp_path / "app")
    assert current_form({"APPIMAGE": "/tmp/S.AppImage"}, marker, package) is Form.APPIMAGE
    marker.write_text("[Application]\n", encoding="utf-8")
    assert current_form({}, marker, package) is Form.FLATPAK


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("/home/u/.local/share/pipx/venvs/snapmockit", Installer.PIPX),
        ("/home/u/.local/pipx/venvs/snapmockit", Installer.PIPX),
        ("/home/u/.local/share/uv/tools/snapmockit", Installer.UV_TOOL),
        ("/home/u/AppData/Roaming/uv/data/tools/snapmockit", Installer.UV_TOOL),
        ("/home/u/project/.venv", Installer.PIP),
        ("/usr", Installer.PIP),
        ("/home/u/venvs/snapmockit", Installer.PIP),  # a venvs folder that is not pipx's
    ],
)
def test_the_installer_is_read_from_the_environment_s_place(
    prefix: str, expected: Installer
) -> None:
    assert installer({}, prefix) is expected


def test_pipx_home_and_uv_tool_dir_are_honoured() -> None:
    assert installer({"PIPX_HOME": "/opt/apps"}, "/opt/apps/venvs/snapmockit") is Installer.PIPX
    assert installer({"UV_TOOL_DIR": "/opt/tools"}, "/opt/tools/snapmockit") is Installer.UV_TOOL


def test_each_installer_has_its_upgrade_line(marker: Path, tmp_path: Path) -> None:
    package = _installed(tmp_path / "venv")
    lines = {
        prefix: upgrade_instruction({}, marker, package, prefix)
        for prefix in (
            "/h/.local/share/pipx/venvs/snapmockit",
            "/h/.local/share/uv/tools/snapmockit",
            "/h/.venv",
        )
    }
    assert list(lines.values()) == [
        "Upgrade with pipx upgrade snapmockit.",
        "Upgrade with uv tool upgrade snapmockit.",
        "Upgrade with pip install --upgrade snapmockit.",
    ]
    assert upgrade_instruction({}, marker, tmp_path / "checkout" / "snapmock") is None


def test_the_index_form_is_started_by_the_command_on_the_path(
    marker: Path, tmp_path: Path
) -> None:
    """pipx and uv tool link the environment's command into a folder on the path."""
    package = _installed(tmp_path / "venv")
    beside = _command(tmp_path / "venv" / "bin")
    linked = tmp_path / "local-bin"
    linked.mkdir()
    (linked / "snapmockit").symlink_to(beside)
    python = str(tmp_path / "venv" / "bin" / "python")
    env = {"PATH": str(linked)}
    assert launch_command(env, marker, python, package) == "snapmockit"
    assert capture_command("region", env, marker, python, package) == (
        "snapmockit --capture region"
    )


def test_an_environment_off_the_path_is_started_by_its_command_s_full_path(
    marker: Path, tmp_path: Path
) -> None:
    """A virtual environment that is not activated (the notes' silence 6, corrected)."""
    package = _installed(tmp_path / "my venv")
    beside = _command(tmp_path / "my venv" / "bin")
    python = str(tmp_path / "my venv" / "bin" / "python")
    elsewhere = _command(tmp_path / "other")  # another installation's command
    for path in (str(tmp_path / "empty"), str(elsewhere.parent)):
        assert launch_command({"PATH": path}, marker, python, package) == shlex.quote(str(beside))


def test_the_index_form_without_its_command_names_the_interpreter(
    marker: Path, tmp_path: Path
) -> None:
    package = _installed(tmp_path / "venv")
    python = str(tmp_path / "venv" / "bin" / "python")
    assert launch_command({"PATH": ""}, marker, python, package) == (
        f"{shlex.quote(python)} -m snapmock"
    )
