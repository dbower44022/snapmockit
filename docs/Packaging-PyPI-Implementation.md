# Packaging: the Python Package Index — Implementation Notes

Last Updated: 09-19-26 00:11 · Revision 1.5

Snapmockit published on the Python Package Index, so that `pipx install snapmockit`, `uv tool install snapmockit`, or `pip install snapmockit` installs the application on any platform with Python 3.12 or later, and every later release reaches the index from the release workflow. The kickoff prompt is `docs/Packaging-PyPI-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The decisions, the metadata, the command, the sdist's contents, proven here | Done 09-18-26 (Sections 2 and 5); Technical Architecture PRD 1.67 | f70ff8b, ab7baca |
| 2 | The fourth form in `config/packaging.py`, and Check for Updates' wording for it | Done 09-18-26 (Section 6); General UI PRD 2.51, Screen Capture PRD 1.2 | 7c3effd |
| 3 | The index's side (Doug), the rehearsal on the test index, the publish job, the first release | In progress: step 1 done by Doug, step 2 written (Section 7); a defect the rehearsal found fixed (7.3); the rehearsal passed 09-19-26 (7.4); the first release next | dab76f5, 133d0af, this commit |
| Close-out | The README, the release-engineering notes, the release process | Not started | |

## 2. Decisions

All five were presented with the consequential decision template on 09-18-26, one at a time, and each was taken as recommended. Decisions 1 and 3 were recommended against the kickoff prompt's own recommendation or reasoning, for the reasons given under each.

### 2.1 How a release reaches the index: option C, the workflow, gated by Doug's approval

Presented at 13:08, taken by 14:27. A job of its own, `publish-pypi`, runs after the `release` job on a `vX.Y.Z` tag: it downloads the `snapmockit-dist` artifact of the same run and uploads it with `pypa/gh-action-pypi-publish@release/v1` through a trusted publisher, with `id-token: write` on the job alone, in the GitHub environment `pypi` (address `https://pypi.org/p/snapmockit`). **The `pypi` environment requires Doug's approval on each run.** No token for the index exists anywhere. The action's signed attestations stay on, as they are by default.

