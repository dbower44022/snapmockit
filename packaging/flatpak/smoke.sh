#! /bin/bash
# The Flatpak's smoke test (Flatpak decision 2; docs/Packaging-Flatpak-Implementation.md):
# the bundle installs, the installed application answers --version with the version in the
# bundle's own name, and its Python builds the main window on the offscreen platform inside
# the sandbox. It leaves the machine as it found it.
#
#     bash packaging/flatpak/smoke.sh dist/Snapmockit-<version>-x86_64.flatpak
set -euo pipefail

bundle="${1:?usage: smoke.sh <bundle>}"
[ -f "$bundle" ] || { echo "no such file: $bundle" >&2; exit 1; }
app="io.github.dbower44022.snapmockit"
name="$(basename "$bundle")"
version="${name#Snapmockit-}"; version="${version%-x86_64.flatpak}"

was_installed="no"
flatpak info --user "$app" >/dev/null 2>&1 && was_installed="yes"

echo "== install"
# A bundle of a version already installed is refused, which is the development
# machine's ordinary state, so the installed copy goes first; its settings under
# ~/.var/app are left alone. Afterwards this bundle is the installed one.
if [ "$was_installed" = "yes" ]; then
  flatpak uninstall --user -y "$app" >/dev/null
fi
flatpak install --user -y --bundle "$bundle"

echo "== --version"
got="$(flatpak run "$app" --version)"
echo "$got"
[ "$got" = "Snapmockit $version" ] || { echo "expected 'Snapmockit $version'" >&2; exit 1; }

echo "== the sandbox builds the main window offscreen"
flatpak run --command=python3 --env=QT_QPA_PLATFORM=offscreen "$app" - <<'PY'
import sys
from PyQt6.QtCore import QT_VERSION_STR
from PyQt6.QtWidgets import QApplication
from snapmock import __version__
from snapmock.main_window import MainWindow
app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.processEvents()
print(f"window built: {window.windowTitle()!r}, snapmock {__version__}, Qt {QT_VERSION_STR}")
PY

if [ "$was_installed" = "no" ]; then
  echo "== uninstall"
  flatpak uninstall --user -y "$app"
fi
echo "== smoke test passed"
