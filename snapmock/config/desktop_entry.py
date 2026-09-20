"""Put the application in the desktop's main menu, and take it out again.

End-to-end pass finding 1: the AppImage carries a desktop entry, an icon set, and a
shared-mime-info file inside it and installs none of them, and an installation from
the Python Package Index installs none either, so the only route into the menu was a
recipe of nine shell lines in the README. This module is the route from inside the
application.

What it writes, all of it under ``$XDG_DATA_HOME`` (default ``~/.local/share``) and
never anywhere else, never as root, and never outside the user's own home:

* ``applications/io.github.dbower44022.snapmockit.desktop``, the entry of
  ``resources/desktop/`` with its ``Exec`` line replaced by an absolute path to the
  running form (decision 2), ``%F`` kept so a project opens by a double-click;
* ``icons/hicolor/<size>x<size>/apps/io.github.dbower44022.snapmockit.png`` at the
  sizes the AppImage recipe renders, from the application's own SVG through Qt, plus
  that SVG at ``icons/hicolor/scalable/apps/``;
* ``mime/packages/io.github.dbower44022.snapmockit.xml`` (decision 4), so a ``.smk``
  project carries the application's icon and opens on a double-click.

``update-desktop-database`` and ``update-mime-database`` are run when they are on the
path and skipped, without an error, when they are not. Removal deletes exactly what an
install writes and nothing else, so a Flatpak's own entry, which lives in the Flatpak's
exports and not here, survives it.

Nothing here reads a setting or shows a widget: the caller decides, this writes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from snapmock.config.constants import APP_NAME, DESKTOP_ENTRY_ID
from snapmock.config.packaging import (
    APPIMAGE_VARIABLE,
    DISTRIBUTION_COMMAND,
    FLATPAK_MARKER,
    PACKAGE_DIRECTORY,
    Form,
    current_form,
)

RESOURCE_DIRECTORY = PACKAGE_DIRECTORY / "resources" / "desktop"
"""Where the entry and the shared-mime-info file ship: in the package, so every form
carries them (silence 8). The AppImage and Flatpak recipes read the same two files."""

DESKTOP_TEMPLATE = RESOURCE_DIRECTORY / f"{DESKTOP_ENTRY_ID}.desktop"
MIME_TEMPLATE = RESOURCE_DIRECTORY / f"{DESKTOP_ENTRY_ID}.xml"
ICON_SOURCE = PACKAGE_DIRECTORY / "resources" / "icons" / "snapmockit.svg"

ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256, 512)
"""The sizes the AppImage recipe renders, which is what the desktop reads (silence 2)."""

APPIMAGE_DESTINATION = Path("Applications") / f"{APP_NAME}.AppImage"
"""Relative to the user's home: where the AppImage copies itself (decision 3), the
fixed name the README's recipe already uses, so a later release overwrites one file."""

APPIMAGE_MAGIC = b"AI\x02"
"""Bytes 8 to 10 of a type 2 AppImage, which is what a destination must be before it
is overwritten."""

EXEC_KEY = "Exec"
FILES_FIELD = "%F"

_EXEC_RESERVED = set(" \t\n\"'\\><~|&;$*?#()`")


