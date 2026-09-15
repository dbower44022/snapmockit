"""The one-time move of the on-disk names from SnapMock to Snapmockit (packaging decision 4).

Three places kept the earlier product name after the rename of 09-14-26 so that a
user's settings and library were still found: the QSettings store
(``~/.config/SnapMock/SnapMock.conf``), the presets and themes
(``~/.config/snapmock``), and the default library (``~/SnapMock/Library``). On the
first start of a version that carries this module each is moved to the product's
name, only when the old exists and the new does not, and only the library that is
at its default path. Nothing is ever deleted or overwritten: a move that fails, or
that must not happen, leaves the old location in place, and the three lookup
functions below then answer with the old location, so the application reads what
it read before. The paths inside the settings that named the old library
(recent files, open files, remembered zooms) are rewritten to the new one.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QSettings, QStandardPaths

from snapmock.config.constants import (
    DATA_DIRECTORY_NAME,
    LEGACY_DATA_DIRECTORY_NAME,
    LEGACY_LIBRARY_SUBPATH,
    LEGACY_ORG_NAME,
    LEGACY_STORAGE_APP_NAME,
    LIBRARY_SUBPATH,
    ORG_NAME,
    STORAGE_APP_NAME,
)

log = logging.getLogger("snapmock")

LIBRARY_DIRECTORY_KEY = "library/directory"
"""The settings key of the library path preference (``AppSettings.library_directory``)."""


def config_root() -> Path:
    """The platform's generic configuration location, ``~/.config`` on Linux."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    return Path(base) if base else Path.home() / ".config"


def settings_file(root: Path, org: str, app: str) -> Path:
    """Where QSettings keeps ``(org, app)`` under *root*, as it does on Linux."""
    return root / org / f"{app}.conf"


# ---- the lookups the application reads through ------------------------------------------


def storage_names(root: Path | None = None) -> tuple[str, str]:
    """The ``(organisation, application)`` names QSettings opens: the product's, unless
    only the old store exists (a migration that has not run, or could not)."""
    root = config_root() if root is None else root
    if settings_file(root, ORG_NAME, STORAGE_APP_NAME).exists():
        return ORG_NAME, STORAGE_APP_NAME
    if settings_file(root, LEGACY_ORG_NAME, LEGACY_STORAGE_APP_NAME).exists():
        return LEGACY_ORG_NAME, LEGACY_STORAGE_APP_NAME
    return ORG_NAME, STORAGE_APP_NAME


def data_directory(root: Path | None = None) -> Path:
    """Where presets, themes, the tool state, and custom stamps live: the product's
    directory, unless only the old one exists."""
    root = config_root() if root is None else root
    new = root / DATA_DIRECTORY_NAME
    old = root / LEGACY_DATA_DIRECTORY_NAME
    return new if new.exists() or not old.exists() else old


def default_library_directory(home: Path | None = None) -> Path:
    """The library's default path: the product's, unless only the old one exists."""
    home = Path.home() if home is None else home
    new = home / LIBRARY_SUBPATH
    old = home / LEGACY_LIBRARY_SUBPATH
    return new if new.exists() or not old.exists() else old


# ---- the migration ----------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    """One of the three moves: made, or not made and why."""

    what: str
    old: Path
    new: Path
    done: bool
    reason: str = ""


@dataclass
class MigrationReport:
    """What one run of :func:`migrate_storage` did."""

    moves: list[Move] = field(default_factory=list)

    @property
    def moved(self) -> list[Move]:
        return [move for move in self.moves if move.done]

    @property
    def failed(self) -> list[Move]:
        return [move for move in self.moves if not move.done]

    def message(self) -> str:
        """The one line the user sees after the moves (General UI PRD 1.3: a message,
        never a dialog that blocks); empty when nothing moved."""
        parts: list[str] = []
        for move in self.moved:
            if move.what == "settings":
                parts.append(f"settings to {display_path(move.new)}")
            elif move.what == "data":
                parts.append(f"presets and themes to {display_path(move.new)}")
            elif move.what == "library":
                parts.append(f"the library to {display_path(move.new)}")
        if not parts:
            return ""
        if len(parts) == 1:
            joined = parts[0]
        else:
            joined = ", ".join(parts[:-1]) + " and " + parts[-1]
        return f"Moved {joined}."


