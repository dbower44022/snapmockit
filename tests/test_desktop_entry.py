"""The desktop entry, the icons, and the MIME type written and removed under a temporary home.

Menu-entry Phase 1. Every test writes to a temporary directory: nothing here ever touches
the developer's own ``~/.local/share``, which the kickoff forbids. The two database tools
are not run (``run_databases=False``) unless the test is about them, since a runner has
neither.
"""

from __future__ import annotations

import configparser
import os
import stat
from collections.abc import Mapping
from pathlib import Path

import pytest

from snapmock.config import desktop_entry
from snapmock.config.constants import APP_NAME, DESKTOP_ENTRY_ID
from snapmock.config.packaging import APPIMAGE_VARIABLE

MIME_TYPE = "application/x-snapmockit-project"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A home of this test's own, with ``XDG_DATA_HOME`` inside it."""
    base = tmp_path / "home"
    (base / ".local" / "share").mkdir(parents=True)
    return base


@pytest.fixture
def env(home: Path) -> dict[str, str]:
    """An environment naming that home and nothing else the module reads."""
    return {"HOME": str(home), "XDG_DATA_HOME": str(home / ".local" / "share"), "PATH": ""}


def source_environment(env: Mapping[str, str], **extra: str) -> dict[str, str]:
    """*env* with anything that would make the form the AppImage's removed."""
    values = {key: value for key, value in env.items() if key != APPIMAGE_VARIABLE}
    values.update(extra)
    return values


# ---- where things go -------------------------------------------------------------------


def test_data_home_reads_the_variable_then_falls_back(home: Path) -> None:
    named = {"HOME": str(home), "XDG_DATA_HOME": str(home / "elsewhere")}
    assert desktop_entry.data_home(named) == home / "elsewhere"
    assert desktop_entry.data_home({"HOME": str(home)}) == home / ".local" / "share"
    assert desktop_entry.data_home({"HOME": str(home), "XDG_DATA_HOME": ""}) == (
        home / ".local" / "share"
    )


def test_nothing_is_written_outside_the_data_home(env: dict[str, str], home: Path) -> None:
    base = home / ".local" / "share"
    for path in desktop_entry.written_paths(env):
        assert base in path.parents, path


def test_the_icon_paths_are_the_recipe_sizes_and_the_scalable_svg(env: dict[str, str]) -> None:
    paths = desktop_entry.icon_paths(env)
    assert len(paths) == len(desktop_entry.ICON_SIZES) + 1
    assert [p.parent.parent.name for p in paths[:-1]] == [
        f"{size}x{size}" for size in desktop_entry.ICON_SIZES
    ]
    assert paths[-1].parent.parent.name == "scalable"
    assert paths[-1].suffix == ".svg"


# ---- what the entry says ---------------------------------------------------------------


def test_quote_exec_leaves_a_plain_path_alone_and_quotes_a_space() -> None:
    assert desktop_entry.quote_exec("/home/doug/.local/bin/snapmockit") == (
        "/home/doug/.local/bin/snapmockit"
    )
    assert desktop_entry.quote_exec("/home/doug/My Apps/Snapmockit.AppImage") == (
        '"/home/doug/My Apps/Snapmockit.AppImage"'
    )
    assert desktop_entry.quote_exec("/tmp/a$b") == '"/tmp/a\\\\$b"'


def test_the_appimage_entry_names_the_running_file(env: dict[str, str], tmp_path: Path) -> None:
    appimage = tmp_path / "Downloads" / "Snapmockit-1.2.0-x86_64.AppImage"
    appimage.parent.mkdir(parents=True)
    appimage.write_bytes(b"\x7fELF\x02\x01\x01\x00AI\x02")
    program = desktop_entry.program_path({**env, APPIMAGE_VARIABLE: str(appimage)})
    assert program == str(appimage)


def test_the_index_entry_names_the_command_beside_the_interpreter(
    env: dict[str, str], tmp_path: Path
) -> None:
    """Decision 2, option B: an absolute path, never the bare console name."""
    venv = tmp_path / "venvs" / "snapmockit"
    binaries = venv / "bin"
    binaries.mkdir(parents=True)
    command = binaries / "snapmockit"
    command.write_text("#!/bin/sh\n")
    command.chmod(command.stat().st_mode | stat.S_IEXEC)
    package = venv / "lib" / "python3.12" / "site-packages" / "snapmock"
    package.mkdir(parents=True)

    program = desktop_entry.program_path(
        source_environment(env, PATH=str(binaries)),
        executable=str(binaries / "python"),
        package_directory=package,
    )
    assert program == str(command)


