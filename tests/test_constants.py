"""Tests for application constants and configuration."""

from snapmock.config.constants import (
    APP_NAME,
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    GRID_SIZE_DEFAULT,
    LAYER_Z_RANGE,
    UNDO_LIMIT,
    ZOOM_DEFAULT,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_PIXEL_GRID_THRESHOLD,
)
from snapmock.config.shortcuts import SHORTCUTS


def test_app_name() -> None:
    assert APP_NAME == "Snapmockit"


def test_canvas_defaults() -> None:
    assert DEFAULT_CANVAS_WIDTH == 1920
    assert DEFAULT_CANVAS_HEIGHT == 1080


def test_zoom_bounds_valid() -> None:
    assert 0 < ZOOM_MIN < ZOOM_DEFAULT < ZOOM_MAX
    assert ZOOM_PIXEL_GRID_THRESHOLD > ZOOM_DEFAULT


def test_layer_z_range_positive() -> None:
    assert LAYER_Z_RANGE > 0


def test_undo_limit_positive() -> None:
    assert UNDO_LIMIT > 0


def test_grid_size_positive() -> None:
    assert GRID_SIZE_DEFAULT > 0


def test_shortcuts_are_nonempty() -> None:
    assert len(SHORTCUTS) > 0


def test_shortcuts_have_string_values() -> None:
    for action, key_seq in SHORTCUTS.items():
        assert isinstance(action, str)
        assert isinstance(key_seq, str)
        # Some tools (e.g. pan) use empty key sequences because they are
        # activated via special key handling (Space bar) instead of shortcuts.
