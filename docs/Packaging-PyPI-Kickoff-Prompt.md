# Kickoff Prompt: The Python Package Index

Last Updated: 09-18-26 10:24 · Revision 1.0

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. Start it only when no other session is committing in this working directory and no continuous-integration run of the current commit is in progress, since a push cancels a run in progress on the same branch. This is the next part of step 3 of the release-engineering list (`docs/Release-Engineering.md`, Sections 1 and 4). It comes after Doug closed the Flathub submission on 09-18-26 (`docs/Packaging-Flathub-Implementation.md`). `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) still governs the standards, and this prompt governs the work. Where the two disagree, the general prompt wins and this one is corrected. The work is three phases and a close-out. A session pasting this prompt starts at the first phase not marked done in Section 1 of the notes document this work creates.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root.

## Task

Publish Snapmockit on the Python Package Index, so that `pip install snapmockit` (or `pipx install snapmockit`, or `uv tool install snapmockit`) installs the application on any platform with Python 3.12 or later, and every later release reaches the index without a step by hand:

- **The package metadata brought to the index's standard**: a command the installation puts on the path, classifiers, keywords, the project addresses, and a README that renders on the project's page.
- **An sdist and a wheel that carry what they should and nothing else.**
- **Publication from the release job**, through the index's trusted publishing from GitHub Actions, never through a token kept on this machine.
- **The first release published there**, and the README and Check for Updates saying how an installation from the index is updated.

The session opens by presenting the decisions below with the consequential decision template, and then waits. **Nothing is uploaded to either index, and no tag is pushed, without Doug's word at that moment**, since a release published to the index is public, is in his name, and its version number can never be used again even if the release is deleted.

## Read first, in this order

1. `docs/Release-Engineering.md` whole, and `docs/Packaging-AppImage-Implementation.md` Sections 2 and 9, for how releases are built and published now.
2. `docs/Packaging-Flathub-Implementation.md` Section 2.1, for why the Flathub work closed.
3. `pyproject.toml`, `snapmock/__init__.py`, `snapmock/__main__.py`, `snapmock/app.py` (its `main`), and `snapmock/config/packaging.py` whole.
4. `.github/workflows/ci.yml` whole, and `tests/test_ci_workflow.py`.
5. `snapmock/main_window.py`, the Check for Updates handler and its `FLATPAK_UPDATE_INSTRUCTION`; `tests/test_help_check_updates.py`.
6. `PRDs/SnapMock-Technical-Architecture-PRD.html` 7.3, 9, 9.1, and 10; `PRDs/SnapMock-General-UI-PRD.html` 3.8.
7. The current documentation of the index, because it changes and this prompt will age: https://docs.pypi.org/trusted-publishers/ (creating a pending publisher, and using it from GitHub Actions), https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/, and the index's acceptable use policy and terms. **Check them for any rule about AI-generated software** before anything else: the Flathub work closed on such a rule (Flathub notes, Section 2.1). **Where the documentation and this prompt disagree, the documentation wins and the notes record the difference.**

Do not write anything until all seven are read.

## Starting state, verified on 09-18-26

Verified on this machine by running the tools, not by reading:

- **v1.1.0 is the latest release**, carrying the AppImage and the Flatpak bundle. `snapmock/__init__.py` reads `1.1.0`.
- **The name `snapmockit` is free on the index**: `https://pypi.org/pypi/snapmockit/json` answered 404 at 10:23. So did `snapmock`. A name is only held once a first release is uploaded, or a pending trusted publisher is registered for it.
- **`uv build` makes `snapmockit-1.1.0-py3-none-any.whl` (0.76 MB) and `snapmockit-1.1.0.tar.gz` (1.69 MB).** The wheel carries the `snapmock` package alone. **The sdist carries the whole working tree that `.gitignore` does not exclude**: 347 files of `snapmock/`, but also 139 of `tests/`, 45 of `docs/`, 16 of `PRDs/`, `packaging/`, `CLAUDE.md`, `.github/`, `uv.lock`, a test project under `Example Snag Files/`, and, built here, the untracked `.claude/settings.local.json` and `.flatpak-builder/`. A build on the runner, from a clean checkout, carries none of the untracked files. A build here would.
- **No command is installed.** `pyproject.toml` has no `[project.scripts]` or `[project.gui-scripts]`, so an installation from the index starts only as `python -m snapmock`. The Flatpak launcher and the AppImage's `AppRun` both call the module, not a command.
- **The metadata** has a name, a dynamic version, a description, the README, the MIT licence with its file, one author, `requires-python = ">=3.12"`, five dependencies, and two addresses. It has **no classifiers, no keywords, and no homepage or documentation address.**
- **`config/packaging.py` knows three forms**: source, AppImage, and Flatpak. An installation from the index is read as "source", and the shortcut command it shows is the interpreter's module line.
- **Continuous integration** has five jobs: checks (Python 3.12 and 3.13), the wheel and sdist build (kept as the `snapmockit-dist` artifact), the AppImage, the Flatpak, and the release job on a `vX.Y.Z` tag, which publishes a GitHub release with both Linux files. Nothing publishes to the index.
- **`twine` 7.0.0 answers through `uvx`**, so `twine check` can read the built files here without a new dependency in the project.

