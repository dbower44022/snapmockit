# The Flatpak Repository — Implementation Notes

Last Updated: 09-28-26 00:05 · Revision 1.3

A signed Flatpak repository of the project's own, so a Snapmockit user on Linux gets each release through `flatpak update` and through the desktop's own updater instead of downloading a bundle and installing it by hand. It replaces Flatpak decision 2 (`docs/Packaging-Flatpak-Implementation.md`, Section 2.2, option A: a bundle on the GitHub release). The kickoff prompt is `docs/Flatpak-Repository-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The five decisions, the silences, the corrections to the kickoff prompt, and this document | Done 09-27-26 (Sections 2 to 4) | f91a18e |
| 2 | The signing key and the address, done with Doug: the key generated, its public half committed, its private half a repository secret and an offline copy; GitHub Pages on, the DNS record at GoDaddy, HTTPS enforced; the `github-pages` environment's gate | Done 09-28-26 but the certificate, which GitHub had not issued by 09-28-26 00:05; closed at the rehearsal, the site's first deployment, on Doug's choice of 09-28-26 00:03 (Section 5) | this commit |
| 3 | The recipe and the workflow: the Flatpak repository built and signed, the bundle naming its address, the `.flatpakref` and `.flatpakrepo` files, the publishing job, the tests, the Technical Architecture PRD rows; the rehearsal on the live address (silence 5) | Written and proven locally 09-28-26 (Section 6), with decision 2.6 taken after the first run failed; the rehearsal waits for Doug | caa95d9, this commit |
| 4 | The application and the documents: Check for Updates inside a Flatpak, the README, the release process, the Flatpak notes' change-log row | Not started | |
| 5 | The proof: 1.6.0 published into the Flatpak repository and arriving on Doug's machine through the Update Manager (silence 4) | Not started | |
| Close-out | The phase table done, the revision bumped, the next required step, memory updated | Not started | |

## 2. Decisions

All five were presented one at a time with the consequential decision template on 09-27-26 between 23:00 and 23:32, and Doug approved each as recommended.

### 2.1 Where the Flatpak repository lives: option B, GitHub Pages behind `flatpak.snapmockit.com`

The repository's GitHub Pages site, served at the subdomain `flatpak.snapmockit.com` through a CNAME record at GoDaddy, which holds `snapmockit.com`'s DNS (registered 09-14-26; Doug manages it). The address survives a repository rename, which has happened once, and a move off GitHub.

**The cost:** one DNS record, a certificate step GitHub carries out itself once the record resolves, and updates that now depend on `snapmockit.com` being renewed each year. GitHub Pages' limits, from knowledge and not checked in this session: a 1 GB site and a soft 100 GB of traffic a month.

**Follow-on detail:** the Flatpak repository is at `https://flatpak.snapmockit.com/repo/`; `snapmockit.flatpakref` and `snapmockit.flatpakrepo` are at the site's root and attached to every GitHub release. The site holds nothing else, so a later project website at `snapmockit.com` does not touch it.

### 2.2 What the Flatpak repository keeps between releases: option C, a fresh Flatpak repository on every release

Each release builds a Flatpak repository holding only the new version, signed, and deploys it as the whole GitHub Pages site. Nothing is pulled from the live site and nothing binary enters git. Old versions stay available as the bundles on the GitHub releases.

This option exists because the kickoff prompt's premise was proven wrong (correction 4.1). **The cost:** no rollback through `flatpak update --commit`, and an update downloads the changed files one at a time rather than as one static delta. A Flatpak client refuses a version whose timestamp is older than the installed one (from knowledge, not tested here), so a version can only be withdrawn by publishing a newer build.

### 2.3 Whose key signs it: option A, a key made for this Flatpak repository alone

Generated on this machine into a GnuPG keyring of its own under the scratchpad, never into `~/.gnupg`; the public key committed under `packaging/flatpak/`; the private key a GitHub repository secret and an offline copy Doug keeps where he chooses. Doug's keyring on this machine holds no private key, and the repository had no secrets, both read on 09-27-26.

**The cost:** one more secret Doug keeps safe, whose offline copy is the only way back if the repository secret is lost.

