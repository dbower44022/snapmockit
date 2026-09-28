# Kickoff Prompt: The Flatpak Repository

Last Updated: 09-27-26 22:53 · Revision 1.0

Paste everything below the line into a new Claude Code session rooted in this repository on the Linux machine. Start it only when no other session is committing in this working directory and no continuous-integration run of the current commit is in progress, since a push cancels a run in progress on the same branch. This replaces Flatpak decision 2 (`docs/Packaging-Flatpak-Implementation.md`, Section 2.2, option A: a bundle on the GitHub release) with a signed Flatpak repository that Snapmockit's users add once and that updates them from then on. Doug asked for it on 09-27-26, after installing 1.5.0 by hand, as option 1 of four: a repository of the project's own, not a Flathub submission, which he declined on 09-18-26 (`docs/Packaging-Flathub-Implementation.md`). `docs/General-UI-Implementation-Kickoff-Prompt.md` (revision 1.1) still governs the standards, and this prompt governs the work. Where the two disagree, the general prompt wins and this one is corrected. The work is five phases and a close-out, the fifth being the proof. A session pasting this prompt starts at the first phase not marked done in Section 1 of the notes document this work creates.

---

Operating mode: DETAIL

Read the project `CLAUDE.md` at the repository root. No other repository is involved in this session. Every reply opens with the local time from `date`, as the global guidance says.

## Task

Give the Flatpak an update source, so that a Snapmockit user on Linux gets each release through `flatpak update` and through the desktop's own updater (Linux Mint's Update Manager on Doug's machine) instead of downloading a bundle and installing it by hand:

- **A Flatpak repository**, the OSTree repository `packaging/flatpak/build.py` already builds on every run, published as static files at a stable web address, signed with a key of the project's own, and carrying the application's AppStream data so a software centre can show it.
- **A one-time way in**: a `.flatpakref` file that installs Snapmockit and adds the repository in one step, and a `.flatpakrepo` file for adding the repository alone, both carrying the public key and naming Flathub as the runtime's source.
- **Each release published into the repository by the release workflow**, with no step by hand beyond the tag and the approvals the release process already has.
- **The bundle kept** on the GitHub release beside the AppImage, built so that a bundle installation also updates from the repository.
- **Check for Updates** telling a Flatpak user the right thing for how their copy was installed.
- **The README, the release process, and the product requirements documents** brought to the new route.

The session opens by presenting decision 1 below with the consequential decision template, and then waits. The decisions are presented one at a time, each waiting for Doug's answer before the next.

## Read first, in this order

1. `docs/Packaging-Flatpak-Implementation.md` whole, above all Section 2 (the five decisions, 2.2 being the one this work replaces and 2.5 the message this work changes), Section 8 (the recipe), Section 12 (the build in continuous integration), and Section 13 (the release).
2. `docs/Release-Engineering.md` Sections 1, 5, and 6, and its change log from 1.22 down to 1.19.
3. `packaging/flatpak/build.py` whole (`build_repository`, `bundle`, and what `main` does with them), the manifest `packaging/flatpak/io.github.dbower44022.snapmockit.yml` (its `branch: stable` and the comment above it), and `packaging/flatpak/smoke.sh`.
4. `.github/workflows/ci.yml`: the `flatpak` job, the `release` job, and the `publish-pypi` job, for the shape of a publishing job that downloads what another job built and is gated by an environment.
5. `snapmock/config/packaging.py` (`in_flatpak`, `upgrade_instruction`) and `snapmock/main_window.py`'s `FLATPAK_UPDATE_INSTRUCTION` and the Check for Updates reply around it (about line 4333).
6. `README.md`'s Flatpak section (about lines 85 to 95).
7. `PRDs/SnapMock-Technical-Architecture-PRD.html` 7.3 and Section 10 (the `packaging/flatpak/` rows), and `PRDs/SnapMock-General-UI-PRD.html` 3.8 (Check for Updates) with its 2.50 row.
8. `tests/test_packaging_flatpak.py`, for what the Flatpak recipe's tests already assert.

Do not write anything until all eight are read.

## Starting state, verified on 09-27-26 at 22:53

