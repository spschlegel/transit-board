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
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as dtime
from typing import Optional

from transit_board.config import Config
from transit_board.display.matrix import MatrixDisplay
from transit_board.display.renderer import draw_panel_chrome, new_canvas
from transit_board.providers.cache import TTLCache
from transit_board.providers.transit import Departure, MBTAClient, mock_departures
from transit_board.providers.weather import WeatherClient, WeatherData, mock_weather
from transit_board.widgets import clock as clock_widget
from transit_board.widgets import departures as dep_widget
from transit_board.widgets import uv as uv_widget
from transit_board.widgets import weather as weather_widget

log = logging.getLogger(__name__)

FRAME_INTERVAL = 1.0 / 20  # target ~20 FPS
SCROLL_SPEED = 1  # pixels per frame (scroll advances each rendered frame)

# 22:00 to 00:01 local time: UV + weather-conditions widgets show tomorrow's
# forecast instead of current/today — more useful once today is basically
# over. Reverts at 00:01 once "tomorrow" has actually become today.
_FORECAST_PREVIEW_START = dtime(22, 0)
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
    scroll_offset: int = 0
    tick: int = 0


async def run(cfg: Config, matrix: MatrixDisplay, dev: bool = False) -> None:
    """Main render loop — runs until cancelled."""
    mbta = MBTAClient(cfg.mbta_api_key)
    weather_client = WeatherClient(cfg.lat, cfg.lon)

    # Per-stop TTL caches
    transit_caches: dict[str, TTLCache[list[Departure]]] = {
        stop.id: TTLCache(cfg.refresh.transit_secs) for stop in cfg.stops
    }
    weather_cache: TTLCache[WeatherData] = TTLCache(cfg.refresh.weather_secs)

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
        log.info("Dev mode: loaded mock data for %d stop(s)", len(cfg.stops))

    try:
        while True:
            t0 = time.monotonic()

            # ── Data refresh (skipped in dev mode) ───────────────────────────
            if not dev:
                await _refresh_transit(
                    cfg,
                    mbta,
                    transit_caches,
                    state,
                )
                await _refresh_weather(cfg, weather_client, weather_cache, state)

            # ── Brightness schedule (checked ~once/sec, not every frame) ────────
            if state.tick % 20 == 0:
                matrix.set_brightness(cfg.display.brightness_for())

            # ── Render frame ──────────────────────────────────────────────────
            image, _ = new_canvas(matrix.width, matrix.height)

            dep_widget.draw_departures(
                image=image,
                stops=cfg.stops,
                departures_by_stop=state.departures_by_stop,
                departures_per_stop=cfg.display.departures_per_stop,
                scroll_offset=state.scroll_offset,
                tick=state.tick,
            )
            clock_widget.draw_clock(image=image)
            show_forecast = _forecast_preview_active(datetime.now())
            weather_widget.draw_weather(
                image=image, weather=state.weather, tick=state.tick, show_forecast=show_forecast
            )
            uv_widget.draw_uv(image=image, weather=state.weather, show_forecast=show_forecast)

            draw_panel_chrome(image)  # divider + section lines on top
            matrix.render(image)

            # ── Advance scroll ────────────────────────────────────────────────
            state.scroll_offset += SCROLL_SPEED
            state.tick += 1

            # ── Frame pacing ──────────────────────────────────────────────────
            elapsed = time.monotonic() - t0
            sleep = FRAME_INTERVAL - elapsed
            if sleep > 0:
                await asyncio.sleep(sleep)

    except asyncio.CancelledError:
        log.info("Loop cancelled — cleaning up")
    finally:
        await mbta.aclose()
        await weather_client.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _refresh_transit(
    cfg: Config,
    mbta: MBTAClient,
    caches: dict[str, TTLCache[list[Departure]]],
    state: AppState,
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
        else:
            stop_id, deps = result
            caches[stop_id].set(deps)
            state.departures_by_stop[stop_id] = deps
            log.debug("Fetched %d departure(s) for stop %s", len(deps), stop_id)


async def _refresh_weather(
    cfg: Config,
    client: WeatherClient,
    cache: TTLCache[WeatherData],
    state: AppState,
) -> None:
    if not cache.expired:
        return
    try:
        state.weather = await client.fetch()
        cache.set(state.weather)
        log.debug(
            "Weather: %.1f°C, code %d, UV %.1f",
            state.weather.temperature_c,
            state.weather.weather_code,
            state.weather.uv_index,
        )
    except Exception as exc:
        log.warning("Weather refresh failed: %s", exc)
