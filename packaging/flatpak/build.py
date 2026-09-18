"""Build the Linux Flatpak (Technical Architecture PRD 7.3; Flatpak decision 1, option A).

One command from the repository at a commit::

    uv run python packaging/flatpak/build.py

produces ``dist/Snapmockit-<version>-x86_64.flatpak``, the version read from the wheel
``uv build`` makes, never typed. The recipe:

1. Build the wheel with ``uv build``.
2. Render the application icon (``snapmock/resources/icons/snapmockit.svg``) to the PNG
   sizes the desktop integration needs, through Qt's own SVG renderer, and fill the
   AppStream metainfo's release row from the wheel's version and the build date. Both
   are the AppImage recipe's own functions, imported from ``packaging/appimage``, so the
   two forms cannot drift.
3. Stage the wheel, the desktop entry, the metainfo, the MIME type, and the icons where
   the manifest's ``dir`` source reads them.
4. Run ``flatpak-builder`` over ``io.github.dbower44022.snapmockit.yml`` into a local
   OSTree repository, then ``flatpak build-bundle`` that repository into one file.

The dependency modules are generated, not written by hand::

    uv run python packaging/flatpak/build.py --update-deps

reads the versions ``uv.lock`` pins, asks the Python Package Index for each one's
CPython 3.13 wheel, and writes ``python3-deps.json`` with the addresses and their
SHA-256 digests. ``flatpak-builder`` downloads those itself, so the build sandbox never
reaches the network. PyQt6 is not among them: the base application carries it (decision
1). The dependency versions the application runs are therefore the lock file's for
Pillow, numpy, psutil, and send2trash, and the base application's for PyQt6.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from snapmock.config.constants import APP_NAME, DESKTOP_ENTRY_ID  # noqa: E402


def appimage_recipe() -> ModuleType:
    """``packaging/appimage/build.py``, loaded by path under its own name.

    The two recipes share the desktop files, the icon rendering, the metainfo
    template fill, and the wheel build, so neither form can drift from the other.
    Loading by path keeps the two modules, both named ``build``, apart.
    """
    path = ROOT / "packaging" / "appimage" / "build.py"
    spec = importlib.util.spec_from_file_location("snapmock_appimage_build", path)
    if spec is None or spec.loader is None:  # pragma: no cover - the file is in the tree
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_appimage = appimage_recipe()
DESKTOP_FILE: Path = _appimage.DESKTOP_FILE
ICON_SOURCE: Path = _appimage.ICON_SOURCE
METAINFO_FILE: Path = _appimage.METAINFO_FILE
MIME_FILE: Path = _appimage.MIME_FILE
build_wheel = _appimage.build_wheel
fill_template = _appimage.fill_template
render_icons = _appimage.render_icons
run = _appimage.run
wheel_version = _appimage.wheel_version

ARCH = "x86_64"
MANIFEST = HERE / f"{DESKTOP_ENTRY_ID}.yml"
DEPS_MODULE = HERE / "python3-deps.json"
LAUNCHER = HERE / "snapmockit.sh"

PYTHON_TAG = "cp313"
"""The interpreter the KDE runtime carries (decision 1); the wheels must match it."""

BASE_APPLICATION_PACKAGES = frozenset({"pyqt6", "pyqt6-qt6", "pyqt6-sip"})
"""What the PyQt base application already installs, so the manifest must not."""

PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"
PLATFORM_PREFERENCE = ("manylinux_2_28_", "manylinux_2_17_", "manylinux2014_", "manylinux_2_")
"""Tried in order; a pure-Python wheel (``py3-none-any``) is taken whatever the order."""


# ---- the parts a test can hold without a build -----------------------------------------


def bundle_name(version: str) -> str:
    """``Snapmockit-<version>-x86_64.flatpak`` (silence 2)."""
    return f"{APP_NAME}-{version}-{ARCH}.flatpak"


def dependency_pins(export: str) -> list[tuple[str, str]]:
    """The ``(name, version)`` pairs the manifest must build, from a ``uv export``.

    The three PyQt6 distributions are left out: the base application carries them.
    """
    pins: list[tuple[str, str]] = []
    for raw in export.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        line = line.split(" \\")[0].split(" #")[0].strip().rstrip("\\").strip()
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        if name.strip().lower() in BASE_APPLICATION_PACKAGES:
            continue
        pins.append((name.strip(), version.strip()))
    return pins


ABI3_TAG = re.compile(r"-cp3(\d+)-abi3-")
"""A stable-ABI wheel, which any later CPython 3 loads; psutil ships one."""


def runs_on_the_runtime(filename: str, python_tag: str = PYTHON_TAG) -> bool:
    """Whether the runtime's interpreter and its glibc can load *filename*.

    Three shapes qualify: a pure-Python wheel; this interpreter's own build
    (``cp313-cp313``, never the free-threaded ``cp313t``); and a stable-ABI wheel
    (``cp36-abi3``) whose minor version is this one or older. Everything else, an
    aarch64 or a musl wheel included, does not.
    """
    if filename.endswith("-py3-none-any.whl"):
        return True
    if not filename.endswith(f"_{ARCH}.whl") or "musllinux" in filename:
        return False
    if f"-{python_tag}-{python_tag}-" in filename:
        return True
    match = ABI3_TAG.search(filename)
    return match is not None and int(match.group(1)) <= int(python_tag.removeprefix("cp3"))


def choose_wheel(files: list[dict[str, Any]], python_tag: str = PYTHON_TAG) -> dict[str, Any]:
    """The one wheel of a release to install, preferring the newest glibc floor."""
    wheels = [
        f
        for f in files
        if f.get("packagetype") == "bdist_wheel"
        and not f.get("yanked")
        and runs_on_the_runtime(str(f["filename"]), python_tag)
    ]
    pure = [f for f in wheels if str(f["filename"]).endswith("-py3-none-any.whl")]
    if pure:
        return pure[0]
    for prefix in PLATFORM_PREFERENCE:
        for wheel in wheels:
            if prefix in str(wheel["filename"]):
                return wheel
    if wheels:
        return wheels[0]
    raise RuntimeError(f"no {python_tag} {ARCH} wheel among {[f['filename'] for f in files]}")


def deps_module(wheels: list[dict[str, str]]) -> dict[str, Any]:
    """The ``python3-deps.json`` module: every wheel a source, one pip install command."""
    names = " ".join(wheel["filename"] for wheel in wheels)
    return {
        "name": "python3-deps",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --no-index --no-deps --no-build-isolation "
            f'--prefix="${{FLATPAK_DEST}}" {names}'
        ],
        "sources": [
            {"type": "file", "url": wheel["url"], "sha256": wheel["sha256"]} for wheel in wheels
        ],
    }


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    """The manifest as data; used by the tests and by :func:`build`."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a manifest")
    return data