**Follow-on detail:** RSA 4096, which every Flatpak client can check; no expiry date, since a key that expires would stop every user's updates on that day; no passphrase on the copy in the repository secret, where the secret is the protection. **The key's email address is open**, asked of Doug when Phase 2 generates the key.

### 2.4 What publishes into it: option A, a release tag into `stable`, on Doug's approval

The publishing job runs on a `v*.*.*` tag after the release job, and waits for Doug's approval on the run's page as the upload to the Python Package Index does.

**The cost:** one more approval per release; until it is given, Check for Updates in a Flatpak copy reports the new release while `flatpak update` finds nothing.

**Follow-on detail:** GitHub Pages deploys from a workflow only through GitHub's own `github-pages` environment, and a job names one environment, so the gate is set on that environment: Doug as required reviewer, and the `v*.*.*` tags admitted. This is from GitHub's documentation as remembered, and Phase 2 reads it back once GitHub Pages is on.

### 2.5 The bundle and the copies already installed from one: option A, the bundle kept and naming its address

The bundle stays on the GitHub release, built with `--repo-url=https://flatpak.snapmockit.com/repo/` and `--gpg-keys` with the public key, so a fresh installation of it updates from the Flatpak repository with signatures checked.

**The cost:** a bundle installed over a 1.x bundle installation updates without its signatures being checked until one command is run (correction 4.3); and a bundle installation now contacts the Flatpak repository, which a user who wanted no remote must remove. **The 1.x installations are very likely Doug's alone:** the five 1.x bundles have been downloaded three times in all, once each for v1.1.0, v1.4.0, and v1.5.0 (read from the GitHub releases on 09-27-26), matching his own installs.

**Follow-on detail, for Phase 4:** a running copy cannot tell how it was installed (correction 4.4), so Check for Updates in new versions says one thing for both kinds of copy: update with `flatpak update` or the desktop's software updater, and where that finds nothing, the README's one-time move applies.

### 2.6 Where the bundle gets its signature: option A, the publishing job builds it

Found by continuous integration on 09-28-26 (run 36377535497) and reproduced here: **a bundle that carries the public key installs only when its commit is signed** ("GPG verification enabled, but no signatures found"), and the `flatpak` job, which runs on every push, has no key. Presented with the consequential decision template at 00:32 and approved by Doug as recommended.

The publishing job, behind Doug's approval, builds the bundle from the site's signed Flatpak repository, checks it by installing it into a throwaway Flatpak installation (where the signature is checked, and where the commit must be the one the site serves), deploys the site, and then attaches the bundle to the release. The release job attaches the AppImage and the two reference files only. The `flatpak` job's bundle keeps the address, drops the key, and is never attached to anything; it exists for the smoke test.

**The cost:** until Doug approves, the release shows the AppImage and the two reference files and no bundle, which appears a few minutes after; if he never approves, the release carries none. The publishing job gains `contents: write`, as the release job has.

**Follow-on detail, one change from what was presented:** the presentation said a rehearsal builds no bundle. It builds and checks one of its own branch and attaches nothing, so the signing and the check are proven on the runner at the rehearsal, not first at 1.6.0.

The options not taken: B, a signing job on every tag with no approval, which uses the key outside decision 4's gate; C, a bundle with the address and no key, whose every installation would update without signatures checked.

## 3. Silences decided

