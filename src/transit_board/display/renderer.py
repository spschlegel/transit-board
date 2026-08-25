"""Pillow rendering helpers used by all widgets."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Bundled pixel font (Tiny5, SIL OFL) — a thin monospace-ish pixel font whose
# glyph ink fits inside an 8px row at size 8 (ascent 7 / descent 2, drawn at
# rows 2-7) with no vertical clipping or offset tricks needed. Unlike Pillow's
# built-in default font (unreadable at panel sizes — 5/6 collide, antialiased)
# or Silkscreen (legible but its 11px line height overflowed the 8px row grid
# and looked chunkier than needed at this size).
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_DEFAULT_FONT_PATH = str(_FONT_DIR / "Tiny5-Regular.ttf")

# Font cache keyed by (path_or_None, size)
_font_cache: dict[tuple[Optional[str], int], ImageFont.ImageFont] = {}


def get_font(path: Optional[str] = None, size: int = 8) -> ImageFont.ImageFont:
    """
    Return a cached Pillow font.

    If *path* points to an existing TTF/OTF file it is loaded at *size* pt.
    Falls back to the bundled Silkscreen pixel font, then to Pillow's built-in
    default font if that's somehow missing.
    """
    path = path or _DEFAULT_FONT_PATH
    key = (path, size)
    if key not in _font_cache:
        font: ImageFont.ImageFont
        if Path(path).exists():
            try:
                font = ImageFont.truetype(path, size)
            except Exception:
                font = ImageFont.load_default(size=size)
        else:
            font = ImageFont.load_default(size=size)
        _font_cache[key] = font
    return _font_cache[key]


def get_draw(image: Image.Image) -> ImageDraw.ImageDraw:
    """
    Return an ImageDraw context configured for crisp, fully-lit LED text.

    fontmode="1" disables FreeType antialiasing so every glyph pixel is drawn
    either fully on or fully off — an antialiased edge pixel renders as a dim,
    partial-brightness grey on the physical panel instead of a clean line.
    Non-text drawing (rectangles, lines, points) is unaffected by fontmode, so
    this is a drop-in replacement for ImageDraw.Draw(image) everywhere.
    """
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"
    return draw


def new_canvas(width: int = 128, height: int = 64) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Return a fresh black RGB image and its draw context."""
    img = Image.new("RGB", (width, height), (0, 0, 0))
    return img, get_draw(img)


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
        draw = get_draw(image)
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
    surf_draw = get_draw(surf)
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

    draw = get_draw(image)
    draw.text((x + pad_x, y), text, font=font, fill=fg_color)

    return chip_w


def draw_panel_chrome(image: Image.Image, departures_per_stop: int = 3) -> None:
    """
    Draw structural chrome on top of all widget layers (always drawn last):
      • Vertical divider at VERT_DIV_X — full height, info column vs. departures
      • Horizontal stop divider — departures column only, position depends on
        *departures_per_stop* (must match what draw_departures() was called
        with — see layout.stop_panel_layout())
      • Horizontal info-column dividers at INFO_DIV_YS — info column only
    """
    from transit_board.display import layout

    draw = ImageDraw.Draw(image)

    # Vertical divider between info column and departures (full height)
    draw.line(
        [(layout.VERT_DIV_X, 0), (layout.VERT_DIV_X, layout.DISPLAY_H - 1)],
        fill=layout.PANEL_DIVIDER,
    )

    # Horizontal divider between stop 1 and stop 2 (departures column only)
    top_margin, panel_h = layout.stop_panel_layout(departures_per_stop)
    stop_div_y = top_margin + panel_h
    draw.line(
        [
            (layout.DEPARTURES_X, stop_div_y),
            (layout.DEPARTURES_X + layout.DEPARTURES_W - 1, stop_div_y),
        ],
        fill=layout.PANEL_DIVIDER,
    )

    # Horizontal dividers within the info column
    for div_y in layout.INFO_DIV_YS:
        draw.line(
            [(layout.INFO_X, div_y), (layout.INFO_X + layout.INFO_W - 1, div_y)],
            fill=layout.SECTION_DIV,
        )
