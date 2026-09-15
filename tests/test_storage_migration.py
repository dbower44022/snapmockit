"""The one-time move of the on-disk names (packaging decision 4; config/migration.py).

Every test works in a temporary home and configuration root; nothing here touches the
real ``~/.config`` or the real library.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings

from snapmock.config import migration
from snapmock.config.constants import APP_NAME
from snapmock.config.migration import (
    MigrationReport,
    Move,
    data_directory,
    default_library_directory,
    library_preference,
    migrate_storage,
    rewrite_paths,
    storage_names,
)

OLD_CONF = Path("SnapMock") / "SnapMock.conf"
NEW_CONF = Path(APP_NAME) / f"{APP_NAME}.conf"


@pytest.fixture
def places(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    root = home / ".config"
    root.mkdir(parents=True)
    return home, root


def make_old_layout(home: Path, root: Path, *, preference: str = "") -> Path:
    """The disk as the earlier name left it: the store, the data directory, the library."""
    old_lib = home / "SnapMock" / "Library"
    old_lib.mkdir(parents=True)
    (old_lib / "Capture_2026-09-07.smk").write_bytes(b"PK")
    (root / "snapmock").mkdir()
    (root / "snapmock" / "tool_state.json").write_text("{}", encoding="utf-8")
    conf = root / OLD_CONF
    conf.parent.mkdir()
    settings = QSettings(str(conf), QSettings.Format.IniFormat)
    settings.setValue("library/directory", preference)
    settings.setValue(
        "files/recent", [str(old_lib / "Capture_2026-09-07.smk"), "/elsewhere/x.smk"]
    )
    settings.setValue("library/openFiles", f"{old_lib}/Capture_2026-09-07.smk, /elsewhere/x.smk")
    settings.setValue("window/geometry", b"\x01\x02")
    settings.setValue("view/zoom", 150)
    settings.sync()
    return conf


# ---- the lookups ----


def test_lookups_answer_with_the_product_names_on_a_fresh_machine(
    places: tuple[Path, Path],
) -> None:
    home, root = places
    assert storage_names(root) == (APP_NAME, APP_NAME)
    assert data_directory(root) == root / "snapmockit"
    assert default_library_directory(home) == home / APP_NAME / "Library"


def test_lookups_answer_with_the_old_names_while_only_the_old_store_exists(
    places: tuple[Path, Path],
) -> None:
    home, root = places
    make_old_layout(home, root)
    assert storage_names(root) == ("SnapMock", "SnapMock")
    assert data_directory(root) == root / "snapmock"
    assert default_library_directory(home) == home / "SnapMock" / "Library"


def test_lookups_prefer_the_new_location_when_both_exist(places: tuple[Path, Path]) -> None:
    home, root = places
    make_old_layout(home, root)
    (root / NEW_CONF).parent.mkdir()
    (root / NEW_CONF).write_text("[General]\n", encoding="utf-8")
    (root / "snapmockit").mkdir()
    (home / APP_NAME / "Library").mkdir(parents=True)
    assert storage_names(root) == (APP_NAME, APP_NAME)
    assert data_directory(root) == root / "snapmockit"
    assert default_library_directory(home) == home / APP_NAME / "Library"


# ---- the migration ----


def test_migration_moves_all_three_and_rewrites_the_library_paths(
    places: tuple[Path, Path],
) -> None:
    home, root = places
    make_old_layout(home, root)
    report = migrate_storage(home, root)

    assert [m.what for m in report.moved] == ["settings", "data", "library"]
    assert not report.failed
    assert not (root / "SnapMock").exists()
    assert not (root / "snapmock").exists()
    assert not (home / "SnapMock").exists()  # the empty parent is removed too
    assert (root / NEW_CONF).is_file()
    assert (root / "snapmockit" / "tool_state.json").is_file()
    new_lib = home / APP_NAME / "Library"
    assert (new_lib / "Capture_2026-09-07.smk").read_bytes() == b"PK"

    settings = QSettings(str(root / NEW_CONF), QSettings.Format.IniFormat)
    assert settings.value("files/recent") == [
        str(new_lib / "Capture_2026-09-07.smk"),
        "/elsewhere/x.smk",
    ]
    assert settings.value("library/openFiles") == (
        f"{new_lib}/Capture_2026-09-07.smk, /elsewhere/x.smk"
    )
    assert int(str(settings.value("view/zoom"))) == 150  # INI keeps no type; the app converts
    assert bytes(settings.value("window/geometry")) == b"\x01\x02"
    assert storage_names(root) == (APP_NAME, APP_NAME)
    assert data_directory(root) == root / "snapmockit"
    assert default_library_directory(home) == new_lib
    assert report.message() == (
        f"Moved settings to {migration.display_path(root / APP_NAME)}, presets and themes to "
        f"{migration.display_path(root / 'snapmockit')} and the library to "
        f"{migration.display_path(new_lib)}."
    )


def test_migration_is_idempotent_and_does_nothing_on_a_fresh_machine(
    places: tuple[Path, Path],
) -> None:
    home, root = places
    assert migrate_storage(home, root).moves == []
    make_old_layout(home, root)
    first = migrate_storage(home, root)
    assert len(first.moved) == 3
    second = migrate_storage(home, root)
    assert second.moves == []
    assert second.message() == ""


def test_migration_never_overwrites_an_existing_new_location(places: tuple[Path, Path]) -> None:
    home, root = places
    make_old_layout(home, root)
    (root / NEW_CONF).parent.mkdir()
    (root / NEW_CONF).write_text("[General]\nkeep=1\n", encoding="utf-8")
    new_lib = home / APP_NAME / "Library"
    new_lib.mkdir(parents=True)
    (new_lib / "mine.smk").write_bytes(b"mine")
    report = migrate_storage(home, root)
    assert [m.what for m in report.moved] == ["data"]
    settings_move, library_move = (m for m in report.failed)
    assert settings_move.what == "settings" and "already exists" in settings_move.reason
    assert library_move.what == "library" and "already exists" in library_move.reason
    assert (root / OLD_CONF).is_file()
    assert (root / NEW_CONF).read_text(encoding="utf-8") == "[General]\nkeep=1\n"
    assert (home / "SnapMock" / "Library" / "Capture_2026-09-07.smk").is_file()
    assert (new_lib / "mine.smk").read_bytes() == b"mine"


def test_a_library_the_preference_puts_elsewhere_is_left_alone(places: tuple[Path, Path]) -> None:
    home, root = places
    make_old_layout(home, root, preference=str(home / "Pictures" / "Captures"))
    report = migrate_storage(home, root)
    assert [m.what for m in report.moved] == ["settings", "data"]
    library_move = report.failed[0]
    assert library_move.what == "library" and "preference" in library_move.reason
    assert (home / "SnapMock" / "Library" / "Capture_2026-09-07.smk").is_file()
    assert library_preference(root / NEW_CONF) == home / "Pictures" / "Captures"


def test_a_preference_naming_the_old_default_moves_with_the_library(
    places: tuple[Path, Path],
) -> None:
    home, root = places
    make_old_layout(home, root, preference=str(home / "SnapMock" / "Library"))
    report = migrate_storage(home, root)
    assert [m.what for m in report.moved] == ["settings", "data", "library"]
    assert library_preference(root / NEW_CONF) == home / APP_NAME / "Library"


def test_a_failed_move_leaves_the_old_location_readable(
    places: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    home, root = places
    make_old_layout(home, root)

    def refuse(src: str, dst: str) -> str:
        raise OSError(13, "Permission denied", src)

    monkeypatch.setattr(shutil, "move", refuse)
    report = migrate_storage(home, root)
    assert report.moved == []
    assert [m.what for m in report.failed] == ["settings", "data", "library"]
    assert all("Permission denied" in m.reason for m in report.failed)
    assert (root / OLD_CONF).is_file()
    assert (home / "SnapMock" / "Library" / "Capture_2026-09-07.smk").is_file()
    assert storage_names(root) == ("SnapMock", "SnapMock")
    assert data_directory(root) == root / "snapmock"
    assert default_library_directory(home) == home / "SnapMock" / "Library"
    assert report.message() == ""


def test_rewrite_paths_touches_only_strings_that_name_the_old_library(
    tmp_path: Path,
) -> None:
    conf = tmp_path / "x.conf"
    settings = QSettings(str(conf), QSettings.Format.IniFormat)
    settings.setValue("a", "/old/Library/one.smk")
    settings.setValue("b", ["/old/Library/two.smk", "/keep/three.smk"])
    settings.setValue("c", "untouched")
    settings.setValue("d", 7)
    settings.sync()
    assert rewrite_paths(conf, Path("/old/Library"), Path("/new/Library")) == 2
    settings = QSettings(str(conf), QSettings.Format.IniFormat)
    assert settings.value("a") == "/new/Library/one.smk"
    assert settings.value("b") == ["/new/Library/two.smk", "/keep/three.smk"]
    assert settings.value("c") == "untouched"
    assert settings.value("d") == 7
    assert rewrite_paths(tmp_path / "missing.conf", Path("/old"), Path("/new")) == 0


def test_report_message_reads_as_one_sentence() -> None:
    report = MigrationReport(
        [
            Move("settings", Path("/h/.config/SnapMock"), Path("/h/.config/Snapmockit"), True),
            Move(
                "library", Path("/h/SnapMock/Library"), Path("/h/Snapmockit/Library"), False, "x"
            ),
        ]
    )
    assert report.message() == "Moved settings to /h/.config/Snapmockit."
