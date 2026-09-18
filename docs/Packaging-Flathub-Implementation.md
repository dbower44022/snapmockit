# Packaging: the Flathub Submission — Implementation Notes

Last Updated: 09-18-26 10:22 · Revision 1.0

**Closed at Phase 1, not submitted.** On 09-18-26 at 10:20 Doug decided that Snapmockit will not be submitted to Flathub, and that the Python Package Index comes next. This document records why, what Flathub requires as of that date, and what reopening the work would take. The kickoff prompt was `docs/Packaging-Flathub-Kickoff-Prompt.md` (revision 1.0). Operating mode: DETAIL.

## 1. Phases

| Phase | Scope | Status | Commits |
|---|---|---|---|
| 1 | What Flathub requires, and the decisions | Done 09-18-26: the requirements checked (Section 4), one decision the kickoff prompt did not foresee (Section 2), and the work closed by it | this commit |
| 2 | The metainfo and the screenshots | Not started: closed by decision 2.1 | |
| 3 | The Flathub manifest | Not started: closed by decision 2.1 | |
| 4 | The submission | Not started: closed by decision 2.1 | |
| Close-out | The update path, the README, the release-engineering notes | Done 09-18-26, reduced to recording the decision (Section 5) | this commit |

## 2. Decisions

### 2.1 Whether to submit at all: option C, no Flathub submission; the Python Package Index next

**Presented 09-18-26 at 10:18 with the consequential decision template; Doug chose option C at 10:20.** The recommendation was option B, and it was not taken.

**What forced the question.** Flathub's current documentation, which the kickoff prompt says wins over the prompt, carries two rules the prompt did not know of:

- **The Generative AI policy** (requirements page): submitters must disclose AI-generated code, documentation, packaging, and other material, naming the parts and the approximate extent. "AI tools or agents must not open or automate Flathub submission pull requests, or generate their commit messages, descriptions, review comments, or replies." Reviewers "may reject a submission, including without further review, based on the extent or role of generated material". The submission page adds that pull requests that "contain excessive AI-generated content may be closed without a review".
- **The exception policy** (linter page): exceptions "that enable breaking out of the Flatpak sandbox including but not limited to home, host, flatpak-spawn, arbitrary bus name access will not be granted if there are signs of LLM usage in the software or in the exception PR", and large language models must not be used for exception requests at all.

**This repository:** 394 of its 422 commits carry a Claude co-author line (counted at 03d4db8).

**The options as presented:**

- **A.** Submit with full disclosure. The session would build the metainfo, the screenshots, and the manifest here, disclosed as AI-generated. Doug would fork, push, open the pull request, and answer reviewers in his own words. The home-directory permission would be dropped for Flathub.
- **B (recommended).** Ask Flathub first. Doug would post one question on Flathub's forum or Matrix room, in his own words, while the session did only Phase 2.
- **C (taken).** Stop the Flathub work and move to the Python Package Index. The bundle on the GitHub release stays the Flatpak route.

**The cost of what was taken:** a Flatpak user updates by downloading the next bundle, as Flatpak decision 2 already says, and never through `flatpak update`. Check for Updates keeps its bundle wording (General UI PRD 3.8, row 2.50). The metainfo keeps no screenshots and one release row, which only a software centre reading the AppImage's metainfo would show.

### 2.2 The kickoff's five decisions

None was presented or taken: decision 2.1 closed the work before them. Section 3 records what Flathub's documentation says about each, so that a later session does not have to find it again.

## 3. Corrections to the kickoff prompt

Recorded as the prompt asks where the documentation and the prompt disagree. They apply only if the work is reopened.

1. **Phase 4 cannot be done by an assistant.** The prompt has the session push the fork, open the pull request, ask for `bot, build`, and answer every reviewer comment. Flathub's policy forbids an AI tool to do any of these, or to write their text. Doug would do each of them himself, in his own words.
2. **Decision 2, the sandbox, has one viable option on Flathub.** `--filesystem=home` needs an exception that the linter page says will not be granted where the software shows signs of large language model use. The Flathub manifest would carry the narrower set (for example `xdg-pictures`, `xdg-documents`, `xdg-desktop`, and `~/Snapmockit:create`) and reach every other file through the file chooser portal. Whether a file opened through the portal keeps a path that recent files and session restore can use after a restart is inferred to be likely, not checked. The GitHub bundle would keep the whole home directory.
3. **Decision 3, where the manifest lives:** a copy into the Flathub repository is a commit whose message an assistant may not write, so every copy is Doug's own act.
4. **Decision 4, the screenshots:** Flathub asks for links "from a tag or a commit and not a branch". The `v1.1.0` tag holds no screenshots, so the link would name the commit that adds them. The metainfo must be integrated upstream and must validate, so the build Flathub makes needs a tag later than `v1.1.0` whose metainfo is a finished file, not the `@VERSION@` template.
5. **Decision 1, the dependencies:** the rule is "built entirely from source code", with exceptions "to well-known vendors". Practice, read from the Flathub organisation's repositories on 09-18-26, is mixed: applications already on Flathub list prebuilt manylinux numpy wheels (for example `se.sjoerd.GIScan` and `org.cloudcompare.CloudCompare`), and others build numpy from its source archive (for example `org.inkscape.Inkscape`, `org.freecad.FreeCAD`, and `org.pitivi.Pitivi`). A source build remains the course that invites no question.

## 4. What Flathub requires, checked against the repository (Phase 1 step 1)

Read from docs.flathub.org (the requirements, submission, MetaInfo guidelines, and linter pages) on 09-18-26 at about 10:15, and checked against the repository at 03d4db8.

