"""
Async main loop.

Responsibilities:
  - Refresh MBTA departures every cfg.refresh.transit_secs seconds per stop
  - Refresh weather every cfg.refresh.weather_secs seconds
  - Render one frame every FRAME_INTERVAL seconds (~20 FPS)
  - Advance horizontal scroll offset each frame
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from datetime import time as dtime
from typing import Optional

from transit_board.config import Config
from transit_board.control import Control
from transit_board.display import layout
from transit_board.display.matrix import MatrixDisplay
from transit_board.display.renderer import draw_panel_chrome, new_canvas
from transit_board.modes import default_scene
from transit_board.providers.cache import TTLCache
from transit_board.providers.logos import LogoCache
from transit_board.providers.sports import Game, SportsClient, mock_games, relevant_games
from transit_board.providers.transit import Departure, MBTAClient, mock_departures
from transit_board.providers.weather import WeatherClient, WeatherData, mock_weather
from transit_board.widgets import clock as clock_widget
from transit_board.widgets import departures as dep_widget
from transit_board.widgets import idle as idle_widget
from transit_board.widgets import scores as scores_widget
from transit_board.widgets import uv as uv_widget
from transit_board.widgets import weather as weather_widget

log = logging.getLogger(__name__)

FRAME_INTERVAL = 1.0 / 20  # target ~20 FPS
SCROLL_SPEED = 1  # pixels per frame (scroll advances each rendered frame)

# 20:00 to 00:01 local time: UV + weather-conditions widgets show tomorrow's
# forecast instead of current/today — more useful once today is basically
# over. Reverts at 00:01 once "tomorrow" has actually become today.
_FORECAST_PREVIEW_START = dtime(20, 0)
_FORECAST_PREVIEW_END = dtime(0, 1)


def _forecast_preview_active(now: datetime) -> bool:
    t = now.time()
    return t >= _FORECAST_PREVIEW_START or t < _FORECAST_PREVIEW_END


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


@dataclass
class AppState:
    departures_by_stop: dict[str, list[Departure]] = field(default_factory=dict)
    weather: Optional[WeatherData] = None
    games: list[Game] = field(default_factory=list)
    # event_id -> first time it was observed as finished ("post"). ESPN doesn't
    # reliably expose a "finished at" timestamp, so this is how the post-game
    # display window (SportsConfig.post_game_window_minutes) is measured —
    # see the comment on Game.end_time in providers/sports.py.
    sports_first_seen_post: dict[str, datetime] = field(default_factory=dict)
    scroll_offset: int = 0
    tick: int = 0


@dataclass(frozen=True)
class _PanelPlan:
    kind: str  # "idle" | "departures" | "sports_full" | "sports_hybrid"
    games: list[Game]
    show_stop_divider: bool
    default: str = ""  # scheduled default scene (ignoring any override)
    reason: str = ""  # why that default: "transit-window" | "night" | "day"


def _resolve_panel(cfg: Config, state: AppState, now: datetime, control: Control) -> _PanelPlan:
    """Decide what goes in the departures-panel region this frame.

    Scene = the manual override if one is active, else the scheduled default
    (modes.default_scene). "auto" shows sports while any game is relevant and
    falls back to schedule.auto_fallback otherwise. *now* is naive local time;
    the relevance filter internally uses its own tz-aware UTC clock.
    """
    sched = cfg.schedule
    ov = control.override
    if ov is not None and not ov.active:
        control.override = ov = None

    default, reason = default_scene(sched, now)
    scene = ov.scene if ov is not None else default
    relevant = relevant_games(state.games, cfg.sports, datetime.now(timezone.utc))

    # A live game pre-empts the *scheduled* night idle animation, but never a
    # manual override or a transit window.
    if (
        ov is None
        and reason == "night"
        and scene == "idle"
        and relevant
        and cfg.sports.prefer_scores_over_idle
    ):
        scene = "auto"

    def plan(kind: str, games: list[Game], divider: bool) -> _PanelPlan:
        return _PanelPlan(kind, games, divider, default, reason)

    if scene == "auto":
        if not relevant:
            scene = sched.auto_fallback
        elif len(relevant) <= cfg.sports.hybrid_compact_max_games and len(cfg.stops) >= 2:
            return plan("sports_hybrid", relevant, True)
        else:
            return plan("sports_full", relevant, False)

    if scene == "sports":
        # Explicit sports takes over fully, even with zero relevant games —
        # the widget's own "No games" state shows.
        return plan("sports_full", relevant, False)
    if scene == "idle":
        return plan("idle", relevant, False)
    return plan("departures", relevant, True)


async def run(cfg: Config, matrix: MatrixDisplay, control: Control, dev: bool = False) -> None:
    """Main render loop — runs until cancelled.

    *control* carries the manual scene override in, and the current scene and
    refresh health out, for the web server (see control.py).
    """
    mbta = MBTAClient(cfg.mbta_api_key)
    weather_client = WeatherClient(cfg.lat, cfg.lon)
    sports_client = SportsClient()
    logo_cache = LogoCache()

    # Per-stop TTL caches
    transit_caches: dict[str, TTLCache[list[Departure]]] = {
        stop.id: TTLCache(cfg.refresh.transit_secs) for stop in cfg.stops
    }
    weather_cache: TTLCache[WeatherData] = TTLCache(cfg.refresh.weather_secs)
    sports_cache: TTLCache[list[Game]] = TTLCache(cfg.refresh.sports_secs)

    state = AppState()

    # ── Walk-time initialisation ──────────────────────────────────────────────
    if dev:
        for stop in cfg.stops:
            if stop.walk_minutes is None:
                stop.walk_minutes = 8
        log.info("Dev mode: using 8 min walk time for all stops")
    else:
        for stop in cfg.stops:
            if stop.walk_minutes is None:
                try:
                    lat, lon = await mbta.stop_coords(stop.id)
                    dist_km = _haversine_km(cfg.lat, cfg.lon, lat, lon)
                    stop.walk_minutes = max(1, round(dist_km / cfg.walk_speed_kmh * 60))
                    log.info(
                        "Stop %s: %.2f km from home \u2192 %d min walk",
                        stop.id,
                        dist_km,
                        stop.walk_minutes,
                    )
                except Exception as exc:
                    log.warning("Could not get walk time for stop %s: %s", stop.id, exc)

    if dev:
        # Seed with mock data immediately
        for stop in cfg.stops:
            state.departures_by_stop[stop.id] = mock_departures(stop.id, stop.type)
        state.weather = mock_weather()
        state.games = mock_games()
        log.info("Dev mode: loaded mock data for %d stop(s)", len(cfg.stops))

    try:
        while True:
            t0 = time.monotonic()

            # ── Data refresh (skipped in dev mode) ───────────────────────────
            if not dev:
                await _refresh_transit(cfg, mbta, transit_caches, state, control)
                await _refresh_weather(cfg, weather_client, weather_cache, state, control)
                await _refresh_sports(cfg, sports_client, logo_cache, sports_cache, state, control)

            # ── Brightness schedule (checked ~once/sec, not every frame) ────────
            if state.tick % 20 == 0:
                matrix.set_brightness(cfg.display.brightness_for())

            # ── Render frame ──────────────────────────────────────────────────
            image, _ = new_canvas(matrix.width, matrix.height)

            now = datetime.now()
            plan = _resolve_panel(cfg, state, now, control)
            control.default_scene = plan.default
            control.default_reason = plan.reason
            control.panel_kind = plan.kind
            control.relevant_games = len(plan.games)

            if plan.kind == "idle":
                idle_widget.draw_idle(
                    image=image,
                    tick=state.tick,
                    now=now,
                    weather=state.weather,
                    lat=cfg.lat,
                    lon=cfg.lon,
                )
            elif plan.kind == "departures":
                dep_widget.draw_departures(
                    image=image,
                    stops=cfg.stops,
                    departures_by_stop=state.departures_by_stop,
                    departures_per_stop=cfg.display.departures_per_stop,
                    scroll_offset=state.scroll_offset,
                    tick=state.tick,
                )
            elif plan.kind == "sports_full":
                scores_widget.draw_scores(
                    image=image,
                    games=plan.games,
                    logo_cache=logo_cache,
                    x0=layout.DEPARTURES_X,
                    y0=0,
                    w=layout.DEPARTURES_W,
                    h=layout.DISPLAY_H,
                    tick=state.tick,
                )
            else:  # "sports_hybrid" — one slot keeps real departures, the other shows scores
                top_margin, panel_h, _header_gap = layout.stop_panel_layout(
                    cfg.display.departures_per_stop
                )
                sports_slot = max(0, min(cfg.sports.replaceable_stop_index, len(cfg.stops[:2]) - 1))
                kept_slot = 1 - sports_slot
                kept_stop = cfg.stops[kept_slot]
                dep_widget.draw_single_stop(
                    image=image,
                    stop=kept_stop,
                    deps=state.departures_by_stop.get(kept_stop.id, []),
                    n_rows=cfg.display.departures_per_stop,
                    scroll_offset=state.scroll_offset,
                    tick=state.tick,
                    slot_index=kept_slot,
                )
                scores_widget.draw_scores(
                    image=image,
                    games=plan.games,
                    logo_cache=logo_cache,
                    x0=layout.DEPARTURES_X,
                    y0=top_margin + sports_slot * panel_h,
                    w=layout.DEPARTURES_W,
                    h=panel_h,
                    tick=state.tick,
                )

            clock_widget.draw_clock(image=image)
            show_forecast = _forecast_preview_active(now)
            weather_widget.draw_weather(
                image=image, weather=state.weather, tick=state.tick, show_forecast=show_forecast
            )
            uv_widget.draw_uv(image=image, weather=state.weather, show_forecast=show_forecast)

            draw_panel_chrome(  # divider + section lines on top
                image,
                departures_per_stop=cfg.display.departures_per_stop,
                show_stop_divider=plan.show_stop_divider,
            )
            matrix.render(image)

            # ── Advance scroll ────────────────────────────────────────────────
            state.scroll_offset += SCROLL_SPEED
            state.tick += 1

            # ── Frame pacing ──────────────────────────────────────────────────
            # Always await something, even when a frame overruns FRAME_INTERVAL
            # (sleep <= 0): asyncio can only deliver a cancellation at an await
            # suspension point, and the only other awaits in this loop are the
            # transit/weather refreshes, gated behind TTL caches that might not
            # expire for another 30s+. Without this, a slow render (e.g. real
            # hardware SwapOnVSync taking longer than 50ms at higher
            # gpio_slowdown) starves Ctrl-C/SIGTERM of any chance to land,
            # making shutdown feel like it hangs.
            elapsed = time.monotonic() - t0
            sleep = FRAME_INTERVAL - elapsed
            await asyncio.sleep(max(sleep, 0))

    except asyncio.CancelledError:
        log.info("Loop cancelled — cleaning up")
    finally:
        await mbta.aclose()
        await weather_client.aclose()
        await sports_client.aclose()
        await logo_cache.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _refresh_transit(
    cfg: Config,
    mbta: MBTAClient,
    caches: dict[str, TTLCache[list[Departure]]],
    state: AppState,
    control: Control,
) -> None:
    """Fetch any expired stop caches in parallel."""
    expired = [s for s in cfg.stops if caches[s.id].expired]
    if not expired:
        return

    async def fetch_one(stop_id: str, max_results: int) -> tuple[str, list[Departure]]:
        deps = await mbta.departures(stop_id, max_results)
        return stop_id, deps

    tasks = [
        asyncio.create_task(fetch_one(stop.id, cfg.display.departures_per_stop)) for stop in expired
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for stop, result in zip(expired, results):
        if isinstance(result, Exception):
            log.warning("Failed to fetch stop %s: %s", stop.id, result)
            control.failed("transit", result)
        else:
            control.refreshed("transit")
            stop_id, deps = result
            caches[stop_id].set(deps)
            state.departures_by_stop[stop_id] = deps
            log.debug("Fetched %d departure(s) for stop %s", len(deps), stop_id)


async def _refresh_weather(
    cfg: Config,
    client: WeatherClient,
    cache: TTLCache[WeatherData],
    state: AppState,
    control: Control,
) -> None:
    if not cache.expired:
        return
    try:
        state.weather = await client.fetch()
        cache.set(state.weather)
        control.refreshed("weather")
        log.debug(
            "Weather: %.1f°C, code %d, UV %.1f",
            state.weather.temperature_c,
            state.weather.weather_code,
            state.weather.uv_index,
        )
    except Exception as exc:
        log.warning("Weather refresh failed: %s", exc)
        control.failed("weather", exc)


async def _refresh_sports(
    cfg: Config,
    client: SportsClient,
    logo_cache: LogoCache,
    cache: TTLCache[list[Game]],
    state: AppState,
    control: Control,
) -> None:
    if not cache.expired:
        return
    try:
        games = await client.fetch_all(cfg.sports)
    except Exception as exc:
        log.warning("Sports refresh failed: %s", exc)
        control.failed("sports", exc)
        return

    now = datetime.now(timezone.utc)
    seen_ids: set[str] = set()
    resolved: list[Game] = []
    for g in games:
        seen_ids.add(g.event_id)
        if g.status == "post" and g.end_time is None:
            first_seen = state.sports_first_seen_post.get(g.event_id)
            if first_seen is None:
                first_seen = now
                state.sports_first_seen_post[g.event_id] = now
            g = replace(g, end_time=first_seen)
        resolved.append(g)

    # Prune bookkeeping only for events no longer returned at all. A time-based
    # prune here is a trap: ESPN's scoreboard endpoints keep returning "post"
    # games for days (confirmed live — the NFL scoreboard was still listing a
    # 5-day-old final), so pruning a still-listed event's timestamp would make
    # the very next refresh treat it as newly finished and reset its clock —
    # the game would then cyclically reappear as "relevant" every prune
    # interval for as long as ESPN keeps listing it, instead of just going
    # relevant once and staying gone. Bounded naturally: this dict can only
    # ever hold as many entries as the scoreboards currently return (a few
    # dozen), so there's no unbounded-growth risk from skipping a time bound.
    state.sports_first_seen_post = {
        eid: ts for eid, ts in state.sports_first_seen_post.items() if eid in seen_ids
    }

    cache.set(resolved)
    state.games = resolved
    control.refreshed("sports")

    urls = {c.logo_url for g in resolved for c in g.competitors if c.logo_url}
    if urls:
        await logo_cache.ensure(urls)

    log.debug("Sports: %d relevant-or-not game(s) fetched", len(resolved))