# ---- the generated dependency modules ---------------------------------------------------


def fetch_release_files(name: str, version: str) -> list[dict[str, Any]]:
    """What the Python Package Index lists for one release."""
    with urllib.request.urlopen(PYPI_JSON.format(name=name, version=version)) as reply:
        data = json.load(reply)
    files = data.get("urls")
    if not isinstance(files, list) or not files:
        raise RuntimeError(f"no files listed for {name} {version}")
    return files


def update_deps(path: Path = DEPS_MODULE) -> Path:
    """Regenerate *path* from the versions ``uv.lock`` pins. Reads the network."""
    export = run(
        ["uv", "export", "--no-dev", "--no-emit-project", "--frozen", "--no-hashes"], cwd=ROOT
    )
    wheels: list[dict[str, str]] = []
    for name, version in dependency_pins(export):
        chosen = choose_wheel(fetch_release_files(name, version))
        print(f"+ {name} {version}: {chosen['filename']}", flush=True)
        wheels.append(
            {
                "filename": str(chosen["filename"]),
                "url": str(chosen["url"]),
                "sha256": str(chosen["digests"]["sha256"]),
            }
        )
    path.write_text(json.dumps(deps_module(wheels), indent=2) + "\n", encoding="utf-8")
    return path


# ---- the build ---------------------------------------------------------------------------