| Requirement | State in this repository | What it would take |
|---|---|---|
| Generative AI policy: disclose, and no assistant opens or answers the pull request | Largely AI-written (Section 2.1) | Full disclosure, and every Flathub-facing act done by Doug; acceptance at the reviewers' discretion |
| Application id: reverse domain name, `io.github.` for a GitHub project, at least four components, matching the repository | Met: `io.github.dbower44022.snapmockit` against `github.com/dbower44022/snapmockit` | Nothing |
| Development history: "a meaningful history", tagged releases, not a very short existence | Commits since 02-27-26; three tagged releases, `v0.9.0` to `v1.1.0`, within four days in September 2026 | At the reviewers' discretion |
| Sources: publicly reachable addresses with checksums; no local directory; no binaries in the pull request | Not met: the application module reads the staging directory `../../build/flatpak/stage` (linter error `module-snapmockit-source-dir-not-allowed`) | The application built from a git tag with its commit, with hatchling and its build dependencies as modules |
| Built entirely from source, the runtime dependencies included | Not met: numpy, Pillow, and psutil are prebuilt manylinux wheels; send2trash is a pure-Python wheel | numpy, Pillow, and psutil from their source archives inside the KDE SDK (Section 3, item 5) |
| Manifest at the top level of the submission, named for the id; YAML style of two-space indentation and a logical key order | The manifest is named for the id; its key order departs from the guide's (`branch` before `runtime`, `base` before `command`) | A Flathub copy without `branch: stable` (linter error `toplevel-unnecessary-branch`), in the guide's key order |
| Runtime hosted on Flathub and the latest at submission | `org.kde.Platform` 6.11 with `com.riverbankcomputing.PyQt.BaseApp` 6.11, the newest branch of each on 09-17-26 | Checked again at submission |
| Architectures: x86_64 and aarch64 by default, or a `flathub.json` naming one | The recipe and the wheels are x86_64 only | A `flathub.json`, or an aarch64 build proven |
| Permissions: static permissions at an absolute minimum, a portal where one fits | `--filesystem=home` (linter error `finish-args-home-filesystem-access`); the other five permissions are ordinary for a graphical application with network use | Section 3, item 2 |
| Licence: redistributable, declared in the metainfo, matching the source; licence files installed under `share/licenses/<id>` for each module | MIT, declared as `project_license` and in `LICENSE`; no licence file is installed by the manifest | `license-files` or an install command for the application and each dependency module |
| Metainfo: `share/metainfo/<id>.metainfo.xml`, integrated upstream, validated with warnings fatal | Installed under that name by the Flatpak recipe; filled from a template at build time; not validated strictly | A finished file in the repository, `flatpak-builder-lint appstream` clean |
| Metainfo: one or more screenshots, from a tag or commit address | None | Screenshots in the repository and captions (Section 3, item 4) |
| Metainfo: a release history, dates not in the future, versions ordered | One row, filled with the version being built | Rows for 0.9.0, 1.0.0, and 1.1.0 at least, with dates and notes |
| Metainfo: a `developer` tag with a reverse-domain id and one name | Met: `io.github.dbower44022`, Doug Bower | Nothing |
| Metainfo: `branding` colours for light and dark; OARS content rating | No branding; `<content_rating type="oars-1.1"/>` present | Two colours; the rating confirmed as empty, which is right for an application with no user-generated or violent content |
| Metainfo: `url type="homepage"`, and `vcs-browser` recommended | Homepage and bug tracker present | A `vcs-browser` link |
| Desktop file and icon: a desktop file, and an SVG or a 256 pixel PNG icon | Met: `io.github.dbower44022.snapmockit.desktop`, the scalable icon, and eight PNG sizes | Nothing |
| English localisation | Met: the interface is English only | Nothing |
| Name and icon distinct, no trademark | Snapmockit and its own icon; the description names Snagit only as a file format read and written | Reviewers' reading of the Snagit mention |

## 5. Close-out

**Done, reduced to recording the decision.** No file under `packaging/`, no code, no metainfo, and no test changed. Nothing left this machine except reads of Flathub's public pages and repositories.

**What changed with it:** `docs/Release-Engineering.md` Sections 1 and 4 (the Flathub submission removed from what is left, the Python Package Index next); the README's "Other forms" paragraph; Technical Architecture PRD 1.66, which records that 7.3's Flatpak is published as the bundle on the GitHub release and not on Flathub; and the kickoff prompt's change log, which marks it closed.

**What of Technical Architecture PRD 7.3 remains:** the Python Package Index, the Windows installer and portable archive, and the macOS bundle. **Out of scope and still open:** the menu entry the AppImage does not install (end-to-end pass finding 1), and the Windows and macOS capture backends. **A Flatpak user's update path** is the one Flatpak decision 2 set: the next bundle downloaded from the release page and installed with `flatpak install`, which Check for Updates says.

**Reopening the work** would start from option B of decision 2.1: a question to Flathub in Doug's own words, then Section 3's corrections and Section 4's table.

**The display checks this work owes:** none.

**The next required step** is the Python Package Index; its kickoff prompt is `docs/Packaging-PyPI-Kickoff-Prompt.md`.

## Change Log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 09-18-26 10:22 | Claude (Claude Code) | Initial notes, written at the close of the work: the requirements pass of Phase 1 step 1 against Flathub's documentation of 09-18-26; decision 2.1 (no Flathub submission, option C, Doug's choice at 10:20, against the recommendation of B) forced by Flathub's Generative AI policy and its exception policy; five corrections to the kickoff prompt for a later reopening; the close-out. |
