"""
Breaking-news widget: a red "BREAKING" header and the word-wrapped headline.

Draws into a caller-supplied box: the full right panel (over the sky scene) or
one stop slot (next to departures or scores). When the headline needs more
lines than fit, it pages through them every _PAGE_FRAMES frames rather than
scrolling, so each page is a still, readable block on the panel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

from transit_board.display import layout
from transit_board.display.renderer import get_draw, get_font, text_pixel_width

if TYPE_CHECKING:
    from transit_board.providers.news import NewsAlert

_PAGE_FRAMES = 80  # ~4 s per page at 20 FPS
_PAD = 2


def _wrap(text: str, font: object, max_w: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        while text_pixel_width(font, word) > max_w:  # a single word wider than the box
            cut = len(word)
            while cut > 1 and text_pixel_width(font, word[:cut]) > max_w:
                cut -= 1
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:cut])
            word = word[cut:]
        candidate = f"{line} {word}" if line else word
        if text_pixel_width(font, candidate) <= max_w:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_news(
    image: Image.Image,
    alert: "NewsAlert",
    x0: int,
    y0: int,
    w: int,
    h: int,
    tick: int = 0,
    font_path: str | None = None,
) -> None:
    font = get_font(font_path, size=8)
    draw = get_draw(image)

    # Header: accent bar + "BREAKING" (same idiom as a stop header), time on the right.
    draw.rectangle([x0, y0, x0 + 2, y0 + layout.HEADER_H - 1], fill=layout.RED)
    draw.text((x0 + 5, y0), "BREAKING", font=font, fill=layout.RED)
    stamp = alert.qualified_at.astimezone().strftime("%H:%M")
    draw.text(
        (x0 + w - _PAD - text_pixel_width(font, stamp), y0), stamp, font=font, fill=layout.WHITE
    )

    lines = _wrap(alert.headline, font, w - 2 * _PAD)
    rows = max(1, (h - layout.HEADER_H) // layout.ROW_H)
    pages = max(1, -(-len(lines) // rows))
    page = (tick // _PAGE_FRAMES) % pages
    shown = lines[page * rows : (page + 1) * rows]

    # Centre the block in the space below the header; text sits 1 px above the row top
    # so glyph ink is centred in the 8 px row (same convention as departures rows).
    body_h = h - layout.HEADER_H
    y = y0 + layout.HEADER_H + max(0, (body_h - len(shown) * layout.ROW_H) // 2)
    for line in shown:
        draw.text((x0 + _PAD, y - 1), line, font=font, fill=layout.WHITE)
        y += layout.ROW_H

    if pages > 1:  # page indicator: one pixel per page in the header gap, current one red
        for p in range(pages):
            px = x0 + w - _PAD - text_pixel_width(font, stamp) - 4 - 2 * (pages - 1 - p)
            draw.point((px, y0 + 3), fill=layout.RED if p == page else layout.WHITE)
