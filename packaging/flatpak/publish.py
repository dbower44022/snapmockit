"""Publish the Flatpak repository (docs/Flatpak-Repository-Implementation.md).

The Flatpak repository is the project's own update source for the Flatpak: a static
site served by GitHub Pages at ``https://flatpak.snapmockit.com/`` (decision 1, option
B), signed with the key whose public half is ``snapmockit-flatpak.gpg`` beside this file
(decision 3, option A). One command, run by the release workflow's publishing job::

    python3 packaging/flatpak/publish.py --source build/flatpak/repo --site site \\
        --references dist --branch stable

builds the whole site from nothing (decision 2, option C):

1. A new, empty Flatpak repository at ``<site>/repo``.
2. The application's commit copied into it from the Flatpak repository ``build.py``
   left behind (``flatpak build-commit-from``), signed, under *branch*: ``stable`` for
   a release (decision 4), ``rehearsal`` for a run started by hand (silence 5).
   Nothing else of the build is copied: not its debug extension, not its history.
3. The summary, the AppStream branches, and a static delta for a first installation,
   all signed (``flatpak build-update-repo``).
4. The two reference files at the site's root: ``snapmockit.flatpakref``, which installs
   the application and adds the Flatpak repository in one step, and
   ``snapmockit.flatpakrepo``, which adds the Flatpak repository alone. They are the
   files ``build.py`` wrote for the GitHub release, copied, so the release and the site
   carry the same bytes.

The signing key is read from the GnuPG home directory the job imported the repository
secret into; this script never sees the key itself, only its fingerprint.

Nothing here imports Qt or any package outside the standard library, so the publishing
job runs it with the runner's own ``python3``.
"""

from __future__ import annotations

import argparse
import base64
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from snapmock.config.constants import APP_NAME, DESKTOP_ENTRY_ID  # noqa: E402

ARCH = "x86_64"
SITE_ADDRESS = "https://flatpak.snapmockit.com/"
"""The GitHub Pages site's address (decision 1). Every installed copy keeps it."""

REPOSITORY_ADDRESS = f"{SITE_ADDRESS}repo/"
"""Where the Flatpak repository itself is, and what a remote's ``url`` holds."""

HOMEPAGE = "https://github.com/dbower44022/snapmockit"
FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"
"""The KDE runtime's source, named by the ``.flatpakref`` and the bundle (silence 3)."""

PUBLIC_KEY = HERE / "snapmockit-flatpak.gpg"
KEY_FINGERPRINT = "DF8F47BD1CCF5D535B7F2986BC563E79934E4F6C"
"""The signing key's fingerprint (decision 3); its private half is a repository secret."""

FLATPAKREF_TEMPLATE = HERE / "snapmockit.flatpakref.in"
FLATPAKREPO_TEMPLATE = HERE / "snapmockit.flatpakrepo.in"
FLATPAKREF = "snapmockit.flatpakref"
FLATPAKREPO = "snapmockit.flatpakrepo"
REFERENCE_FILES = (FLATPAKREF, FLATPAKREPO)

STABLE = "stable"
"""What a release publishes into (decision 4); the manifest's own branch."""

REHEARSAL = "rehearsal"
"""What a run started by hand publishes into, never ``stable`` (silence 5)."""

REPOSITORY_CONFIG = "[core]\nrepo_version=1\nmode=archive-z2\nindexed-deltas=true\n"
"""An OSTree repository served over HTTP, as ``flatpak-builder --repo`` makes one."""


def app_ref(branch: str) -> str:
    """The OSTree ref of the application on *branch*."""
    return f"app/{DESKTOP_ENTRY_ID}/{ARCH}/{branch}"


def encoded_key(path: Path = PUBLIC_KEY) -> str:
    """The public key as the reference files carry it: the binary key, base64, one line."""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def fill_reference(template: str, key: str, url: str = REPOSITORY_ADDRESS) -> str:
    """A reference file from its template: the address and the key filled in."""
    return template.replace("@URL@", url).replace("@GPGKEY@", key)