Verified on this machine by running the tools, not by reading:

- **A bundle installation cannot update.** Doug's 1.5.0 is installed in the user installation from the bundle, and its origin remote, `snapmockit-origin`, has an empty `url=` and `gpg-verify=false`. `flatpak update` has nowhere to look.
- **`packaging/flatpak/build.py` already makes an OSTree repository** with `flatpak-builder --repo=...`, then `flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo` from it into the one file the release carries. The repository is thrown away after each build. The manifest publishes the branch `stable`.
- **The tools this needs exist in Flatpak 1.14.6 here**: `flatpak build-bundle --repo-url=URL` (a bundle that names its repository, so its installation updates from there), and `flatpak build-update-repo` with `--gpg-sign`, `--generate-static-deltas`, `--prune`, `--prune-depth`, `--title`, and `--default-branch`.
- **The repository has no GitHub Pages site**: `gh api repos/dbower44022/snapmockit/pages` answers 404. The repository is public and its default branch is `main`, the only branch on the remote.
- **Doug's machine runs Linux Mint 22.2** with `mintupdate` installed; the Update Manager is expected to list updates for Flatpaks from any remote, which the display run must prove, not assume.
- **Check for Updates inside a Flatpak** says "Download the new .flatpak bundle from the release page and install it with flatpak install." Its docstring says it becomes `flatpak update` once Flatpak decision 2's Flathub step exists; this work is that step by another route.
- **The release process** (`docs/Release-Engineering.md` Section 5) has nine steps; the tag publishes the GitHub release, and the upload to the Python Package Index waits for Doug's approval of the `pypi` environment on the run's page. An approval typed in the chat does not reach GitHub.

## Phases

Five phases and a close-out. Each phase is one or more commits and is closed out before the next starts: the PRD rows, the notes' section, the phase-table row marked done, and the next required step. Every commit is ruff-clean and mypy-strict-clean with the suite passing. The full suite runs from a scratch `git worktree` at the commit under test with `QT_QPA_PLATFORM=offscreen uv run pytest -q -o faulthandler_timeout=120 --deselect tests/test_property_panel.py::test_font_combo_reflects_text_item_font --deselect tests/test_app.py::test_main_window_default_size`, in about 7 minutes. A push to `main` cancels the continuous-integration run in progress, so push once per phase, after the suite.

### Phase 1, the decisions

The decisions below, presented one at a time with the consequential decision template, and `docs/Flatpak-Repository-Implementation.md` (revision 1.0) created with the phase table, the decisions as taken, and the silences decided. One commit.

### Phase 2, the key and the address, done with Doug

1. **The signing key**, per decision 3. If the session generates it, it does so on this machine into a keyring of its own under the scratchpad, never into Doug's own `~/.gnupg`, and prints nothing of the private key. The public key is committed under `packaging/flatpak/`. The private key reaches GitHub as a repository secret, which is set in Doug's name and so is asked of him at that moment, with the command shown first. What Doug keeps as the offline copy, and where, is his to say.
2. **The address**, per decision 1: GitHub Pages turned on for the repository, and a custom domain's DNS record if decision 1 takes one. Each is an action in Doug's name on GitHub or at his DNS host, asked of him at that moment, and written as steps with the `instruction-discipline` skill where he does it himself.
3. The notes record what exists where, without any secret in them.

### Phase 3, the recipe and the workflow

1. **`build.py` keeps the repository it builds**, or a new command beside it publishes it, per decision 2: `flatpak build-update-repo` with the title, the default branch `stable`, the signature, static deltas, the AppStream data, and the pruning silence 1 settles.
2. **The bundle names its repository**: `build-bundle --repo-url=` the published address, so a new bundle installation updates from the repository (decision 5).
3. **The `.flatpakref` and `.flatpakrepo` files**, generated from one template each with the public key embedded, published at the repository's address, and attached to the GitHub release.
4. **A publishing job in `ci.yml`**, gated as decision 4 says, that takes the repository the `flatpak` job built and publishes it without building anything itself, as the `publish-pypi` job does for the index.
5. **Tests** in `tests/test_packaging_flatpak.py`: the reference files' keys and the embedded key's form, the bundle command naming the repository, the workflow job's trigger, its gate, and its needs, and the repository step's options.
6. Technical Architecture PRD Section 10 rows for every new file under `packaging/flatpak/`, and a 7.3 row saying how the Flatpak is now published, in the same commit that adds them.

