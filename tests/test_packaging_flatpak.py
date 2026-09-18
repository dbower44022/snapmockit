"""The Flatpak recipe (docs/Packaging-Flatpak-Implementation.md, decisions 1 and 3).

Nothing here builds anything or reaches the network: the manifest, the generated
dependency module, and the launcher are read as files, and the recipe's pure
functions are called directly.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from snapmock.config.constants import APP_NAME, DESKTOP_ENTRY_ID

ROOT = Path(__file__).resolve().parents[1]
FLATPAK = ROOT / "packaging" / "flatpak"
MANIFEST = FLATPAK / f"{DESKTOP_ENTRY_ID}.yml"
DEPS = FLATPAK / "python3-deps.json"
LAUNCHER = FLATPAK / "snapmockit.sh"
APPIMAGE = ROOT / "packaging" / "appimage"

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recipe() -> ModuleType:
    return _load("snapmock_flatpak_build", FLATPAK / "build.py")


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def deps() -> dict[str, Any]:
    data = json.loads(DEPS.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


# ---- the manifest ------------------------------------------------------------------------


def test_manifest_is_built_on_the_kde_runtime_and_the_pyqt_base_application(
    manifest: dict[str, Any],
) -> None:
    """Decision 1, option A, on the 6.11 branch."""
    assert manifest["runtime"] == "org.kde.Platform"
    assert manifest["runtime-version"] == "6.11"
    assert manifest["sdk"] == "org.kde.Sdk"
    assert manifest["base"] == "com.riverbankcomputing.PyQt.BaseApp"
    assert manifest["base-version"] == "6.11"
    assert manifest["branch"] == "stable"  # what a user sees in flatpak list
    assert "/app/cleanup-BaseApp.sh" in manifest["cleanup-commands"]


def test_manifest_id_matches_the_desktop_entry_the_metainfo_and_the_mime_file(
    manifest: dict[str, Any],
) -> None:
    """One id for both Linux forms (silence 1)."""
    assert manifest["id"] == DESKTOP_ENTRY_ID
    assert MANIFEST.name == f"{DESKTOP_ENTRY_ID}.yml"
    assert (APPIMAGE / f"{DESKTOP_ENTRY_ID}.desktop").is_file()
    assert (APPIMAGE / f"{DESKTOP_ENTRY_ID}.xml").is_file()
    metainfo = (APPIMAGE / f"{DESKTOP_ENTRY_ID}.appdata.xml").read_text(encoding="utf-8")
    assert f"<id>{DESKTOP_ENTRY_ID}</id>" in metainfo


def test_manifest_permissions_are_the_ones_decision_3_names(manifest: dict[str, Any]) -> None:
    """Option A: the home directory, both display sockets, the GPU, IPC, and the network."""
    assert set(manifest["finish-args"]) == {
        "--filesystem=home",
        "--socket=wayland",
        "--socket=fallback-x11",
        "--share=ipc",
        "--device=dri",
        "--share=network",
    }


def test_manifest_builds_the_dependencies_then_the_application(manifest: dict[str, Any]) -> None:
    modules = manifest["modules"]
    assert modules[0] == "python3-deps.json"
    app = modules[1]
    assert app["name"] == "snapmockit"
    assert app["buildsystem"] == "simple"
    commands = "\n".join(app["build-commands"])
    assert "pip3 install --no-index --no-deps" in commands
    assert "snapmockit-*.whl" in commands
    for share in (
        f"share/applications/{DESKTOP_ENTRY_ID}.desktop",
        f"share/metainfo/{DESKTOP_ENTRY_ID}.metainfo.xml",
        f"share/mime/packages/{DESKTOP_ENTRY_ID}.xml",
        f"share/icons/hicolor/scalable/apps/{DESKTOP_ENTRY_ID}.svg",
    ):
        assert share in commands
    assert manifest["command"] == "snapmockit"
    assert "bin/snapmockit" in commands
    paths = {source.get("path") for source in app["sources"]}
    assert "../../build/flatpak/stage" in paths
    assert "snapmockit.sh" in paths


def test_manifest_removes_the_web_engine_the_application_never_imports(
    manifest: dict[str, Any],
) -> None:
    env = manifest["build-options"]["env"]
    assert env["BASEAPP_REMOVE_WEBENGINE"] == "1"
    assert env["BASEAPP_REMOVE_PYWEBENGINE"] == "1"


def test_the_bundle_names_the_manifest_s_branch(
    recipe: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Left to itself, flatpak build-bundle takes the branch master (finding 2)."""
    called: list[list[str]] = []
    monkeypatch.setattr(recipe, "run", lambda command, **kwargs: called.append(command) or "")
    destination = tmp_path / "Snapmockit-1.0.0-x86_64.flatpak"
    with pytest.raises(RuntimeError):  # the faked command writes no file
        recipe.bundle(tmp_path / "repo", destination)
    assert called[0][-2:] == [DESKTOP_ENTRY_ID, "stable"]
    assert str(destination) in called[0]


