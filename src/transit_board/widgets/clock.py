"""Right-sidebar clock widget: HH:MM + short date."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from transit_board.display import layout
from transit_board.display.renderer import get_font


def draw_clock(image: Image.Image, font_path: str | None = None) -> None:
    """Render the clock into the CLOCK region of the sidebar."""
    draw = ImageDraw.Draw(image)
    now = datetime.now()

    font_time = get_font(font_path, size=10)
    font_date = get_font(font_path, size=7)

    x0 = layout.SIDEBAR_X

    # Background
    draw.rectangle(
        [x0, layout.CLOCK_Y, x0 + layout.SIDEBAR_W - 1, layout.CLOCK_Y + layout.CLOCK_H - 1],
        fill=layout.SIDEBAR_BG,
    )

    # Time — HH:MM, horizontally centred
    time_str = now.strftime("%H:%M")
    bbox = draw.textbbox((0, 0), time_str, font=font_time)
    tw = bbox[2] - bbox[0]
    tx = x0 + max(0, (layout.SIDEBAR_W - tw) // 2)
    draw.text((tx, layout.CLOCK_Y + 2), time_str, font=font_time, fill=layout.WHITE)

    # Date — "Fri 09", smaller, dimmer
    date_str = now.strftime("%a %d")
    bbox_d = draw.textbbox((0, 0), date_str, font=font_date)
    dw = bbox_d[2] - bbox_d[0]
    dx = x0 + max(0, (layout.SIDEBAR_W - dw) // 2)
    draw.text((dx, layout.CLOCK_Y + 13), date_str, font=font_date, fill=layout.DIM)