### Phase 4, the application and the documents

1. **Check for Updates inside a Flatpak** (decision 5): what it says for a copy installed from the repository, and what it says for a copy installed from an old bundle, which cannot update until it is reinstalled once. Whether the running copy can tell the two apart from inside the sandbox is to be found out by reading `/.flatpak-info` in the sandbox, not assumed. General UI PRD 3.8 row.
2. **The README's Flatpak section** rewritten: the one-time install from the `.flatpakref`, the update that follows, the move from a bundle installation, and the bundle still offered for a machine that does not want a remote.
3. **`docs/Release-Engineering.md` Section 5** gains the repository's step and its read-back, and Section 1's step 3 says how the Flatpak is published.
4. **`docs/Packaging-Flatpak-Implementation.md`** gains a change-log row saying that decision 2 is replaced and by what.

### Phase 5, the proof

A repository proves itself only when an update arrives through it, which needs two versions published into it.

1. **The first version into the repository**, per decision 4 and silence 4, then Doug installs from the `.flatpakref` over his bundle installation, following steps written with the `instruction-discipline` skill.
2. **The second version**, the next ordinary release, published through the whole release process; Doug's Update Manager lists it, installs it, and Help > About reads the new version. `flatpak update` is proven the same way from the command line.
3. The notes record both runs with Doug's words quoted.

### Close-out of the work

The phase table done, the notes' revision bumped, the next required step stated, and memory updated.

## Decisions to surface

Apply the two-part test from the global guidance. These five are expected to pass it; present each with the consequential decision template, one at a time.

- **1. Where the repository lives, and at what address.** Option A: GitHub Pages for this repository, at `https://dbower44022.github.io/snapmockit/`, free, served by GitHub, and needing only Pages turned on. Option B: the same Pages site behind a subdomain of `snapmockit.com`, such as `flatpak.snapmockit.com`, which survives a move off GitHub at the cost of a DNS record and a certificate step. Option C: a host of Doug's own, which costs a server and its care. Why it matters: every installed copy carries the address in its remote for as long as it is installed, so moving later means every user re-adds the repository. Recommendation: B if Doug controls `snapmockit.com`'s DNS, since the address outlives the host; otherwise A.
- **2. How the repository survives between runs.** A GitHub Actions runner starts empty, and an OSTree repository must keep the commits a user's installation already has, or `flatpak update` has nothing to go from. Option A: a `gh-pages` branch holding the repository, replaced by a single new commit on each release so its history does not grow with every binary. Option B: each publishing run pulls the live repository from its own address, adds the new build with `flatpak build-commit-from` or `ostree pull`, and deploys the whole site as a Pages artifact, so no branch holds binaries at all. Why it matters: it decides whether the repository can be lost by a mistaken push and how big the project's git history becomes. Recommendation: B, since nothing binary enters git; its cost is that a failed pull must stop the run rather than publish a repository missing its history.
- **3. Whose signing key.** Option A: a key made for this repository alone, its private half only in a GitHub secret and in an offline copy Doug keeps. Option B: a key Doug already has. Why it matters: every user trusts that key from the day they add the repository, and a lost key means every user re-adds the repository with a new one. Recommendation: A; its cost is one more secret Doug keeps safe.
- **4. What publishes into the repository.** Option A: only a release tag, into `stable`, behind a GitHub environment that asks Doug to approve as `pypi` does. Option B: a release tag into `stable` with no approval, since the tag is already the deliberate act. Option C: B, plus every push to `main` into a `beta` branch that a tester can follow. Why it matters: a version in `stable` reaches every user's Update Manager, and unlike the index it can be withdrawn only by publishing another. Recommendation: A for the first releases, the same shape as the index.
- **5. What happens to the bundle and to the copies already installed from one.** Option A: the bundle stays on the release, now built with `--repo-url`, so installing it also adds the repository and updates follow; copies installed from a 1.x bundle are moved once by installing from the `.flatpakref`, which Check for Updates and the README say. Option B: the bundle is dropped from the release, and the `.flatpakref` is the only Flatpak route. Why it matters: it decides whether a download-and-install user is still served, and what 1.x users are told. Recommendation: A; its cost is that a bundle installation now contacts the repository, which a user who wanted no remote must remove.