def test_a_path_with_a_space_is_quoted_in_the_entry(env: dict[str, str], tmp_path: Path) -> None:
    venv = tmp_path / "My Tools" / "snapmockit"
    binaries = venv / "bin"
    binaries.mkdir(parents=True)
    command = binaries / "snapmockit"
    command.write_text("#!/bin/sh\n")
    command.chmod(command.stat().st_mode | stat.S_IEXEC)
    package = venv / "lib" / "python3.12" / "site-packages" / "snapmock"
    package.mkdir(parents=True)

    program = desktop_entry.program_path(
        source_environment(env, PATH=str(binaries)),
        executable=str(binaries / "python"),
        package_directory=package,
    )
    assert program == f'"{command}"'


def test_without_an_installed_command_the_interpreter_runs_the_module(
    env: dict[str, str], tmp_path: Path
) -> None:
    interpreter = tmp_path / "python"
    interpreter.write_text("")
    program = desktop_entry.program_path(source_environment(env), executable=str(interpreter))
    assert program == f"{interpreter} -m snapmock"


def test_the_entry_keeps_every_packaged_field_and_takes_the_new_exec() -> None:
    text = desktop_entry.entry_text("/opt/snapmockit")
    parser = configparser.RawConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[method-assign]
    parser.read_string(text)
    section = parser["Desktop Entry"]
    assert section["Exec"] == "/opt/snapmockit %F"
    assert section["Name"] == APP_NAME
    assert section["Icon"] == DESKTOP_ENTRY_ID
    assert section["Categories"] == "Graphics;Utility;"
    assert section["MimeType"] == f"{MIME_TYPE};"
    assert section["StartupWMClass"] == APP_NAME


# ---- install and remove ----------------------------------------------------------------


def test_install_writes_the_entry_the_icons_and_the_mime_file(
    qapp: object, env: dict[str, str], home: Path
) -> None:
    outcome = desktop_entry.install(source_environment(env), run_databases=False)
    assert outcome.changed
    assert not outcome.notes, outcome.notes
    for path in desktop_entry.written_paths(env):
        assert path.is_file(), path
    entry = desktop_entry.entry_path(env)
    assert entry.read_text(encoding="utf-8").startswith("[Desktop Entry]")
    assert MIME_TYPE in desktop_entry.mime_path(env).read_text(encoding="utf-8")
    assert desktop_entry.installed(env)
    assert str(home) in str(entry)


def test_every_icon_is_written_at_its_own_size(qapp: object, env: dict[str, str]) -> None:
    from PyQt6.QtGui import QImage

    desktop_entry.install(source_environment(env), run_databases=False)
    paths = desktop_entry.icon_paths(env)
    for size, path in zip(desktop_entry.ICON_SIZES, paths[:-1], strict=True):
        image = QImage(str(path))
        assert (image.width(), image.height()) == (size, size), path
    assert paths[-1].read_bytes() == desktop_entry.ICON_SOURCE.read_bytes()


def test_the_entry_is_read_back_by_the_entry_point(qapp: object, env: dict[str, str]) -> None:
    """``app.desktop_entry_installed`` is what gives Qt the desktop id at start."""
    from snapmock.app import desktop_entry_installed

    assert not desktop_entry_installed(environ={**env, "XDG_DATA_DIRS": ""})
    desktop_entry.install(source_environment(env), run_databases=False)
    assert desktop_entry_installed(environ={**env, "XDG_DATA_DIRS": ""})


def test_a_second_install_over_the_first_leaves_one_entry(
    qapp: object, env: dict[str, str]
) -> None:
    desktop_entry.install(source_environment(env), program="/one", run_databases=False)
    second = desktop_entry.install(source_environment(env), program="/two", run_databases=False)
    assert second.changed
    text = desktop_entry.entry_path(env).read_text(encoding="utf-8")
    assert "Exec=/two %F" in text
    assert "Exec=/one %F" not in text


def test_remove_leaves_nothing_behind(qapp: object, env: dict[str, str]) -> None:
    desktop_entry.install(source_environment(env), run_databases=False)
    outcome = desktop_entry.remove(source_environment(env), run_databases=False)
    assert outcome.changed
    for path in desktop_entry.written_paths(env):
        assert not path.exists(), path
    assert not desktop_entry.installed(env)


def test_remove_with_nothing_installed_says_so_and_writes_nothing(env: dict[str, str]) -> None:
    outcome = desktop_entry.remove(source_environment(env), run_databases=False)
    assert not outcome.changed
    assert "was not in the menu" in outcome.message()


