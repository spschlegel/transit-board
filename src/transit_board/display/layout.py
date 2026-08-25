"""
Layout constants for the 128×64 display — vertical variant.

Vertical-split layout:
  Left   84×64  — departures panel, two stops stacked  (x 0–83)
  x=84           — 1 px vertical divider
  Right  44×64  — info column: clock / weather / temp / UV, stacked (x 84–127)

Departures panel:
  Top    84×32  — stop 1  (y 0–31)
  y=32           — 1 px horizontal stop divider
  Bottom 84×32  — stop 2  (y 32–63)

Info column (horizontal dividers at y = 26, 40, 52) — clock gets the largest
share since a bigger clock is the whole point of this layout, the rest are
compact single-row designs:
  Clock    y  0–25  (26 px)
  Weather  y 26–39  (14 px)
  Temp     y 40–51  (12 px)
  UV       y 52–63  (12 px)
"""

from __future__ import annotations

# ── Physical display ───────────────────────────────────────────────────────────
DISPLAY_W = 128
DISPLAY_H = 64

# ── Departures panel (left ~2/3) ────────────────────────────────────────────────
DEPARTURES_X = 0
DEPARTURES_W = 84

STOP_H = 32  # each stop's panel height (header + 3 rows)
STOP_DIV_Y = 32  # y of 1 px horizontal divider between stop 1 and stop 2

HEADER_H = 8  # stop-name / leave-time header row
ROW_H = 8  # one departure row
# HEADER_H + 3 × ROW_H = 32 = STOP_H ✓

# ── Vertical divider between departures and info column (full height) ──────────
VERT_DIV_X = 84

# ── Info column (right ~1/3, full height) ───────────────────────────────────────
INFO_X = 84
INFO_W = 44  # 128 - 84

CLOCK_Y = 0
CLOCK_H = 26

WEATHER_Y = 26
WEATHER_H = 14

TEMP_Y = 40
TEMP_H = 12

UV_Y = 52
UV_H = 12
# CLOCK_H + WEATHER_H + TEMP_H + UV_H = 64 = DISPLAY_H ✓

INFO_DIV_YS: tuple[int, ...] = (26, 40, 52)  # y positions of horizontal info-column dividers

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
SECTION_DIV = (18, 18, 28)  # secondary info-column dividers

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
