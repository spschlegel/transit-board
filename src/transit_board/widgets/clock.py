"""Info-strip clock section: HH:MM + short date, bottom-left of display."""

from __future__ import annotations

from datetime import datetime

from PIL import Image

from transit_board.display import layout
from transit_board.display.renderer import get_draw, get_font


def draw_clock(image: Image.Image, font_path: str | None = None) -> None:
    """Render the clock into the CLOCK section of the bottom info strip."""
    draw = get_draw(image)
    now = datetime.now()

    # Tiny5 is narrow enough that the time can run bigger than the 8px grid
    # used elsewhere without overflowing CLOCK_W ("23:11" is 27px at size 12,
    # vs. 32px available) — this is the standalone clock column, not a row
    # inside the fixed 8px departure grid, so it isn't bound to that size.
    font_time = get_font(font_path, size=12)
    font_date = get_font(font_path, size=8)

    x0 = layout.CLOCK_X
    w = layout.CLOCK_W
    y0 = layout.INFO_Y

    # Background
    draw.rectangle(
        [x0, y0, x0 + w - 1, y0 + layout.INFO_H - 1],
        fill=layout.SIDEBAR_BG,
    )

    # Time — HH:MM, horizontally centred
    time_str = now.strftime("%H:%M")
    bbox = draw.textbbox((0, 0), time_str, font=font_time)
    tw = bbox[2] - bbox[0]
    tx = x0 + max(0, (w - tw) // 2)
    draw.text((tx, y0 + 2), time_str, font=font_time, fill=layout.WHITE)

    # Date — "Fri 09", smaller, dimmer, centred below time
    date_str = now.strftime("%a %d")
    bbox_d = draw.textbbox((0, 0), date_str, font=font_date)
    dw = bbox_d[2] - bbox_d[0]
    dx = x0 + max(0, (w - dw) // 2)
    draw.text((dx, y0 + 18), date_str, font=font_date, fill=layout.DIM)
