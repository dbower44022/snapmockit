# Snapmockit

Snapmockit is an open-source screenshot annotation and user interface mockup tool for Linux, Windows, and macOS, written in Python with PyQt6. Capture a screen, a window, or a region; annotate it with shapes, arrows, text, callouts, highlights, blur, numbered steps, stamps, and emoji on layers; then export it as PNG, JPEG, SVG, or PDF, or save it as a project to come back to. It reads and writes Snagit's `.snagx` files.

Status: the application is complete against its nine product requirements documents (the `PRDs/` directory). Release 1.3.0 installs from the Python Package Index on any platform with Python 3.12 or later, and on Linux also ships as an AppImage and a Flatpak bundle; on Linux it puts itself in the desktop's main menu from Help > Add to Menu. The Windows and macOS capture backends are written but have not yet been tested on those machines.

## Install from the Python Package Index (any platform)

With Python 3.12 or later, install Snapmockit as an application of its own with [pipx](https://pipx.pypa.io/) or [uv](https://docs.astral.sh/uv/):

```bash
pipx install snapmockit
```

```bash
uv tool install snapmockit
```

Either puts a `snapmockit` command on your path; start the application with it. `snapmockit --version` prints the version, and `snapmockit --capture full` takes a capture straight away and opens it. `pip install snapmockit` into a virtual environment works too.

To upgrade, use the tool you installed with: `pipx upgrade snapmockit`, `uv tool upgrade snapmockit`, or `pip install --upgrade snapmockit`. Help > Check for Updates names the right one when a new release is out.

On Linux, Qt needs the same system libraries the AppImage lists below, which every desktop installation has. The package installs no menu entry or icon of its own; **Help > Add to Menu** in the application puts Snapmockit in the desktop's main menu, as described under "Putting it in the menu" below. Windows and macOS installations run, but the screen capture backends for both are untested.

## Install on Linux

Snapmockit ships in two forms on Linux, both for x86_64: an **AppImage**, one file that carries its own Python and Qt, and a **Flatpak**, a 26 MB bundle that runs on the KDE runtime and in a sandbox. Neither needs a package manager or a password. The AppImage runs anywhere with glibc 2.34 or later (Ubuntu 22.04, Debian 12, Fedora 35, RHEL 9, and later); the Flatpak runs anywhere Flatpak does.

### The AppImage

1. Download `Snapmockit-<version>-x86_64.AppImage` from the latest release at https://github.com/dbower44022/snapmockit/releases.
2. Make it executable and run it. From a file manager, right-click the file, allow it to run as a program under Properties, and double-click it. From a terminal, with the file in your Downloads folder:

```bash
chmod +x ~/Downloads/Snapmockit-*.AppImage
~/Downloads/Snapmockit-*.AppImage
```

`--version` prints the version, `--capture full` takes a capture straight away and opens it, and a project file named on the command line opens. Help > Check for Updates in the application reads the latest release.

The file needs these libraries from the system, which every desktop installation has and a bare server may not: on Debian and Ubuntu, `libegl1 libgl1 libglib2.0-0 libdbus-1-3 libfontconfig1 libfreetype6 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xkb1 libxcb-render-util0 libxcb-image0 libx11-6 libxfixes3`, plus `libwayland-client0` and `xdg-desktop-portal` with a backend for your desktop under Wayland. Fonts, the colour emoji font included, come from the system. Settings live under `~/.config/Snapmockit`, presets and themes under `~/.config/snapmockit`, and the library at `~/Snapmockit/Library` unless you moved it; a first start moves what earlier builds kept under the SnapMock name and says so once.

### Putting it in the menu

**Help > Add to Menu**, in the application, writes the desktop entry, the icon set, and the `.smk` file type under `~/.local/share`, so Snapmockit starts from the desktop's main menu and a project file opens on a double-click. The same row then reads **Remove from Menu** and takes away exactly what it wrote. Nothing outside your own home directory is touched and nothing asks for a password. It works from the AppImage and from an installation from the Python Package Index; the Flatpak installs its own entry with the package, so its row says so and writes nothing.

The AppImage is asked one question first: whether to copy itself to `~/Applications/Snapmockit.AppImage` and point the entry at the copy, which is the default, or to point the entry at the file where it sits. The copy costs 122 MB and means the entry survives a tidy-up of the Downloads folder; a later release replaces that one file and the entry stays. Removing the entry offers to delete the copy as well, and never deletes the file you are running.

If the entry appears but its icon does not, the running desktop has not rescanned its icon folders yet: a restart of the desktop shell (Ctrl+Alt+Esc on Cinnamon under X11) or a fresh login shows it.

With the Flatpak installed and Snapmockit also added to the menu from another form, some desktops — Cinnamon among them — list two entries, one of them marked as the Flatpak's, although the desktop entry specification makes two files of one application id a single entry. Add to Menu says so when it finds another form's entry.

#### By hand

The same thing without the application, if you would rather do it yourself. Copy the AppImage to a fixed name, take the icons out of it, and write an entry that points at the copy:

```bash
mkdir -p ~/Applications ~/.local/share/applications ~/.local/share/icons/hicolor/256x256/apps ~/.local/share/icons/hicolor/scalable/apps
cp ~/Downloads/Snapmockit-*.AppImage ~/Applications/Snapmockit.AppImage
(cd /tmp && ~/Applications/Snapmockit.AppImage --appimage-extract 'usr/share/icons/hicolor/*/apps/*')
cp /tmp/squashfs-root/usr/share/icons/hicolor/256x256/apps/io.github.dbower44022.snapmockit.png ~/.local/share/icons/hicolor/256x256/apps/
cp /tmp/squashfs-root/usr/share/icons/hicolor/scalable/apps/io.github.dbower44022.snapmockit.svg ~/.local/share/icons/hicolor/scalable/apps/
rm -rf /tmp/squashfs-root
cat > ~/.local/share/applications/io.github.dbower44022.snapmockit.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Snapmockit
GenericName=Screenshot Annotation Tool
Comment=Capture, annotate, and mock up screenshots
Exec=$HOME/Applications/Snapmockit.AppImage %F
Icon=io.github.dbower44022.snapmockit
Terminal=false
Categories=Graphics;Utility;
MimeType=application/x-snapmockit-project;
Keywords=screenshot;capture;annotate;mockup;
StartupNotify=true
StartupWMClass=Snapmockit
EOF
update-desktop-database ~/.local/share/applications
```

This writes two of the icon sizes; Add to Menu writes eight and the scalable file, and registers the `.smk` file type as well, which the recipe above does not. To undo it, delete the entry file, the two icon files, and the copy.

### The Flatpak

```bash
cd ~/Downloads
flatpak install --user Snapmockit-<version>-x86_64.flatpak
flatpak run io.github.dbower44022.snapmockit
```

Download the bundle from the same release page. The first install offers to fetch the KDE runtime 6.11 from Flathub, which is most of what the application needs; the bundle itself is 26 MB because Qt is shared with every other KDE application on the machine. The desktop entry and the icon are installed with it, so Snapmockit is in the main menu at once, and `flatpak run io.github.dbower44022.snapmockit --capture full` is the command to bind to a key.

The sandbox reaches your whole home directory, the display, the graphics device, and the network, and nothing else. Its settings live under `~/.var/app/io.github.dbower44022.snapmockit/`, copied once from `~/.config/Snapmockit` on the first start if you have been running another form; the library is the same `~/Snapmockit/Library` both forms use. A bundle installed by hand does not update itself: a new version is a new download. Both forms can be installed at once. They carry one application id, which by the desktop entry specification makes them one menu entry; Cinnamon lists a Flatpak's own entry separately, so a machine with the Flatpak installed and Snapmockit added to the menu from another form shows two entries, one of them marked as the Flatpak's. Add to Menu says so when it finds another form's entry.

### Other forms

Windows and macOS have no package of their own yet; install from the Python Package Index (above) or run from source. The capture backends for both are written but untested. The Flatpak is published as the bundle above and not on Flathub.

## Running from source

Requirements: Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/dbower44022/snapmockit.git
cd snapmockit
uv sync
uv run python -m snapmock
```

To take a capture straight from the command line and open it in the application:

```bash
uv run python -m snapmock --capture full
```

## Building the packages

The release job builds both Linux forms from a clean runner on every tag, and both recipes run from a checkout with one command each, landing under `dist/`.

The AppImage:

```bash
uv sync --group packaging
uv run --group packaging python packaging/appimage/build.py
```

The Flatpak, which needs `flatpak-builder` (or Flathub's `org.flatpak.Builder`), the KDE runtime 6.11 with its SDK, the PyQt base application 6.11, and an SVG loader on the machine that builds:

```bash
flatpak install flathub org.kde.Platform//6.11 org.kde.Sdk//6.11 \
  com.riverbankcomputing.PyQt.BaseApp//6.11
uv run python packaging/flatpak/build.py
```

`packaging/flatpak/build.py --update-deps` regenerates the dependency module from `uv.lock` when a dependency changes.

## Developing

```bash
uv run pytest            # the test suite, about 6 minutes; QT_QPA_PLATFORM=offscreen for a headless run
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy snapmock     # type check, strict
```

The product requirements documents under `PRDs/` are the single source of truth for behaviour; `docs/` holds the implementation notes and kickoff prompts each piece of work was built from; `CLAUDE.md` holds the working conventions.

## Reporting a problem

Open an issue at https://github.com/dbower44022/snapmockit/issues. Help > About > Copy Version Info in the application puts the version, the build date, and the platform on the clipboard for the report.

## Licence

MIT. Copyright (c) 2026 Doug Bower. Icons are [Tabler Icons](https://tabler.io/icons) by Paweł Kuna, MIT.
