"""Build the Linux AppImage (Technical Architecture PRD 7.3; packaging decision 1, option A).

One command from the repository at a commit::

    uv run --group packaging python packaging/appimage/build.py

produces ``dist/Snapmockit-<version>-x86_64.AppImage``, the version read from the
wheel ``uv build`` makes, never typed. The recipe:

1. Build the wheel with ``uv build`` and export the locked runtime dependencies
   with ``uv export``, so what ships is what the lock file and the CI build prove.
2. Render the application icon (``snapmock/resources/icons/snapmockit.svg``) to the
   PNG sizes the desktop integration needs, through Qt's own SVG renderer.
3. Hand ``python-appimage`` a staging directory holding the desktop entry, the icon,
   the entry point, and the requirements (the locked dependencies, then the wheel).
   It extracts its relocatable CPython 3.12 built on ``manylinux_2_28`` (pinned
   below, downloaded once into the work directory), installs the requirements into
   it with pip, and writes ``AppRun`` from the entry point.
4. Add what ``python-appimage`` does not carry: the AppStream metainfo, the
   shared-mime-info file for ``.smk``, the hicolor icon set, and a ``usr/bin``
   symlink named as the desktop entry's ``Exec``.
5. Seal the AppDir with ``appimagetool``, which ``python-appimage`` fetches.

Nothing here is pruned: every package is installed whole, so every Qt platform
plugin, QtDBus, QtNetwork, and the 175 resources are present because they were
installed. The functions that need no network or build (the wheel name, the
requirement lines, the template fill, the icon rendering) are what the tests hold.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from snapmock.config.constants import APP_NAME, DESKTOP_ENTRY_ID  # noqa: E402
from snapmock.config.desktop_entry import DESKTOP_TEMPLATE, MIME_TEMPLATE  # noqa: E402
from snapmock.config.desktop_entry import ICON_SIZES as _ICON_SIZES  # noqa: E402

ARCH = "x86_64"
DISTRIBUTION_NAME = "snapmockit"
ICON_SOURCE = ROOT / "snapmock" / "resources" / "icons" / "snapmockit.svg"
ICON_SIZES: tuple[int, ...] = _ICON_SIZES
"""The sizes the desktop reads; the one source is config/desktop_entry.py, which the
application itself renders from at run time (menu-entry silence 8)."""
BUNDLED_ICON_SIZE = 256
"""The one PNG handed to python-appimage, and the AppImage's own top-level icon."""

PYTHON_VERSION = "3.12"
BASE_IMAGE = "python3.12.14-cp312-cp312-manylinux_2_28_x86_64.AppImage"
"""The relocatable CPython the AppImage is built on, pinned so a build is reproducible
and never reads GitHub's API (python-appimage's own lookup does, and a shared runner
is rate limited). Its glibc floor is manylinux_2_28's, 2.28."""
BASE_IMAGE_URL = (
    f"https://github.com/niess/python-appimage/releases/download/python{PYTHON_VERSION}/"
    f"{BASE_IMAGE}"
)

DESKTOP_FILE = DESKTOP_TEMPLATE
METAINFO_FILE = HERE / f"{DESKTOP_ENTRY_ID}.appdata.xml"
MIME_FILE = MIME_TEMPLATE
"""The entry and the shared-mime-info file ship inside the package, so every installed
form carries them and the application can install them itself (menu-entry silence 8);
only the AppStream metainfo, which nothing but a build reads, stays beside this recipe."""
ENTRYPOINT_FILE = HERE / "entrypoint.sh"

WHEEL_NAME = re.compile(rf"^{DISTRIBUTION_NAME}-(?P<version>[^-]+)-py3-none-any\.whl$")


# ---- the parts a test can hold without a build -----------------------------------------


def wheel_version(wheel: Path) -> str:
    """The version in a wheel's file name; ``ValueError`` for a wheel that is not ours."""
    match = WHEEL_NAME.match(wheel.name)
    if match is None:
        raise ValueError(f"not a {DISTRIBUTION_NAME} wheel: {wheel.name}")
    return match.group("version")


def appimage_name(version: str) -> str:
    """``Snapmockit-<version>-x86_64.AppImage`` (kickoff silence 1)."""
    return f"{APP_NAME}-{version}-{ARCH}.AppImage"


def requirement_lines(export: str) -> list[str]:
    """The requirement lines of a ``uv export`` output: no comments, blanks, or hashes."""
    lines: list[str] = []
    for raw in export.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        line = line.split(" \\")[0].split(" #")[0].strip().rstrip("\\").strip()
        if line:
            lines.append(line)
    return lines


def fill_template(text: str, version: str, date: dt.date) -> str:
    """Replace ``@VERSION@`` and ``@DATE@``; the metainfo's release row is built from them."""
    return text.replace("@VERSION@", version).replace("@DATE@", date.isoformat())


def render_icons(svg: Path, out_dir: Path, sizes: tuple[int, ...] = ICON_SIZES) -> dict[int, Path]:
    """Render *svg* to one PNG per size under *out_dir* (``<size>.png``) with Qt.

    Imports Qt on call, not on import, so the module loads without a display.
    """
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QGuiApplication, QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    if QGuiApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        QGuiApplication([])
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise ValueError(f"cannot render {svg}")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[int, Path] = {}
    for size in sizes:
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        path = out_dir / f"{size}.png"
        if not image.save(str(path), "PNG"):
            raise OSError(f"cannot write {path}")
        written[size] = path
    return written


# ---- the build ---------------------------------------------------------------------------


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    """Run *command*, echoing it, and return its standard output; a failure raises."""
    print("+", " ".join(command), flush=True)
    result = subprocess.run(
        command, cwd=cwd, env=env, check=True, text=True, stdout=subprocess.PIPE
    )
    return result.stdout


