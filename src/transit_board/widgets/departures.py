"""Transit panel widget: two stops stacked vertically, centred in the column."""

from __future__ import annotations

from PIL import Image

from transit_board.config import StopConfig
from transit_board.display import layout
from transit_board.display.renderer import (
    draw_chip,
    draw_text_clipped,
    get_draw,
    get_font,
    text_pixel_width,
)
from transit_board.providers.transit import Departure

# ── Colour helpers ─────────────────────────────────────────────────────────────


def _route_color(route: str, stop_type: str) -> tuple[int, int, int]:
    lower = route.lower()
    for name, color in layout.LINE_COLORS.items():
        if name in lower:
            return color
    return layout.ROUTE_COLORS.get(stop_type, layout.WHITE)


def _stop_color(stop: StopConfig) -> tuple[int, int, int]:
    """Header colour: match a named MBTA line in the stop name (e.g. 'Red',
    'Orange') so subway headers show the real line colour instead of a
    generic subway/bus colour; falls back to the type-based colour."""
    lower = stop.name.lower()
    for name, color in layout.LINE_COLORS.items():
        if name in lower:
            return color
    return layout.ROUTE_COLORS.get(stop.type, layout.WHITE)


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
    return "BRD" if minutes == 0 else f"{minutes}m"


# ── Single stop panel ──────────────────────────────────────────────────────────


def _draw_stop_panel(
    image: Image.Image,
    stop: StopConfig,
    deps: list[Departure],
    n_rows: int,
    scroll_offset: int,
    brd_bright: bool,
    font: object,
    font_chip: object,
    x0: int,
    y0: int,
    panel_h: int,
) -> None:
    draw = get_draw(image)
    stop_color = _stop_color(stop)
    pw = layout.DEPARTURES_W  # panel width

    y = y0

    # ── Header: accent bar + scrolling stop name (full width) ───────────────────────
    draw.rectangle([x0, y, x0 + 2, y + layout.HEADER_H - 1], fill=stop_color)
    draw_text_clipped(
        image=image,
        xy=(x0 + 5, y),  # y+0: top-aligned so full 8 px row is used
        text=stop.name.upper(),
        font=font,
        color=stop_color,
        max_width=pw - 7,  # leave a 2 px right margin
        row_h=layout.HEADER_H + 1,  # +1 headroom so scrolled text isn't clipped vs static text
        scroll_offset=scroll_offset,
        pause_frames=80,
        end_pause_frames=40,
        scroll_speed_inv=3,
    )

    y += layout.HEADER_H

    # Filter to only reachable departures (dep.minutes >= walk time).
    # If walk_minutes not yet known, show all (fallback for startup).
    if stop.walk_minutes is not None:
        deps_shown = [d for d in deps if d.minutes >= stop.walk_minutes]
    else:
        deps_shown = deps

    # ── Departure rows ─────────────────────────────────────────────────────────
    # Centred in the space below the header rather than stacked flush under
    # it: with fewer than n_rows departures, a full bottom-anchor pushed the
    # rows down enough to open a large gap under the header, which read as
    # "too far up"/oddly spaced. Splitting the leftover space keeps a little
    # air on both sides instead of dumping it all on one edge.
    deps_to_show = deps_shown[:n_rows]
    if deps_to_show:
        available_h = y0 + panel_h - y
        leftover = available_h - len(deps_to_show) * layout.ROW_H
        y += max(0, leftover) // 2

    shown = 0
    for dep in deps_to_show:
        if y >= y0 + panel_h:
            break

        route_color = _route_color(dep.route, stop.type)
        route_text = dep.route[:4]  # trim to fit tight chip space

        # Text baseline sits 1px *above* the row top so the font's glyph ink
        # (drawn at relative rows 2-7 at size 8) is centred with even padding
        # inside the 8px ROW_H instead of pushed toward the bottom edge.
        text_y = y - 1

        # Route label (pad_x=1 to save horizontal room in 64 px panel)
        chip_w = draw_chip(image, x0 + 1, text_y, route_text, route_color, font_chip, pad_x=1)

        # Departure minutes (right-aligned, urgency-coloured)
        min_label = _minutes_label(dep.minutes)
        if min_label == "BRD":
            min_color = layout.GREEN if brd_bright else (0, 130, 0)
        else:
            min_color = _minutes_color(dep.minutes, dep.realtime)

        min_w = text_pixel_width(font, min_label)
        # 2 px gap + 1 px realtime dot at far right
        min_x = x0 + pw - min_w - 3
        draw.text((min_x, text_y), min_label, font=font, fill=min_color)

        # Realtime dot (top-right corner of row)
        if dep.realtime:
            draw.point((x0 + pw - 1, y + 1), fill=layout.GREEN)

        # Headsign (middle, scrolling when too wide). Teal keeps it visually
        # distinct from the white/urgency-coloured minutes so the two don't
        # blend together when the headsign runs right up to the edge.
        hs_x = x0 + 1 + chip_w + 2
        hs_max_w = min_x - hs_x - 3
        if hs_max_w > 0 and dep.headsign:
            draw_text_clipped(
                image=image,
                xy=(hs_x, text_y),
                text=dep.headsign,
                font=font,
                color=layout.TEAL,
                max_width=hs_max_w,
                row_h=layout.ROW_H + 2,  # +2 to fully capture font descenders
                scroll_offset=scroll_offset,
            )

        y += layout.ROW_H
        shown += 1

    # "No service" when stop has no predictions or all are unreachable —
    # centred in the empty rows rather than pinned to the top.
    if shown == 0:
        msg = "No service"
        bbox = draw.textbbox((0, 0), msg, font=font)
        mw = bbox[2] - bbox[0]
        remaining_h = y0 + panel_h - y
        mx = x0 + max(0, (pw - mw) // 2)
        my = y + max(0, (remaining_h - 8) // 2)
        draw.text((mx, my), msg, font=font, fill=layout.WHITE)


# ── Public draw function ───────────────────────────────────────────────────────


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
    Render the departures panel into the right DEPARTURES_W×128 px region of *image*.

    Up to 2 stops are drawn stacked vertically, each an 8px header plus
    departures_per_stop × 8px rows (route chip / scrolling headsign / minutes
    + dot). The pair is vertically centred in the full column — see
    layout.stop_panel_layout() — rather than assumed to fill it exactly, so
    running with fewer than 3 rows per stop opens real margin around the
    block instead of leaving it stranded as padding inside each stop.

    All bus lines at a stop are included; the soonest departures_per_stop are
    shown regardless of route.
    """
    font = get_font(font_path, size=8)
    font_chip = get_font(font_path, size=7)
    brd_bright = (tick // 15) % 2 == 0

    top_margin, panel_h = layout.stop_panel_layout(departures_per_stop)

    for i, stop in enumerate(stops[:2]):
        x0 = layout.DEPARTURES_X
        y0 = top_margin + i * panel_h
        deps = departures_by_stop.get(stop.id, [])
        _draw_stop_panel(
            image,
            stop,
            deps,
            departures_per_stop,
            scroll_offset,
            brd_bright,
            font,
            font_chip,
            x0,
            y0,
            panel_h,
        )
