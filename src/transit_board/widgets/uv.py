"""Info-column UV-index section: "UV {value} {sub}" + WHO colour-scale progress bar."""

from __future__ import annotations

from typing import Optional

from PIL import Image

from transit_board.display import layout
from transit_board.display.renderer import get_draw, get_font
from transit_board.providers.weather import WeatherData

_UV_MAX = 11.0  # clamp scale


def _uv_color(uv: float) -> tuple[int, int, int]:
    """WHO UV index colour scale."""
    if uv < 3:
        return layout.GREEN
    if uv < 6:
        return layout.YELLOW
    if uv < 8:
        return (255, 140, 0)  # amber
    if uv < 11:
        return layout.RED
    return layout.PURPLE


def draw_uv(
    image: Image.Image,
    weather: Optional[WeatherData],
    font_path: str | None = None,
    show_forecast: bool = False,
) -> None:
    """
    Render the UV section of the info column: one combined line + a colour bar.

    *show_forecast* is the 22:00-00:01 evening preview window (see loop.py):
    there's no "current" UV reading for tomorrow, so the headline switches to
    tomorrow's forecast max and the trailing label reads "TMRW" instead of the
    usual "^{today's max}".
    """
    draw = get_draw(image)
    # Tiny5 only rasterizes cleanly at its native size (8px) and exact
    # multiples (16px, too wide for this 44px column) — anything in between
    # comes out with uneven stroke widths and glyph artifacts, so text stays
    # at 8px; the colour-scale bar below is what gives this section more
    # visual weight instead of a bigger point size.
    font = get_font(font_path, size=8)

    x0 = layout.INFO_X
    w = layout.INFO_W
    y0 = layout.UV_Y

    # Background
    draw.rectangle(
        [x0, y0, x0 + w - 1, y0 + layout.UV_H - 1],
        fill=layout.SIDEBAR_BG,
    )

    if weather is not None:
        if show_forecast:
            headline_uv = weather.uv_index_max_tomorrow
            sub_label = "TMRW"
        else:
            headline_uv = weather.uv_index
            sub_label = f"^{weather.uv_index_max:.0f}"  # ^ + today's max
        color = _uv_color(headline_uv)
        label = f"UV {headline_uv:.0f} {sub_label}"
    else:
        headline_uv = 0.0
        label = "UV -- --"
        color = layout.DIM

    # Single combined line: current UV + today's max (or tomorrow's forecast
    # max + "TMRW" in the preview window)
    bbox = draw.textbbox((0, 0), label, font=font)
    tx = x0 + max(0, (w - (bbox[2] - bbox[0])) // 2)
    draw.text((tx, y0 + 2), label, font=font, fill=color)

    # Colour-scale progress bar (2 px tall, near bottom of section)
    bar_max = w - 4
    # 0 when UV=0 avoids a stray 1px bar at the very start of the scale
    bar_w = int(min(headline_uv / _UV_MAX, 1.0) * bar_max) if weather else 0
    bar_y = y0 + layout.UV_H - 2
    if bar_w > 0:
        draw.rectangle(
            [x0 + 2, bar_y, x0 + 2 + bar_w - 1, bar_y + 1],
            fill=color,
        )