1. **How many old versions the Flatpak repository keeps: one**, settled by decision 2. The pruning options are not used. `--generate-static-deltas` is kept, since a delta from nothing still speeds a first installation.
2. **The AppStream data: the metainfo keeps its one release row**, filled with the version and the build date at build time as it is today. The Flatpak repository is rebuilt on every release, so its `appstream` branch only ever needs the current version; the release notes stay the annotated tag's message on the release page, since a second copy in the metainfo would drift from it. Revisited if the Update Manager shows an empty release-notes field Doug wants filled.
3. **The runtime comes from Flathub.** The `.flatpakref` names `https://dl.flathub.org/repo/flathub.flatpakrepo` as `RuntimeRepo`, the same runtime source the bundle names today. The `.flatpakrepo` cannot (correction 4.5): a user who adds the Flatpak repository alone needs Flathub added already, which the README says. Nothing of Snapmockit goes to Flathub.
4. **The first version into the Flatpak repository is 1.6.0, the release that carries this work**: its Check for Updates wording and its bundle's address both change. Nothing is unreleased since v1.5.0 but two documents. Before 1.6.0 is published, Doug's 1.5.0 installation is moved in place with the one command of correction 4.2, so 1.6.0 arriving through Linux Mint's Update Manager is the proof of an update through the Flatpak repository at the first release, not the second. The `.flatpakref` is proven on his display after 1.6.0, against the live address. `flatpak update` from the command line is proven in the rehearsal (silence 5).
5. **The rehearsal runs on the live address, before any user has it.** Until 1.6.0, `flatpak.snapmockit.com` is not named by any file a user has. Two runs started by hand from `main` publish two builds of `main` into the live Flatpak repository under the branch `rehearsal`, never `stable`, on Doug's approval; a throwaway Flatpak installation on this machine installs the first over HTTPS with the signature checked, and updates to the second with `flatpak update`. The `github-pages` environment admits `main` for these runs only. **After the rehearsal passes, the manual trigger of the publishing job and the `main` allowance are removed, before 1.6.0**, because a later manual run would replace the whole site (decision 2) and take `stable` away from every user. The 1.6.0 publish replaces the rehearsal's site whole.

## 4. Corrections to the kickoff prompt

Each was found on 09-27-26 in throwaway Flatpak installations under the scratchpad (`FLATPAK_USER_DIR` pointed there), with local Flatpak repositories made by `flatpak build-commit-from` from the last local build and, for the last three, signed with a key made for the test. The installations, the Flatpak repositories, and the key were deleted afterwards, and Doug's own 1.5.0 installation was read back unchanged.

### 4.1 The server does not need the version a user has installed

The kickoff's decision 2 says an OSTree repository must keep the commits a user's installation already has, or `flatpak update` has nothing to go from. **Proven otherwise:** a copy installed from one Flatpak repository (commit `cc12929017545cd7`) had its remote pointed at a second Flatpak repository, built from nothing, that did not contain that commit, and `flatpak update` moved it to the second's commit (`a7945f00f291af02`). The client has the old version's files and fetches the files the new version lacks. What a kept history buys is a static delta from the old version and a rollback. Decision 2 gained option C from this.

### 4.2 The `.flatpakref` is refused over a bundle installation

Phase 5 step 1 has Doug install from the `.flatpakref` over his bundle installation. **Refused:** `flatpak install --from snapmockit.flatpakref` over a 1.x bundle installation answers "App io.github.dbower44022.snapmockit, branch stable is already installed", **and so does `--reinstall`**. It installs after `flatpak uninstall`, which keeps the settings under `~/.var/app` unless `--delete-data` is given. **The move that works in place**, proven with signature checking on and an update afterwards:

```
flatpak remote-modify --user --url=https://flatpak.snapmockit.com/repo/ \
  --gpg-import=<the public key file> --gpg-verify snapmockit-origin
flatpak update
```

`--gpg-import` alone imports the key and leaves checking off; `--gpg-verify` turns on both `gpg-verify` and `gpg-verify-summary`. Phase 5 step 1 is therefore this command, written for Doug with the instruction-discipline skill; the `.flatpakref` display check moves after 1.6.0 (silence 4).

### 4.3 A new bundle over an old one leaves signature checking off

A bundle built with `--repo-url` and `--gpg-keys`, installed fresh, creates the remote `snapmockit-origin` with the address and `gpg-verify=true`. **Installed over a 1.x bundle installation, it fills in the address and leaves `gpg-verify=false`**: the installation keeps the remote the first bundle created. Doug's own remote shows the same: its `xa.title` is still `Snapmockit-1.0.0-x86_64.flatpak` after three later bundles. Updates then arrive over HTTPS without their signatures checked, until the command of 4.2 is run. This is decision 5's named cost; the README and the 1.6.0 release notes carry the command.

### 4.4 A running copy cannot tell how it was installed