## Phases

Three phases and a close-out. Each phase is one or more commits and is closed out before the next starts: the PRD rows, the notes' section, the phase-table row marked done, and the next required step. Every commit is ruff-clean and mypy-strict-clean with the suite passing. The full suite runs from a scratch `git worktree` at the commit under test with `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font`, in about 6 minutes. A push to `main` cancels the continuous-integration run in progress, so push once per phase, after the suite.

### Phase 1, the decisions and the package

1. **The decisions**, presented with the consequential decision template, and `docs/Packaging-PyPI-Implementation.md` (revision 1.0) created with the phase table, the decisions, and the silences decided. One commit.
2. **The metadata**: the command (decision 3), classifiers (development status, the three operating systems, Python 3.12 and 3.13, the X11 and Qt environments, the graphics topic, MIT), keywords, and the project addresses, all read against the index's documentation.
3. **The sdist's contents** per decision 4, with `[tool.hatch.build.targets.sdist]` naming what is included, so a build here and a build on the runner carry the same files.
4. **Proven here**: `uv build`, then `uvx twine check --strict` on both files; the file lists of both read and compared with decision 4; and the wheel installed into a fresh virtual environment with `uv venv` and `uv pip install`, where the command answers `--version` and the main window builds on the offscreen platform.
5. **Tests** for what a test can hold: the command's entry point names a function that exists, the classifiers name the Python versions continuous integration runs, and the sdist's include list excludes what decision 4 excludes.
6. **Phase close-out**, with the Technical Architecture PRD rows for 7.3 and 9.

### Phase 2, the form and what the application says

1. **`config/packaging.py` learns the fourth form** per decision 5: an installation from the index, told apart from a checkout. The shortcut command shown on the first-run Wayland page and in Preferences > Capture becomes the installed command for that form.
2. **Check for Updates** gains the wording decision 5 settles (General UI PRD 3.8, a third wording beside the ordinary one and the Flatpak's), with tests.
3. **Phase close-out**, with the General UI PRD 3.8 row and the Screen Capture PRD row for the shortcut command.

### Phase 3, publication

1. **The index's side, done by Doug.** An account on the index with two-factor authentication. A **pending trusted publisher** for the project `snapmockit`, naming the owner `dbower44022`, the repository `snapmockit`, the workflow `ci.yml`, and the environment `pypi`. The same on the test index if decision 2 takes it. The session writes the steps with the `instruction-discipline` skill and waits. It never creates an account or a publisher itself.
2. **The release job** gains the publish step per decision 1: the `snapmockit-dist` artifact downloaded, and `pypa/gh-action-pypi-publish` run with `id-token: write` in the `pypi` environment, after the GitHub release is created. A test holds the step, its permission, and its environment.
3. **The first release to the index.** Its version is Doug's to pick. The next ordinary release carries Phases 1 and 2, since a release published to the index can never be replaced. The release notes are written for Doug to read before the tag, and the tag is pushed only on his word. Afterwards: the project page read as a user reads it, and `pipx install snapmockit` on this machine, from the index, started from the command.
4. **Phase close-out.**

### Close-out of the work

The README's "Install" names the index for every platform, with `pipx` or `uv tool` as the recommended route and what the platform must supply (Qt's system libraries on Linux). `docs/Release-Engineering.md` Sections 1 and 4 brought to the state of the work. The Technical Architecture PRD 7.3 row. The release process written down with the upload to the index as one of its steps. The next required step, which is expected to be the menu entry the AppImage lacks (end-to-end pass finding 1). **Say plainly what remains**: the menu entry, and Windows and macOS.

## Decisions to surface

Apply the two-part test from the global guidance. Five decisions are expected to pass it. Present them with the consequential decision template, **one at a time, as DETAIL mode asks**, before Phase 1 step 2, and wait for each.

