"""Info-strip UV-index section: label + WHO colour-scale progress bar."""

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
) -> None:
    """Render UV index into the UV section of the bottom info strip."""
    draw = get_draw(image)
    font = get_font(font_path, size=8)

    x0 = layout.UV_X
    w = layout.UV_W
    y0 = layout.INFO_Y

    # Background
    draw.rectangle(
        [x0, y0, x0 + w - 1, y0 + layout.INFO_H - 1],
        fill=layout.SIDEBAR_BG,
    )

    if weather is not None:
        uv = weather.uv_index
        uv_max = weather.uv_index_max
        label = f"UV {uv:.0f}"
        color = _uv_color(uv)
        max_label = f"^{uv_max:.0f}"  # ^ + today's max (ASCII, avoids tofu on bitmap fonts)
        max_color = _uv_color(uv_max)
    else:
        uv = 0.0
        uv_max = 0.0
        label = "UV --"
        max_label = "^ --"
        color = layout.DIM
        max_color = layout.DIM

    # Line 1: current UV label
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    tx = x0 + max(0, (w - tw) // 2)
    draw.text((tx, y0 + 3), label, font=font, fill=color)

    # Line 2: today's max UV
    bbox = draw.textbbox((0, 0), max_label, font=font)
    tw = bbox[2] - bbox[0]
    tx = x0 + max(0, (w - tw) // 2)
    draw.text((tx, y0 + 13), max_label, font=font, fill=max_color)

    # Colour-scale progress bar (2 px tall, near bottom of section)
    bar_max = w - 4  # 28 px usable
    bar_w = int(min(uv / _UV_MAX, 1.0) * bar_max) if weather else 0  # 0 when UV=0, no stray pixel
    bar_y = y0 + layout.INFO_H - 5
    if bar_w > 0:
        draw.rectangle(
            [x0 + 2, bar_y, x0 + 2 + bar_w - 1, bar_y + 1],
            fill=color,
        )