Phase 4 step 1 asks this to be found out by reading `/.flatpak-info` in the sandbox. **Read inside Doug's installed 1.5.0:** `/.flatpak-info` carries the application's commit, branch, and path, and no origin or remote; and `~/.local/share/flatpak` is hidden inside the sandbox although the home directory is shared, so the remote's file cannot be read either. Check for Updates therefore gives one message for both kinds of copy (decision 5's follow-on detail).

### 4.5 A `.flatpakrepo` cannot name the runtime's source

Silence 3 of the kickoff has both reference files name Flathub as `RuntimeRepo`. Read from Flatpak 1.14.6's own manual pages on 09-28-26: `flatpak-flatpakref(5)` lists `RuntimeRepo`, and `flatpak-flatpakrepo(5)` does not (its keys are `Version`, `Url`, `GPGKey`, `DefaultBranch`, `Subset`, `Title`, `Comment`, `Description`, `Icon`, `Homepage`, `Filter`, and three collection keys). The `.flatpakrepo` therefore carries no runtime source, and silence 3 is corrected above.

## 5. The key and the address (Phase 2)

Everything here was done on 09-27-26 and 09-28-26, each action in Doug's name approved by him at the moment it was taken. **No secret is in this document.**

**The signing key**, generated 09-27-26 at 23:39 into a GnuPG keyring of its own under the scratchpad (never `~/.gnupg`): RSA 4096, signing and certifying, no expiry date, identity `Snapmockit Flatpak repository <flatpak@snapmockit.com>` (Doug chose a new address over his own, 23:39), fingerprint **`DF8F 47BD 1CCF 5D53 5B7F 2986 BC56 3E79 934E 4F6C`**, long key id `BC563E79934E4F6C`.

- **The public half** is `packaging/flatpak/snapmockit-flatpak.gpg` (1,180 bytes, binary, read back as holding no secret key), committed with its Technical Architecture PRD 1.75 row and Section 10 line.
- **The private half is in exactly two places.** The repository secret `FLATPAK_GPG_PRIVATE_KEY` (set 09-28-26 03:43 UTC, piped from GnuPG to `gh secret set`, never written to a file or printed), and Doug's password manager, in the entry `Snapmockit Flatpak signing key`, which holds the armored private key and GnuPG's revocation certificate as two attachments and the fingerprint in its notes (Doug's choice, 23:45; confirmed "saved" at 23:55). GnuPG writes a revocation certificate with a colon in front of its first armor line, so it cannot be imported by accident, and the colon is removed before it is used (GnuPG's documented convention; the file itself was not inspected for it).
- **The scratchpad copies were shredded** at 23:55: the two exported files and the whole keyring. No other copy exists on this machine.

**The address.**

- **GitHub Pages turned on** 09-27-26 23:56 with `build_type=workflow` (GitHub Actions as the source), and the custom domain set to `flatpak.snapmockit.com` in the same minute, before the DNS record existed, so no other site could claim it in between.
- **The DNS record**, added by Doug at GoDaddy by 09-28-26 00:00: `flatpak` CNAME `dbower44022.github.io`. Read back from this machine: `flatpak.snapmockit.com is an alias for dbower44022.github.io`, which resolves to GitHub's addresses (185.199.110.153, 185.199.111.153).
- **The certificate: not issued by 09-28-26 00:05.** GitHub reports no certificate for the domain, and a check every minute from 00:00 found none. Inferred, not checked: GitHub may issue it only at the site's first deployment. **Doug chose at 00:03 to close Phase 2 with it open** and start Phase 3; the rehearsal's first run is the site's first deployment, and Enforce HTTPS is turned on as soon as the certificate exists.

**The gate (decision 4).** GitHub created the `github-pages` environment itself when GitHub Pages was turned on, with one deployment rule, the branch `main`. At 00:02 Doug became its required reviewer and the tag rule `v*.*.*` was added; read back, the environment carries the reviewer `dbower44022` and the rules `branch main` and `tag v*.*.*`. **The `main` rule is for the rehearsal only** (silence 5) and is removed after it, before 1.6.0.

## 6. The recipe and the workflow (Phase 3)

