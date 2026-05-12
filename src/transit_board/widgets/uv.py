"""Right-sidebar UV-index widget: label + WHO colour-scale progress bar."""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from transit_board.display import layout
from transit_board.display.renderer import get_font
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
    """Render UV index into the UV sidebar region."""
    draw = ImageDraw.Draw(image)
    font = get_font(font_path, size=8)
    x0 = layout.SIDEBAR_X

    draw.rectangle(
        [x0, layout.UV_Y, x0 + layout.SIDEBAR_W - 1, layout.UV_Y + layout.UV_H - 1],
        fill=layout.SIDEBAR_BG,
    )

    if weather is not None:
        uv = weather.uv_index
        label = f"UV {uv:.0f}"
        color = _uv_color(uv)
    else:
        uv = 0.0
        label = "UV --"
        color = layout.DIM

    # Centred label
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    tx = x0 + max(0, (layout.SIDEBAR_W - tw) // 2)
    draw.text((tx, layout.UV_Y + 2), label, font=font, fill=color)

    # Colour-scale progress bar (2 px tall, 3 px from section bottom)
    bar_max = layout.SIDEBAR_W - 4  # 28 px
    bar_w = max(1, int(min(uv / _UV_MAX, 1.0) * bar_max)) if weather else 0
    bar_y = layout.UV_Y + layout.UV_H - 3
    if bar_w > 0:
        draw.rectangle(
            [x0 + 2, bar_y, x0 + 2 + bar_w - 1, bar_y + 1],
            fill=color,
        )
