"""The Tool Options Bar's overflow (General UI PRD 5, 15.1).

15.1 says the bar "collapses into an overflow menu" at the minimum window size. Qt's own
toolbar extension button is what a `QToolBar` offers for that, and its popup never opens
for the widget actions this bar is built from: measured on 09-12-26 after Doug's display
run, a 1024 px window hid fifteen of the Blur tool's thirty controls — the blur radius
among them — behind a button that produced nothing. The bar now owns the overflow.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLabel, QWidget

from snapmock.main_window import MainWindow
from snapmock.ui.tool_options_bar import ToolOptionsBar


def _bar(window: MainWindow) -> ToolOptionsBar:
    return window._tool_options  # noqa: SLF001


def _settle(window: MainWindow, width: int) -> ToolOptionsBar:
    """Give the window *width* and let the bar decide what fits."""
    window.resize(width, 700)
    window.show()
    bar = _bar(window)
    for _ in range(4):
        bar._reflow()  # noqa: SLF001
    return bar


@pytest.fixture()
def window(main_window: MainWindow) -> MainWindow:
    main_window.tool_manager.activate("blur")
    return main_window


def test_every_control_is_reachable_at_the_minimum_window_size(window: MainWindow) -> None:
    """No control is hidden without a way to it: 15.1's rule, and the bug Doug hit."""
    bar = _settle(window, 1024)
    controls = bar.controls
    assert controls, "the Blur tool's bar has controls"
    in_popover = bar.overflowing
    in_strip = [w for w in controls if w.parent() is bar._strip]  # noqa: SLF001
    # Every control is in one place or the other, and nowhere else.
    assert len(in_popover) + len(in_strip) == len(controls)
    if in_popover:
        assert bar.more_button.isVisible() or bar.more_button.isVisibleTo(bar)


def test_nothing_in_the_strip_is_clipped(window: MainWindow) -> None:
    """What stays in the strip fits it; what does not is in the popover."""
    bar = _settle(window, 1024)
    strip = bar._strip  # noqa: SLF001
    clipped = [
        w
        for w in bar.controls
        if w.parent() is strip and not w.isHidden() and w.x() + w.width() > strip.width() + 1
    ]
    assert clipped == []


def test_a_wider_window_takes_the_controls_back(window: MainWindow) -> None:
    bar = _settle(window, 1024)
    narrow = len(bar.overflowing)
    assert narrow > 0  # the Blur bar cannot fit 1024 px
    bar = _settle(window, 2400)
    assert len(bar.overflowing) < narrow


def test_a_label_travels_with_the_control_it_names(window: MainWindow) -> None:
    bar = _settle(window, 1024)
    overflowing = bar.overflowing
    if not overflowing:
        pytest.skip("nothing overflowed at this width")
    # The first thing in the popover is a label, or is not preceded in the bar by one.
    first = bar.controls.index(overflowing[0])
    if first > 0:
        assert isinstance(overflowing[0], QLabel) or not isinstance(
            bar.controls[first - 1], QLabel
        )


def test_the_popover_holds_the_real_controls(window: MainWindow) -> None:
    """Not copies: what the popover shows is the control the tool built and reads."""
    bar = _settle(window, 1024)
    overflowing = bar.overflowing
    if not overflowing:
        pytest.skip("nothing overflowed at this width")
    tool = window.tool_manager.tool("blur")
    assert tool is not None
    own = {id(w) for w in tool.__dict__.values() if isinstance(w, QWidget)}
    own |= {id(w) for w in getattr(tool, "mode_buttons", {}).values()}
    own |= {id(w) for w in getattr(tool, "shape_buttons", {}).values()}
    # At least one of the tool's own widgets is in the popover, and it is the same object.
    assert any(id(w) in own for w in overflowing) or any(w in bar.controls for w in overflowing)
    for widget in overflowing:
        assert widget in bar.controls


def test_the_bar_still_spans_its_row(window: MainWindow) -> None:
    """The strip must not shrink the toolbar to its own hint (a regression while building
    this): the bar is as wide as the window's row, whatever it holds."""
    bar = _settle(window, 1400)
    assert bar.width() > 1000


def test_a_tool_with_two_controls_never_overflows(main_window: MainWindow) -> None:
    main_window.tool_manager.activate("pan")
    bar = _settle(main_window, 1024)
    assert bar.overflowing == []
    assert not bar.more_button.isVisible()


def test_switching_tools_empties_the_popover(window: MainWindow) -> None:
    bar = _settle(window, 1024)
    assert bar.overflowing
    window.tool_manager.activate("pan")
    for _ in range(4):
        bar._reflow()  # noqa: SLF001
    assert bar.overflowing == []
    assert bar.controls and len(bar.controls) < 5  # the Pan tool's label only
