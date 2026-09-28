"""The Flatpak recipe (docs/Packaging-Flatpak-Implementation.md, decisions 1 and 3) and
the Flatpak repository it publishes into (docs/Flatpak-Repository-Implementation.md).

Nothing here builds anything or reaches the network: the manifest, the generated
dependency module, the launcher, the public key, and the reference-file templates are
read as files, and the recipe's pure functions are called directly.
"""

from __future__ import annotations

import base64
import configparser
import hashlib
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
def publisher() -> ModuleType:
    return _load("snapmock_flatpak_publish_test", FLATPAK / "publish.py")


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
    # Both files ship inside the package, so every form carries them and the
    # application installs them itself (menu-entry silence 8).
    desktop_resources = ROOT / "snapmock" / "resources" / "desktop"
    assert (desktop_resources / f"{DESKTOP_ENTRY_ID}.desktop").is_file()
    assert (desktop_resources / f"{DESKTOP_ENTRY_ID}.xml").is_file()
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


def test_the_bundle_names_the_flatpak_repository_and_carries_its_key(
    recipe: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flatpak repository decision 5: a fresh bundle installation updates from there."""
    called: list[list[str]] = []
    monkeypatch.setattr(recipe, "run", lambda command, **kwargs: called.append(command) or "")
    with pytest.raises(RuntimeError):  # the faked command writes no file
        recipe.bundle(tmp_path / "repo", tmp_path / "Snapmockit-1.0.0-x86_64.flatpak")
    assert "--repo-url=https://flatpak.snapmockit.com/repo/" in called[0]
    assert f"--gpg-keys={FLATPAK / 'snapmockit-flatpak.gpg'}" in called[0]
    assert "--runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo" in called[0]


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


# ---- the Flatpak repository (docs/Flatpak-Repository-Implementation.md) -------------------

KEY_FINGERPRINT = "DF8F47BD1CCF5D535B7F2986BC563E79934E4F6C"
PUBLIC_KEY_TAG = 6
SECRET_KEY_TAGS = {5, 7}


def _packets(data: bytes) -> list[tuple[int, bytes]]:
    """The OpenPGP packets of *data* as ``(tag, body)`` (RFC 4880, Section 4.2)."""
    packets: list[tuple[int, bytes]] = []
    at = 0
    while at < len(data):
        header = data[at]
        assert header & 0x80, "not an OpenPGP packet"
        if header & 0x40:  # the new format
            tag = header & 0x3F
            first = data[at + 1]
            if first < 192:
                length, at = first, at + 2
            elif first < 224:
                length, at = ((first - 192) << 8) + data[at + 2] + 192, at + 3
            else:
                assert first == 255, "partial lengths do not occur in a key"
                length, at = int.from_bytes(data[at + 2 : at + 6], "big"), at + 6
        else:  # the old format
            tag = (header >> 2) & 0x0F
            size = {0: 1, 1: 2, 2: 4}[header & 0x03]
            length = int.from_bytes(data[at + 1 : at + 1 + size], "big")
            at += 1 + size
        packets.append((tag, data[at : at + length]))
        at += length
    return packets


def test_the_public_key_is_the_signing_key_and_holds_no_secret(publisher: ModuleType) -> None:
    """Decision 3: the committed key is the public half only, of the fingerprint recorded."""
    packets = _packets(publisher.PUBLIC_KEY.read_bytes())
    assert not {tag for tag, _ in packets} & SECRET_KEY_TAGS
    tag, body = packets[0]
    assert tag == PUBLIC_KEY_TAG
    assert body[0] == 4  # a version 4 key, whose fingerprint is this SHA-1
    fingerprint = hashlib.sha1(b"\x99" + len(body).to_bytes(2, "big") + body).hexdigest()
    assert fingerprint.upper() == KEY_FINGERPRINT == publisher.KEY_FINGERPRINT
    assert body[5] == 1  # RSA
    bits = int.from_bytes(body[6:8], "big")
    assert bits == 4096


def _reference(publisher: ModuleType, template: Path, group: str) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]  # keys keep their case
    parser.read_string(publisher.fill_reference(template.read_text("utf-8"), "KEY"))
    return dict(parser[group])


def test_the_flatpakref_installs_the_application_from_the_flatpak_repository(
    publisher: ModuleType, manifest: dict[str, Any]
) -> None:
    ref = _reference(publisher, publisher.FLATPAKREF_TEMPLATE, "Flatpak Ref")
    assert ref["Name"] == manifest["id"] == DESKTOP_ENTRY_ID
    assert ref["Branch"] == manifest["branch"] == "stable"
    assert ref["Url"] == "https://flatpak.snapmockit.com/repo/"
    assert ref["IsRuntime"] == "false"
    # Silence 3: the KDE runtime comes from Flathub, as the bundle says.
    assert ref["RuntimeRepo"] == "https://dl.flathub.org/repo/flathub.flatpakrepo"
    assert ref["GPGKey"] == "KEY"
    assert ref["Title"] == APP_NAME


def test_the_flatpakrepo_adds_the_flatpak_repository_alone(publisher: ModuleType) -> None:
    repo = _reference(publisher, publisher.FLATPAKREPO_TEMPLATE, "Flatpak Repo")
    assert repo["Url"] == "https://flatpak.snapmockit.com/repo/"
    assert repo["DefaultBranch"] == "stable"
    assert repo["GPGKey"] == "KEY"
    # Correction 4.5: a .flatpakrepo has no key naming a runtime's source.
    assert "RuntimeRepo" not in repo
    assert "Name" not in repo


def test_the_reference_files_carry_the_key_whole_on_one_line(
    publisher: ModuleType, tmp_path: Path
) -> None:
    written = publisher.write_reference_files(tmp_path)
    assert [path.name for path in written] == ["snapmockit.flatpakref", "snapmockit.flatpakrepo"]
    for path in written:
        text = path.read_text("utf-8")
        assert "@URL@" not in text and "@GPGKEY@" not in text
        (line,) = [line for line in text.splitlines() if line.startswith("GPGKey=")]
        assert base64.b64decode(line.removeprefix("GPGKey="), validate=True) == (
            publisher.PUBLIC_KEY.read_bytes()
        )


def test_the_commit_is_the_build_s_stable_one_signed_under_the_branch(
    publisher: ModuleType, tmp_path: Path
) -> None:
    """Decision 2: one commit copied into a new Flatpak repository, and nothing else."""
    command = publisher.commit_command(
        tmp_path / "build", tmp_path / "site" / "repo", "rehearsal", "KEYID", "/gnupg"
    )
    assert command[:2] == ["flatpak", "build-commit-from"]
    assert f"--src-repo={tmp_path / 'build'}" in command
    assert f"--src-ref=app/{DESKTOP_ENTRY_ID}/x86_64/stable" in command
    assert "--gpg-sign=KEYID" in command
    assert "--gpg-homedir=/gnupg" in command
    assert command[-2:] == [
        str(tmp_path / "site" / "repo"),
        f"app/{DESKTOP_ENTRY_ID}/x86_64/rehearsal",
    ]


def test_the_repository_step_signs_the_summary_and_keeps_one_version(
    publisher: ModuleType, tmp_path: Path
) -> None:
    """Silence 1: no pruning, since the Flatpak repository only ever holds one version."""
    command = publisher.update_command(tmp_path / "repo", "stable", "KEYID", None)
    assert command[:2] == ["flatpak", "build-update-repo"]
    assert "--title=Snapmockit" in command
    assert "--default-branch=stable" in command
    assert "--generate-static-deltas" in command
    assert "--gpg-sign=KEYID" in command
    assert not [option for option in command if option.startswith("--prune")]
    assert "--no-update-appstream" not in command  # a software centre reads it (silence 2)
    assert command[-1] == str(tmp_path / "repo")


def test_the_site_is_always_built_from_nothing(publisher: ModuleType, tmp_path: Path) -> None:
    repo = publisher.init_repository(tmp_path / "repo")
    assert "mode=archive-z2" in (repo / "config").read_text("ascii")
    with pytest.raises(RuntimeError):
        publisher.init_repository(tmp_path / "repo")


def test_publish_refuses_any_branch_but_stable_or_rehearsal(
    publisher: ModuleType, tmp_path: Path
) -> None:
    with pytest.raises(ValueError):
        publisher.publish(tmp_path / "build", tmp_path / "site", tmp_path, branch="beta")


def test_publish_refuses_a_build_without_the_application(
    publisher: ModuleType, tmp_path: Path
) -> None:
    publisher.write_reference_files(tmp_path / "dist")
    with pytest.raises(RuntimeError, match="holds no"):
        publisher.publish(tmp_path / "build", tmp_path / "site", tmp_path / "dist")
    assert not (tmp_path / "site").exists()  # nothing is built on a refusal