def test_a_read_only_directory_is_reported_and_not_raised(
    qapp: object, env: dict[str, str], home: Path
) -> None:
    share = home / ".local" / "share"
    applications = share / "applications"
    applications.mkdir(parents=True)
    applications.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        outcome = desktop_entry.install(source_environment(env), run_databases=False)
    finally:
        applications.chmod(stat.S_IRWXU)
    assert not outcome.changed
    assert "could not be added to the menu" in outcome.message()
    assert not desktop_entry.installed(env)


def test_a_read_only_mime_directory_still_installs_the_entry(
    qapp: object, env: dict[str, str], home: Path
) -> None:
    mime = home / ".local" / "share" / "mime"
    mime.mkdir(parents=True)
    mime.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        outcome = desktop_entry.install(source_environment(env), run_databases=False)
    finally:
        mime.chmod(stat.S_IRWXU)
    assert desktop_entry.installed(env)
    assert "double-click" in outcome.message()
    assert not desktop_entry.mime_path(env).exists()


def test_the_flatpak_form_writes_nothing_at_all(env: dict[str, str], tmp_path: Path) -> None:
    marker = tmp_path / "flatpak-info"
    marker.write_text("[Application]\n")
    reason = desktop_entry.unsupported_reason(env, marker=marker)
    assert reason is not None and "already in the menu" in reason

    outcome = desktop_entry.install(source_environment(env), marker=marker, run_databases=False)
    assert not outcome.changed
    assert not desktop_entry.entry_path(env).exists()
    removed = desktop_entry.remove(source_environment(env), marker=marker, run_databases=False)
    assert not removed.changed


def test_a_missing_database_tool_is_a_note_and_not_a_failure(
    qapp: object, env: dict[str, str]
) -> None:
    outcome = desktop_entry.install(source_environment(env, PATH=""), run_databases=True)
    assert outcome.changed
    assert any("update-desktop-database is not installed" in note for note in outcome.notes)
    assert any("update-mime-database is not installed" in note for note in outcome.notes)


def test_the_database_tools_are_run_where_they_exist(
    qapp: object, env: dict[str, str], tmp_path: Path
) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "calls.txt"
    for name in ("update-desktop-database", "update-mime-database"):
        script = binaries / name
        script.write_text(f'#!/bin/sh\necho "{name} $1" >> "{log}"\n')
        script.chmod(script.stat().st_mode | stat.S_IEXEC)

    outcome = desktop_entry.install(
        source_environment(env, PATH=str(binaries)), run_databases=True
    )
    assert not outcome.notes, outcome.notes
    lines = log.read_text().splitlines()
    share = desktop_entry.data_home(env)
    assert f"update-desktop-database {share / 'applications'}" in lines
    assert f"update-mime-database {share / 'mime'}" in lines


# ---- the AppImage's own file (decision 3) -----------------------------------------------


def test_the_appimage_destination_is_the_fixed_name(env: dict[str, str], home: Path) -> None:
    assert (
        desktop_entry.appimage_destination(env) == home / "Applications" / f"{APP_NAME}.AppImage"
    )


def test_the_copy_is_made_executable_and_overwrites_an_earlier_one(tmp_path: Path) -> None:
    source = tmp_path / "Snapmockit-1.2.0-x86_64.AppImage"
    source.write_bytes(b"\x7fELF\x02\x01\x01\x00AI\x02new")
    destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    destination.parent.mkdir()
    destination.write_bytes(b"\x7fELF\x02\x01\x01\x00AI\x02old")

    assert desktop_entry.copy_appimage(source, destination) == destination
    assert destination.read_bytes() == source.read_bytes()
    assert os.access(destination, os.X_OK)


def test_a_destination_that_is_not_an_appimage_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "Snapmockit.AppImage"
    source.write_bytes(b"\x7fELF\x02\x01\x01\x00AI\x02")
    destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    destination.parent.mkdir()
    destination.write_text("a file of the user's own")

    with pytest.raises(ValueError):
        desktop_entry.copy_appimage(source, destination)
    assert destination.read_text() == "a file of the user's own"


def test_the_entry_can_be_pointed_at_the_copy(qapp: object, env: dict[str, str]) -> None:
    """Decision 3: the AppImage's entry names the copy, not the file it ran from."""
    destination = desktop_entry.appimage_destination(env)
    desktop_entry.install(source_environment(env), program=str(destination), run_databases=False)
    text = desktop_entry.entry_path(env).read_text(encoding="utf-8")
    assert f"Exec={destination} %F" in text
