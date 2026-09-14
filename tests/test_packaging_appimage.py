"""The Linux AppImage recipe's inputs (Technical Architecture PRD 7.3; packaging notes).

Nothing here builds an AppImage or reaches the network: the desktop entry, the
AppStream metainfo, the MIME file, the entry point, the icon, and the pure parts
of ``packaging/appimage/build.py`` are held on their own. The two system
validators run where they are installed and are skipped where they are not.
"""

from __future__ import annotations

import configparser
import datetime as dt
import importlib.util
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType

import pytest
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from snapmock import __version__
from snapmock.config.constants import APP_NAME, DESKTOP_ENTRY_ID, PROJECT_EXTENSION
from snapmock.ui.icons import (
    APPLICATION_ICON_FILE,
    APPLICATION_ICON_SIZES,
    application_icon,
    render_application_icon,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging" / "appimage"
DESKTOP_FILE = PACKAGING / f"{DESKTOP_ENTRY_ID}.desktop"
METAINFO_FILE = PACKAGING / f"{DESKTOP_ENTRY_ID}.appdata.xml"
MIME_FILE = PACKAGING / f"{DESKTOP_ENTRY_ID}.xml"
ENTRYPOINT_FILE = PACKAGING / "entrypoint.sh"
MIME_TYPE = "application/x-snapmockit-project"


@pytest.fixture(scope="module")
def build_module() -> ModuleType:
    """``packaging/appimage/build.py`` loaded by path; importing it runs nothing."""
    spec = importlib.util.spec_from_file_location("appimage_build", PACKAGING / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_desktop_entry() -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read(DESKTOP_FILE, encoding="utf-8")
    return dict(parser["Desktop Entry"])


# ---- the desktop entry (silence 2) ----


def test_desktop_entry_names_the_product_the_icon_and_the_project_type() -> None:
    entry = read_desktop_entry()
    assert entry["Type"] == "Application"
    assert entry["Name"] == APP_NAME
    assert entry["Icon"] == DESKTOP_ENTRY_ID
    assert entry["Exec"].split() == ["snapmockit", "%F"]
    assert entry["Terminal"] == "false"
    assert set(entry["Categories"].rstrip(";").split(";")) == {"Graphics", "Utility"}
    assert entry["MimeType"].rstrip(";").split(";") == [MIME_TYPE]
    assert entry["StartupWMClass"] == DESKTOP_ENTRY_ID


@pytest.mark.skipif(
    shutil.which("desktop-file-validate") is None, reason="desktop-file-validate not installed"
)
def test_desktop_entry_validates() -> None:
    result = subprocess.run(
        ["desktop-file-validate", str(DESKTOP_FILE)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "error" not in result.stdout.lower(), result.stdout


# ---- the metainfo ----


def test_metainfo_carries_the_id_the_launchable_and_the_project_type() -> None:
    root = ET.parse(METAINFO_FILE).getroot()
    assert root.tag == "component" and root.get("type") == "desktop-application"
    assert root.findtext("id") == DESKTOP_ENTRY_ID
    assert root.findtext("name") == APP_NAME
    assert root.findtext("project_license") == "MIT"
    launchable = root.find("launchable")
    assert launchable is not None
    assert launchable.get("type") == "desktop-id"
    assert launchable.text == DESKTOP_FILE.name
    assert root.findtext("provides/mediatype") == MIME_TYPE
    release = root.find("releases/release")
    assert release is not None
    assert release.get("version") == "@VERSION@" and release.get("date") == "@DATE@"


def test_fill_template_puts_the_package_version_in_the_release_row(
    build_module: ModuleType,
) -> None:
    filled = build_module.fill_template(
        METAINFO_FILE.read_text(encoding="utf-8"), __version__, dt.date(2026, 9, 14)
    )
    release = ET.fromstring(filled).find("releases/release")
    assert release is not None
    assert release.get("version") == __version__
    assert release.get("date") == "2026-09-14"
    assert "@" not in filled


@pytest.mark.skipif(shutil.which("appstreamcli") is None, reason="appstreamcli not installed")
def test_metainfo_validates(build_module: ModuleType, tmp_path: Path) -> None:
    filled = tmp_path / METAINFO_FILE.name
    filled.write_text(
        build_module.fill_template(
            METAINFO_FILE.read_text(encoding="utf-8"), __version__, dt.date.today()
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["appstreamcli", "validate", "--no-net", str(filled)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---- the MIME file and the entry point ----


def test_mime_file_claims_the_project_extension_and_not_snagit() -> None:
    ns = {"m": "http://www.freedesktop.org/standards/shared-mime-info"}
    root = ET.parse(MIME_FILE).getroot()
    types = root.findall("m:mime-type", ns)
    assert [t.get("type") for t in types] == [MIME_TYPE]
    globs = [g.get("pattern") for g in types[0].findall("m:glob", ns)]
    assert globs == [f"*{PROJECT_EXTENSION}"]
    icon = types[0].find("m:icon", ns)
    assert icon is not None and icon.get("name") == DESKTOP_ENTRY_ID


def test_entry_point_runs_the_module_isolated_with_the_arguments() -> None:
    text = ENTRYPOINT_FILE.read_text(encoding="utf-8")
    assert text.startswith("#! /bin/bash")
    assert '-I -m snapmock "$@"' in text
    assert "{{ python-executable }}" in text
    assert "QT_QPA_PLATFORM=" not in text


# ---- the icon (decision 3) ----


def test_application_icon_renders_square_and_opaque_at_the_centre(
    qapp: QApplication,
) -> None:
    assert APPLICATION_ICON_FILE.exists()
    for size in (16, 48, 256):
        pixmap = render_application_icon(size)
        assert pixmap.width() == size and pixmap.height() == size
        image = pixmap.toImage()
        assert image.pixelColor(size // 2, size // 2).alpha() == 255
        assert image.pixelColor(0, 0).alpha() == 0  # the rounded corner is transparent
    icon = application_icon()
    assert not icon.isNull()
    assert {s.width() for s in icon.availableSizes()} == set(APPLICATION_ICON_SIZES)


def test_render_icons_writes_every_size(build_module: ModuleType, tmp_path: Path) -> None:
    written = build_module.render_icons(APPLICATION_ICON_FILE, tmp_path, (16, 32, 512))
    assert sorted(written) == [16, 32, 512]
    for size, path in written.items():
        image = QImage(str(path))
        assert (image.width(), image.height()) == (size, size), path
    assert build_module.BUNDLED_ICON_SIZE in build_module.ICON_SIZES


# ---- the pure parts of the build script ----


def test_wheel_version_and_the_appimage_name_come_from_the_wheel(
    build_module: ModuleType,
) -> None:
    wheel = Path(f"snapmockit-{__version__}-py3-none-any.whl")
    assert build_module.wheel_version(wheel) == __version__
    assert build_module.appimage_name(__version__) == f"{APP_NAME}-{__version__}-x86_64.AppImage"
    with pytest.raises(ValueError):
        build_module.wheel_version(Path("other-1.0-py3-none-any.whl"))


def test_requirement_lines_keep_the_pins_and_drop_the_rest(build_module: ModuleType) -> None:
    export = (
        "# This file was autogenerated by uv\n"
        "#    uv export --no-dev\n"
        "numpy==2.4.2 \\\n"
        "    --hash=sha256:abc \\\n"
        "    --hash=sha256:def\n"
        "    # via snapmockit\n"
        "pyqt6==6.10.2\n"
        "\n"
        "send2trash==2.1.0 \\\n"
        "    # via snapmockit\n"
    )
    assert build_module.requirement_lines(export) == [
        "numpy==2.4.2",
        "pyqt6==6.10.2",
        "send2trash==2.1.0",
    ]


def test_the_recipe_files_exist_and_the_desktop_id_is_the_constant(
    build_module: ModuleType,
) -> None:
    for path in (DESKTOP_FILE, METAINFO_FILE, MIME_FILE, ENTRYPOINT_FILE):
        assert path.exists(), path
    assert build_module.DESKTOP_FILE == DESKTOP_FILE
    assert build_module.BASE_IMAGE.startswith("python3.12.")
    assert "manylinux_2_28_x86_64" in build_module.BASE_IMAGE
