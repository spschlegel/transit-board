"""
Layout constants for the 128×64 display — vertical variant.

Vertical-split layout:
  Left   52×64  — info column: clock / weather / temp / UV, stacked (x 0–51)
  x=52           — 1 px vertical divider
  Right  76×64  — departures panel, two stops stacked  (x 52–127)

Departures panel width was trimmed from 84px: at that width, a headsign like
"Forest Hills" left ~11px of dead air before the right-aligned minutes column
on every row. 76px keeps most common headsigns un-scrolled while closing most
of that gap; longer ones (already handled fine) just scroll a bit more often.

Departures panel: each stop's panel height is HEADER_H + departures_per_stop
× ROW_H, not a fixed constant — someone running with departures_per_stop=2
has 8px less content per stop than the 3-row default, and that's real spare
canvas rather than something to leave stranded. stop_panel_layout() splits
that slack two ways: up to 4px becomes a gap between the header and the
first row (so the header doesn't sit flush against its data), and whatever's
left becomes a top/bottom margin around the whole two-stop block. See
stop_panel_layout().

Info column (horizontal dividers at y = 30, 40, 52) — clock gets the largest
share since a bigger clock is the whole point of this layout, the rest are
compact single-row designs. Weather's icon dropped from 2x to 1x scale (7px)
so its row could shrink to 10px, with the reclaimed space going to the clock:
  Clock    y  0–29  (30 px)
  Weather  y 30–39  (10 px)
  Temp     y 40–51  (12 px)
  UV       y 52–63  (12 px)
"""

from __future__ import annotations

# ── Physical display ───────────────────────────────────────────────────────────
DISPLAY_W = 128
DISPLAY_H = 64

# ── Info column (left, full height) ───────────────────────────────────────
INFO_X = 0
INFO_W = 52

CLOCK_Y = 0
CLOCK_H = 30

WEATHER_Y = 30
WEATHER_H = 10

TEMP_Y = 40
TEMP_H = 12

UV_Y = 52
UV_H = 12
# CLOCK_H + WEATHER_H + TEMP_H + UV_H = 64 = DISPLAY_H ✓

INFO_DIV_YS: tuple[int, ...] = (30, 40, 52)  # y positions of horizontal info-column dividers

# ── Vertical divider between info column and departures (full height) ──────────
VERT_DIV_X = 52

# ── Departures panel (right) ────────────────────────────────────────────────
DEPARTURES_X = 52
DEPARTURES_W = 76

HEADER_H = 8  # stop-name / leave-time header row
ROW_H = 8  # one departure row


_MAX_HEADER_GAP = 4  # px, cap on the gap carved out between header and first row


def stop_panel_layout(n_rows: int) -> tuple[int, int, int]:
    """
    Return (top_margin, panel_h, header_gap) for the two stacked stop panels.

    At the default n_rows=3, header + 3 rows already fills the full 64px
    column between the two stops (32px × 2), so there's no slack to spend and
    this returns (0, 32, 0) — same as ever, no regression there.

    With fewer rows configured there's real slack, and it used to all go to
    a top/bottom margin around the pair — which looked wrong two ways at
    once: the header sat with a lot of empty air above it, and butted
    straight up against the first row below with none. header_gap claims up
    to _MAX_HEADER_GAP px of that slack to sit between the header and the
    first row instead, and only what's left over becomes outer margin.
    """
    bare_panel_h = HEADER_H + n_rows * ROW_H
    slack = DISPLAY_H - 2 * bare_panel_h
    header_gap = min(_MAX_HEADER_GAP, max(0, slack // 4))
    panel_h = bare_panel_h + header_gap
    top_margin = max(0, (DISPLAY_H - 2 * panel_h) // 2)
    return top_margin, panel_h, header_gap


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
