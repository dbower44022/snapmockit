#! /bin/bash
# The AppImage's entry point: python-appimage substitutes the bundled interpreter and
# writes this into AppRun. -I isolates the bundled Python from the user's PYTHONPATH
# and user site-packages; QT_QPA_PLATFORM is not set, so Qt chooses xcb or wayland.
exec "{{ python-executable }}" -I -m snapmock "$@"
