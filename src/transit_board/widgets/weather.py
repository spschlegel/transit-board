"""Right-sidebar weather widget: temperature + pixel-art icon + condition label."""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from transit_board.display import layout
from transit_board.display.renderer import get_draw, get_font
from transit_board.providers.weather import WeatherData

# ── 7×7 pixel-art weather icons ──────────────────────────────────────────────
# Each entry is a list of (x, y) offsets from the icon's top-left corner.

_SUN: list[tuple[int, int]] = [
    (3, 0),
    (1, 1),
    (5, 1),
    (2, 2),
    (3, 2),
    (4, 2),
    (0, 3),
    (2, 3),
    (4, 3),
    (6, 3),
    (2, 4),
    (3, 4),
    (4, 4),
    (1, 5),
    (5, 5),
    (3, 6),
]

# Pixels that belong to the sun peek in the PARTLY icon
_PARTLY_SUN: set[tuple[int, int]] = {(5, 0), (6, 1)}
_PARTLY: list[tuple[int, int]] = [
    (5, 0),
    (6, 1),  # sun peek
    (1, 2),
    (2, 2),
    (3, 2),
    (4, 2),
    (0, 3),
    (1, 3),
    (2, 3),
    (3, 3),
    (4, 3),
    (5, 3),
    (1, 4),
    (2, 4),
    (3, 4),
    (4, 4),
]

_CLOUD: list[tuple[int, int]] = [
    (2, 1),
    (3, 1),
    (4, 1),
    (1, 2),
    (2, 2),
    (3, 2),
    (4, 2),
    (5, 2),
    (0, 3),
    (1, 3),
    (2, 3),
    (3, 3),
    (4, 3),
    (5, 3),
    (6, 3),
    (0, 4),
    (1, 4),
    (2, 4),
    (3, 4),
    (4, 4),
    (5, 4),
    (6, 4),
]

_RAIN: list[tuple[int, int]] = [
    (2, 0),
    (3, 0),
    (4, 0),
    (1, 1),
    (2, 1),
    (3, 1),
    (4, 1),
    (5, 1),
    (0, 2),
    (1, 2),
    (2, 2),
    (3, 2),
    (4, 2),
    (5, 2),
    (6, 2),
    (0, 3),
    (1, 3),
    (2, 3),
    (3, 3),
    (4, 3),
    (5, 3),
    (6, 3),
    (1, 5),
    (3, 5),
    (5, 5),  # rain drops
]

_SNOW: list[tuple[int, int]] = [
    (3, 0),
    (1, 1),
    (3, 1),
    (5, 1),
    (2, 2),
    (3, 2),
    (4, 2),
    (0, 3),
    (1, 3),
    (2, 3),
    (3, 3),
    (4, 3),
    (5, 3),
    (6, 3),
    (2, 4),
    (3, 4),
    (4, 4),
    (1, 5),
    (3, 5),
    (5, 5),
    (3, 6),
]

# Pixels that are the lightning bolt in the STORM icon
_STORM_LIGHTNING: set[tuple[int, int]] = {(3, 4), (4, 4), (2, 5), (3, 5), (2, 6)}
_STORM: list[tuple[int, int]] = [
    (2, 0),
    (3, 0),
    (4, 0),
    (1, 1),
    (2, 1),
    (3, 1),
    (4, 1),
    (5, 1),
    (0, 2),
    (1, 2),
    (2, 2),
    (3, 2),
    (4, 2),
    (5, 2),
    (6, 2),
    (0, 3),
    (1, 3),
    (2, 3),
    (4, 3),
    (5, 3),
    (6, 3),
    (3, 4),
    (4, 4),
    (2, 5),
    (3, 5),
    (2, 6),
]