- **1. How a release reaches the index.** Option A: the release job publishes through a trusted publisher on every `vX.Y.Z` tag, from the same run's `snapmockit-dist` artifact. There is no secret to keep and no step by hand, at the cost that a tag now publishes to a place where a version can never be taken back. Option B: Doug uploads by hand with `uv publish` and an index token, which is one more step per release and a token on this machine. Option C: the release job, gated by a GitHub environment that asks Doug to approve each run, which adds one click per release and a second look before the upload. Why it matters: it decides whether a release can reach the index by mistake, and whether a secret exists to leak. Recommendation: A, with the `pypi` environment carrying no approval rule; the tag is already the deliberate act (packaging decision 2).
- **2. Whether the test index comes first.** Option A: a rehearsal on `test.pypi.org` with its own account and pending publisher, a release candidate uploaded there and installed from it, before the real one. Option B: no rehearsal, with the first real upload made from the next release. Why it matters: a mistake on the real index costs a version number for good. Cost of A: a second account, a second publisher, and a version on the test index that must differ from the real one's. Recommendation: A, once, for the first release only.
- **3. The command the installation provides.** Option A: `[project.gui-scripts] snapmockit = "snapmock.app:main"`. On Windows it starts with no console window, at the cost that `--version` prints nowhere there. Option B: `[project.scripts]`, a console command on every platform, at the cost of a console window behind the application on Windows. Option C: both, under two names. Why it matters: it decides what a user types and what a Windows user sees. Recommendation: B now, since Windows packaging is a later step with its own installer, and the Linux user's `--version` and `--capture` need a console command.
- **4. What the sdist carries.** Option A: the package, `tests/`, `README.md`, `LICENSE`, and `pyproject.toml`, so a distribution's packager can build and test from it. Option B: the package, `README.md`, `LICENSE`, and `pyproject.toml` only. Option C: everything tracked, as now. Why it matters: the sdist is what distributions build from, and today it carries the PRDs, the notes, `CLAUDE.md`, and, built here, local files that were never meant to leave this machine. Recommendation: A.
- **5. What Check for Updates says to an installation from the index.** Option A: a third wording, "Upgrade with pip install --upgrade snapmockit, or the tool you installed it with", when the running package is an installed distribution and not a checkout. Option B: the ordinary wording, which points at the release page, where the AppImage and the bundle are and no wheel is. Why it matters: a user sent to the wrong file downloads a second copy instead of upgrading the one they have. Cost of A: a fourth form in `config/packaging.py`, told apart by where the package was imported from, and a branch the tests hold. Recommendation: A, with the wording naming `pipx upgrade snapmockit` if the package was installed by `pipx`, which its virtual environment's path shows.

Everything else follows the PRDs. Where they are silent or disagree, decide, note it under the notes' decisions section and the PRD rows, and continue. Silences known now:

- The distribution name is `snapmockit`, and the import package stays `snapmock` (Release-Engineering Section 2).
- The dependencies stay unpinned in the package metadata, as they are, since pins belong to `uv.lock` and to the packaged forms. The lower bounds of Technical Architecture PRD Section 9 (PyQt6 6.5, Pillow 10.0, NumPy 1.24) are written into `dependencies` where they are missing.
- No desktop entry or icon is installed by the wheel. The menu entry is its own later step.
- v1.1.0 is not uploaded to the index retroactively. The first release on the index is the next one.
- Windows, macOS, and the menu entry are out of scope and are named in the close-out.

## Standards that apply

- Terminology Precision, Writing Register, and Reply Format from the global guidance apply to every reply and to the documents.
- Every new top-level directory or module gets a row in Technical Architecture PRD Section 10 in the commit that creates it.
- Departures from any product requirements document are recorded in that document's revision-control table with a version bump, not only in code comments. **Check the table for a duplicate version number before bumping**, and keep the header's "Document version" and "Last Updated" in step with the table.
- No control is disabled (General UI PRD 1.3).
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy snapmock`, and `uv run pytest` must pass before each commit, with `QT_QPA_PLATFORM` set to `offscreen` for pytest.
- Installing software on Doug's machine is asked of him first. **Anything that leaves this machine in Doug's name, whether an upload, a tag, or a publisher registration, is asked of him at the moment it happens, not once at the start.**
- Document timestamps are read from the machine clock at the time of writing, never estimated.
- Commit messages end with the attribution block the session provides.

## When the work is complete

Update the phase table in `docs/Packaging-PyPI-Implementation.md`, bump its revision, add a change-log row, and state the next required step. Say what of Technical Architecture PRD 7.3 remains, and what an installation from the index's update path now is.

**The display checks this work will owe**, none of which a headless test can settle: the application installed with `pipx install snapmockit` from the index and started from the command; a capture, a save, and an export from that installation; Check for Updates showing the new wording from an installation of the release before; and the project's page on pypi.org read as a user reads it.

---

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-18-26 10:24 | Claude (Claude Code) | Initial kickoff prompt, written after Doug closed the Flathub submission on 09-18-26 and put the Python Package Index next. Starting state verified on 09-18-26: the name `snapmockit` free on the index; the sdist carrying the whole working tree, local files included when built here; no command in the metadata; no classifiers. Three phases and a close-out; five decisions, presented one at a time; five silences. |