def test_the_launcher_runs_the_module_with_the_arguments() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert text.startswith("#! /bin/sh")
    assert 'exec python3 -m snapmock "$@"' in text
    # The host's variables that name things the sandbox does not have (finding 5).
    assert "unset GTK_MODULES" in text
    assert "unset SESSION_MANAGER" in text


# ---- the generated dependency module ------------------------------------------------------


def test_deps_module_installs_wheels_without_the_network(deps: dict[str, Any]) -> None:
    assert deps["name"] == "python3-deps"
    assert deps["buildsystem"] == "simple"
    command = "\n".join(deps["build-commands"])
    assert "pip3 install --no-index --no-deps" in command
    for source in deps["sources"]:
        assert source["type"] == "file"
        assert source["url"].startswith("https://files.pythonhosted.org/")
        assert SHA256.match(source["sha256"])
        assert source["url"].rsplit("/", 1)[1] in command


def test_deps_module_carries_the_locked_dependencies_but_not_pyqt(
    deps: dict[str, Any], recipe: ModuleType
) -> None:
    """PyQt6 comes from the base application; the other four from the lock file."""
    names = [source["url"].rsplit("/", 1)[1].split("-")[0].lower() for source in deps["sources"]]
    assert set(names) == {"numpy", "pillow", "psutil", "send2trash"}
    for source in deps["sources"]:
        assert recipe.runs_on_the_runtime(source["url"].rsplit("/", 1)[1])


# ---- the recipe's own functions -----------------------------------------------------------


def test_bundle_name_is_the_product_the_version_and_the_architecture(recipe: ModuleType) -> None:
    assert recipe.bundle_name("1.1.0") == f"{APP_NAME}-1.1.0-x86_64.flatpak"


def test_dependency_pins_drop_the_three_pyqt_distributions(recipe: ModuleType) -> None:
    export = "\n".join(
        [
            "# via uv export",
            "numpy==2.4.2",
            "    # via snapmockit",
            "pyqt6==6.10.2",
            "pyqt6-qt6==6.10.2",
            "pyqt6-sip==13.11.0",
            "send2trash==2.1.0",
        ]
    )
    assert recipe.dependency_pins(export) == [("numpy", "2.4.2"), ("send2trash", "2.1.0")]


@pytest.mark.parametrize(
    ("filename", "loadable"),
    [
        ("send2trash-2.1.0-py3-none-any.whl", True),
        ("numpy-2.4.2-cp313-cp313-manylinux_2_28_x86_64.whl", True),
        ("psutil-7.2.2-cp36-abi3-manylinux_2_28_x86_64.whl", True),
        ("numpy-2.4.2-cp313-cp313t-manylinux_2_28_x86_64.whl", False),
        ("numpy-2.4.2-cp312-cp312-manylinux_2_28_x86_64.whl", False),
        ("numpy-2.4.2-cp314-cp314-manylinux_2_28_x86_64.whl", False),
        ("numpy-2.4.2-cp313-cp313-manylinux_2_28_aarch64.whl", False),
        ("psutil-7.2.2-cp36-abi3-musllinux_1_2_x86_64.whl", False),
        ("psutil-7.2.2-cp314-abi3-manylinux_2_28_x86_64.whl", False),
    ],
)
def test_only_wheels_the_runtime_can_load_are_taken(
    recipe: ModuleType, filename: str, loadable: bool
) -> None:
    assert recipe.runs_on_the_runtime(filename) is loadable


def test_choose_wheel_prefers_the_newest_glibc_floor(recipe: ModuleType) -> None:
    files = [
        {
            "packagetype": "bdist_wheel",
            "filename": "numpy-2.4.2-cp313-cp313-manylinux_2_17_x86_64.whl",
            "url": "https://files.pythonhosted.org/a",
            "digests": {"sha256": "a" * 64},
        },
        {
            "packagetype": "bdist_wheel",
            "filename": "numpy-2.4.2-cp313-cp313-manylinux_2_28_x86_64.whl",
            "url": "https://files.pythonhosted.org/b",
            "digests": {"sha256": "b" * 64},
        },
        {"packagetype": "sdist", "filename": "numpy-2.4.2.tar.gz", "url": "", "digests": {}},
    ]
    assert recipe.choose_wheel(files)["filename"].endswith("manylinux_2_28_x86_64.whl")


def test_choose_wheel_refuses_a_release_with_no_wheel_for_the_runtime(recipe: ModuleType) -> None:
    files = [
        {
            "packagetype": "bdist_wheel",
            "filename": "numpy-2.4.2-cp312-cp312-manylinux_2_28_x86_64.whl",
            "url": "https://files.pythonhosted.org/a",
            "digests": {"sha256": "a" * 64},
        }
    ]
    with pytest.raises(RuntimeError):
        recipe.choose_wheel(files)


def test_deps_module_shape_is_what_the_manifest_includes(recipe: ModuleType) -> None:
    module = recipe.deps_module(
        [{"filename": "numpy-2.4.2-cp313.whl", "url": "https://x/numpy", "sha256": "a" * 64}]
    )
    assert module["name"] == "python3-deps"
    assert module["sources"] == [{"type": "file", "url": "https://x/numpy", "sha256": "a" * 64}]
    assert "numpy-2.4.2-cp313.whl" in module["build-commands"][0]