**`packaging/flatpak/publish.py`**, new, the publishing job's one command (Technical Architecture PRD 1.76, Section 10). It builds the whole site from nothing (decision 2): an empty OSTree repository at `site/repo`; the build's `stable` commit copied into it with `flatpak build-commit-from`, signed, under `stable` for a release or `rehearsal` for a run started by hand, with nothing else of the build (its debug extension stays behind); `flatpak build-update-repo` with the title, the comment, the homepage, the default branch, the signature, and static deltas, which also writes and signs the two AppStream branches; and the two reference files copied to the site's root. No pruning (silence 1). It imports nothing outside the standard library and the package's constants, so the job runs it with the runner's `python3`. It refuses any branch but the two, a build without the application, and a site directory that is not new.

**The two reference files**, from one template each, `snapmockit.flatpakref.in` and `snapmockit.flatpakrepo.in`, with the address `https://flatpak.snapmockit.com/repo/` and the public key filled in as one base64 line. `build.py` writes both beside the bundle, the release job attaches them to the GitHub release, and the publishing job copies the same files to the site, so the release and the site carry the same bytes. The `.flatpakref` names the application, the branch `stable`, and Flathub as the runtime's source; the `.flatpakrepo` names the default branch and no runtime source (correction 4.5). Neither sets `SuggestRemoteName`, so a `.flatpakref` installation's remote is `snapmockit-origin`, the same name a bundle installation's has, and the one-time move of correction 4.2 names one remote for both.

**`build.py`**: the bundle is built with `--repo-url=https://flatpak.snapmockit.com/repo/` and `--gpg-keys=packaging/flatpak/snapmockit-flatpak.gpg` (decision 5), and the build writes the two reference files. The build's own Flatpak repository was already left at `build/flatpak/repo`; the flatpak job now keeps it as the artifact `snapmockit-flatpak-repo`, one tar file, since it is 2,717 small files.

**`.github/workflows/ci.yml`**: the `flatpak` job keeps the bundle and the two reference files as `snapmockit-flatpak`, and the Flatpak repository as `snapmockit-flatpak-repo`; the `release` job attaches the two reference files; the new `publish-flatpak` job needs `flatpak` and `release`, runs on a release tag once the release exists, or on a run started by hand with the new input `rehearsal` set to `flatpak`, and names the `github-pages` environment, so it waits for Doug's approval either way (decision 4). It downloads both artifacts, imports the key from the `FLATPAK_GPG_PRIVATE_KEY` secret into a keyring under the runner's temporary directory and checks the fingerprint is there, runs `publish.py`, and deploys the site with `actions/upload-pages-artifact` and `actions/deploy-pages`. It builds nothing. **The input `rehearsal`** (`testpypi`, the default, or `flatpak`) also gates the test index's rehearsal job, which until now ran on every run started by hand and would otherwise have run on the Flatpak repository's rehearsal too.

**Proven on this machine, 09-28-26 00:16**, with a throwaway key, throwaway Flatpak installations under the scratchpad, and the last local build (1.5.0), all deleted afterwards and Doug's installation read back unchanged:

- `publish.py` built a site of 57 MB: the Flatpak repository with the application's commit and the two AppStream branches, a static delta for each, and the two reference files. The delta for a first installation roughly doubles the size, well inside GitHub Pages' limit.
- **Served over HTTP from this machine**, a `.flatpakref` pointing at it installed the application with the remote `snapmockit-origin`, `gpg-verify=true` and `gpg-verify-summary=true`, and `flatpak run … --version` answered `Snapmockit 1.5.0`.
- **A site signed by another key was refused**: with the installation's remote pointed at it, `flatpak update` found no application in it ("No such ref … in remote snapmockit-origin") and took nothing, since the summary's signature did not verify.
- ~~A bundle built by the new `bundle()`, installed fresh, created the remote with the address and signature checking on.~~ **Wrong, corrected 09-28-26:** the remote was created, and the installation then failed, which the test hid by discarding the install's output and never reading back what was installed. Continuous integration found it (decision 2.6). **Proven since, 08:03 to 08:07:** a bundle built by `publish.py` from the signed Flatpak repository installs fresh with signature checking on and holds the site's own commit, so `flatpak update` afterwards has nothing to do; the same check refuses a bundle signed by a key other than the one it carries ("GPG signatures found, but none are in trusted keyring"); and a rehearsal's bundle of the branch `rehearsal` is built and checked the same way.