def write_reference_files(out_dir: Path, key_path: Path = PUBLIC_KEY) -> list[Path]:
    """Write ``snapmockit.flatpakref`` and ``snapmockit.flatpakrepo`` into *out_dir*."""
    out_dir.mkdir(parents=True, exist_ok=True)
    key = encoded_key(key_path)
    written: list[Path] = []
    for template, name in ((FLATPAKREF_TEMPLATE, FLATPAKREF), (FLATPAKREPO_TEMPLATE, FLATPAKREPO)):
        target = out_dir / name
        target.write_text(fill_reference(template.read_text(encoding="utf-8"), key), "utf-8")
        written.append(target)
    return written


def init_repository(path: Path) -> Path:
    """An empty OSTree repository at *path*, which must not exist yet."""
    if path.exists():
        raise RuntimeError(f"{path} already exists; the site is always built from nothing")
    for sub in ("objects", "refs/heads", "refs/remotes", "refs/mirrors", "state", "tmp"):
        (path / sub).mkdir(parents=True)
    (path / "config").write_text(REPOSITORY_CONFIG, encoding="ascii")
    return path


def commit_command(
    source: Path, destination: Path, branch: str, key_id: str, homedir: str | None
) -> list[str]:
    """Copy the build's ``stable`` commit into *destination* under *branch*, signed."""
    command = [
        "flatpak",
        "build-commit-from",
        f"--src-repo={source}",
        f"--src-ref={app_ref(STABLE)}",
        f"--gpg-sign={key_id}",
        "--no-update-summary",
    ]
    if homedir:
        command.append(f"--gpg-homedir={homedir}")
    return [*command, str(destination), app_ref(branch)]


def update_command(destination: Path, branch: str, key_id: str, homedir: str | None) -> list[str]:
    """The signed summary, the AppStream branches, and a static delta for a first install.

    No pruning: the Flatpak repository holds one version (silence 1).
    """
    command = [
        "flatpak",
        "build-update-repo",
        f"--title={APP_NAME}",
        "--comment=Screenshot annotation and user interface mockup tool",
        f"--homepage={HOMEPAGE}",
        f"--default-branch={branch}",
        "--generate-static-deltas",
        f"--gpg-sign={key_id}",
    ]
    if homedir:
        command.append(f"--gpg-homedir={homedir}")
    return [*command, str(destination)]


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def publish(
    source: Path,
    site: Path,
    references: Path,
    branch: str = STABLE,
    key_id: str = KEY_FINGERPRINT,
    homedir: str | None = None,
) -> Path:
    """Build the whole site at *site* from the build's Flatpak repository; the site."""
    if branch not in (STABLE, REHEARSAL):
        raise ValueError(f"branch must be {STABLE} or {REHEARSAL}, not {branch!r}")
    if not (source / "refs" / "heads" / app_ref(STABLE)).is_file():
        raise RuntimeError(f"{source} holds no {app_ref(STABLE)}; build it with build.py first")
    missing = [name for name in REFERENCE_FILES if not (references / name).is_file()]
    if missing:
        raise RuntimeError(f"{references} lacks {', '.join(missing)}; build.py writes them")
    if site.exists():
        shutil.rmtree(site)
    repo = init_repository(site / "repo")
    run(commit_command(source, repo, branch, key_id, homedir))
    run(update_command(repo, branch, key_id, homedir))
    for name in REFERENCE_FILES:
        shutil.copy(references / name, site / name)
    return site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Flatpak repository's site.")
    parser.add_argument("--source", type=Path, required=True, help="the build's repository")
    parser.add_argument("--site", type=Path, required=True, help="where the site is built")
    parser.add_argument(
        "--references", type=Path, required=True, help="where build.py wrote the two files"
    )
    parser.add_argument("--branch", choices=(STABLE, REHEARSAL), default=STABLE)
    parser.add_argument("--gpg-homedir", default=None, help="the GnuPG home holding the key")
    args = parser.parse_args(argv)
    site = publish(
        args.source.resolve(),
        args.site.resolve(),
        args.references.resolve(),
        args.branch,
        KEY_FINGERPRINT,
        args.gpg_homedir,
    )
    print(f"site built at {site} with {app_ref(args.branch)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
