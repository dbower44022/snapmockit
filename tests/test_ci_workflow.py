"""The continuous-integration workflow and the AppImage smoke test (packaging decision 2).

The workflow file parses and carries the jobs the release-engineering notes and the
packaging notes describe; the smoke script runs here against a built AppImage when one
is in ``dist/`` and is skipped when none is.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SMOKE = ROOT / "packaging" / "appimage" / "smoke.sh"


@pytest.fixture(scope="module")
def workflow() -> dict[str, object]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_workflow_runs_on_pushes_pull_requests_and_release_tags(
    workflow: dict[str, object],
) -> None:
    on = workflow.get("on") or workflow.get(True)  # YAML 1.1 reads a bare "on" as True
    assert isinstance(on, dict)
    assert on["push"]["branches"] == ["main"]
    assert on["push"]["tags"] == ["v*.*.*"]
    assert "pull_request" in on


def test_workflow_has_the_four_jobs_and_their_needs(workflow: dict[str, object]) -> None:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert set(jobs) == {"checks", "build", "appimage", "release"}
    assert jobs["appimage"]["runs-on"] == "ubuntu-latest"
    assert set(jobs["release"]["needs"]) == {"checks", "build", "appimage"}
    assert "startsWith(github.ref, 'refs/tags/v')" in jobs["release"]["if"]
    assert jobs["release"]["permissions"] == {"contents": "write"}


def test_checks_job_runs_on_both_interpreters(workflow: dict[str, object]) -> None:
    """3.12, the package's own, and 3.13, the KDE runtime's (Flatpak decision 1)."""
    checks = workflow["jobs"]["checks"]  # type: ignore[index]
    assert checks["strategy"]["matrix"]["python-version"] == ["3.12", "3.13"]
    assert checks["strategy"]["fail-fast"] is False
    assert checks["env"]["UV_PYTHON"] == "${{ matrix.python-version }}"


def test_appimage_job_builds_with_the_recipe_smokes_and_keeps_the_file(
    workflow: dict[str, object],
) -> None:
    steps = workflow["jobs"]["appimage"]["steps"]  # type: ignore[index]
    runs = "\n".join(str(step.get("run", "")) for step in steps)
    assert "uv sync --locked --group packaging" in runs
    assert "python packaging/appimage/build.py" in runs
    assert "bash packaging/appimage/smoke.sh" in runs
    uploads = [
        step for step in steps if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert len(uploads) == 1
    assert uploads[0]["with"]["path"] == "dist/*.AppImage"
    assert uploads[0]["with"]["if-no-files-found"] == "error"


def test_release_job_checks_the_tag_against_the_package_version_and_publishes(
    workflow: dict[str, object],
) -> None:
    steps = workflow["jobs"]["release"]["steps"]  # type: ignore[index]
    runs = "\n".join(str(step.get("run", "")) for step in steps)
    assert "snapmock/__init__.py" in runs  # the tag must be the package's version
    assert "gh release create" in runs
    assert "--prerelease" not in runs  # decision 5: an ordinary release
    downloads = [
        step for step in steps if str(step.get("uses", "")).startswith("actions/download-artifact")
    ]
    assert len(downloads) == 1


def test_smoke_script_is_executable_and_checks_the_version_and_the_window() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    assert text.startswith("#! /bin/bash")
    assert "--appimage-extract-and-run --version" in text
    assert "--appimage-extract" in text
    assert "QT_QPA_PLATFORM=offscreen" in text
    assert "MainWindow" in text


@pytest.mark.skipif(
    not list((ROOT / "dist").glob("Snapmockit-*-x86_64.AppImage")),
    reason="no built AppImage under dist/",
)
def test_smoke_script_passes_against_the_built_appimage() -> None:
    app = sorted((ROOT / "dist").glob("Snapmockit-*-x86_64.AppImage"))[-1]
    result = subprocess.run(
        ["bash", str(SMOKE), str(app.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "smoke test passed" in result.stdout