**Why C and not the prompt's A:** the Python Packaging User Guide's page on publishing from GitHub Actions says, as of 09-18-26, "For security reasons, you must require manual approval on each run for the pypi environment", and the prompt says the documentation wins. **The cost:** one click per release; the GitHub release is published before the upload, so the index trails it until the click, and a run left waiting expires (GitHub's limit is 30 days, from memory and not checked this session), after which the job is re-run.

The alternatives were A, the same job with no approval rule (the prompt's recommendation), and B, an upload by hand with `uv publish` and a token kept on this machine.

### 2.2 Whether the test index comes first: option A, one rehearsal through the workflow

Presented at 14:27, taken by 14:30. A `publish-testpypi` job, started only by hand from the Actions tab (`workflow_dispatch`), uploads to `test.pypi.org` in its own environment `testpypi`, with no approval rule, through its own pending publisher. It is run once before the first real release, from a branch whose version is a release candidate (for example `1.2.0rc1`); that version is never tagged, so no GitHub release is made and Check for Updates never sees it, and the branch is deleted after the rehearsal. The installation from the test index takes its dependencies from the real index only. The job stays in the workflow for later rehearsals and never runs on a tag.

**The cost:** a second account (the test index keeps its own), a second pending publisher, a second GitHub environment, a commit that never reaches `main`, and a job that runs only by hand. The alternatives were a rehearsal by hand with a token for the test index, which does not exercise the trusted publisher, and no rehearsal.

### 2.3 The command: option B, a console command

Presented at 14:30, taken by 14:40. `[project.scripts] snapmockit = "snapmock.app:main"`. `main()` takes no argument and reads `sys.argv`, so it serves as the entry point unchanged; `python -m snapmock` keeps working beside it.

**A correction to the prompt's reasoning:** on Linux and macOS the installer writes the same launcher for a console command and a graphical one, so `--version` and `--capture` print in a terminal under either. The choice changes Windows alone, where a graphical command starts through `pythonw` with no console and nowhere to print, and a console command keeps a console window behind the application. **The cost:** a Windows user installing from the index sees that console window until the Windows packaging step ships its own launcher. The alternatives were `[project.gui-scripts]`, and both under two names.

### 2.4 What the sdist carries: option A, corrected

Presented at 14:40, taken by 16:41. `snapmock/`, `tests/`, `packaging/`, `README.md`, `LICENSE`, and `pyproject.toml`, named in an explicit `include` under `[tool.hatch.build.targets.sdist]`, so a build here and a build on the runner carry the same files and no untracked file can enter.

**A correction to the prompt's option A:** three test files read outside `tests/`. `test_packaging_appimage.py` and `test_packaging_flatpak.py` read `packaging/`, and `test_ci_workflow.py` reads `.github/workflows/ci.yml`. The prompt's option A, `tests/` without `packaging/`, would have handed a packager a suite that fails in three files. `packaging/` is therefore included, which also gives a distribution the desktop entry, the AppStream metainfo, and the MIME file for `.smk`; `test_ci_workflow.py` skips when the workflow file is absent. **The cost:** one skip condition, and 38 KB of recipe that only this project's continuous integration runs. The alternatives were the package alone, and everything tracked as now.

The wheel is `py3-none-any`, so `pip`, `pipx`, and `uv` install the wheel and never build the sdist; the sdist is read by distribution packagers and by anyone auditing a release.

### 2.5 What Check for Updates tells an installation from the index: option A

Presented at 16:41, taken by 16:42. `config/packaging.py` gains a fourth form, the installation from the index, told apart by where the `snapmock` package was imported from: the Flatpak marker is tested first and the AppImage variable second, since both of those forms also install into a `site-packages`; a package imported from inside a `site-packages` or `dist-packages` directory is then the index's form; anything else, the editable install `uv sync` makes in a checkout included, stays the source form. A newer release is reported with one upgrade line by installer:

- "Upgrade with pipx upgrade snapmockit." when the package lies under a pipx environment (its default path, or `PIPX_HOME` when set);
- "Upgrade with uv tool upgrade snapmockit." when it lies under a uv tool environment (its default path, or `UV_TOOL_DIR` when set);
- "Upgrade with pip install --upgrade snapmockit." otherwise.

The check still asks GitHub (General UI PRD 3.8). Open Release Page stays, since the release notes are there. **The cost:** a fourth form and three wordings the tests hold; and, because of decision 2.1, a gap between the GitHub release and Doug's approval during which the message names a version the index does not yet have. The alternatives were the ordinary wording, and the same wording with the index's JSON address asked instead of GitHub for this form alone.

## 3. Silences decided

The kickoff's five, each taken as the kickoff states:

1. The distribution name is `snapmockit` and the import package stays `snapmock` (Release-Engineering Section 2).
2. The dependencies stay unpinned in the package metadata; the lower bounds of Technical Architecture PRD Section 9 (PyQt6 6.5, Pillow 10.0, NumPy 1.24) are written into `dependencies` where they are missing.
3. The wheel installs no desktop entry and no icon; the menu entry is its own later step.
4. v1.1.0 is not uploaded to the index. The first release there is the next one.
5. Windows, macOS, and the menu entry are out of scope and named in the close-out.

One more, found in the reading:

6. `launch_command` in `config/packaging.py` already answers `snapmockit` wherever that name is on the path. **Corrected in Phase 1 step 4:** that is not enough. The wheel installed into a virtual environment that is not activated put `snapmockit` in the environment's `bin/`, off the path, and `launch_command` answered `<interpreter> -m snapmock`. pipx and uv tool link the command into `~/.local/bin`, which is usually on the path; a plain virtual environment does not. Phase 2 therefore gives the index's form the command beside the running interpreter when the path does not carry it.

## 4. The index's documentation, read 09-18-26 (Phase 1, reading item 7)

- **No rule about AI-generated software** in the index's acceptable use policy (`policies.python.org/pypi.org/Acceptable-Use-Policy/`), its terms of use, or the trusted publisher pages. The terms ask that the uploader's included licence permit the index to redistribute the files unmodified; MIT does. The rule that closed the Flathub work (`docs/Packaging-Flathub-Implementation.md`, Section 2.1) has no counterpart here.
- **A pending publisher reserves nothing.** The name is taken by the first upload; if another account uploads a project of that name first, the pending publisher is invalidated. `https://pypi.org/pypi/snapmockit/json` and the test index's answered 404 at 13:08.
- **Two differences from the kickoff prompt,** both taken from the Python Packaging User Guide: publishing is a job of its own, never a step in a job that builds or does other work ("Building distributions in a publishing job is unsupported; publishing jobs should only download the already-built artifacts and upload them"); and the `pypi` environment must require approval on each run (decision 2.1). Phase 3 step 2 is corrected accordingly: a `publish-pypi` job after `release`, not a step inside `release`.
- **The trusted publisher form** asks for the owner, the repository name, the workflow's file name, and the environment name. The environment is optional on the index's side and "strongly recommended"; it is used here.

## 5. Phase 1: the package (09-18-26)

**The metadata** (`pyproject.toml`): `[project.scripts] snapmockit = "snapmock.app:main"` (decision 2.3); thirteen classifiers, each checked against the index's list of 09-18-26 (development status 5, the X11 Qt environment, end users, Linux, Windows, and macOS, Python 3 only with 3.12 and 3.13, and the graphics, screen capture, and vector editor topics); seven keywords; the Homepage, Documentation, Repository, Issues, and Changelog addresses; the lower bounds of silence 2, which moved `uv.lock`'s recorded specifiers and nothing it resolves.

**A departure from the kickoff prompt:** it lists MIT among the classifiers. None is carried, because the licence is the SPDX expression `license = "MIT"` and PEP 639 deprecates a licence classifier beside one. hatchling builds with it either way (checked here); the index's page shows the expression.

**The sdist** names its contents in `[tool.hatch.build.targets.sdist]` (decision 2.4). hatchling adds `PKG-INFO` and the tracked `.gitignore`; nothing else outside the six paths enters.

**Proven here, 16:44:**

- `uv build` makes `snapmockit-1.1.0-py3-none-any.whl` (759,453 bytes) and `snapmockit-1.1.0.tar.gz` (867,021 bytes, against 1.69 MB before).
- `uvx twine check --strict` passes both, so the README renders on the project's page.
- The sdist's files, compared with `git ls-files` for the six paths: identical, plus `PKG-INFO` and `.gitignore`. It carries 347 files of `snapmock/`, 139 of `tests/`, and 11 of `packaging/`. No `docs/`, `PRDs/`, `CLAUDE.md`, `.github/`, `uv.lock`, `.claude/`, or `.flatpak-builder/`, though the last two lie in this tree.
- The wheel carries `snapmock/` (347 files) and its `dist-info`, whose `entry_points.txt` names the console command.
- The wheel installed with `uv venv` and `uv pip install` into a fresh Python 3.12 environment: `snapmockit --version` answered `Snapmockit 1.1.0`; the main window built on the offscreen platform from the installed package under a scratch home. The form read `source` and the shortcut command the interpreter's module line, which is Phase 2's work (silence 6, corrected).

**Tests:** `tests/test_packaging_pypi.py`, six: the command is a console command naming a callable `main`; the classifiers' Python versions are the checks job's matrix and `requires-python` their lowest, with no licence classifier; the three lower bounds; the five addresses; the include list against decision 2.4 and the paths never to be carried; and an sdist built with `uv build --sdist` into a temporary directory whose top-level entries are only the included ones (skipped outside a checkout or without uv). `tests/test_ci_workflow.py`'s workflow fixture skips when the workflow file is absent, so the suite passes from the sdist.

**Technical Architecture PRD 1.67:** the change-log row for 7.3 and 9, and Section 9's packaging row naming the wheel, the sdist, and trusted publishing. Section 10 is unchanged.

**The next required step** is Phase 2: the fourth form in `config/packaging.py` and Check for Updates' upgrade line (decision 2.5), with the shortcut command of silence 6.

## 6. Phase 2: the fourth form (09-18-26)

**`config/packaging.py`** gains `Form.INDEX` and an `Installer` enumeration. `current_form` tests the Flatpak marker, then the AppImage variable, then whether the directory the `snapmock` package was imported from lies in a `site-packages` or `dist-packages` directory. `installer` reads the running environment's prefix: under `<PIPX_HOME>/venvs/` or a `pipx/venvs/` folder it is pipx's; under `<UV_TOOL_DIR>/` or a `uv/tools/` (`uv/data/tools/` on Windows) folder it is uv's; anything else is pip's. `upgrade_instruction` gives the line of decision 2.5 for the index's form and nothing for the others.

**The shortcut command** (silence 6, corrected): for the index's form, `launch_command` names `snapmockit` when the path's `snapmockit` resolves to the command beside the running interpreter, which is how pipx and uv tool install it, links in `~/.local/bin`; that command's full path, quoted, when the path carries none or another installation's; and the interpreter's module line only when no command is installed beside it. The source form keeps its rule, `snapmockit` when the path has one, and now reads the path from the environment it is given, which the tests use. The first-run Wayland page and Preferences > Capture take the command from `capture_command`, as before.

**Check for Updates:** `update_message_text` adds the upgrade line after the newer-release sentence when `upgrade_instruction` gives one; the Flatpak's wording is tested first and is unchanged. Open Release Page stays.

**Proven here:** the wheel reinstalled into the scratch virtual environment of Section 5 reads `Form.INDEX`, `Installer.PIP`, and "Upgrade with pip install --upgrade snapmockit."; its region command is the full path of the environment's `bin/snapmockit` when that folder is off the path, and `snapmockit --capture full` when it is on it. The suite's own run reads the source form, since `uv sync` installs the checkout as editable.

**Tests:** `tests/test_packaging_form.py` gains eleven cases (the checkout is the source form; `site-packages` and `dist-packages` are the index's; the Flatpak and the AppImage win over their own `site-packages`; seven environment places for the installer; `PIPX_HOME` and `UV_TOOL_DIR`; the three upgrade lines; the command on the path through a link, off the path by its full path with a space quoted, and the module line with no command). `tests/test_help_check_updates.py` gains the three wordings, with Open Release Page kept and the up-to-date outcome unchanged.

**General UI PRD 2.51** (3.8) and **Screen Capture PRD 1.2** (3.5, 9.2) record it. Section 10 is unchanged.

**Not proven here:** an installation by pipx or uv tool, which is not installed on this machine by this work without Doug's word; Phase 3 installs from the index with pipx, and the display checks read the message then.

**The next required step** is Phase 3, step 1: the index's side, done by Doug, for which the steps are written next.

## 7. Phase 3: publication (09-18-26)

### 7.1 The index's side (step 1)

The steps were written for Doug with the `instruction-discipline` skill and published as a page (https://claude.ai/artifact/KaPnW5upxurXHdw7FLKqXr): the pypi.org account with two-factor authentication, its pending publisher (`snapmockit`, `dbower44022/snapmockit`, `ci.yml`, environment `pypi`), the same on test.pypi.org with environment `testpypi`, and the two GitHub environments. Doug did them by 23:39. Neither index lets the pending publishers be read without Doug's login, so they are proven only by the rehearsal's upload.

**What the GitHub interface did differently, read back through the API at 23:39:** section 4, step 10 had no "Configure environment" button, yet `testpypi` existed with no rules, as intended. `pypi` had its `v*.*.*` rule saved as a branch rule, not a tag rule, and no required reviewer. As it stood, a tag would have been refused the environment, and nothing would have gated the upload once that was fixed. **Fixed at 23:40 through the API on Doug's word (option A of the question put to him):** `dbower44022` (id 36448107) set as the required reviewer with Prevent self-review off; the branch rule deleted; `v*.*.*` added as a tag rule (id 60386684). Read back: the environment carries `required_reviewers` with `dbower44022` and the one tag rule. The page's section 4 carried labels that the interface of 09-18-26 does not show, and a later reader should prefer the API.

### 7.2 The publish jobs (step 2)

`.github/workflows/ci.yml` gains a `workflow_dispatch` trigger and two jobs, per decisions 2.1 and 2.2 and Section 4's two corrections:

- **`publish-pypi`**, on a `v` tag only, after `release`: in the `pypi` environment (address `https://pypi.org/p/snapmockit`), with `id-token: write` on the job and nowhere else, it downloads `snapmockit-dist` and runs `pypa/gh-action-pypi-publish@release/v1`. It builds nothing. It waits for Doug's approval before it starts.
- **`publish-testpypi`**, on `workflow_dispatch` only, after `checks` and `build`: the same, in the `testpypi` environment, with `repository-url: https://test.pypi.org/legacy/`.

`tests/test_ci_workflow.py` holds the trigger, the seven jobs, and each publish job's condition, needs, environment, permission, download, and action, with no build command in the real one. `actionlint` 1.7.12, run through `uvx`, finds nothing in the workflow.

**The next required step** is the rehearsal (step 3's first half), which needs Doug's word: a branch `rehearsal-1.2.0rc1` whose `snapmock/__init__.py` reads `1.2.0rc1`, pushed, and `publish-testpypi` started on it from the Actions tab.

### 7.3 The first rehearsal run, and the defect it found

On Doug's word at 23:47, the branch `rehearsal-1.2.0rc1` (one commit on dab76f5: `__version__ = "1.2.0rc1"`) was pushed and the workflow started on it with `gh workflow run ci.yml --ref rehearsal-1.2.0rc1` (run 35419613807). **Nothing was uploaded:** the checks failed on both interpreters, 3 failed and 1779 passed each, so `publish-testpypi`, which needs them, was skipped. The AppImage, the Flatpak, and the wheel and sdist all built.

**The defect:** Check for Updates could not read a running pre-release. `parse_version` accepts digits and dots only, so a running `1.2.0rc1` made every check report "The latest release could not be read". Nothing released was affected, since no release has carried a suffix. **Doug chose option A at 23:55**: fix the checker, then rehearse at `1.2.0rc1` as planned. The alternatives were a plain version on the test index with the checker left as it was, and an upload job that skips the checks.

**The fix:** `parse_running_version` in `snapmock/core/update_check.py` reads the running version, accepting PEP 440's `a`, `b`, `rc`, and `dev` suffixes, and `interpret` counts a pre-release as older than its release. So `1.2.0rc1` is offered `v1.2.0` and is up to date against `v1.1.0`. A release's tag is parsed as strictly as before. One test in `tests/test_help_check_updates.py` had fed the running version back as the release tag; it now uses `v0.0.1`, older than any running version. `tests/test_update_check.py` gains the parse table, the tag's strictness, and the pre-release's four comparisons. The two test files pass both at `1.1.0` and with the package set to `1.2.0rc1`. General UI PRD 2.52.

**The next required step** is the rehearsal again: the branch rebased onto this commit, force-pushed (it holds only the rehearsal's one commit), and the workflow started on it once more.

### 7.4 The rehearsal, passed (09-19-26)

The branch was rebased onto 133d0af and force-pushed, and the workflow started on it again at 00:05 (run 35420334832). **Every job passed:** the checks on both interpreters, the wheel and sdist, the AppImage, the Flatpak, and `publish-testpypi`; `release` and `publish-pypi` were skipped, as they are on anything but a tag. **Uploaded to test.pypi.org:** `snapmockit-1.2.0rc1-py3-none-any.whl` (761,024 bytes) and `snapmockit-1.2.0rc1.tar.gz` (872,616 bytes). Both carry an attestation naming the publisher: GitHub, `dbower44022/snapmockit`, `ci.yml`, environment `testpypi`. So the pending publisher and the trusted publishing path work end to end. The index's JSON shows the summary and the five project addresses. The real index still answers 404 for `snapmockit`.

**Installed from the test index** into a scratch Python 3.12 environment: `snapmockit==1.2.0rc1` alone with `--no-deps` from the test index, then its five dependencies from the real index, so nothing but the application came from the test index. `uv pip check` found the environment consistent. `snapmockit --version` answered `Snapmockit 1.2.0rc1`. The main window built on the offscreen platform. The form read `index`, the upgrade line was pip's, and the region command was the environment's `bin/snapmockit` by full path, since that folder is not on the path. A check against the tag `v1.1.0` read up to date, which is the fix of 7.3 working from the installed package.

The branch `rehearsal-1.2.0rc1` was deleted locally and on GitHub at 00:10. `1.2.0rc1` stays on the test index for good, which costs nothing on the real one.

**Not done here:** an installation with pipx, which comes from the real index in step 3.

**The next required step** is step 3, the first release on the index. Its version is Doug's to choose; the release notes are written for him to read before the tag; the tag is pushed only on his word; and `publish-pypi` then waits for his approval in the `pypi` environment.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.5 | 09-19-26 00:11 | Claude (Claude Code) | Section 7.4: the rehearsal passed; 1.2.0rc1 uploaded to the test index through the trusted publisher with its attestation, installed from it, started, and read as the index's form; the branch deleted. |
| 1.4 | 09-18-26 23:58 | Claude (Claude Code) | Section 7.3: the first rehearsal run uploaded nothing; its checks found that Check for Updates could not read a running pre-release; fixed on Doug's choice of option A. General UI PRD 2.52. |
| 1.3 | 09-18-26 23:41 | Claude (Claude Code) | Phase 3 steps 1 and 2 (Section 7): the index's side done by Doug; the `pypi` environment's reviewer and tag rule set through the API on his word, since the interface saved a branch rule and no reviewer; the two publish jobs and their tests. |
| 1.2 | 09-18-26 16:55 | Claude (Claude Code) | Phase 2 done (Section 6): the index's form, its installer, its upgrade line in Check for Updates, and its shortcut command, off the path included. General UI PRD 2.51, Screen Capture PRD 1.2. |
| 1.1 | 09-18-26 16:46 | Claude (Claude Code) | Phase 1 done (Section 5): the metadata, the console command, the sdist's include list, proven here with `twine check --strict` and an installation of the wheel; one departure (no licence classifier, PEP 639); silence 6 corrected (the command is off the path in a virtual environment that is not activated); decision 2.4's size corrected (38 KB). Technical Architecture PRD 1.67. |
| 1.0 | 09-18-26 16:43 | Claude (Claude Code) | Initial notes: the five decisions taken on 09-18-26, each as recommended (1 C, 2 A, 3 B, 4 A as corrected, 5 A), with the two places the recommendation departed from the kickoff prompt (decision 1 on the index's documentation, decision 4 on the tests that read `packaging/` and `.github/`); the six silences; the index's documentation read. |
