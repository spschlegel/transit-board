"""
Idle scene: a live sky.

The sun crosses an arc between today's real sunrise and sunset (computed
locally from lat/lon, see astro.py); after sunset the moon (current phase)
takes the same arc until sunrise, with a starfield that fills in as it gets
dark. Clouds, rain, snow and lightning follow the current weather code. The
bottom strip shows the next sunrise/sunset.

Everything is drawn with hard-edged, fully-on pixels (no fades or
anti-aliasing — see CLAUDE.md on the LED panel): stars blink rather than
dim, the dusk glow is a dithered band, and clouds are solid sprites. The
sky is composed on its own layer and pasted into the panel region so
sprites can't spill into the info column. The moon's position is decorative
(it just follows the night), not a real ephemeris.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

from PIL import Image, ImageDraw

from transit_board import astro
from transit_board.display import layout
from transit_board.display.renderer import get_draw, get_font, text_pixel_width

if TYPE_CHECKING:
    from transit_board.providers.weather import WeatherData

# ── Moon phase ───────────────────────────────────────────────────────────────

_SYNODIC_MONTH_DAYS = 29.530588853
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def _moon_phase_fraction(now: datetime) -> float:
    """
    Fraction of the way through the current lunar cycle.

    0.0/1.0 = new moon, 0.25 = first quarter, 0.5 = full moon, 0.75 = last
    quarter. Naive *now* is presumed local time (datetime.astimezone()'s
    default behaviour), consistent with the rest of the app (e.g. clock.py's
    datetime.now()).
    """
    days = (now.astimezone(timezone.utc) - _KNOWN_NEW_MOON).total_seconds() / 86400.0
    return (days % _SYNODIC_MONTH_DAYS) / _SYNODIC_MONTH_DAYS


_MOON_LIT = (235, 235, 210, 255)
_MOON_OUTLINE = (55, 55, 65, 255)


@lru_cache(maxsize=8)
def _render_moon(phase_key: float, radius: int) -> Image.Image:
    """
    Render an RGBA disc of the moon at *phase_key* (0-1, see
    _moon_phase_fraction), lit region pale-white and opaque, unlit region
    transparent so the starfield shows through behind it. *phase_key* is
    rounded by the caller before hitting this cache — the phase only moves a
    fraction of a percent per hour, so there's no need to re-rasterize every
    frame.

    Terminator geometry: for a unit circle, the boundary between lit and
    unlit is half of an ellipse whose horizontal extent at height ny is
    cos(2*pi*phase) * sqrt(1-ny^2). Waxing (phase<=0.5) sweeps that curve
    from the right edge (new moon, nothing lit) through the centre (first
    quarter) to the left edge (full moon, everything lit); waning
    (phase>0.5) mirrors the same curve so the lit side flips from right to
    left as it shrinks back to new moon.
    """
    d = radius * 2 + 1
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, d - 1, d - 1], outline=_MOON_OUTLINE)

    theta = 2 * math.pi * phase_key
    cos_t = math.cos(theta)
    waxing = phase_key <= 0.5

    px = img.load()
    for y in range(d):
        ny = (y - radius) / radius
        if abs(ny) > 1:
            continue
        half_chord = math.sqrt(max(0.0, 1 - ny * ny))
        x_term = cos_t * half_chord
        for x in range(d):
            nx = (x - radius) / radius
            if nx * nx + ny * ny > 1:
                continue
            lit = nx >= x_term if waxing else nx <= -x_term
            if lit:
                px[x, y] = _MOON_LIT

    return img


def _phase_key(now: datetime) -> float:
    return round(_moon_phase_fraction(now), 3)


# ── Geometry ─────────────────────────────────────────────────────────────────

_W = layout.DEPARTURES_W
_H = layout.DISPLAY_H
_HORIZON_Y = 51  # sky above, ground below (the text strip lives down there)
_TEXT_Y = 55
_ARC_MARGIN = 7
_ARC_HEIGHT = 38
_SUN_RADIUS = 5
_MOON_RADIUS = 7
_GROUND = (0, 100, 50)
_GLOW = (255, 90, 40)


def _arc_pos(f: float) -> tuple[int, int]:
    """Body centre at progress *f* (0 rising .. 1 setting); half under the horizon at both ends."""
    f = max(0.0, min(1.0, f))
    x = _ARC_MARGIN + f * (_W - 2 * _ARC_MARGIN)
    y = _HORIZON_Y + 1 - math.sin(math.pi * f) * (_ARC_HEIGHT + _SUN_RADIUS)
    return round(x), round(y)


# ── Time of day ──────────────────────────────────────────────────────────────


def _sky_body(lat: float, lon: float, now: datetime, el: float) -> tuple[str, float]:
    """Which body is up and how far along its arc: ("sun"|"moon", 0..1)."""
    day = now.date()
    rise, sett = astro.sun_times(lat, lon, day)
    if rise and sett and rise <= now < sett:
        return "sun", (now - rise) / (sett - rise)

    start = end = None
    if rise and now < rise:
        start, end = astro.sun_times(lat, lon, day - timedelta(days=1))[1], rise
    elif sett and now >= sett:
        start, end = sett, astro.sun_times(lat, lon, day + timedelta(days=1))[0]
    if start and end and end > start:
        return "moon", (now - start) / (end - start)
    return ("sun" if el > 0 else "moon"), 0.5  # polar day/night


def _next_sun_event(lat: float, lon: float, now: datetime) -> Optional[tuple[str, datetime]]:
    day = now.date()
    rise, sett = astro.sun_times(lat, lon, day)
    if rise and now < rise:
        return "SUNRISE", rise
    if sett and now < sett:
        return "SUNSET", sett
    tomorrow_rise = astro.sun_times(lat, lon, day + timedelta(days=1))[0]
    return ("SUNRISE", tomorrow_rise) if tomorrow_rise else None


# ── Weather → sky ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Conditions:
    clouds: int  # how many of _CLOUDS to show
    cover: float  # 0 clear .. 1 overcast — thins out the stars
    dark: bool  # storm/rain-grey clouds instead of white
    precip: Optional[str]  # None | "rain" | "snow" | "storm"


_CLEAR = _Conditions(0, 0.0, False, None)


def _conditions(weather: Optional["WeatherData"]) -> _Conditions:
    if weather is None:
        return _CLEAR
    code = weather.weather_code
    if code == 0:
        return _CLEAR
    if code == 1:
        return _Conditions(1, 0.0, False, None)
    if code == 2:
        return _Conditions(2, 0.5, False, None)
    if code == 3:
        return _Conditions(4, 1.0, False, None)
    if code in (45, 48):
        return _Conditions(4, 1.0, True, None)
    if code in (71, 73, 75, 77, 85, 86):
        return _Conditions(3, 1.0, False, "snow")
    if code >= 95:
        return _Conditions(3, 1.0, True, "storm")
    if 51 <= code <= 67 or 80 <= code <= 82:
        return _Conditions(3, 1.0, True, "rain")
    return _Conditions(2, 0.5, False, None)


# ── Stars ────────────────────────────────────────────────────────────────────

_STAR_COUNT = 24
_STAR_SEED = 20260101  # fixed → stable field across restarts, not regenerated each run


@dataclass(frozen=True)
class _Star:
    x: int
    y: int
    color: tuple[int, int, int]
    period: int  # frames between blinks
    offset: int


def _generate_stars() -> list[_Star]:
    rng = random.Random(_STAR_SEED)
    palette = [(255, 255, 255)] * 4 + [(255, 240, 180), (170, 200, 255)]
    stars: list[_Star] = []
    attempts = 0
    while len(stars) < _STAR_COUNT and attempts < _STAR_COUNT * 50:
        attempts += 1
        x, y = rng.randint(0, _W - 1), rng.randint(0, _HORIZON_Y - 4)
        # Keep stars apart: two touching pixels read as a streak, not two stars.
        if any(abs(x - o.x) < 4 and abs(y - o.y) < 4 for o in stars):
            continue
        stars.append(
            _Star(
                x=x,
                y=y,
                color=rng.choice(palette),
                period=rng.randint(50, 160),
                offset=rng.randint(0, 160),
            )
        )
    return stars


_STARS = _generate_stars()
_BLINK_FRAMES = 6  # a star is off for this many frames each period — a blink, not a fade

# ── Clouds ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _CloudSpec:
    w: int
    h: int
    base_x: int
    y: int
    speed: float  # px per frame


_CLOUDS = [
    _CloudSpec(26, 10, 5, 12, 0.045),
    _CloudSpec(20, 8, 50, 26, 0.03),
    _CloudSpec(30, 11, 28, 5, 0.025),
    _CloudSpec(18, 7, 66, 36, 0.05),
]


@lru_cache(maxsize=32)
def _cloud_sprite(w: int, h: int, color: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill = (*color, 255)
    base_top = int(h * 0.5)
    d.rounded_rectangle([0, base_top, w - 1, h - 1], radius=(h - base_top) // 2, fill=fill)
    d.ellipse([int(w * 0.08), int(h * 0.3), int(w * 0.38), h - 1], fill=fill)
    d.ellipse([int(w * 0.28), 0, int(w * 0.70), h - 2], fill=fill)
    d.ellipse([int(w * 0.58), int(h * 0.25), int(w * 0.92), h - 1], fill=fill)
    return img


def _cloud_color(el: float, dark: bool) -> tuple[int, int, int]:
    day = el > 0
    if dark:
        return (120, 130, 160) if day else (50, 58, 85)
    return (255, 255, 255) if day else (70, 80, 110)


# ── Precipitation ────────────────────────────────────────────────────────────

_RAIN = [(random.Random(7 + i).randint(0, _W - 1), i * 3, 0.9 + (i % 4) * 0.15) for i in range(34)]
_FLAKES = [
    (random.Random(99 + i).randint(0, _W - 1), i * 5, 0.2 + (i % 3) * 0.06, i * 0.9)
    for i in range(24)
]
_RAIN_COLOR = (70, 130, 255)
_LIGHTNING_CYCLE = 240
_LIGHTNING_FRAMES = 4


def _draw_precip(draw: ImageDraw.ImageDraw, kind: str, tick: int) -> None:
    if kind == "snow":
        for x, y0, speed, phase in _FLAKES:
            y = (y0 + tick * speed) % _HORIZON_Y
            fx = x + round(2 * math.sin(tick / 25 + phase))
            draw.point((fx, int(y)), fill=(255, 255, 255))
        return
    count = len(_RAIN) if kind == "storm" else 22
    for x, y0, speed in _RAIN[:count]:
        y = int((y0 + tick * speed * (1.4 if kind == "storm" else 1.0)) % _HORIZON_Y)
        draw.line([(x, y), (x - 1, y + 2)], fill=_RAIN_COLOR)
    if kind == "storm" and tick % _LIGHTNING_CYCLE < _LIGHTNING_FRAMES:
        rng = random.Random(tick // _LIGHTNING_CYCLE)
        x, y = rng.randint(14, _W - 14), 14
        while y < _HORIZON_Y:
            nx = x + rng.choice((-3, 0, 3))
            draw.line([(x, y), (nx, y + 4)], fill=(255, 255, 160), width=1)
            x, y = nx, y + 4


# ── Drawing helpers ──────────────────────────────────────────────────────────


def _draw_sun(draw: ImageDraw.ImageDraw, f: float, el: float, tick: int) -> None:
    cx, cy = _arc_pos(f)
    color = (255, 70, 0) if el < 4 else (255, 140, 0) if el < 12 else (255, 215, 0)
    r = _SUN_RADIUS
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    # Four rays that alternate between + and x so the sun visibly "shimmers".
    diagonal = (tick // 30) % 2 == 1
    offsets = (
        ((7, 7), (-7, 7), (7, -7), (-7, -7)) if diagonal else ((9, 0), (-9, 0), (0, 9), (0, -9))
    )
    for dx, dy in offsets:
        draw.point((cx + dx, cy + dy), fill=color)
        draw.point((cx + dx * 8 // 9, cy + dy * 8 // 9), fill=color)


def _draw_glow(draw: ImageDraw.ImageDraw) -> None:
    """Dusk/dawn band: dithered rows above the horizon, denser toward it."""
    for row, step in ((1, 2), (2, 4), (3, 8)):
        y = _HORIZON_Y - row
        for x in range(row % 2, _W, step):
            draw.point((x, y), fill=_GLOW)


def _draw_strip(layer: Image.Image, label: str, when: datetime) -> None:
    font = get_font(size=8)
    text = f"{label} {when:%H:%M}"
    if text_pixel_width(font, text) > _W - 2:
        text = f"{label[:4]} {when:%H:%M}"  # SUNR / SUNS fallback if it ever overflows
    color = layout.ORANGE if label == "SUNSET" else layout.YELLOW
    x = max(0, (_W - text_pixel_width(font, text)) // 2)
    get_draw(layer).text((x, _TEXT_Y), text, font=font, fill=color)


# ── Public draw function ──────────────────────────────────────────────────────


def draw_idle(
    image: Image.Image,
    tick: int = 0,
    now: datetime | None = None,
    weather: Optional["WeatherData"] = None,
    *,
    lat: float,
    lon: float,
) -> None:
    """Render the live sky into the departures-panel region of *image*."""
    now = (now or datetime.now()).astimezone()
    el = astro.solar_elevation_deg(lat, lon, now)
    cond = _conditions(weather)
    body, f = _sky_body(lat, lon, now, el)

    layer = Image.new("RGB", (_W, _H), (0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # Stars fill in as the sun drops below -2° (discrete count, no dimming), and
    # cloud cover hides them.
    if el < -2:
        dark = min(1.0, (-2 - el) / 10)
        for star in _STARS[: int(len(_STARS) * dark * (1 - cond.cover))]:
            if (tick + star.offset) % star.period >= _BLINK_FRAMES:
                draw.point((star.x, star.y), fill=star.color)

    if -6 < el < 8:
        _draw_glow(draw)

    if body == "sun":
        _draw_sun(draw, f, el, tick)
    else:
        moon = _render_moon(_phase_key(now), _MOON_RADIUS)
        cx, cy = _arc_pos(f)
        layer.paste(moon, (cx - _MOON_RADIUS, cy - _MOON_RADIUS), moon)

    color = _cloud_color(el, cond.dark)
    for spec in _CLOUDS[: cond.clouds]:
        x = (spec.base_x + tick * spec.speed) % (_W + spec.w) - spec.w
        sprite = _cloud_sprite(spec.w, spec.h, color)
        layer.paste(sprite, (round(x), spec.y), sprite)

    if cond.precip:
        _draw_precip(draw, cond.precip, tick)

    # Ground hides the lower half of a rising/setting body; the line marks the horizon.
    draw.rectangle([0, _HORIZON_Y, _W - 1, _H - 1], fill=(0, 0, 0))
    draw.line([(0, _HORIZON_Y), (_W - 1, _HORIZON_Y)], fill=_GROUND)

    event = _next_sun_event(lat, lon, now)
    if event:
        _draw_strip(layer, *event)

    image.paste(layer, (layout.DEPARTURES_X, 0))
