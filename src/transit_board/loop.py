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
import time
from dataclasses import dataclass, field
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

    if dev:
        # Seed with mock data immediately
        for stop in cfg.stops:
            state.departures_by_stop[stop.id] = mock_departures(
                stop.id, stop.type, cfg.display.departures_per_stop
            )
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
            weather_widget.draw_weather(image=image, weather=state.weather)
            uv_widget.draw_uv(image=image, weather=state.weather)

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
