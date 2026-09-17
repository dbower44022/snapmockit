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
    Form,
    capture_command,
    current_form,
    in_flatpak,
    launch_command,
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
