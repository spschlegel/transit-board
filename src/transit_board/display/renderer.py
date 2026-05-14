"""Pillow rendering helpers used by all widgets."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Font cache keyed by (path_or_None, size)
_font_cache: dict[tuple[Optional[str], int], ImageFont.ImageFont] = {}


def get_font(path: Optional[str] = None, size: int = 8) -> ImageFont.ImageFont:
    """
    Return a cached Pillow font.

    If *path* points to an existing TTF/OTF file it is loaded at *size* pt.
    Falls back to Pillow's built-in default font (requires Pillow >= 10.0).
    """
    key = (path, size)
    if key not in _font_cache:
        font: ImageFont.ImageFont
        if path and Path(path).exists():
            try:
                font = ImageFont.truetype(path, size)
            except Exception:
                font = ImageFont.load_default(size=size)
        else:
            font = ImageFont.load_default(size=size)
        _font_cache[key] = font
    return _font_cache[key]


def new_canvas(width: int = 128, height: int = 64) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Return a fresh black RGB image and its draw context."""
    img = Image.new("RGB", (width, height), (0, 0, 0))
    return img, ImageDraw.Draw(img)


def text_pixel_width(font: ImageFont.ImageFont, text: str) -> int:
    """Return the rendered pixel width of *text* in *font*."""
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = tmp.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def draw_text_clipped(
    image: Image.Image,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    color: tuple[int, int, int],
    max_width: int,
    row_h: int = 8,
    scroll_offset: int = 0,
) -> None:
    """
    Draw *text* at *xy*, clipped to *max_width* pixels.

    If the text is wider it scrolls horizontally using *scroll_offset* (px).
    A 16 px gap separates the end of the text from the looped start.
    """
    tw = text_pixel_width(font, text)

    if tw <= max_width:
        draw = ImageDraw.Draw(image)
        draw.text(xy, text, font=font, fill=color)
        return

    gap = 16
    period = tw + gap
    surf = Image.new("RGB", (period * 2, row_h), (0, 0, 0))
    surf_draw = ImageDraw.Draw(surf)
    surf_draw.text((0, 0), text, font=font, fill=color)
    surf_draw.text((period, 0), text, font=font, fill=color)

    offset = int(scroll_offset) % period
    clip = surf.crop((offset, 0, offset + max_width, row_h))
    image.paste(clip, (xy[0], xy[1]))


def draw_chip(
    image: Image.Image,
    x: int,
    y: int,
    text: str,
    fg_color: tuple[int, int, int],
    font: ImageFont.ImageFont,
    pad_x: int = 3,
    chip_h: int = 6,
) -> int:
    """
    Draw a coloured route "chip" (pill with tinted background) at (x, y).

    The chip is *chip_h* pixels tall and wide enough to hold *text* with
    *pad_x* pixels of horizontal padding on each side.

    Returns the chip pixel width so the caller can position the next element.
    """
    tw = text_pixel_width(font, text)
    chip_w = tw + pad_x * 2

    # Background: ~20 % brightness of the fg colour
    bg = tuple(max(0, int(c * 0.20)) for c in fg_color)

    draw = ImageDraw.Draw(image)
    draw.rectangle([x, y, x + chip_w - 1, y + chip_h - 1], fill=bg)
    draw.text((x + pad_x, y), text, font=font, fill=fg_color)

    return chip_w


def draw_panel_chrome(image: Image.Image) -> None:
    """
    Draw structural chrome on top of all widget layers (always drawn last):
      • Horizontal divider at HORIZ_DIV_Y — full width
      • Vertical stop divider at STOP_DIV_X — transit panel only (y 0..TRANSIT_H-1)
      • Vertical info-strip dividers at INFO_DIV_XS — info strip only (y INFO_Y..DISPLAY_H-1)
    """
    from transit_board.display import layout

    draw = ImageDraw.Draw(image)

    # Horizontal transit / info-strip divider
    draw.line(
        [(0, layout.HORIZ_DIV_Y), (layout.DISPLAY_W - 1, layout.HORIZ_DIV_Y)],
        fill=layout.PANEL_DIVIDER,
    )

    # Vertical divider between stop 1 and stop 2 (transit panel only)
    draw.line(
        [(layout.STOP_DIV_X, 0), (layout.STOP_DIV_X, layout.TRANSIT_H - 1)],
        fill=layout.PANEL_DIVIDER,
    )

    # Vertical dividers within the info strip
    for div_x in layout.INFO_DIV_XS:
        draw.line(
            [(div_x, layout.INFO_Y), (div_x, layout.DISPLAY_H - 1)],
            fill=layout.SECTION_DIV,
        )
