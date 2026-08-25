"""
Layout constants for the 128×64 display.

Horizontal-split layout:
  Top    128×32  — transit panel, two stops side-by-side  (y 0–31)
  y=32           — 1 px horizontal divider
  Bottom 128×31  — info strip: clock / temp / weather / UV  (y 33–63)

Transit panel:
  Left   64×32  — stop 1  (x 0–63)
  x=64           — 1 px vertical stop divider
  Right  64×32  — stop 2  (x 64–127)

Info strip columns (vertical dividers drawn at x = 32, 64, 96) — four equal
32 px columns:
  Clock    x   0–31
  Temp     x  32–63
  Weather  x  64–95
  UV       x  96–127
"""

from __future__ import annotations

# ── Physical display ───────────────────────────────────────────────────────────
DISPLAY_W = 128
DISPLAY_H = 64

# ── Transit panel (top 32 px) ──────────────────────────────────────────────────
TRANSIT_Y = 0
TRANSIT_H = 32

STOP_W = 64  # each stop occupies half the width
STOP_H = 32  # and the full transit panel height

STOP_DIV_X = 64  # x of 1 px vertical divider between stops

# ── Row heights within each stop panel ────────────────────────────────────────
HEADER_H = 8  # stop-name / leave-time header row
ROW_H = 8  # one departure row
# HEADER_H + 3 × ROW_H = 32 = STOP_H ✓

# ── Horizontal divider between transit and info strip ─────────────────────────
HORIZ_DIV_Y = 32  # y of the 1 px separator line

# ── Info strip (y 33–63 = 31 px tall) ─────────────────────────────────────────
INFO_Y = 33
INFO_H = 31  # 63 − 33 + 1

CLOCK_X = 0
CLOCK_W = 32

TEMP_X = 32
TEMP_W = 32

WEATHER_X = 64
WEATHER_W = 32

UV_X = 96
UV_W = 32

INFO_DIV_XS: tuple[int, ...] = (32, 64, 96)  # x positions of vertical info-strip dividers

# ── Colours (R, G, B) ─────────────────────────────────────────────────────────
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
DIM = WHITE  # grey was unreadable on LED panels — alias kept so old references stay white
ORANGE = (255, 115, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
TEAL = (0, 215, 225)
YELLOW = (255, 215, 0)
BLUE = (0, 90, 255)
PURPLE = (170, 0, 255)

SIDEBAR_BG = (0, 0, 20)  # header / info strip background tint
PANEL_DIVIDER = (35, 35, 45)  # main structural divider lines
SECTION_DIV = (18, 18, 28)  # secondary info-strip dividers

# ── Route type → default text colour ──────────────────────────────────────────
ROUTE_COLORS: dict[str, tuple[int, int, int]] = {
    "bus": YELLOW,
    "subway": ORANGE,
    "default": WHITE,
}

# ── MBTA named line → colour (keys must be lowercase) ─────────────────────────
LINE_COLORS: dict[str, tuple[int, int, int]] = {
    "red": RED,
    "rl": RED,
    "orange": ORANGE,
    "ol": ORANGE,
    "green": GREEN,
    "gl": GREEN,
    "blue": BLUE,
    "bl": BLUE,
    "silver": WHITE,
    "sl": WHITE,
    "purple": PURPLE,
}
