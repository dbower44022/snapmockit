# The Flatpak Repository — Implementation Notes

Last Updated: 09-27-26 23:38 · Revision 1.0

A signed Flatpak repository of the project's own, so a Snapmockit user on Linux gets each release through `flatpak update` and through the desktop's own updater instead of downloading a bundle and installing it by hand. It replaces Flatpak decision 2 (`docs/Packaging-Flatpak-Implementation.md`, Section 2.2, option A: a bundle on the GitHub release). The kickoff prompt is `docs/Flatpak-Repository-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | The five decisions, the silences, the corrections to the kickoff prompt, and this document | Done 09-27-26 (Sections 2 to 4) | this commit |
| 2 | The signing key and the address, done with Doug: the key generated, its public half committed, its private half a repository secret and an offline copy; GitHub Pages on, the DNS record at GoDaddy, HTTPS enforced; the `github-pages` environment's gate | Not started | |
| 3 | The recipe and the workflow: the Flatpak repository built and signed, the bundle naming its address, the `.flatpakref` and `.flatpakrepo` files, the publishing job, the tests, the Technical Architecture PRD rows; the rehearsal on the live address (silence 5) | Not started | |
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

## 3. Silences decided

1. **How many old versions the Flatpak repository keeps: one**, settled by decision 2. The pruning options are not used. `--generate-static-deltas` is kept, since a delta from nothing still speeds a first installation.
2. **The AppStream data: the metainfo keeps its one release row**, filled with the version and the build date at build time as it is today. The Flatpak repository is rebuilt on every release, so its `appstream` branch only ever needs the current version; the release notes stay the annotated tag's message on the release page, since a second copy in the metainfo would drift from it. Revisited if the Update Manager shows an empty release-notes field Doug wants filled.
3. **The runtime comes from Flathub.** The `.flatpakref` and `.flatpakrepo` name `https://dl.flathub.org/repo/flathub.flatpakrepo` as `RuntimeRepo`, the same runtime source the bundle names today. Nothing of Snapmockit goes to Flathub.
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

## 5. The next required step

Phase 2 with Doug: the key's email address, then the key generated and its private half set as a repository secret; GitHub Pages turned on with the GitHub Actions source; the CNAME record at GoDaddy; HTTPS enforced; the `github-pages` environment's reviewer and tag rule. Each is asked of Doug at the moment it happens.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-27-26 23:38 | Claude (Claude Code) | Initial notes: the phase table; the five decisions as Doug approved them on 09-27-26 (1 B, 2 C, 3 A, 4 A, 5 A); the five silences, with the first version into the Flatpak repository set at 1.6.0 and the rehearsal on the live address under the branch `rehearsal`; and four corrections to the kickoff prompt, each proven in throwaway Flatpak installations: the server needs no history, the `.flatpakref` is refused over a bundle installation, a new bundle over an old one leaves signature checking off, and the sandbox cannot tell its origin. |
