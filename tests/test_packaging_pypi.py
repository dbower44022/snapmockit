"""The package metadata the Python Package Index reads (docs/Packaging-PyPI-Implementation.md).

The command names a function that exists (decision 3), the classifiers name the
interpreters continuous integration runs, the dependencies carry Technical Architecture
PRD Section 9's lower bounds, and the sdist carries what decision 4 names and nothing
else.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

SDIST_INCLUDE = [
    "/snapmock",
    "/tests",
    "/packaging",
    "/README.md",
    "/LICENSE",
    "/pyproject.toml",
]
"""Decision 4, option A as corrected: the suite reads packaging/, so it is carried."""

NEVER_IN_SDIST = [
    "docs",
    "PRDs",
    "CLAUDE.md",
    ".github",
    "uv.lock",
    ".claude",
    ".flatpak-builder",
    "Example Snag Files",
    "dist",
]


@pytest.fixture(scope="module")
def project() -> dict[str, object]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert isinstance(project, dict)
    return project


def test_the_command_is_a_console_command_naming_main(project: dict[str, object]) -> None:
    """Decision 3: a console command on every platform, never a graphical one."""
    assert project["scripts"] == {"snapmockit": "snapmock.app:main"}
    assert "gui-scripts" not in project
    module_name, _, attribute = "snapmock.app:main".partition(":")
    assert callable(getattr(importlib.import_module(module_name), attribute))


def test_the_classifiers_name_the_interpreters_continuous_integration_runs(
    project: dict[str, object],
) -> None:
    classifiers = project["classifiers"]
    assert isinstance(classifiers, list)
    declared = sorted(
        c.rsplit(" :: ", 1)[1]
        for c in classifiers
        if c.startswith("Programming Language :: Python :: 3.")
    )
    if WORKFLOW.exists():
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        tested = workflow["jobs"]["checks"]["strategy"]["matrix"]["python-version"]
        assert declared == sorted(tested)
    assert project["requires-python"] == f">={declared[0]}"
    assert "Programming Language :: Python :: 3 :: Only" in classifiers
    # The licence is the SPDX expression; PEP 639 deprecates the classifier beside it.
    assert project["license"] == "MIT"
    assert not [c for c in classifiers if c.startswith("License ::")]


def test_the_dependencies_carry_section_9_lower_bounds(project: dict[str, object]) -> None:
    dependencies = project["dependencies"]
    assert isinstance(dependencies, list)
    for bound in ("PyQt6>=6.5", "Pillow>=10.0", "numpy>=1.24"):
        assert bound in dependencies


def test_the_project_addresses_name_the_repository(project: dict[str, object]) -> None:
    urls = project["urls"]
    assert isinstance(urls, dict)
    assert set(urls) == {"Homepage", "Documentation", "Repository", "Issues", "Changelog"}
    for url in urls.values():
        assert str(url).startswith("https://github.com/dbower44022/snapmockit")


def test_the_sdist_include_list_is_decision_4() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = data["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert include == SDIST_INCLUDE
    for name in NEVER_IN_SDIST:
        assert f"/{name}" not in include


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not on the path")
@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="not a checkout")
def test_a_built_sdist_carries_only_the_included_paths(tmp_path: Path) -> None:
    """Built here, where untracked files lie in the tree, it still carries none of them."""
    result = subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (sdist,) = tmp_path.glob("snapmockit-*.tar.gz")
    with tarfile.open(sdist) as archive:
        members = [m.name.split("/", 1)[1] for m in archive.getmembers() if "/" in m.name]
    tops = {name.split("/", 1)[0] for name in members if name}
    allowed = {entry.lstrip("/") for entry in SDIST_INCLUDE} | {"PKG-INFO", ".gitignore"}
    assert tops <= allowed, tops - allowed
    assert {"snapmock", "tests", "packaging", "README.md", "LICENSE"} <= tops
