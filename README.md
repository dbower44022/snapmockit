# Snapmockit

Snapmockit is an open-source screenshot annotation and user interface mockup tool for Linux, Windows, and macOS, written in Python with PyQt6. Capture a screen, a window, or a region; annotate it with shapes, arrows, text, callouts, highlights, blur, numbered steps, stamps, and emoji on layers; then export it as PNG, JPEG, SVG, or PDF, or save it as a project to come back to. It reads and writes Snagit's `.snagx` files.

Status: the application is complete against its nine product requirements documents (the `PRDs/` directory). Its first release, 0.9.0, is the Linux AppImage (below); it also runs from source; the Windows and macOS capture backends are written but wait for machines to test them on.

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

## The Linux AppImage

The first packaged form is a Linux AppImage, `Snapmockit-<version>-x86_64.AppImage`, one file that carries its own Python and Qt. Download it from the latest release at https://github.com/dbower44022/snapmockit/releases, or build it from the repository with one command:

```bash
uv sync --group packaging
uv run --group packaging python packaging/appimage/build.py
```

A build lands under `dist/`. Make the file executable and run it, or double-click it in a file manager:

```bash
chmod +x dist/Snapmockit-*.AppImage
dist/Snapmockit-*.AppImage
dist/Snapmockit-*.AppImage --version
dist/Snapmockit-*.AppImage --capture full
```

It needs glibc 2.34 or later (Ubuntu 22.04, Debian 12, Fedora 35, RHEL 9, and later) and these libraries from the system, which every desktop installation has and a bare server may not: on Debian and Ubuntu, `libegl1 libgl1 libglib2.0-0 libdbus-1-3 libfontconfig1 libfreetype6 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xkb1 libxcb-render-util0 libxcb-image0 libx11-6 libxfixes3`, plus `libwayland-client0` and `xdg-desktop-portal` with a backend for your desktop under Wayland. Fonts, the colour emoji font included, come from the system. Settings live under `~/.config/Snapmockit`, presets and themes under `~/.config/snapmockit`, and the library at `~/Snapmockit/Library` unless you moved it; a first start moves what earlier builds kept under the SnapMock name and says so once. Help > Check for Updates reads the latest release.

### Putting the AppImage in the menu

The file carries its menu entry and icon but does not install them yet. To have Snapmockit in the desktop's main menu, copy the file to a fixed name, take the icons out of it, and write an entry that points at the copy; nothing needs a password:

```bash
mkdir -p ~/Applications ~/.local/share/applications ~/.local/share/icons/hicolor/256x256/apps ~/.local/share/icons/hicolor/scalable/apps
cp Snapmockit-*.AppImage ~/Applications/Snapmockit.AppImage
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

The entry appears at once; if its icon does not, the running desktop has not rescanned its icon folders yet, and a restart of the desktop shell (Ctrl+Alt+Esc on Cinnamon under X11) or a fresh login shows it. A later release replaces the copy at `~/Applications/Snapmockit.AppImage` and the entry stays. To remove it, delete the entry file, the two icon files, and the copy.

## Developing

```bash
uv run pytest            # the test suite, about 1 hour 40 minutes; QT_QPA_PLATFORM=offscreen for a headless run
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy snapmock     # type check, strict
```

The product requirements documents under `PRDs/` are the single source of truth for behaviour; `docs/` holds the implementation notes and kickoff prompts each piece of work was built from; `CLAUDE.md` holds the working conventions.

## Reporting a problem

Open an issue at https://github.com/dbower44022/snapmockit/issues. Help > About > Copy Version Info in the application puts the version, the build date, and the platform on the clipboard for the report.

## Licence

MIT. Copyright (c) 2026 Doug Bower. Icons are [Tabler Icons](https://tabler.io/icons) by Paweł Kuna, MIT.
