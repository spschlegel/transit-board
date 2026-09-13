"""
Idle-mode widget: moon (current phase) + a twinkling starfield.

Meant to replace the departures panel late at night once MBTA service has
stopped running — not wired into the render loop yet, this is just the
moon/starfield rendering itself.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from PIL import Image, ImageDraw

from transit_board.display import layout

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


# ── Starfield ────────────────────────────────────────────────────────────────

_MOON_RADIUS = 18
_MOON_CX = layout.DEPARTURES_X + layout.DEPARTURES_W // 2
_MOON_CY = layout.DISPLAY_H // 2

_STAR_COUNT = 22
_STAR_SEED = 20260101  # fixed → stable field across restarts, not regenerated each run


@dataclass(frozen=True)
class _Star:
    x: int
    y: int
    base_level: int  # baseline brightness, 0-255
    twinkle_amp: int  # +/- swing around base_level
    period_frames: int  # frames per full twinkle cycle
    phase_offset: float


def _generate_stars(cx: int, cy: int, exclude_radius: int) -> list[_Star]:
    rng = random.Random(_STAR_SEED)
    x_lo, x_hi = layout.DEPARTURES_X, layout.DISPLAY_W - 1
    y_lo, y_hi = 0, layout.DISPLAY_H - 1
    exclude_r2 = exclude_radius * exclude_radius

    stars: list[_Star] = []
    attempts = 0
    while len(stars) < _STAR_COUNT and attempts < _STAR_COUNT * 30:
        attempts += 1
        x = rng.randint(x_lo, x_hi)
        y = rng.randint(y_lo, y_hi)
        if (x - cx) ** 2 + (y - cy) ** 2 <= exclude_r2:
            continue  # leave the moon's own footprint star-free
        stars.append(
            _Star(
                x=x,
                y=y,
                base_level=rng.randint(90, 160),
                twinkle_amp=rng.randint(40, 95),
                period_frames=rng.randint(40, 140),
                phase_offset=rng.uniform(0, 2 * math.pi),
            )
        )
    return stars


_STARS = _generate_stars(_MOON_CX, _MOON_CY, _MOON_RADIUS + 3)


# ── Public draw function ──────────────────────────────────────────────────────


def draw_idle(image: Image.Image, tick: int = 0, now: datetime | None = None) -> None:
    """Render the moon (current phase) + twinkling starfield into the departures panel."""
    now = now or datetime.now()

    for star in _STARS:
        level = star.base_level + star.twinkle_amp * math.sin(
            2 * math.pi * tick / star.period_frames + star.phase_offset
        )
        level = max(30, min(255, int(level)))
        image.putpixel((star.x, star.y), (level, level, level))

    moon = _render_moon(_phase_key(now), _MOON_RADIUS)
    top_left = (_MOON_CX - _MOON_RADIUS, _MOON_CY - _MOON_RADIUS)
    image.paste(moon, top_left, moon)