def build_wheel(out_dir: Path) -> Path:
    """``uv build --wheel`` into *out_dir*; the one wheel it makes."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    run(["uv", "build", "--wheel", "--out-dir", str(out_dir)], cwd=ROOT)
    wheels = sorted(out_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one wheel in {out_dir}, found {len(wheels)}")
    return wheels[0]


def locked_requirements() -> list[str]:
    """The runtime dependencies pinned by ``uv.lock``, without the project itself."""
    export = run(
        ["uv", "export", "--no-dev", "--no-emit-project", "--frozen", "--no-hashes"], cwd=ROOT
    )
    return requirement_lines(export)


def fetch_base_image(work_dir: Path) -> Path:
    """The pinned CPython AppImage, downloaded once into *work_dir*."""
    target = work_dir / BASE_IMAGE
    if not target.exists():
        print("+ download", BASE_IMAGE_URL, flush=True)
        partial = target.with_suffix(".part")
        urllib.request.urlretrieve(BASE_IMAGE_URL, partial)
        partial.rename(target)
    target.chmod(0o755)
    return target


def stage_inputs(stage: Path, wheel: Path, requirements: list[str], icon_png: Path) -> None:
    """Write what python-appimage reads: desktop entry, icon, entry point, requirements."""
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy(DESKTOP_FILE, stage / DESKTOP_FILE.name)
    shutil.copy(ENTRYPOINT_FILE, stage / ENTRYPOINT_FILE.name)
    shutil.copy(icon_png, stage / f"{DESKTOP_ENTRY_ID}.png")
    lines = [*requirements, str(wheel.resolve())]
    (stage / "requirements.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_appdir(stage: Path, base_image: Path, work_dir: Path) -> Path:
    """Run python-appimage without packaging; the AppDir it leaves in *work_dir*."""
    appdir = work_dir / f"{APP_NAME}-{ARCH}"
    if appdir.exists():
        shutil.rmtree(appdir)
    run(
        [
            sys.executable,
            "-m",
            "python_appimage",
            "build",
            "app",
            "--base-image",
            str(base_image),
            "--no-packaging",
            str(stage),
        ],
        cwd=work_dir,
    )
    if not (appdir / "AppRun").exists():
        raise RuntimeError(f"python-appimage left no AppDir at {appdir}")
    return appdir


def complete_appdir(appdir: Path, icons: dict[int, Path], version: str, date: dt.date) -> None:
    """Add the metainfo, the MIME file, the icon set, and the ``usr/bin`` name."""
    metainfo_dir = appdir / "usr" / "share" / "metainfo"
    metainfo_dir.mkdir(parents=True, exist_ok=True)
    for stale in metainfo_dir.glob("python*.appdata.xml"):
        stale.unlink()
    (metainfo_dir / METAINFO_FILE.name).write_text(
        fill_template(METAINFO_FILE.read_text(encoding="utf-8"), version, date), encoding="utf-8"
    )

    mime_dir = appdir / "usr" / "share" / "mime" / "packages"
    mime_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(MIME_FILE, mime_dir / MIME_FILE.name)

    hicolor = appdir / "usr" / "share" / "icons" / "hicolor"
    for size, png in icons.items():
        target = hicolor / f"{size}x{size}" / "apps" / f"{DESKTOP_ENTRY_ID}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(png, target)
    scalable = hicolor / "scalable" / "apps" / f"{DESKTOP_ENTRY_ID}.svg"
    scalable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ICON_SOURCE, scalable)

    bin_dir = appdir / "usr" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / DISTRIBUTION_NAME
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(Path("..") / ".." / "AppRun")


def appimagetool() -> Path:
    """The ``appimagetool`` python-appimage keeps in its cache, fetched if absent."""
    run([sys.executable, "-m", "python_appimage", "install", "appimagetool"])
    path = run([sys.executable, "-m", "python_appimage", "which", "appimagetool"]).strip()
    if not path:
        raise RuntimeError("python-appimage could not provide appimagetool")
    return Path(path)


def seal(appdir: Path, destination: Path) -> Path:
    """``appimagetool`` over the AppDir into *destination*."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    env = dict(os.environ, ARCH=ARCH)
    run([str(appimagetool()), str(appdir), str(destination)], env=env)
    if not destination.exists():
        raise RuntimeError(f"appimagetool left no file at {destination}")
    destination.chmod(0o755)
    return destination


def build(out_dir: Path, work_dir: Path) -> Path:
    """The whole recipe; the AppImage's path."""
    work_dir.mkdir(parents=True, exist_ok=True)
    wheel = build_wheel(work_dir / "wheel")
    version = wheel_version(wheel)
    requirements = locked_requirements()
    icons = render_icons(ICON_SOURCE, work_dir / "icons")
    stage = work_dir / "stage"
    stage_inputs(stage, wheel, requirements, icons[BUNDLED_ICON_SIZE])
    base_image = fetch_base_image(work_dir)
    appdir = make_appdir(stage, base_image, work_dir)
    complete_appdir(appdir, icons, version, dt.date.today())
    return seal(appdir, out_dir / appimage_name(version))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Linux AppImage.")
    parser.add_argument(
        "--out-dir", type=Path, default=ROOT / "dist", help="where the AppImage lands"
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=ROOT / "build" / "appimage",
        help="the wheel, the base image, the staging directory, and the AppDir",
    )
    args = parser.parse_args(argv)
    result = build(args.out_dir.resolve(), args.work_dir.resolve())
    size_mb = result.stat().st_size / (1024 * 1024)
    print(f"built {result} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
