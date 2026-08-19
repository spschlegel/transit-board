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
    pause_frames: int = 60,
    end_pause_frames: int = 40,
    scroll_speed_inv: int = 2,
) -> None:
    """
    Draw *text* at *xy*, clipped to *max_width* pixels.

    If the text is wider than *max_width*, it uses a pause-scroll-pause cycle:
      1. Show start of text for *pause_frames* frames (start pause)
      2. Scroll 1 px per *scroll_speed_inv* frames until end of text is visible
      3. Hold end of text for *end_pause_frames* frames (end pause)
      4. Jump back to start and repeat

    *scroll_offset* is treated as a frame counter (increments by 1 per frame).
    """
    tw = text_pixel_width(font, text)

    if tw <= max_width:
        draw = ImageDraw.Draw(image)
        draw.text(xy, text, font=font, fill=color)
        return

    overflow = tw - max_width
    scroll_frames = overflow * scroll_speed_inv
    cycle = pause_frames + scroll_frames + end_pause_frames

    phase = int(scroll_offset) % cycle
    if phase < pause_frames:
        visual_offset = 0
    elif phase < pause_frames + scroll_frames:
        visual_offset = (phase - pause_frames) // scroll_speed_inv
    else:
        visual_offset = overflow

    # Render onto a surface tall enough to hold the full glyph (including
    # descenders), but always crop starting at y=0 so the scrolling path
    # lands on exactly the same row as the direct draw.text() call above.
    # (A previous version cropped from the glyph's measured top, which made
    # scrolling text render 1-2px higher than static text at the same xy —
    # visible as misaligned headers when one stop's name scrolled and the
    # other's didn't.)
    surf_w = tw + 4
    surf_h = row_h + 4
    surf = Image.new("RGB", (surf_w, surf_h), (0, 0, 0))
    surf_draw = ImageDraw.Draw(surf)
    surf_draw.text((0, 0), text, font=font, fill=color)

    visual_offset = max(0, min(visual_offset, surf_w - max_width))
    clip = surf.crop((visual_offset, 0, visual_offset + max_width, row_h))
    image.paste(clip, (xy[0], xy[1]))


def draw_chip(
    image: Image.Image,
    x: int,
    y: int,
    text: str,
    fg_color: tuple[int, int, int],
    font: ImageFont.ImageFont,
    pad_x: int = 3,
) -> int:
    """
    Draw a coloured route label at (x, y), padded *pad_x* pixels on each side.

    No background fill — a tinted box behind small route text made it harder
    to read on the LED panel, so colour now comes from the text alone.

    Returns the pixel width (including padding) so the caller can position
    the next element.
    """
    tw = text_pixel_width(font, text)
    chip_w = tw + pad_x * 2

    draw = ImageDraw.Draw(image)
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
