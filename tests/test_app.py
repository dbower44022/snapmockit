"""Tests for the main application window and the entry point."""

from pathlib import Path

import pytest

from snapmock.app import main, version_text
from snapmock.config.constants import APP_NAME, APP_VERSION
from snapmock.core.scene import SnapScene
from snapmock.io.project_serializer import save_project
from snapmock.main_window import MainWindow


def test_main_window_title(main_window: MainWindow) -> None:
    """Window title follows the PRD 2.4 pattern: [Project Name] - Snapmockit."""
    assert main_window.windowTitle() == "Untitled - Snapmockit"


def test_main_window_minimum_size(main_window: MainWindow) -> None:
    """PRD 15.1: the window cannot shrink below 1024x600."""
    assert main_window.minimumWidth() == 1024
    assert main_window.minimumHeight() == 600


def test_main_window_default_size(main_window: MainWindow) -> None:
    """Window should have a reasonable default size.

    Exact dimensions may differ from the requested 1200x800 due to
    display scaling, restored QSettings geometry, or window-manager
    constraints, so we only verify sensible minimums.
    """
    assert main_window.width() >= 800
    assert main_window.height() >= 600


def test_main_window_has_scene(main_window: MainWindow) -> None:
    """MainWindow should expose a SnapScene."""
    assert main_window.scene is not None


def test_main_window_has_view(main_window: MainWindow) -> None:
    """The active document's SnapView lives inside the central tab widget."""
    assert main_window.view is not None
    central = main_window.centralWidget()
    assert central is not None
    assert main_window.view.parent() is not None
    assert central.isAncestorOf(main_window.view)


def test_version_flag_prints_the_product_and_exits_before_qt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Packaging silence 6: ``--version`` prints the name and version, exit code 0."""
    with pytest.raises(SystemExit) as exit_info:
        main(["snapmock", "--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"{APP_NAME} {APP_VERSION}"
    assert version_text() == f"{APP_NAME} {APP_VERSION}"


def test_open_paths_opens_a_project_from_the_command_line(
    main_window: MainWindow, tmp_path: Path
) -> None:
    """Packaging silence 2: files named on the command line open in tabs."""
    path = tmp_path / "from-desktop.smk"
    save_project(SnapScene(width=300, height=200), path)
    main_window.open_paths([path])
    assert main_window.active_document.file_path == path
    assert main_window.scene.canvas_size.width() == 300
