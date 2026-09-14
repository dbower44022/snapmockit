"""Application-wide constants."""

from enum import Enum
from pathlib import Path

from snapmock import __version__

APP_NAME = "Snapmockit"
"""The product's name, decided 09-14-26 (it was SnapMock while the domain was in
question). Everything a user reads takes it from here."""
APP_VERSION = __version__
"""One source: ``snapmock/__init__.py``, which ``pyproject.toml`` reads at build time."""
# Set by the release process; the About dialog shows it beside the version (PRD 11.6).
APP_BUILD_DATE = "2026-09-08"
APP_LICENSE = "MIT License"
COPYRIGHT = "Copyright (c) 2026 Doug Bower"
ORG_NAME = "SnapMock"
"""The organisation name QSettings stores under (``~/.config/SnapMock``): kept at the
earlier name so existing settings are found, until a release carries a migration."""
STORAGE_APP_NAME = "SnapMock"
"""The application name QSettings stores under, kept for the same reason."""
ORG_DOMAIN = "snapmockit.com"
REPOSITORY_URL = "https://github.com/dbower44022/snapmockit"
DOCUMENTATION_URL = f"{REPOSITORY_URL}#readme"
ISSUES_URL = f"{REPOSITORY_URL}/issues"

# Main window (General UI PRD 2.2, 15.1)
MIN_WINDOW_WIDTH = 1024
MIN_WINDOW_HEIGHT = 600
DEFAULT_PANEL_WIDTH = 300

# Panel collapse thresholds (General UI PRD 15.1, 15.2; Preferences > Appearance)
PANEL_NARROW_THRESHOLD_DEFAULT = 1280
PANEL_STRIP_THRESHOLD_DEFAULT = 1024
PANEL_THRESHOLD_MIN = 600
PANEL_THRESHOLD_MAX = 5120

# Canvas defaults
DEFAULT_CANVAS_WIDTH = 1920
DEFAULT_CANVAS_HEIGHT = 1080

# Zoom bounds (percentage)
ZOOM_MIN = 10
ZOOM_MAX = 3200
ZOOM_DEFAULT = 100
ZOOM_PIXEL_GRID_THRESHOLD = 800

# Layer z-value allocation: each layer gets a range of this size
LAYER_Z_RANGE = 10_000

# Undo/redo stack limit
UNDO_LIMIT = 200

# Grid snapping (General UI PRD 11.3 Canvas & Grid)
GRID_SIZE_DEFAULT = 10
SNAP_TOLERANCE_DEFAULT = 5
GUIDE_COLOR_DEFAULT = "#00BFFF"
GUIDE_OPACITY_DEFAULT = 70

# Recent files (General UI PRD 11.3 General)
RECENT_FILES_DEFAULT = 10
RECENT_ZOOM_MAX = 50  # zoom levels kept per recently opened project (PRD 15.4)

# Layer thumbnail refresh delay (General UI PRD 11.3 Performance)
THUMBNAIL_DELAY_DEFAULT_MS = 500

# Autosave interval in milliseconds (2 minutes)
AUTOSAVE_INTERVAL_MS = 120_000

# File format
PROJECT_EXTENSION = ".smk"
THUMBNAIL_MAX_SIZE = 256

# Library
DEFAULT_LIBRARY_DIRECTORY = Path.home() / "SnapMock" / "Library"  # kept: existing libraries
LIBRARY_THUMBNAIL_MIN = 80
LIBRARY_THUMBNAIL_MAX = 256
LIBRARY_THUMBNAIL_DEFAULT = 128
LIBRARY_PREVIEW_MIN = 48
LIBRARY_PREVIEW_MAX = 128
LIBRARY_PREVIEW_DEFAULT = 64
LIBRARY_WRITE_BACK_DELAY_MS = 300
LIBRARY_PATHS_MIME = "application/x-snapmock-library-paths"
LIBRARY_IMPORT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif", ".webp")
PROJECT_FORMAT_VERSION = 1
DEFAULT_CANVAS_DPI = 72
RECENT_COLORS_MAX = 12  # recent and saved swatches per row (General UI PRD 11.1)
SNAGIT_EXTENSION = ".snagx"
SNAGIT_FORMAT_VERSION = "1.0"

