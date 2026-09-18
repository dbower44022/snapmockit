#! /bin/sh
# The Flatpak's command (the manifest's `command: snapmockit`). The wheel installs no
# console script, so the module is the entry point, as AppRun does in the AppImage.
# Arguments are passed through: the files the desktop entry's %F names and --capture.
#
# Two variables the host sets reach the sandbox and name things that are not in it, so
# each start printed a line a user would read as an error (display run, finding 5):
# GTK_MODULES names the desktop's own GTK modules ("Failed to load module
# xapp-gtk3-module"), and SESSION_MANAGER names a socket the sandbox cannot open
# ("Qt: Session management error"). Neither is used: the application is Qt, and Qt's
# session management is not part of what it does.
unset GTK_MODULES
unset SESSION_MANAGER
exec python3 -m snapmock "$@"