Everything else follows the documents; where they are silent, decide, note it in the notes and the PRD rows, and continue. Five silences are known:

- **1. How many old versions the repository keeps.** Keep enough for a user a few releases behind to update through static deltas, and prune the rest with `--prune-depth`; decide the number and say why.
- **2. The AppStream data.** `build-update-repo` builds the repository's `appstream` branch from the metainfo the recipe installs; a software centre reads it, and the Update Manager may show its release notes. Decide whether the metainfo gains a `<releases>` entry per release and where that comes from.
- **3. The runtime.** The `.flatpakref` and `.flatpakrepo` name Flathub as `RuntimeRepo`, so a machine without Flathub is offered it for the KDE runtime; this is the same runtime source the bundle names today, and nothing of Snapmockit goes to Flathub.
- **4. The first version into the repository.** Either the next ordinary release, or a rebuild of v1.5.0 published into the repository by hand through the workflow, so the second proof run can happen at the release after. Decide by what Doug's release plans are at the time.
- **5. The rehearsal.** A publishing job that has never run should be run once against a throwaway address, such as a branch of the site or a separate test site, before it runs against the real one; decide how, as the index work used its test index.

## Standards that apply

- Terminology Precision, Writing Register, and Reply Format from the global guidance apply to every reply and to the documents.
- Every new file under `packaging/` and every new module gets a row in Technical Architecture PRD Section 10 in the commit that creates it.
- Departures from any product requirements document are recorded in that document's revision-control table with a version bump, not only in code comments. **Check the table for a duplicate version number before bumping**, and keep the header's "Document version", "Last Updated", and document identifier in step with the table.
- No control is disabled (General UI PRD 1.3).
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy snapmock`, and `uv run pytest` must pass before each commit, with `QT_QPA_PLATFORM` set to `offscreen` for pytest.
- **No secret enters the repository, the notes, a commit message, a log line, or a reply.** The private key is generated and handled only as Phase 2 says.
- Installing software on Doug's machine is asked of him first. **Anything that leaves this machine in Doug's name, whether a secret set on GitHub, Pages turned on, a DNS record, a tag, or a publish into the repository, is asked of him at the moment it happens, not once at the start.** An approval of a GitHub environment is his click on the run's page; the session reads it back with `gh api repos/dbower44022/snapmockit/actions/runs/<run id>/approvals` rather than taking a chat message for it.
- Every instruction to Doug is written with the `instruction-discipline` skill, in the chat and on one standing page.
- Document timestamps are read from the machine clock at the time of writing, never estimated.
- Commit messages end with the attribution block the session provides.

## When the work is complete

Update the phase table in `docs/Flatpak-Repository-Implementation.md`, bump its revision, add a change-log row, and state the next required step. Say what a Flatpak user now does the first time and at each release, what a 1.x bundle user does once, and what of Technical Architecture PRD 7.3 remains.

**The display checks this work will owe**, none of which a headless test can settle: the `.flatpakref` opened on Doug's machine installing Snapmockit and adding the repository; Help > About reading the installed version; the next release listed by Linux Mint's Update Manager and installed from there; `flatpak update` doing the same from the command line; and Check for Updates saying the right thing in a copy from the repository and in a copy from an old bundle.

---

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-27-26 22:53 | Claude (Claude Code) | Initial kickoff prompt, written at Doug's request on 09-27-26 after he installed the 1.5.0 bundle by hand and chose option 1 of four: a signed Flatpak repository of the project's own. Starting state verified on 09-27-26: the bundle installation's origin remote has no address; `build-bundle --repo-url` and `build-update-repo` with signing, deltas, and pruning exist in Flatpak 1.14.6; no GitHub Pages site; Linux Mint 22.2 with the Update Manager. Five phases counting the proof, a close-out, five decisions, and five silences. |