def _draw_icon(image: Image.Image, ox: int, oy: int, code: int, scale: int = 1) -> None:
    """Render a 7×7 weather icon with top-left at (ox, oy), each pixel *scale* px wide."""
    draw = ImageDraw.Draw(image)

    def put(x: int, y: int, color: tuple[int, int, int]) -> None:
        px, py = ox + x * scale, oy + y * scale
        if scale == 1:
            draw.point((px, py), fill=color)
        else:
            draw.rectangle([px, py, px + scale - 1, py + scale - 1], fill=color)

    if code <= 1:  # Clear
        for x, y in _SUN:
            put(x, y, layout.YELLOW)

    elif code <= 2:  # Partly cloudy — two colours
        for x, y in _PARTLY:
            put(x, y, layout.YELLOW if (x, y) in _PARTLY_SUN else layout.WHITE)

    elif code <= 3:  # Overcast
        for x, y in _CLOUD:
            put(x, y, layout.DIM)

    elif code < 70:  # Rain / drizzle
        for x, y in _RAIN:
            put(x, y, layout.BLUE if y >= 5 else layout.TEAL)

    elif code < 80:  # Snow
        for x, y in _SNOW:
            put(x, y, layout.WHITE)

    elif code < 90:  # Rain showers
        for x, y in _RAIN:
            put(x, y, layout.BLUE if y >= 5 else layout.WHITE)

    else:  # Thunderstorm
        for x, y in _STORM:
            put(x, y, layout.YELLOW if (x, y) in _STORM_LIGHTNING else layout.DIM)


# ── Public draw function ──────────────────────────────────────────────────────


def draw_weather(
    image: Image.Image,
    weather: Optional[WeatherData],
    tick: int = 0,
    font_path: str | None = None,
) -> None:
    """Render temperature (TEMP section) and icon+label (WEATHER section) in info strip."""
    draw = get_draw(image)
    font = get_font(font_path, size=8)

    # ── Temperature section: current (line 1) + today's max (line 2) ─────────
    # Mirrors the UV widget's current/max layout for a consistent look.
    tx0 = layout.TEMP_X
    tcol_w = layout.TEMP_W
    ty0 = layout.INFO_Y
    draw.rectangle(
        [tx0, ty0, tx0 + tcol_w - 1, ty0 + layout.INFO_H - 1],
        fill=layout.SIDEBAR_BG,
    )
    if weather is not None:
        temp_str = f"{weather.temperature_c:.0f}\u00b0C"
        max_str = f"^{weather.temperature_max_c:.0f}\u00b0"

        bbox = draw.textbbox((0, 0), temp_str, font=font)
        tx = tx0 + max(0, (tcol_w - (bbox[2] - bbox[0])) // 2)
        draw.text((tx, ty0 + 3), temp_str, font=font, fill=layout.YELLOW)

        bbox = draw.textbbox((0, 0), max_str, font=font)
        mx = tx0 + max(0, (tcol_w - (bbox[2] - bbox[0])) // 2)
        draw.text((mx, ty0 + 13), max_str, font=font, fill=layout.DIM)
    else:
        draw.text((tx0 + 2, ty0 + 3), "--\u00b0C", font=font, fill=layout.DIM)

    # ── Weather section: current condition icon (2x scale) + short label ───
    wx0 = layout.WEATHER_X
    ww = layout.WEATHER_W
    y0 = layout.INFO_Y
    draw.rectangle(
        [wx0, y0, wx0 + ww - 1, y0 + layout.INFO_H - 1],
        fill=layout.SIDEBAR_BG,
    )
    if weather is not None:
        icon_scale = 2
        icon_px = 7 * icon_scale
        icon_x = wx0 + (ww - icon_px) // 2
        icon_y = y0 + 2
        _draw_icon(image, icon_x, icon_y, weather.weather_code, scale=icon_scale)

        cond_txt = weather.short_label
        bbox = draw.textbbox((0, 0), cond_txt, font=font)
        lw = bbox[2] - bbox[0]
        draw.text(
            (wx0 + max(0, (ww - lw) // 2), icon_y + icon_px + 2),
            cond_txt,
            font=font,
            fill=layout.TEAL,
        )
    else:
        draw.text((wx0 + 8, y0 + 11), "---", font=font, fill=layout.DIM)
