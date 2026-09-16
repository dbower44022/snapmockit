"""Keyboard shortcut definitions.

Each entry maps a logical action name to a key sequence string
compatible with ``QKeySequence``. ``ALTERNATE_SHORTCUTS`` lists extra
sequences bound to the same action (General UI PRD 3.2: Delete / Backspace).
The Keyboard Shortcuts dialog (Help menu) is built from these tables.
"""

from PyQt6.QtGui import QKeySequence

SHORTCUTS: dict[str, str] = {
    # File
    "file.new": "Ctrl+N",
    "file.open": "Ctrl+O",
    "file.save": "Ctrl+S",
    "file.save_as": "Ctrl+Shift+S",
    "file.export": "Ctrl+E",
    "file.import_image": "Ctrl+I",
    "file.export_quick_png": "Ctrl+Shift+E",
    "file.print": "Ctrl+P",
    "file.preferences": "Ctrl+,",
    "file.close_tab": "Ctrl+W",
    "file.quit": "Ctrl+Q",
    # Edit
    "edit.undo": "Ctrl+Z",
    "edit.redo": "Ctrl+Shift+Z",
    "edit.cut": "Ctrl+X",
    "edit.copy": "Ctrl+C",
    "edit.paste": "Ctrl+V",
    "edit.duplicate": "Ctrl+D",
    "edit.delete": "Delete",
    "edit.select_all": "Ctrl+A",
    "edit.select_all_layers": "Ctrl+Shift+A",
    "edit.deselect": "Escape",
    "edit.select_all_text": "Ctrl+T",
    # View
    "view.zoom_in": "Ctrl+=",
    "view.zoom_out": "Ctrl+-",
    "view.fit_window": "Ctrl+0",
    "view.actual_size": "Ctrl+1",
    "view.toggle_grid": "Ctrl+'",
    "view.toggle_rulers": "Ctrl+R",
    "view.toggle_guides": "Ctrl+;",
    "view.zoom_to_selection": "Ctrl+Shift+0",
    "view.snap_to_grid": "Ctrl+Shift+'",
    "view.next_tab": "Ctrl+Tab",
    "view.previous_tab": "Ctrl+Shift+Tab",
    # Image
    "image.crop_to_canvas": "Ctrl+Shift+C",
    # Layers
    "layer.new": "Ctrl+Shift+N",
    "layer.delete": "Ctrl+Shift+Delete",
    "layer.merge_down": "Ctrl+Shift+M",
    "layer.flatten": "Ctrl+Shift+F",
    "layer.rename": "F2",
    "layer.move_up": "Ctrl+]",
    "layer.move_down": "Ctrl+[",
    "layer.move_to_top": "Ctrl+Shift+]",
    "layer.move_to_bottom": "Ctrl+Shift+[",
    # Arrange
    "arrange.bring_to_front": "Ctrl+Shift+Up",
    "arrange.bring_forward": "Ctrl+Up",
    "arrange.send_backward": "Ctrl+Down",
    "arrange.send_to_back": "Ctrl+Shift+Down",
    "arrange.group": "Ctrl+G",
    "arrange.ungroup": "Ctrl+Shift+G",
    # Tools
    "tool.select": "V",
    "tool.rectangle": "R",
    "tool.ellipse": "E",
    "tool.line": "L",
    "tool.arrow": "A",
    "tool.arc": "Shift+A",
    "tool.polygon": "G",
    "tool.freehand": "P",
    "tool.text": "T",
    "tool.callout": "C",
    "tool.highlight": "H",
    "tool.blur": "B",
    "tool.numbered_step": "N",
    "tool.stamp": "S",
    "tool.emoji": "Shift+E",
    "tool.crop": "X",
    "tool.raster_select": "M",
    "tool.eyedropper": "I",
    "tool.pan": "",
    "tool.zoom": "Z",
    "tool.lasso_select": "Shift+M",
    # Library
    "library.toggle_panel": "Ctrl+L",
    # Capture (defaults; the live values follow the hotkey preferences)
    "capture.region": "Print",
    "capture.window": "Alt+Print",
    "capture.full_screen": "Ctrl+Print",
    "capture.preferences": "",
    # Additional edit shortcuts
    "edit.paste_in_place": "Ctrl+Shift+V",
}

ALTERNATE_SHORTCUTS: dict[str, list[str]] = {
    "edit.delete": ["Backspace"],
    # Ctrl+Y beside Ctrl+Shift+Z, the key most applications use (end-to-end pass finding 7)
    "edit.redo": ["Ctrl+Y"],
    # General UI PRD 3.3 binds Zoom In to Ctrl++; Ctrl+= is the same key without Shift.
    "view.zoom_in": ["Ctrl++"],
}


def key_sequences(action: str) -> list[QKeySequence]:
    """Every key sequence bound to *action*: the primary one plus any alternates."""
    seqs = [SHORTCUTS[action]] + ALTERNATE_SHORTCUTS.get(action, [])
    return [QKeySequence(text) for text in seqs if text]
