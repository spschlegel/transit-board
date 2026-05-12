"""Left-panel widget: departure rows with route chips and urgency colouring."""

from __future__ import annotations

from PIL import Image, ImageDraw

from transit_board.config import StopConfig
from transit_board.display import layout
from transit_board.display.renderer import (
    draw_chip,
    draw_text_clipped,
    get_font,
    text_pixel_width,
)
from transit_board.providers.transit import Departure

# ── Helpers ───────────────────────────────────────────────────────────────────


def _route_color(route: str, stop_type: str) -> tuple[int, int, int]:
    lower = route.lower()
    for name, color in layout.LINE_COLORS.items():
        if name in lower:
            return color
    return layout.ROUTE_COLORS.get(stop_type, layout.WHITE)


def _minutes_color(minutes: int, realtime: bool) -> tuple[int, int, int]:
    if not realtime:
        return layout.DIM
    if minutes <= 2:
        return layout.GREEN
    if minutes <= 5:
        return layout.YELLOW
    if minutes <= 9:
        return (255, 155, 0)  # amber
    return layout.WHITE


def _minutes_label(minutes: int) -> str:
    if minutes == 0:
        return "BRD"
    return f"{minutes}m"


# ── Public draw function ──────────────────────────────────────────────────────


def draw_departures(
    image: Image.Image,
    stops: list[StopConfig],
    departures_by_stop: dict[str, list[Departure]],
    departures_per_stop: int,
    scroll_offset: int,
    tick: int = 0,
    font_path: str | None = None,
) -> None:
    """
    Render the departure board into the left 95×64 px region of *image*.

    Per stop (HEADER_H=8 + departures_per_stop×ROW_H=3×8=24 = 32 px):
      • 3 px coloured left-edge accent bar
      • Stop name right of bar
      • Departure rows: [route chip] [scrolling headsign] [Nm / BRD]  •realtime dot
    Two stops × 32 px = 64 px — fills the panel exactly.
    """
    draw = ImageDraw.Draw(image)
    font = get_font(font_path, size=8)
    font_chip = get_font(font_path, size=7)

    x0 = layout.DEPART_X
    panel_w = layout.DEPART_W
    y = layout.DEPART_Y

    # BRD blink state: alternate every 15 frames
    brd_bright = (tick // 15) % 2 == 0

    for stop in stops:
        if y >= layout.DISPLAY_H:
            break

        deps = departures_by_stop.get(stop.id, [])
        stop_color = layout.ROUTE_COLORS.get(stop.type, layout.WHITE)

        # ── Stop header ───────────────────────────────────────────────────────
        # Dark background
        draw.rectangle([x0, y, x0 + panel_w - 1, y + layout.HEADER_H - 1], fill=layout.SIDEBAR_BG)
        # 3 px coloured left accent bar
        draw.rectangle([x0, y, x0 + 2, y + layout.HEADER_H - 1], fill=stop_color)
        # Stop name
        draw.text((x0 + 5, y + 1), stop.name.upper(), font=font, fill=stop_color)
        y += layout.HEADER_H

        # ── Departure rows ────────────────────────────────────────────────────
        shown = 0
        for dep in deps[:departures_per_stop]:
            if y >= layout.DISPLAY_H:
                break

            route_color = _route_color(dep.route, stop.type)
            route_text = dep.route[:5]

            # Route chip
            chip_w = draw_chip(
                image,
                x0 + 1,
                y + 1,
                route_text,
                route_color,
                font_chip,
                pad_x=2,
                chip_h=6,
            )

            # Minutes (right-aligned, urgency coloured)
            min_label = _minutes_label(dep.minutes)
            if min_label == "BRD":
                min_color = layout.GREEN if brd_bright else (0, 130, 0)
            else:
                min_color = _minutes_color(dep.minutes, dep.realtime)

            min_w = text_pixel_width(font, min_label)
            # Reserve 1 px for realtime dot on the far right
            min_x = x0 + panel_w - min_w - 3
            draw.text((min_x, y + 1), min_label, font=font, fill=min_color)

            # Realtime dot (top-right corner of the row)
            if dep.realtime:
                draw.point((x0 + panel_w - 1, y + 1), fill=layout.GREEN)

            # Headsign (middle, scrolling if too long)
            hs_x = x0 + 1 + chip_w + 3
            hs_max_w = min_x - hs_x - 2
            if hs_max_w > 0 and dep.headsign:
                draw_text_clipped(
                    image=image,
                    xy=(hs_x, y + 1),
                    text=dep.headsign,
                    font=font,
                    color=layout.DIM,
                    max_width=hs_max_w,
                    row_h=layout.ROW_H - 2,
                    scroll_offset=scroll_offset,
                )

            y += layout.ROW_H
            shown += 1

        # Empty-stop placeholder
        if shown == 0:
            draw.text((x0 + 5, y + 1), "No service", font=font, fill=layout.DIM)

        # Pad remaining rows so next stop header sits on the right pixel
        y += (departures_per_stop - shown) * layout.ROW_H

        # Thin inter-stop divider (skipped for last stop)
        if y < layout.DISPLAY_H:
            draw.line([x0 + 3, y - 1, x0 + panel_w - 1, y - 1], fill=(25, 25, 35))
