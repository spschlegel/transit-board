"""Right-sidebar weather widget: temperature + pixel-art icon + condition label."""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from transit_board.display import layout
from transit_board.display.renderer import get_font
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


def _draw_icon(image: Image.Image, ox: int, oy: int, code: int) -> None:
    """Render a 7×7 weather icon with top-left at (ox, oy)."""
    draw = ImageDraw.Draw(image)

    if code <= 1:  # Clear
        for x, y in _SUN:
            draw.point((ox + x, oy + y), fill=layout.YELLOW)

    elif code <= 2:  # Partly cloudy — two colours
        for x, y in _PARTLY:
            color = layout.YELLOW if (x, y) in _PARTLY_SUN else layout.WHITE
            draw.point((ox + x, oy + y), fill=color)

    elif code <= 3:  # Overcast
        for x, y in _CLOUD:
            draw.point((ox + x, oy + y), fill=layout.DIM)

    elif code < 70:  # Rain / drizzle
        for x, y in _RAIN:
            color = layout.BLUE if y >= 5 else layout.TEAL
            draw.point((ox + x, oy + y), fill=color)

    elif code < 80:  # Snow
        for x, y in _SNOW:
            draw.point((ox + x, oy + y), fill=layout.WHITE)

    elif code < 90:  # Rain showers
        for x, y in _RAIN:
            color = layout.BLUE if y >= 5 else layout.WHITE
            draw.point((ox + x, oy + y), fill=color)

    else:  # Thunderstorm
        for x, y in _STORM:
            color = layout.YELLOW if (x, y) in _STORM_LIGHTNING else layout.DIM
            draw.point((ox + x, oy + y), fill=color)


# ── Public draw function ──────────────────────────────────────────────────────


def draw_weather(
    image: Image.Image,
    weather: Optional[WeatherData],
    tick: int = 0,
    font_path: str | None = None,
) -> None:
    """Render temperature (TEMP section) and icon+label (WEATHER section) in info strip."""
    draw = ImageDraw.Draw(image)
    font = get_font(font_path, size=8)
    font_sm = get_font(font_path, size=7)

    # ── Temperature section ─────────────────────────────────────────────────────
    tx0 = layout.TEMP_X
    draw.rectangle(
        [tx0, layout.INFO_Y, tx0 + layout.TEMP_W - 1, layout.INFO_Y + layout.INFO_H - 1],
        fill=layout.SIDEBAR_BG,
    )
    if weather is not None:
        temp_str = f"{weather.temperature_c:.0f}\u00b0C"  # °C
        bbox = draw.textbbox((0, 0), temp_str, font=font)
        tw = bbox[2] - bbox[0]
        tx = tx0 + max(0, (layout.TEMP_W - tw) // 2)
        draw.text((tx, layout.INFO_Y + 11), temp_str, font=font, fill=layout.YELLOW)
    else:
        draw.text((tx0 + 2, layout.INFO_Y + 11), "--\u00b0C", font=font, fill=layout.DIM)

    # ── Weather section: current icon (left) + forecast icon (right) ───────────────────
    # Layout (40 px wide, 31 px tall):
    #   Left 19 px  — current icon + "NOW" label
    #   1 px sep at wx0+19
    #   Right 20 px — forecast icon + "DAY" label
    #   Bottom row: current condition label, full width
    wx0 = layout.WEATHER_X
    ww = layout.WEATHER_W  # 40
    y0 = layout.INFO_Y
    draw.rectangle(
        [wx0, y0, wx0 + ww - 1, y0 + layout.INFO_H - 1],
        fill=layout.SIDEBAR_BG,
    )
    if weather is not None:
        # Icons at top of section
        left_icon_x = wx0 + (19 - 7) // 2  # centred in left 19 px
        right_icon_x = wx0 + 20 + (20 - 7) // 2  # centred in right 20 px
        icon_y = y0 + 2
        _draw_icon(image, left_icon_x, icon_y, weather.weather_code)
        _draw_icon(image, right_icon_x, icon_y, weather.forecast_weather_code)

        # Thin vertical separator between the two halves
        draw.line(
            [(wx0 + 19, y0 + 2), (wx0 + 19, y0 + 18)],
            fill=layout.SECTION_DIV,
        )

        # Condition abbreviations under each icon (NOW=current, DAY=today's forecast)
        for cond_txt, half_x, half_w in (
            (weather.short_label, wx0, 19),
            (weather.forecast_short_label, wx0 + 20, 20),
        ):
            bbox = draw.textbbox((0, 0), cond_txt, font=font_sm)
            lw = bbox[2] - bbox[0]
            draw.text(
                (half_x + (half_w - lw) // 2, y0 + 11), cond_txt, font=font_sm, fill=layout.TEAL
            )
    else:
        draw.text((wx0 + 12, y0 + 11), "---", font=font, fill=layout.DIM)
