"""Open-Meteo API client — temperature, weather condition, UV index."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

OPEN_METEO_BASE = "https://api.open-meteo.com/v1"

# WMO weather interpretation codes → short display label (max ~6 chars for 32px sidebar)
_WMO_LABEL: dict[int, str] = {
    0: "Clear",
    1: "Clear",
    2: "Partly",
    3: "Cloudy",
    45: "Foggy",
    48: "Fog",
    51: "Drizl",
    53: "Drizl",
    55: "Drizl",
    61: "Rain",
    63: "Rain",
    65: "Rain",
    71: "Snow",
    73: "Snow",
    75: "Snow",
    77: "Snow",
    80: "Showr",
    81: "Showr",
    82: "Showr",
    85: "Snow",
    86: "Snow",
    95: "Storm",
    96: "Storm",
    99: "Storm",
}


def _wmo_label(code: int) -> str:
    """Return display label for WMO weather code, searching downward."""
    for c in sorted(_WMO_LABEL.keys(), reverse=True):
        if code >= c:
            return _WMO_LABEL[c]
    return "Clear"


@dataclass
class WeatherData:
    temperature_c: float
    weather_code: int
    uv_index: float
    uv_index_max: float = 0.0  # today's daily UV maximum
    forecast_weather_code: int = 0  # today's overall forecast WMO code

    @property
    def temperature_f(self) -> float:
        return self.temperature_c * 9.0 / 5.0 + 32.0

    @property
    def label(self) -> str:
        return _wmo_label(self.weather_code)

    @property
    def forecast_label(self) -> str:
        return _wmo_label(self.forecast_weather_code)


class WeatherClient:
    def __init__(self, lat: float, lon: float) -> None:
        self._lat = lat
        self._lon = lon
        self._http = httpx.AsyncClient(base_url=OPEN_METEO_BASE, timeout=10.0)

    async def fetch(self) -> WeatherData:
        try:
            r = await self._http.get(
                "/forecast",
                params={
                    "latitude": self._lat,
                    "longitude": self._lon,
                    "current": "temperature_2m,weather_code,uv_index",
                    "daily": "weather_code,uv_index_max",
                    "temperature_unit": "celsius",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Weather fetch failed: %s", exc)
            raise

        body = r.json()
        cur = body["current"]
        daily = body.get("daily", {})
        daily_codes = daily.get("weather_code", [])
        daily_uv_max = daily.get("uv_index_max", [])
        return WeatherData(
            temperature_c=float(cur["temperature_2m"]),
            weather_code=int(cur["weather_code"]),
            uv_index=float(cur.get("uv_index", 0.0)),
            uv_index_max=float(daily_uv_max[0]) if daily_uv_max else 0.0,
            forecast_weather_code=int(daily_codes[0]) if daily_codes else 0,
        )

    async def aclose(self) -> None:
        await self._http.aclose()


def mock_weather() -> WeatherData:
    """Return fake weather data for --dev mode."""
    return WeatherData(
        temperature_c=22.0,
        weather_code=1,
        uv_index=4.5,
        uv_index_max=7.0,
        forecast_weather_code=3,  # Cloudy (for visible contrast in dev)
    )
