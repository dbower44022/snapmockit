#! /bin/bash
# The AppImage's smoke test (packaging decision 2; docs/Packaging-AppImage-Implementation.md,
# Section 9): the file answers --version with the version in its name, and its bundled
# Python builds the main window on the offscreen platform. Runs without FUSE, so it runs
# on a continuous-integration runner and here alike:
#
#     bash packaging/appimage/smoke.sh dist/Snapmockit-<version>-x86_64.AppImage
set -euo pipefail

app="${1:?usage: smoke.sh <AppImage>}"
[ -f "$app" ] || { echo "no such file: $app" >&2; exit 1; }
chmod +x "$app"
name="$(basename "$app")"
version="${name#Snapmockit-}"; version="${version%-x86_64.AppImage}"

echo "== --version"
got="$("$app" --appimage-extract-and-run --version)"
echo "$got"
[ "$got" = "Snapmockit $version" ] || { echo "expected 'Snapmockit $version'" >&2; exit 1; }

echo "== the bundled Python builds the main window offscreen"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
( cd "$work" && "$OLDPWD/$app" --appimage-extract >/dev/null )
appdir="$work/squashfs-root"
[ -x "$appdir/AppRun" ] || { echo "no AppRun in the extracted image" >&2; exit 1; }
[ -f "$appdir/usr/share/metainfo/io.github.dbower44022.snapmockit.appdata.xml" ] || { echo "no metainfo" >&2; exit 1; }
[ -f "$appdir/usr/share/mime/packages/io.github.dbower44022.snapmockit.xml" ] || { echo "no MIME file" >&2; exit 1; }
[ -f "$appdir/usr/share/icons/hicolor/256x256/apps/io.github.dbower44022.snapmockit.png" ] || { echo "no 256 px icon" >&2; exit 1; }
QT_QPA_PLATFORM=offscreen APPDIR="$appdir" "$appdir/usr/bin/python3.12" -I - <<'PY'
import sys
from PyQt6.QtWidgets import QApplication
from snapmock import __version__
from snapmock.main_window import MainWindow
app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.processEvents()
print(f"window built: {window.windowTitle()!r}, snapmock {__version__}")
PY
echo "== smoke test passed"