# Default item properties
DEFAULT_STROKE_WIDTH = 2.0
DEFAULT_STROKE_COLOR = "#FF0000"
DEFAULT_FILL_COLOR = "#00000000"
DEFAULT_FONT_FAMILY = "Sans Serif"
DEFAULT_FONT_SIZE = 14
# Line spacing multiplier of new text items (Text & Callout PRD 2.2); the range of the
# Property Panel's row (General UI PRD 8.4)
DEFAULT_LINE_SPACING = 1.2
LINE_SPACING_MIN = 0.5
LINE_SPACING_MAX = 5.0

# Text box frame defaults
DEFAULT_TEXT_BG_COLOR = "#00000000"  # transparent
DEFAULT_TEXT_BORDER_COLOR = "#00000000"  # transparent
DEFAULT_TEXT_BORDER_WIDTH = 0.0
DEFAULT_TEXT_BORDER_RADIUS = 0.0
DEFAULT_TEXT_PADDING = 8.0
DEFAULT_TEXT_WIDTH = 200.0
MIN_DRAG_TEXT_BOX = 10.0  # min px to count as drag-to-create
MIN_TEXT_BOX_WIDTH = 20.0
MIN_TEXT_BOX_HEIGHT = 16.0


class VerticalAlign(Enum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class BubbleShape(Enum):
    ROUNDED_RECT = "rounded_rect"
    RECT = "rect"
    ELLIPSE = "ellipse"
    CLOUD = "cloud"
    STARBURST = "starburst"
    PILL = "pill"


class TailStyle(Enum):
    STRAIGHT = "straight"
    CURVED = "curved"
    ELBOW = "elbow"


class TailBaseEdge(Enum):
    AUTO = "auto"
    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"
    LEFT = "left"


class BorderStyle(Enum):
    """The five stroke styles: ``stroke_style`` on a vector item (Basic Shape PRD 2.2) and
    ``border_style`` on the text box, the callout, and the numbered step (Vector Item
    Properties silence 1: one enum, two key names)."""

    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"
    DASHDOT = "dashdot"
    DASHDOTDOT = "dashdotdot"


class StrokeCap(Enum):
    """Line cap style (Basic Shape PRD 2.2): line endpoints and dash caps."""

    FLAT = "flat"
    SQUARE = "square"
    ROUND = "round"


class StrokeJoin(Enum):
    """Line join style (Basic Shape PRD 2.2): the corners of rectangles and polygons."""

    MITER = "miter"
    BEVEL = "bevel"
    ROUND = "round"


class HeadStyle(Enum):
    """An arrowhead's style at either end (Basic Shape PRD 4.3)."""

    NONE = "none"
    OPEN = "open"
    FILLED = "filled"
    DIAMOND = "diamond"
    CIRCLE = "circle"
    SQUARE = "square"


class HeadSize(Enum):
    """The four named arrowhead sizes (Basic Shape PRD 4.3)."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"


HEAD_SIZE_PX: dict[HeadSize, float] = {
    HeadSize.SMALL: 8.0,
    HeadSize.MEDIUM: 12.0,
    HeadSize.LARGE: 18.0,
    HeadSize.XLARGE: 24.0,
}
HEAD_SIZE_CUSTOM_MIN = 4.0
HEAD_SIZE_CUSTOM_MAX = 60.0


DRAWING_PREVIEW_OPACITY = 0.7
"""Basic Shape PRD 2.4: a shape being drawn is shown at 70 percent of its own opacity, to
tell it from the items already placed; the committed item has its own opacity back."""

DRAWING_GUIDE_OPACITY = 0.3
"""Basic Shape PRD 2.4: the dashed guide lines from a shape being drawn to the rulers are
the accent colour at 30 percent opacity."""

CORNER_RADIUS_MAX = 200.0
"""The Corner Radius control's range (Basic Shape PRD 5.4); the item clamps to half the
smaller side (5.3)."""


class CornerRadiusMode(Enum):
    """One radius for all four corners, or one per corner (Basic Shape PRD 5.3)."""

    UNIFORM = "uniform"
    INDIVIDUAL = "individual"


CORNER_KEYS: tuple[str, str, str, str] = (
    "corner_radius_tl",
    "corner_radius_tr",
    "corner_radius_bl",
    "corner_radius_br",
)
"""The four individual radii of 5.3, in the PRD's order and under their 10.3 keys."""


class ArcType(Enum):
    """An arc's closure (Basic Shape PRD 7.3): the curve alone, a chord, or a pie slice."""

    OPEN = "open"
    CHORD = "chord"
    PIE = "pie"


class PolygonMode(Enum):
    """Arbitrary vertices, or a computed equilateral polygon (Basic Shape PRD 8.3)."""

    FREEFORM = "freeform"
    REGULAR = "regular"


class BlurMode(Enum):
    """How a blur region obscures what lies beneath it (Blur PRD 2.2)."""

    GAUSSIAN = "gaussian"
    PIXELATE = "pixelate"
    SOLID = "solid"


class BlurRegionShape(Enum):
    """A blur region's shape (Blur PRD 2.4)."""

    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    FREEFORM = "freeform"
    WHOLE_LAYER = "whole_layer"


class BlurSourceMode(Enum):
    """What content a blur region obscures (Blur PRD 2.5)."""

    ALL_BELOW = "all_below"
    ACTIVE_LAYER = "active_layer"
    SPECIFIC_LAYER = "specific_layer"


HIGHLIGHT_SMOOTHING_WINDOW = 5
"""The moving average while drawing runs over the last this many points (Blur PRD 3.2)."""

HIGHLIGHT_SIMPLIFY_EPSILON = 2.0
"""Ramer-Douglas-Peucker tolerance applied to a highlight stroke on release (3.2)."""

HIGHLIGHT_MIN_LENGTH = 4.0
"""A stroke shorter than this many pixels is an accidental click (3.2)."""

DEFAULT_STRAIGHTEN_THRESHOLD = 1.15
STRAIGHTEN_THRESHOLD_MIN = 1.01
STRAIGHTEN_THRESHOLD_MAX = 1.50
"""Arc length over straight-line distance: below the threshold the stroke is a line (3.3)."""

SNAP_TO_AXIS_DEGREES = 5.0
"""A straightened stroke within this many degrees of an axis snaps to it (3.3)."""

BLUR_RADIUS_MIN = 1.0
BLUR_RADIUS_MAX = 50.0
BLUR_PIXEL_SIZE_MIN = 2
BLUR_PIXEL_SIZE_MAX = 100
BLUR_FEATHER_MAX = 30.0
BLUR_BRUSH_SIZE_MIN = 5.0
BLUR_BRUSH_SIZE_MAX = 200.0
DEFAULT_BLUR_BRUSH_SIZE = 30.0
DEFAULT_BLUR_FILL_COLOR = "#000000"
"""The Blur PRD's 2.5 ranges and defaults."""


class LineStyle(Enum):
    """An arrow's path type (Basic Shape PRD 4.3, 4.5, 4.6)."""

    STRAIGHT = "straight"
    CURVED = "curved"
    ELBOW = "elbow"


# Zoom step ladder (percentage values)
ZOOM_STEPS = [
    10,
    15,
    20,
    25,
    33,
    50,
    67,
    75,
    100,
    125,
    150,
    200,
    250,
    300,
    400,
    500,
    600,
    800,
    1200,
    1600,
    2400,
    3200,
]

# Minimum pixels of mouse movement before a drag is recognised
DRAG_THRESHOLD = 3

# Canvas chrome. Colours live in the theme files (resources/themes/*.qss) and are
# read through core/theme_manager.py (General UI PRD 13.4).
PASTEBOARD_MARGIN = 2000
CANVAS_SHADOW_OFFSET = 4

# Checkerboard transparency (cell size; Preferences > Appearance can change it)
CHECKERBOARD_CELL_SIZE = 8

# Rulers
RULER_SIZE = 20

# Grid overlay (General UI PRD 6.4): a major line every 5 grid units; minor lines
# hide below 200 percent zoom; nothing draws once lines would be closer than 4 px.
GRID_MAJOR_MULTIPLE = 5
GRID_MINOR_MIN_ZOOM = 200
GRID_MIN_PIXEL_SPACING = 4

# Empty canvas prompt (General UI PRD 6.2)
EMPTY_CANVAS_TEXT = (
    "Drag an image here, paste from clipboard (Ctrl+V), or go to File > Import Image"
)
EMPTY_CANVAS_FONT_SIZE = 18


# --- Numbered Step (Numbered Steps, Stamps & Emoji PRD Sections 2.4 and 2.5) ---
DEFAULT_BADGE_COLOR = "#CC0000"
DEFAULT_BADGE_SIZE = 32.0
BADGE_SIZE_MIN = 16.0
BADGE_SIZE_MAX = 128.0
DEFAULT_BADGE_TEXT_COLOR = "#FFFFFF"
DEFAULT_BADGE_FONT_FAMILY = "Arial"
DEFAULT_BADGE_BORDER_COLOR = "#FFFFFF"
DEFAULT_BADGE_BORDER_WIDTH = 2.0
DEFAULT_LABEL_FONT_SIZE = 12.0
DEFAULT_LABEL_COLOR = "#000000"
DEFAULT_LABEL_BACKGROUND = "#CCFFFFFF"  # the PRD's #FFFFFFCC in Qt's #AARRGGBB form
MARKER_MIN_HIT_SIZE = 24.0  # the minimum hit area of Sections 2.10, 3.10, and 4.8

# --- Shadow (PRD Sections 2.4, 3.5, 4.4; decision 1 of the implementation) ---
DEFAULT_SHADOW_COLOR = "#66000000"  # the PRD's #00000066 in Qt's #AARRGGBB form
DEFAULT_SHADOW_OFFSET = 2.0
DEFAULT_SHADOW_BLUR = 4.0

# --- Highlighter (Blur, Highlighter & Eyedropper PRD Section 3.4) ---
DEFAULT_HIGHLIGHT_COLOR = "#CCFFFF00"  # the PRD's #FFFF00CC in Qt's #AARRGGBB form
DEFAULT_HIGHLIGHT_WIDTH = 24.0
HIGHLIGHT_WIDTH_MIN = 10.0
HIGHLIGHT_WIDTH_MAX = 80.0
DEFAULT_HIGHLIGHT_BLEND_MODE = "Multiply"
HIGHLIGHT_PRESET_COLORS: tuple[tuple[str, str], ...] = (
    ("Yellow", "#CCFFFF00"),
    ("Green", "#CC00FF00"),
    ("Cyan", "#CC00FFFF"),
    ("Pink", "#CCFF69B4"),
    ("Orange", "#CCFF8C00"),
    ("Purple", "#CC9B30FF"),
)
"""The six preset highlight colours of Blur PRD 3.5, at the PRD's 80 percent alpha."""

# --- Shadow of the vector items and the text items (Basic Shape PRD 2.2; Vector Item
# Properties silence 2: each PRD's own defaults) ---
DEFAULT_VECTOR_SHADOW_COLOR = "#80000000"  # the PRD's #00000080 in Qt's #AARRGGBB form
DEFAULT_VECTOR_SHADOW_OFFSET = 3.0
DEFAULT_VECTOR_SHADOW_BLUR = 5.0


class BadgeShape(Enum):
    CIRCLE = "circle"
    ROUNDED_SQUARE = "rounded_square"
    SQUARE = "square"
    DIAMOND = "diamond"
    HEXAGON = "hexagon"
    STAR = "star"
    OVAL = "oval"
    PIN = "pin"


class DisplayMode(Enum):
    NUMBER = "number"
    LETTER = "letter"
    ROMAN = "roman"
    TEXT = "text"


class FontWeight(Enum):
    NORMAL = "normal"
    BOLD = "bold"


class LabelPosition(Enum):
    RIGHT = "right"
    LEFT = "left"
    TOP = "top"
    BOTTOM = "bottom"


# --- Eyedropper (Blur, Highlighter & Eyedropper PRD Sections 4.2, 4.4) ---
SAMPLE_SIZES: tuple[int, ...] = (1, 3, 5, 11)
"""The four sample areas of 4.2, as the side of the square in canvas pixels.

4.4 names the property an enum over "1x1", "3x3", "5x5", and "11x11"; the side length
carries the same four values, the label is derived from it, and a preset or a theme stores
it as a plain number (Eyedropper and Blur performance Phase 2).
"""

DEFAULT_SAMPLE_SIZE = 1
"""4.4's default: the exact pixel under the cursor."""


class ColorFormat(Enum):
    """How the Eyedropper's colour value reads (Blur PRD 4.4, 4.5)."""

    HEX = "hex"
    RGB = "rgb"
    HSL = "hsl"


class ApplyTarget(Enum):
    """Which colour property an applied sample sets (Blur PRD 4.4, 4.6).

    4.5's dropdown offers the first three; the other two are the properties 4.7's
    momentary Alt mode reaches on the Highlighter and the Numbered Step tool.
    """

    STROKE_COLOR = "stroke_color"
    FILL_COLOR = "fill_color"
    TEXT_COLOR = "text_color"
    HIGHLIGHT_COLOR = "highlight_color"
    BADGE_COLOR = "badge_color"


DEFAULT_APPLY_TARGET = ApplyTarget.STROKE_COLOR
"""4.4's default target."""

COLOR_HISTORY_MAX = 8
"""4.5's Color History row: the last eight sampled colours."""