def display_path(path: Path) -> str:
    """*path* with the home directory shortened to ``~``, for a message."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _move(what: str, old: Path, new: Path, report: MigrationReport) -> bool:
    """Move *old* to *new* when the old exists and the new does not; record the outcome."""
    if not old.is_dir():
        return False
    if new.exists():
        report.moves.append(Move(what, old, new, False, "the new location already exists"))
        return False
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
    except OSError as exc:
        log.warning("could not move %s from %s to %s: %s", what, old, new, exc)
        report.moves.append(Move(what, old, new, False, str(exc)))
        return False
    report.moves.append(Move(what, old, new, True))
    log.info("moved %s from %s to %s", what, old, new)
    return True


def library_preference(conf: Path) -> Path | None:
    """The library path the settings file names, or None when it names none."""
    if not conf.exists():
        return None
    value = QSettings(str(conf), QSettings.Format.IniFormat).value(LIBRARY_DIRECTORY_KEY, "")
    return Path(str(value)).expanduser() if isinstance(value, str) and value else None


def rewrite_paths(conf: Path, old: Path, new: Path) -> int:
    """Replace every occurrence of *old* in the settings' string values by *new*.

    The recent files, the open files, the remembered zooms, and the library
    preference itself all name library files by absolute path; a moved library
    would otherwise leave every one of them dangling. Returns the count changed.
    """
    if not conf.exists():
        return 0
    old_text, new_text = str(old), str(new)
    settings = QSettings(str(conf), QSettings.Format.IniFormat)
    changed = 0
    for key in settings.allKeys():
        value = settings.value(key)
        if isinstance(value, str):
            if old_text in value:
                settings.setValue(key, value.replace(old_text, new_text))
                changed += 1
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            if any(old_text in item for item in value):
                settings.setValue(key, [item.replace(old_text, new_text) for item in value])
                changed += 1
    settings.sync()
    return changed


def _remove_if_empty(directory: Path) -> None:
    try:
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    except OSError:
        pass


def migrate_storage(home: Path | None = None, root: Path | None = None) -> MigrationReport:
    """Move the three on-disk names to the product's; idempotent and never destructive."""
    home = Path.home() if home is None else home
    root = config_root() if root is None else root
    report = MigrationReport()

    # 1. The QSettings store: the directory, then the file inside it.
    old_dir = root / LEGACY_ORG_NAME
    new_dir = root / ORG_NAME
    if _move("settings", old_dir, new_dir, report):
        old_conf = new_dir / f"{LEGACY_STORAGE_APP_NAME}.conf"
        new_conf = new_dir / f"{STORAGE_APP_NAME}.conf"
        if old_conf.exists() and not new_conf.exists():
            try:
                old_conf.rename(new_conf)
            except OSError as exc:
                log.warning("could not rename %s to %s: %s", old_conf, new_conf, exc)

    # 2. The presets, themes, tool state, and custom stamps.
    _move("data", root / LEGACY_DATA_DIRECTORY_NAME, root / DATA_DIRECTORY_NAME, report)

    # 3. The library, only when it is at the default path and the preference agrees.
    old_lib = home / LEGACY_LIBRARY_SUBPATH
    new_lib = home / LIBRARY_SUBPATH
    if old_lib.is_dir():
        org, app = storage_names(root)
        conf = settings_file(root, org, app)
        preference = library_preference(conf)
        if preference is not None and preference != old_lib:
            report.moves.append(
                Move("library", old_lib, new_lib, False, f"the library preference is {preference}")
            )
        elif _move("library", old_lib, new_lib, report):
            _remove_if_empty(old_lib.parent)
            rewrite_paths(conf, old_lib, new_lib)
    return report
