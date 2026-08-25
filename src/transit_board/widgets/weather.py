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


_TEMP_SCALE_MIN = -10.0  # °C mapped to an empty bar
_TEMP_SCALE_MAX = 35.0  # °C mapped to a full bar


def _temp_color(temp_c: float) -> tuple[int, int, int]:
    """Rough comfort-scale colour: cold blue → mild green → hot red."""
    if temp_c < 0:
        return layout.BLUE
    if temp_c < 10:
        return layout.TEAL
    if temp_c < 21:
        return layout.GREEN
    if temp_c < 27:
        return layout.YELLOW
    if temp_c < 32:
        return (255, 140, 0)  # amber
    return layout.RED


# ── Public draw function ──────────────────────────────────────────


def draw_weather(
    image: Image.Image,
    weather: Optional[WeatherData],
    tick: int = 0,
    font_path: str | None = None,
    show_forecast: bool = False,
) -> None:
    """
    Render the WEATHER (condition icon + label) and TEMP sections of the info column.

    Both are compact single-row designs: this layout gives the clock most of
    the column's height, so these sections only get 12-14px each.

    *show_forecast* is the 22:00-00:01 evening preview window (see loop.py):
    the conditions icon/label switch to tomorrow's forecast. Temperature always
    shows current + today's max regardless — a future day's temperature isn't
    "current" in any sense, so there's nothing useful to preview there.
    """
    draw = get_draw(image)
    # Tiny5 only rasterizes cleanly at its native size (8px) and exact
    # multiples (16px, too wide for this 44px column) — anything in between
    # comes out with uneven stroke widths and glyph artifacts, so text stays
    # at 8px; the colour-scale bar is what gives the temp row visual weight.
    font = get_font(font_path, size=8)
    x0 = layout.INFO_X
    w = layout.INFO_W

    # ── Weather section: condition icon (2x scale, left) + short label (right) ──
    # In the forecast-preview window, both swap to tomorrow's; the label slot
    # shows "TMRW" instead of the WMO short-code so it's clear at a glance
    # this isn't the current condition (the icon alone reads as "now" otherwise).
    wy0 = layout.WEATHER_Y
    draw.rectangle(
        [x0, wy0, x0 + w - 1, wy0 + layout.WEATHER_H - 1],
        fill=layout.SIDEBAR_BG,
    )
    if weather is not None:
        code = weather.weather_code_tomorrow if show_forecast else weather.weather_code
        cond_txt = "TMRW" if show_forecast else weather.short_label

        icon_scale = 2
        icon_px = 7 * icon_scale  # 14px — exactly fills WEATHER_H
        icon_x = x0 + 2
        icon_y = wy0 + (layout.WEATHER_H - icon_px) // 2
        _draw_icon(image, icon_x, icon_y, code, scale=icon_scale)

        label_x = icon_x + icon_px + 3
        bbox = draw.textbbox((0, 0), cond_txt, font=font)
        lh = bbox[3] - bbox[1]
        label_y = wy0 + (layout.WEATHER_H - lh) // 2 - bbox[1]
        draw.text((label_x, label_y), cond_txt, font=font, fill=layout.TEAL)
    else:
        draw.text((x0 + 2, wy0 + 3), "---", font=font, fill=layout.DIM)

    # ── Temp section: "{current} {^max}" combined on one line + colour bar ──
    ty0 = layout.TEMP_Y
    draw.rectangle(
        [x0, ty0, x0 + w - 1, ty0 + layout.TEMP_H - 1],
        fill=layout.SIDEBAR_BG,
    )
    if weather is not None:
        temp_str = f"{weather.temperature_c:.0f}\u00b0C ^{weather.temperature_max_c:.0f}\u00b0"
        temp_color = _temp_color(weather.temperature_c)

        bbox = draw.textbbox((0, 0), temp_str, font=font)
        tx = x0 + max(0, (w - (bbox[2] - bbox[0])) // 2)
        draw.text((tx, ty0 + 2), temp_str, font=font, fill=temp_color)

        # Colour-scale temperature bar (2 px tall, near bottom), mirrors the
        # UV widget's gauge so the two rows read as one visual family.
        bar_max = w - 4
        frac = (weather.temperature_c - _TEMP_SCALE_MIN) / (_TEMP_SCALE_MAX - _TEMP_SCALE_MIN)
        bar_w = int(max(0.0, min(frac, 1.0)) * bar_max)
        bar_y = ty0 + layout.TEMP_H - 2
        if bar_w > 0:
            draw.rectangle(
                [x0 + 2, bar_y, x0 + 2 + bar_w - 1, bar_y + 1],
                fill=temp_color,
            )
    else:
        draw.text((x0 + 2, ty0 + 2), "--\u00b0C", font=font, fill=layout.DIM)
