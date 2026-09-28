"""The continuous-integration workflow and the two packaging smoke tests.

The workflow file parses and carries the jobs the release-engineering notes and the two
packaging notes describe (AppImage decision 2, Flatpak decision 2); the AppImage smoke
script runs here against a built file when one is in ``dist/`` and is skipped when none
is. The Flatpak's smoke script installs a bundle, so it is read here and run on the
runner, never during the suite.
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
    if not WORKFLOW.exists():
        # The sdist carries the suite but not .github/ (PyPI decision 4).
        pytest.skip("no workflow file: running from the sdist")
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
    assert "workflow_dispatch" in on  # the test index's rehearsal (PyPI decision 2)
    # Which rehearsal a run started by hand makes: the test index, or the Flatpak
    # repository under the branch "rehearsal" (Flatpak repository silence 5).
    rehearsal = on["workflow_dispatch"]["inputs"]["rehearsal"]
    assert rehearsal["options"] == ["testpypi", "flatpak"]
    assert rehearsal["default"] == "testpypi"


def test_workflow_has_the_eight_jobs_and_their_needs(workflow: dict[str, object]) -> None:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert set(jobs) == {
        "checks",
        "build",
        "appimage",
        "flatpak",
        "release",
        "publish-pypi",
        "publish-testpypi",
        "publish-flatpak",
    }
    assert jobs["appimage"]["runs-on"] == "ubuntu-latest"
    assert set(jobs["release"]["needs"]) == {"checks", "build", "appimage", "flatpak"}
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


def test_flatpak_job_installs_the_runtime_builds_smokes_and_keeps_the_bundle(
    workflow: dict[str, object],
) -> None:
    """Flatpak decision 2: the bundle is built on every push and kept as an artifact."""
    steps = workflow["jobs"]["flatpak"]["steps"]  # type: ignore[index]
    runs = "\n".join(str(step.get("run", "")) for step in steps)
    assert "org.kde.Platform//6.11" in runs
    assert "org.kde.Sdk//6.11" in runs
    assert "com.riverbankcomputing.PyQt.BaseApp//6.11" in runs
    assert "flatpak-builder" in runs
    assert "python packaging/flatpak/build.py" in runs
    assert "bash packaging/flatpak/smoke.sh" in runs
    uploads = [
        step for step in steps if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert [upload["with"]["name"] for upload in uploads] == [
        "snapmockit-flatpak",
        "snapmockit-flatpak-repo",
    ]
    # The bundle and the two reference files build.py writes beside it.
    assert uploads[0]["with"]["path"].split() == [
        "dist/*.flatpak",
        "dist/snapmockit.flatpakref",
        "dist/snapmockit.flatpakrepo",
    ]
    # The Flatpak repository the build left behind, as one file for the publishing job.
    assert "tar -C build/flatpak -cf build/snapmockit-flatpak-repo.tar repo" in runs
    assert uploads[1]["with"]["path"] == "build/snapmockit-flatpak-repo.tar"
    for upload in uploads:
        assert upload["with"]["if-no-files-found"] == "error"


def test_release_job_attaches_both_linux_forms(workflow: dict[str, object]) -> None:
    steps = workflow["jobs"]["release"]["steps"]  # type: ignore[index]
    downloads = [
        str(step.get("with", {}).get("name", ""))
        for step in steps
        if str(step.get("uses", "")).startswith("actions/download-artifact")
    ]
    assert downloads == ["snapmockit-appimage", "snapmockit-flatpak"]
    runs = "\n".join(str(step.get("run", "")) for step in steps)
    assert "dist/Snapmockit-*-x86_64.AppImage" in runs
    # The flatpak job's bundle is unsigned; the release's comes from publish-flatpak
    # (Flatpak repository decision 6).
    assert "gh release create" in runs
    create = runs[runs.index("gh release create") :]
    assert "dist/Snapmockit-*-x86_64.flatpak" not in create.split("--title")[0]
    # The way in to the Flatpak repository (Flatpak repository decision 5).
    assert "dist/snapmockit.flatpakref" in runs
    assert "dist/snapmockit.flatpakrepo" in runs


def test_flatpak_smoke_script_installs_runs_and_leaves_no_trace() -> None:
    text = (ROOT / "packaging" / "flatpak" / "smoke.sh").read_text(encoding="utf-8")
    assert "flatpak install --user -y --bundle" in text
    assert "--version" in text
    assert "QT_QPA_PLATFORM=offscreen" in text
    assert "flatpak uninstall --user -y" in text


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
    assert len(downloads) == 2  # the AppImage and the Flatpak


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


def _publish_steps(job: dict[str, object]) -> tuple[list[str], list[dict[str, object]]]:
    steps = job["steps"]
    assert isinstance(steps, list)
    downloads = [
        str(step["with"]["name"])
        for step in steps
        if str(step.get("uses", "")).startswith("actions/download-artifact")
    ]
    publishes = [
        step
        for step in steps
        if str(step.get("uses", "")) == "pypa/gh-action-pypi-publish@release/v1"
    ]
    return downloads, publishes


def test_the_index_upload_follows_the_release_in_the_approved_environment(
    workflow: dict[str, object],
) -> None:
    """PyPI decision 1: trusted publishing after the GitHub release, gated by approval."""
    job = workflow["jobs"]["publish-pypi"]  # type: ignore[index]
    assert "startsWith(github.ref, 'refs/tags/v')" in job["if"]
    assert job["needs"] == ["release"]
    assert job["environment"] == {"name": "pypi", "url": "https://pypi.org/p/snapmockit"}
    assert job["permissions"] == {"id-token": "write"}  # the job's alone, nothing more
    assert "id-token" not in str(workflow.get("permissions", ""))
    downloads, publishes = _publish_steps(job)
    assert downloads == ["snapmockit-dist"]
    assert len(publishes) == 1
    assert "with" not in publishes[0]  # the real index, and no token
    runs = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert "uv build" not in runs  # the guide: never build in a publishing job


def test_the_rehearsal_uploads_to_the_test_index_only_when_started_by_hand(
    workflow: dict[str, object],
) -> None:
    """PyPI decision 2: a job started from the Actions tab, never on a tag."""
    job = workflow["jobs"]["publish-testpypi"]  # type: ignore[index]
    assert job["if"] == (
        "github.event_name == 'workflow_dispatch' && inputs.rehearsal == 'testpypi'"
    )
    assert set(job["needs"]) == {"checks", "build"}
    assert job["environment"] == {
        "name": "testpypi",
        "url": "https://test.pypi.org/p/snapmockit",
    }
    assert job["permissions"] == {"id-token": "write"}
    downloads, publishes = _publish_steps(job)
    assert downloads == ["snapmockit-dist"]
    assert len(publishes) == 1
    assert publishes[0]["with"] == {"repository-url": "https://test.pypi.org/legacy/"}


def test_the_flatpak_repository_is_published_on_a_release_or_a_rehearsal_on_approval(
    workflow: dict[str, object],
) -> None:
    """Flatpak repository decisions 2 and 4, and silence 5."""
    job = workflow["jobs"]["publish-flatpak"]  # type: ignore[index]
    condition = job["if"]
    assert "!cancelled()" in condition  # the release job is skipped on a rehearsal
    assert "needs.flatpak.result == 'success'" in condition
    assert (
        "(startsWith(github.ref, 'refs/tags/v') && needs.release.result == 'success')" in condition
    )
    assert "(github.event_name == 'workflow_dispatch' && inputs.rehearsal == 'flatpak')" in (
        condition
    )
    assert job["needs"] == ["flatpak", "release"]
    assert job["environment"]["name"] == "github-pages"  # Doug approves each deployment
    assert job["permissions"] == {"pages": "write", "id-token": "write", "contents": "write"}
    steps = job["steps"]
    downloads = [
        str(step.get("with", {}).get("name", ""))
        for step in steps
        if str(step.get("uses", "")).startswith("actions/download-artifact")
    ]
    assert downloads == ["snapmockit-flatpak", "snapmockit-flatpak-repo"]
    runs = "\n".join(str(step.get("run", "")) for step in steps)
    assert "flatpak-builder" not in runs  # it builds nothing
    assert "build.py" not in runs
    assert "python3 packaging/flatpak/publish.py" in runs
    assert "'stable' || 'rehearsal'" in runs  # a rehearsal never publishes into stable
    key_steps = [step for step in steps if "FLATPAK_GPG_PRIVATE_KEY" in str(step.get("env", ""))]
    assert len(key_steps) == 1
    assert key_steps[0]["env"] == {
        "FLATPAK_GPG_PRIVATE_KEY": "${{ secrets.FLATPAK_GPG_PRIVATE_KEY }}"
    }
    assert "RUNNER_TEMP" in key_steps[0]["run"]  # a keyring of the run's own
    uses = [str(step.get("uses", "")) for step in steps]
    assert "actions/upload-pages-artifact@v3" in uses
    assert "actions/deploy-pages@v4" in uses
    # Decision 6: the bundle is built from the signed Flatpak repository and checked,
    # and attached to the release only on a tag, after the site is deployed.
    assert '--bundle "signed/' in runs
    attach = [step for step in steps if "gh release upload" in str(step.get("run", ""))]
    assert len(attach) == 1
    assert attach[0]["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert "signed/Snapmockit-*-x86_64.flatpak" in attach[0]["run"]
    assert steps.index(attach[0]) > uses.index("actions/deploy-pages@v4")
