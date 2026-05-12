"""
Layout constants for the 128×64 display.

Physical split:
  Left  95×64  — departure rows   (x 0–94)
  x=95          — 1 px vertical divider
  Right 32×64  — sidebar: clock / temp / weather / UV  (x 96–127)
"""

from __future__ import annotations

# ── Physical display ──────────────────────────────────────────────────────────
DISPLAY_W = 128
DISPLAY_H = 64

# ── Left departure panel ──────────────────────────────────────────────────────
DEPART_X = 0
DEPART_Y = 0
DEPART_W = 95  # cols 0–94; col 95 is the divider
DEPART_H = 64

# ── Vertical panel divider ────────────────────────────────────────────────────
PANEL_DIV_X = 95

# ── Right sidebar ─────────────────────────────────────────────────────────────
SIDEBAR_X = 96
SIDEBAR_Y = 0
SIDEBAR_W = 32
SIDEBAR_H = 64

# ── Row heights (pixels) ──────────────────────────────────────────────────────
ROW_H = 8  # one departure row
HEADER_H = 8  # stop-name header row
# 2 stops × (HEADER_H + 3×ROW_H) = 2×32 = 64 — fills left panel exactly

# ── Sidebar sub-region Y offsets & heights ────────────────────────────────────
CLOCK_Y = 0
CLOCK_H = 20  # HH:MM + Mon DD

TEMP_Y = 20
TEMP_H = 13  # temperature in °F

WEATHER_Y = 33
WEATHER_H = 18  # 7px icon + 2px gap + 8px label = 17, + 1px margin

UV_Y = 51
UV_H = 13  # text + 3px colour bar at bottom
# Sidebar total: 20+13+18+13 = 64 ✓

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

SIDEBAR_BG = (0, 0, 20)  # right sidebar background tint
PANEL_DIVIDER = (35, 35, 45)  # vertical separator line
SECTION_DIV = (18, 18, 28)  # horizontal sidebar section dividers

# ── Route type → default text colour ─────────────────────────────────────────
ROUTE_COLORS: dict[str, tuple[int, int, int]] = {
    "bus": TEAL,
    "subway": ORANGE,
    "default": WHITE,
}

# ── MBTA named line → colour (keys must be lowercase) ────────────────────────
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
