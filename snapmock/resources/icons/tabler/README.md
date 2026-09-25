# Tabler Icons (vendored subset)

Source: https://github.com/tabler/tabler-icons, release v3.46.0, `icons/outline/`.
Licence: MIT, see `LICENSE` in this directory. Author: Paweł Kuna.

Only the glyphs SnapMock uses are copied here, verbatim. `snapmock/ui/icons.py`
names the glyph for each tool, menu action, and panel button, and
`snapmock/core/theme_manager.py` recolours each file for the active theme at
load time by replacing `currentColor` (General UI PRD Section 13.4).

To add a glyph: copy `icons/outline/<name>.svg` from the same release into this
directory and reference `<name>` from `snapmock/ui/icons.py`.

`vector-bezier-arc.svg` (the Arc tool) and `polygon.svg` (the Polygon tool) were added
on 09-11-26 by the Basic Shape remainder work from the `@tabler/icons` npm package of the
same release (`icons/outline/`), which carries the same paths without the repository's
leading comment block of tags.

`border-outer.svg` (the Border tool) was added on 09-21-26 by the Border tool work from the same release, verbatim.