**Tests**: eleven new in `tests/test_packaging_flatpak.py` (the bundle's address, key, and runtime source; the public key parsed as OpenPGP packets, holding no secret-key packet, a version 4 RSA 4096 key of the recorded fingerprint; both reference files' keys; the key embedded whole on one line; the commit and repository commands' options, no pruning, AppStream kept; the site always built from nothing; the two refusals); `tests/test_ci_workflow.py` gains the publishing job's trigger, gate, needs, downloads, key handling, and deployment, and follows the flatpak job's two artifacts, the release job's two new files, and the rehearsal input.

**After decision 2.6:** `publish.py` gains `bundle_command` (the one place the bundle's options are written; `build.py` calls it without the key) and `check_bundle`, and `--bundle`; the release job no longer attaches the Flatpak bundle; `publish-flatpak` gains `contents: write` and a last step, on a tag only, that attaches the signed bundle after the site is deployed. Three more tests: the build's bundle carries no key, the release's carries it and names the Flatpak repository, and the check installs into a throwaway Flatpak installation and refuses a commit that is not the site's.

**Still owed by Phase 3:** the rehearsal (silence 5), which needs Doug to start two runs and approve each, and which also settles the certificate of Section 5.

## 7. The next required step

The suite at this commit, then the push, then a green run of all jobs. Then the rehearsal: Doug starts a run by hand with `rehearsal` set to `flatpak`, approves its deployment, and a throwaway installation here installs from `https://flatpak.snapmockit.com/repo/` under the branch `rehearsal`; then a second run, and `flatpak update` in the same throwaway installation. Then the `main` rule and the manual trigger's `flatpak` option are removed, and Phase 4 begins.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 09-28-26 08:07 | Claude (Claude Code) | Decision 2.6 (A), after run 36377535497 failed: a bundle carrying the key installs only when its commit is signed, so the publishing job builds the release's bundle from the signed Flatpak repository, checks it by installing it, and attaches it after deploying; the release job attaches the AppImage and the reference files only. Section 6's claim that a fresh bundle installed was wrong and is struck through and corrected. Technical Architecture PRD 1.77. |
| 1.2 | 09-28-26 00:16 | Claude (Claude Code) | Phase 3 written and proven locally (Section 6): `publish.py` and the two reference-file templates, the bundle naming the Flatpak repository and carrying its key, the `publish-flatpak` job gated by `github-pages`, the rehearsal input, eleven recipe tests and the workflow tests. A site built here was installed from over HTTP with signatures checked, and one signed by another key was refused. Correction 4.5: a `.flatpakrepo` cannot name a runtime source. Technical Architecture PRD 1.76. |
| 1.1 | 09-28-26 00:05 | Claude (Claude Code) | Phase 2 done but the certificate (Section 5): the signing key generated (fingerprint DF8F 47BD 1CCF 5D53 5B7F 2986 BC56 3E79 934E 4F6C), its public half committed, its private half the repository secret and Doug's password-manager entry, the scratchpad copies shredded; GitHub Pages on with the custom domain `flatpak.snapmockit.com`, the GoDaddy CNAME resolving; the `github-pages` environment gated on Doug with the `v*.*.*` tag rule and a `main` rule for the rehearsal only. Technical Architecture PRD 1.75. |
| 1.0 | 09-27-26 23:38 | Claude (Claude Code) | Initial notes: the phase table; the five decisions as Doug approved them on 09-27-26 (1 B, 2 C, 3 A, 4 A, 5 A); the five silences, with the first version into the Flatpak repository set at 1.6.0 and the rehearsal on the live address under the branch `rehearsal`; and four corrections to the kickoff prompt, each proven in throwaway Flatpak installations: the server needs no history, the `.flatpakref` is refused over a bundle installation, a new bundle over an old one leaves signature checking off, and the sandbox cannot tell its origin. |
