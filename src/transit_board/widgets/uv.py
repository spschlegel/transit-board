"""Info-column UV-index section: "UV {value} {sub}", centred."""

from __future__ import annotations

from typing import Optional

from PIL import Image

from transit_board.display import layout
from transit_board.display.renderer import get_draw, get_font
from transit_board.providers.weather import WeatherData


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
    Render the UV section of the info column: one combined line, centred.

    *show_forecast* is the 22:00-00:01 evening preview window (see loop.py):
    there's no "current" UV reading for tomorrow, so the headline switches to
    tomorrow's forecast max and the trailing label reads "TMRW" instead of the
    usual "^{today's max}".
    """
    draw = get_draw(image)
    # Tiny5 only rasterizes cleanly at its native size (8px) and exact
    # multiples (16px, too wide for this 44px column) — anything in between
    # comes out with uneven stroke widths and glyph artifacts, so text stays
    # at 8px.
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
        label = "UV -- --"
        color = layout.DIM

    # Single combined line: current UV + today's max (or tomorrow's forecast
    # max + "TMRW" in the preview window), centred both ways
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = x0 + max(0, (w - tw) // 2)
    ty = y0 + (layout.UV_H - th) // 2 - bbox[1]
    draw.text((tx, ty), label, font=font, fill=color)