def stage_inputs(stage: Path, wheel: Path, version: str, date: dt.date) -> Path:
    """Write what the manifest's ``dir`` source reads; the staging directory."""
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy(wheel, stage / wheel.name)  # its own name: pip reads the version from it
    shutil.copy(DESKTOP_FILE, stage / DESKTOP_FILE.name)
    shutil.copy(MIME_FILE, stage / MIME_FILE.name)
    shutil.copy(ICON_SOURCE, stage / f"{DESKTOP_ENTRY_ID}.svg")
    (stage / f"{DESKTOP_ENTRY_ID}.metainfo.xml").write_text(
        fill_template(METAINFO_FILE.read_text(encoding="utf-8"), version, date), encoding="utf-8"
    )
    render_icons(ICON_SOURCE, stage / "icons")
    return stage


def builder_command() -> list[str]:
    """``flatpak-builder``, from the path or from the Flatpak application that carries it."""
    found = shutil.which("flatpak-builder")
    if found:
        return [found]
    return ["flatpak", "run", "org.flatpak.Builder"]


def build_repository(work_dir: Path) -> Path:
    """Run flatpak-builder over the manifest into a local repository; its path."""
    repo = work_dir / "repo"
    state = work_dir / "state"
    build_dir = work_dir / "build-dir"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if repo.exists():
        # A repository kept between builds holds every branch ever built into it, and
        # a bundle of a stale one is worse than a slower build.
        shutil.rmtree(repo)
    run(
        [
            *builder_command(),
            "--force-clean",
            "--disable-rofiles-fuse",
            f"--state-dir={state}",
            f"--repo={repo}",
            str(build_dir),
            str(MANIFEST),
        ],
        cwd=HERE,
    )
    if not (repo / "config").exists():
        raise RuntimeError(f"flatpak-builder left no repository at {repo}")
    return repo


def bundle(repo: Path, destination: Path, branch: str | None = None) -> Path:
    """``flatpak build-bundle`` the repository into one installable file.

    The branch is named, never left to the command's default of ``master``: the
    manifest builds ``stable``, and a bundle of the wrong branch is either the
    build before this one or no build at all.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    run(
        [
            "flatpak",
            "build-bundle",
            "--runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo",
            str(repo),
            str(destination),
            DESKTOP_ENTRY_ID,
            branch or str(load_manifest()["branch"]),
        ]
    )
    if not destination.exists():
        raise RuntimeError(f"flatpak build-bundle left no file at {destination}")
    return destination


def build(out_dir: Path, work_dir: Path) -> Path:
    """The whole recipe; the bundle's path."""
    work_dir.mkdir(parents=True, exist_ok=True)
    wheel = build_wheel(work_dir / "wheel")
    version = wheel_version(wheel)
    stage_inputs(work_dir / "stage", wheel, version, dt.date.today())
    repo = build_repository(work_dir)
    return bundle(repo, out_dir / bundle_name(version))


def digest(path: Path) -> str:
    """The SHA-256 of a built file, printed so a release can be checked."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Linux Flatpak.")
    parser.add_argument(
        "--out-dir", type=Path, default=ROOT / "dist", help="where the bundle lands"
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=ROOT / "build" / "flatpak",
        help="the wheel, the staging directory, the build directory, and the repository",
    )
    parser.add_argument(
        "--update-deps",
        action="store_true",
        help="regenerate python3-deps.json from uv.lock and the Python Package Index",
    )
    args = parser.parse_args(argv)
    if args.update_deps:
        print(f"wrote {update_deps()}")
        return 0
    result = build(args.out_dir.resolve(), args.work_dir.resolve())
    size_mb = result.stat().st_size / (1024 * 1024)
    print(f"built {result} ({size_mb:.1f} MB, sha256 {digest(result)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
