#! /bin/sh
# The Flatpak's command (the manifest's `command: snapmockit`). The wheel installs no
# console script, so the module is the entry point, as AppRun does in the AppImage.
# Arguments are passed through: the files the desktop entry's %F names and --capture.
exec python3 -m snapmock "$@"