@dataclass(frozen=True)
class Outcome:
    """What an install or a removal did, and what it could not do.

    *paths* are the files written or deleted, in the order they were touched.
    *notes* are the things that did not happen, each a sentence a user can read;
    an outcome with notes is not a failure unless *paths* is empty.
    """

    action: str
    paths: tuple[Path, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        """Whether anything was written or removed."""
        return bool(self.paths)

    def message(self) -> str:
        """One paragraph for the toast the caller shows (General UI PRD 1.3)."""
        parts = [self.action] if self.action else []
        parts.extend(self.notes)
        return " ".join(parts)


# ---- where things go -------------------------------------------------------------------


def data_home(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """``$XDG_DATA_HOME``, or ``~/.local/share`` where it is unset or empty."""
    env = os.environ if environ is None else environ
    value = env.get("XDG_DATA_HOME")
    if value:
        return Path(value)
    return (home or Path(env.get("HOME") or Path.home())) / ".local" / "share"


def entry_path(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """The desktop entry this module writes."""
    return data_home(environ, home) / "applications" / f"{DESKTOP_ENTRY_ID}.desktop"


def mime_path(environ: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """The shared-mime-info file this module writes (decision 4)."""
    return data_home(environ, home) / "mime" / "packages" / f"{DESKTOP_ENTRY_ID}.xml"


def icon_paths(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> tuple[Path, ...]:
    """Every icon file this module writes: one PNG per size, then the scalable SVG."""
    hicolor = data_home(environ, home) / "icons" / "hicolor"
    paths = [
        hicolor / f"{size}x{size}" / "apps" / f"{DESKTOP_ENTRY_ID}.png" for size in ICON_SIZES
    ]
    paths.append(hicolor / "scalable" / "apps" / f"{DESKTOP_ENTRY_ID}.svg")
    return tuple(paths)


def written_paths(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> tuple[Path, ...]:
    """Everything an install writes, which is everything a removal deletes."""
    return (entry_path(environ, home), *icon_paths(environ, home), mime_path(environ, home))


def installed(environ: Mapping[str, str] | None = None, home: Path | None = None) -> bool:
    """Whether this module's own entry is in place.

    Narrower than :func:`snapmock.app.desktop_entry_installed`, which answers for the
    whole XDG data path: a Flatpak's entry lives in the Flatpak's exports, counts there,
    and is not ours to remove.
    """
    return entry_path(environ, home).is_file()


def running_appimage(
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    package_directory: Path = PACKAGE_DIRECTORY,
) -> Path | None:
    """The AppImage file this process is running from, or None for every other form."""
    env = os.environ if environ is None else environ
    if current_form(env, marker, package_directory) is not Form.APPIMAGE:
        return None
    return Path(env[APPIMAGE_VARIABLE]).resolve()


def appimage_destination(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """Where the AppImage copies itself under decision 3."""
    env = os.environ if environ is None else environ
    base = home or Path(env.get("HOME") or Path.home())
    return base / APPIMAGE_DESTINATION


# ---- what the entry says ---------------------------------------------------------------


def quote_exec(value: str) -> str:
    """*value* as one argument of a desktop entry's ``Exec``, per the entry specification.

    The specification's quoting is not the shell's: an argument that needs quoting is
    enclosed in double quotes, and a double quote, a backslash, a dollar sign, or a
    backtick inside it is escaped with a backslash. A desktop entry's value then escapes
    each of those backslashes again, since the file format reads ``\\\\`` as one.
    """
    if value and not _EXEC_RESERVED.intersection(value):
        return value
    escaped = ""
    for character in value:
        if character in '"`$\\':
            escaped += "\\\\" + character
        else:
            escaped += character
    return f'"{escaped}"'


def program_path(
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    executable: str | None = None,
    package_directory: Path = PACKAGE_DIRECTORY,
) -> str:
    """The absolute path that starts this form, for the entry's ``Exec`` (decision 2).

    Never the bare console name: a desktop session's environment is the login manager's
    and not the shell's, and an ``Exec`` the desktop cannot resolve fails with no window
    and no message. The AppImage's own file, the installed command's full path, or, when
    no command is installed, the running interpreter with ``-m snapmock``, which exists
    whatever the path holds.
    """
    env = os.environ if environ is None else environ
    form = current_form(env, marker, package_directory)
    if form is Form.APPIMAGE:
        return quote_exec(str(Path(env[APPIMAGE_VARIABLE]).resolve()))
    interpreter = executable or sys.executable
    beside = shutil.which(DISTRIBUTION_COMMAND, path=str(Path(interpreter).parent))
    on_path = shutil.which(DISTRIBUTION_COMMAND, path=env.get("PATH"))
    command = beside or on_path
    if command is not None:
        return quote_exec(str(Path(command).resolve()))
    return f"{quote_exec(str(Path(interpreter).resolve()))} -m snapmock"


def entry_text(program: str, template: Path = DESKTOP_TEMPLATE) -> str:
    """The packaged entry with its ``Exec`` line replaced by *program* and ``%F``.

    Every other field — the name, the comment, the categories, the keywords, the icon,
    the window class, the MIME type — is the packaged file's, so the entry a user
    installs cannot drift from the entry a package installs (silence 8).
    """
    lines = template.read_text(encoding="utf-8").splitlines()
    replaced: list[str] = []
    seen = False
    for line in lines:
        if line.startswith(f"{EXEC_KEY}="):
            replaced.append(f"{EXEC_KEY}={program} {FILES_FIELD}")
            seen = True
        else:
            replaced.append(line)
    if not seen:
        raise ValueError(f"{template} has no {EXEC_KEY} line")
    return "\n".join(replaced) + "\n"


# ---- the icons -------------------------------------------------------------------------


def render_icon(size: int, destination: Path, source: Path = ICON_SOURCE) -> None:
    """Render *source* to a *size* by *size* PNG at *destination* through Qt.

    ``QImage`` rather than ``QPixmap``, so this runs with no display and with no
    application object, which is what the AppImage recipe does at build time.
    """
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise ValueError(f"cannot render {source}")
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(destination), "PNG"):
        raise OSError(f"cannot write {destination}")


# ---- the databases ---------------------------------------------------------------------


def refresh_databases(
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    run: bool = True,
) -> tuple[str, ...]:
    """Run the two database tools where they exist; the notes for the ones that do not.

    A desktop that has neither tool still reads the entry and the icons; only the file
    association waits for the next login. Neither absence is an error (silence 6).
    """
    if not run:
        return ()
    base = data_home(environ, home)
    notes: list[str] = []
    for tool, argument in (
        ("update-desktop-database", base / "applications"),
        ("update-mime-database", base / "mime"),
    ):
        found = shutil.which(tool, path=(os.environ if environ is None else environ).get("PATH"))
        if found is None:
            notes.append(
                f"{tool} is not installed, so the desktop reads the change at next login."
            )
            continue
        try:
            subprocess.run([found, str(argument)], check=False, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            notes.append(
                f"{tool} could not be run, so the desktop reads the change at next login."
            )
    return tuple(notes)


# ---- the AppImage's own file -----------------------------------------------------------


def is_appimage_file(path: Path) -> bool:
    """Whether *path* looks like a type 2 AppImage, which is what may be overwritten."""
    try:
        with path.open("rb") as handle:
            return handle.read(11)[8:11] == APPIMAGE_MAGIC
    except OSError:
        return False


def copy_appimage(source: Path, destination: Path) -> Path:
    """Copy the running AppImage to *destination*, overwriting only another AppImage.

    A destination that holds something else is refused, so nothing of the user's is
    ever overwritten by this (decision 3's follow-on detail).
    """
    if destination.exists() and not is_appimage_file(destination):
        raise ValueError(f"{destination} is not an AppImage; nothing was copied")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    shutil.copyfile(source, temporary)
    temporary.chmod(0o755)
    temporary.replace(destination)
    return destination


# ---- install and remove ----------------------------------------------------------------


def unsupported_reason(
    environ: Mapping[str, str] | None = None,
    marker: Path = FLATPAK_MARKER,
    package_directory: Path = PACKAGE_DIRECTORY,
) -> str | None:
    """Why this form needs nothing, or None where the action applies.

    The Flatpak installs its own entry with the package, so there is nothing here to
    write and nothing of ours to remove. No control is disabled (General UI PRD 1.3):
    the caller shows this sentence instead of greying a row out.
    """
    if current_form(environ, marker, package_directory) is Form.FLATPAK:
        return (
            f"This Flatpak installation is already in the menu: its entry and icon "
            f"are part of the package, so {APP_NAME} has nothing to add or remove."
        )
    return None


def install(
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    marker: Path = FLATPAK_MARKER,
    executable: str | None = None,
    package_directory: Path = PACKAGE_DIRECTORY,
    program: str | None = None,
    run_databases: bool = True,
) -> Outcome:
    """Write the entry, the icons, and the MIME file; report what could not be written.

    *program* overrides the ``Exec`` path, which is how the AppImage points the entry at
    its copy (decision 3) rather than at the file it is running from. A directory that
    cannot be written is reported in the outcome's notes and never raised, so a menu
    action never ends in a traceback.
    """
    reason = unsupported_reason(environ, marker, package_directory)
    if reason is not None:
        return Outcome(action=reason)

    exec_line = program or program_path(environ, marker, executable, package_directory)
    written: list[Path] = []
    notes: list[str] = []

    entry = entry_path(environ, home)
    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(entry_text(exec_line), encoding="utf-8")
        entry.chmod(0o755)
        written.append(entry)
    except OSError as error:
        return Outcome(
            action=f"{APP_NAME} could not be added to the menu.",
            notes=(f"{entry} could not be written ({error.strerror or error}).",),
        )

    paths = icon_paths(environ, home)
    rendered = 0
    for size, path in zip(ICON_SIZES, paths[: len(ICON_SIZES)], strict=True):
        try:
            render_icon(size, path)
            written.append(path)
            rendered += 1
        except (OSError, ValueError) as error:
            notes.append(f"The {size} pixel icon could not be written ({error}).")
    scalable = paths[-1]
    try:
        scalable.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ICON_SOURCE, scalable)
        written.append(scalable)
        rendered += 1
    except OSError as error:
        notes.append(f"The scalable icon could not be written ({error.strerror or error}).")
    if rendered == 0:
        notes.append("No icon could be written, so the menu shows the entry without one.")

    mime = mime_path(environ, home)
    try:
        mime.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MIME_TEMPLATE, mime)
        written.append(mime)
    except OSError as error:
        notes.append(
            "The file type for .smk projects could not be registered "
            f"({error.strerror or error}), so a double-click on a project will not open it."
        )

    notes.extend(refresh_databases(environ, home, run_databases))
    return Outcome(
        action=(
            f"{APP_NAME} is in the menu, and .smk projects now open on a double-click."
            if mime in written
            else f"{APP_NAME} is in the menu."
        ),
        paths=tuple(written),
        notes=tuple(notes),
    )


def remove(
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    marker: Path = FLATPAK_MARKER,
    package_directory: Path = PACKAGE_DIRECTORY,
    run_databases: bool = True,
) -> Outcome:
    """Delete exactly what :func:`install` writes, and nothing else.

    The AppImage's copy at ``~/Applications`` is not touched here: it is offered
    separately, so no 122 MB file disappears without being named (decision 3).
    """
    reason = unsupported_reason(environ, marker, package_directory)
    if reason is not None:
        return Outcome(action=reason)

    deleted: list[Path] = []
    notes: list[str] = []
    for path in written_paths(environ, home):
        try:
            path.unlink()
            deleted.append(path)
        except FileNotFoundError:
            continue
        except OSError as error:
            notes.append(f"{path} could not be removed ({error.strerror or error}).")
    notes.extend(refresh_databases(environ, home, run_databases))
    action = (
        f"{APP_NAME} is no longer in the menu."
        if deleted
        else f"{APP_NAME} was not in the menu; nothing was removed."
    )
    return Outcome(action=action, paths=tuple(deleted), notes=tuple(notes))
