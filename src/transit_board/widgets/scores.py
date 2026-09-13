"""
Sports scores widget — draws into a caller-supplied bounding box (either one
stop-slot for hybrid mode, or the full departures-panel region for a full
takeover), following the same visual language as widgets/departures.py
(chips, urgency colour, scrolling overflow) rather than inventing a new one.

Density is tier-selected, not continuously scaled: with only 8px/16px text
legible on the bundled font (see CLAUDE.md), there are effectively two usable
densities, not a smooth continuum — a "card" tier with a team/player logo
when there's room (>= _CARD_MIN_H px/game), and a compact "row" tier (one 8px
line/game, abbreviations only) when there isn't. More relevant games than fit
even at the row-tier floor page-flip every _PAGE_FRAMES frames.
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

_CARD_MIN_H = 20  # px/game — below this, fall back to the abbreviation-only row tier
_PAGE_FRAMES = 600  # ~30s/page at 20fps — long enough to actually read a page of scores

_LEAGUE_TAG = {"nfl": "NFL", "bundesliga": "BUN", "mlb": "MLB", "tennis": "TEN"}


def _plan(n_games: int, h: int) -> tuple[int, str]:
    """Return (games_visible_per_page, tier in {"card", "row"})."""
    if n_games <= 0:
        return 0, "row"
    max_rows = max(1, h // layout.ROW_H)
    visible = min(n_games, max_rows)
    per_game_h = h // visible
    tier = "card" if per_game_h >= _CARD_MIN_H else "row"
    return visible, tier


def _draw_row(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    game: "Game",
    x0: int,
    y0: int,
    w: int,
    font: object,
    font_chip: object,
    tick: int,
) -> None:
    away, home = game.competitors
    accent = layout.SPORT_COLORS.get(game.league, layout.WHITE)
    league_tag = _LEAGUE_TAG.get(game.league, game.league[:3].upper())

    chip_w = draw_chip(image, x0 + 1, y0, league_tag, accent, font_chip, pad_x=1)

    is_live = game.status == "in"
    status_label = "LIVE" if is_live else "FIN"
    status_w = text_pixel_width(font, status_label)
    status_x = x0 + w - status_w - 3
    if is_live:
        blink = (tick // 15) % 2 == 0
        status_color = layout.GREEN if blink else (0, 130, 0)
    else:
        status_color = layout.WHITE
    draw.text((status_x, y0), status_label, font=font, fill=status_color)

    if is_live:
        draw.point((x0 + w - 1, y0 + 1), fill=layout.GREEN)

    mid_text = f"{away.abbreviation} {away.score}-{home.score} {home.abbreviation}".strip()
    mid_x = x0 + 1 + chip_w + 2
    mid_max_w = status_x - mid_x - 3
    if mid_max_w > 0:
        draw_text_clipped(
            image=image,
            xy=(mid_x, y0),
            text=mid_text,
            font=font,
            color=layout.TEAL,
            max_width=mid_max_w,
            row_h=layout.ROW_H + 2,
            scroll_offset=tick,
        )


def _draw_card(
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

    score_text = f"{away.score}-{home.score}" if (away.score or home.score) else "vs"
    score_w = text_pixel_width(font, score_text)
    score_x = mid_x0 + max(0, (mid_w - score_w) // 2)
    has_status_line = content_h >= 18
    score_y = content_y0 + (
        max(0, (content_h - 17) // 2) if has_status_line else max(0, (content_h - 8) // 2)
    )
    draw.text((score_x, score_y), score_text, font=font, fill=layout.WHITE)

    if has_status_line:
        status_text = game.status_detail or ("LIVE" if game.status == "in" else "FINAL")
        status_w = text_pixel_width(font_chip, status_text)
        if status_w > mid_w:
            status_text = "LIVE" if game.status == "in" else "FIN"
            status_w = text_pixel_width(font_chip, status_text)
        status_x = mid_x0 + max(0, (mid_w - status_w) // 2)
        status_y = score_y + 9
        blink = (tick // 15) % 2 == 0
        status_color = (
            (layout.GREEN if blink else (0, 130, 0)) if game.status == "in" else layout.WHITE
        )
        draw.text((status_x, status_y), status_text, font=font_chip, fill=status_color)


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

    visible, tier = _plan(len(games), h)
    n_pages = max(1, math.ceil(len(games) / visible))
    page = (tick // _PAGE_FRAMES) % n_pages
    page_games = games[page * visible : page * visible + visible]

    per_game_h = h // max(1, len(page_games))
    y = y0
    for game in page_games:
        if tier == "card":
            _draw_card(image, draw, game, x0, y, w, per_game_h, tick, font, font_chip, logo_cache)
        else:
            _draw_row(image, draw, game, x0, y, w, font, font_chip, tick)
        y += per_game_h
