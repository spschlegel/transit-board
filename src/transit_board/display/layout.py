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

Info strip columns (vertical dividers drawn at x = 34, 56, 96):
  Clock    x  0–33   (34 px)
  Temp     x 34–55   (22 px)
  Weather  x 56–95   (40 px)
  UV       x 96–127  (32 px)
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
CLOCK_W = 34

TEMP_X = 34
TEMP_W = 22

WEATHER_X = 56
WEATHER_W = 40

UV_X = 96
UV_W = 32

INFO_DIV_XS: tuple[int, ...] = (34, 56, 96)  # x positions of vertical info-strip dividers

# ── Colours (R, G, B) ─────────────────────────────────────────────────────────
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
DIM = (85, 85, 85)
ORANGE = (255, 115, 0)
RED = (230, 30, 30)
GREEN = (30, 225, 30)
TEAL = (0, 215, 225)
YELLOW = (255, 215, 0)
BLUE = (70, 130, 255)
PURPLE = (185, 45, 235)

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
    "silver": DIM,
    "sl": DIM,
    "purple": PURPLE,
}
