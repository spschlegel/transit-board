"""
Sports scores widget — draws into a caller-supplied bounding box (either one
stop-slot for hybrid mode, or the full departures-panel region for a full
takeover).

Always logo-forward: a game's card shows each competitor's logo (falling
back to a coloured abbreviation chip only when no logo is available), the
score between them, and — when there's enough room — a status line below.
Preferring legible logos over cramming more games on screen means fewer
games are visible per page when there's a lot going on (e.g. a full NFL
Sunday) — the overflow pages through the rest every _PAGE_FRAMES frames
instead.

The status line (game clock, "3rd", "Final", etc) is drawn at the same 8px
font as the score rather than the 7px chip font used for abbreviations —
Tiny5 only rasterizes cleanly at 8px/16px (see CLAUDE.md), and at 7px
arbitrary ESPN strings (colons in a clock like "2:16", letter pairs like the
"la" in "Final") showed visible glyph-spacing artifacts. The 7px chip font
stays fine for abbreviations, which are always short, font-tested strings.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from PIL import Image, ImageDraw

from transit_board.display import layout
from transit_board.display.renderer import (
    draw_chip,
    draw_text_clipped,
    get_draw,
    get_font,
    text_pixel_width,
)

if TYPE_CHECKING:
    from transit_board.providers.logos import LogoCache
    from transit_board.providers.sports import Game

# Floor height per game: SPORTS_LOGO_SIZE_SPACIOUS (14px) plus the 3px top
# margin below the league accent bar, with no slack — below this we page
# through games instead of shrinking logos further (there's no legible size
# between "logo" and "abbreviation chip", see providers/logos.py).
_MIN_GAME_H = 17
_PAGE_FRAMES = 400  # ~20s/page at 20fps


def _visible_count(n_games: int, h: int) -> int:
    max_fit = max(1, h // _MIN_GAME_H)
    return min(n_games, max_fit)


def _draw_game(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    game: "Game",
    x0: int,
    y0: int,
    w: int,
    h: int,
    tick: int,
    font: object,
    font_chip: object,
    logo_cache: Optional["LogoCache"],
) -> None:
    accent = layout.SPORT_COLORS.get(game.league, layout.WHITE)
    draw.rectangle([x0, y0, x0 + w - 1, y0 + 1], fill=accent)

    away, home = game.competitors
    logo_size = layout.SPORTS_LOGO_SIZE_SPACIOUS
    pad = 2
    content_y0 = y0 + 3
    content_h = max(1, h - 3)
    logo_y = content_y0 + max(0, (content_h - logo_size) // 2)
    chip_y = logo_y + max(0, (logo_size - 7) // 2)

    away_img = logo_cache.get_sync(away.logo_url) if logo_cache else None
    if away_img is not None:
        image.paste(away_img, (x0 + pad, logo_y), away_img)
        left_edge = x0 + pad + logo_size
    else:
        chip_w = draw_chip(image, x0 + pad, chip_y, away.abbreviation, accent, font_chip, pad_x=1)
        left_edge = x0 + pad + chip_w

    home_img = logo_cache.get_sync(home.logo_url) if logo_cache else None
    if home_img is not None:
        right_start = x0 + w - pad - logo_size
        image.paste(home_img, (right_start, logo_y), home_img)
        right_edge = right_start
    else:
        text_w = text_pixel_width(font_chip, home.abbreviation) + 2
        right_start = x0 + w - pad - text_w
        draw_chip(image, right_start, chip_y, home.abbreviation, accent, font_chip, pad_x=1)
        right_edge = right_start

    mid_x0 = left_edge + 2
    mid_x1 = right_edge - 2
    mid_w = mid_x1 - mid_x0
    if mid_w <= 0:
        return

    # For tennis, .score is sets won (the headline number, like a team
    # sport's score); the current set's in-progress game score is a second,
    # more granular number shown on the status line below when there's room.
    score_text = f"{away.score}-{home.score}" if (away.score or home.score) else "vs"
    score_w = text_pixel_width(font, score_text)
    score_x = mid_x0 + max(0, (mid_w - score_w) // 2)
    has_status_line = content_h >= 18
    score_y = content_y0 + (
        max(0, (content_h - 17) // 2) if has_status_line else max(0, (content_h - 8) // 2)
    )
    draw.text((score_x, score_y), score_text, font=font, fill=layout.WHITE)

    if has_status_line:
        if game.league == "tennis" and away.game_score and home.game_score:
            status_text = f"{game.status_detail} {away.game_score}-{home.game_score}".strip()
        else:
            status_text = game.status_detail or ("FINAL" if game.status != "in" else "")
        if status_text:
            status_w = text_pixel_width(font, status_text)
            status_x = mid_x0 + max(0, (mid_w - status_w) // 2) if status_w <= mid_w else mid_x0
            status_y = score_y + 9
            draw_text_clipped(
                image=image,
                xy=(status_x, status_y),
                text=status_text,
                font=font,
                color=layout.WHITE,
                max_width=mid_w,
                row_h=8,
                scroll_offset=tick,
            )


def draw_scores(
    image: Image.Image,
    games: list["Game"],
    logo_cache: Optional["LogoCache"],
    x0: int,
    y0: int,
    w: int,
    h: int,
    tick: int = 0,
    font_path: Optional[str] = None,
) -> None:
    """
    Render *games* (already filtered+sorted by providers.sports.relevant_games
    — this function does not re-filter) into the x0/y0/w/h box. Used both for
    a single hybrid stop-slot and for the full departures-panel region.
    """
    font = get_font(font_path, size=8)
    font_chip = get_font(font_path, size=7)
    draw = get_draw(image)

    if not games:
        msg = "No games"
        bbox = draw.textbbox((0, 0), msg, font=font)
        mw = bbox[2] - bbox[0]
        mx = x0 + max(0, (w - mw) // 2)
        my = y0 + max(0, (h - 8) // 2)
        draw.text((mx, my), msg, font=font, fill=layout.WHITE)
        return

    visible = _visible_count(len(games), h)
    n_pages = max(1, math.ceil(len(games) / visible))
    page = (tick // _PAGE_FRAMES) % n_pages
    page_games = games[page * visible : page * visible + visible]

    per_game_h = h // max(1, len(page_games))
    y = y0
    for game in page_games:
        _draw_game(image, draw, game, x0, y, w, per_game_h, tick, font, font_chip, logo_cache)
        y += per_game_h
