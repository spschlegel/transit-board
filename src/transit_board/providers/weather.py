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


# 3-char abbreviated labels (fit in the narrow icon sub-label area)
_WMO_SHORT: dict[int, str] = {
    0: "CLR",
    1: "CLR",
    2: "PRT",
    3: "CLD",
    45: "FOG",
    48: "FOG",
    51: "DRZ",
    53: "DRZ",
    55: "DRZ",
    61: "RAN",
    63: "RAN",
    65: "RAN",
    71: "SNW",
    73: "SNW",
    75: "SNW",
    77: "SNW",
    80: "SHR",
    81: "SHR",
    82: "SHR",
    85: "SNW",
    86: "SNW",
    95: "STM",
    96: "STM",
    99: "STM",
}


def _wmo_short(code: int) -> str:
    """Return 3-char abbreviated label for WMO weather code."""
    for c in sorted(_WMO_SHORT.keys(), reverse=True):
        if code >= c:
            return _WMO_SHORT[c]
    return "CLR"


@dataclass
class WeatherData:
    temperature_c: float
    weather_code: int
    uv_index: float
    uv_index_max: float = 0.0  # today's daily UV maximum
    temperature_max_c: float = 0.0  # today's daily temperature maximum

    @property
    def temperature_f(self) -> float:
        return self.temperature_c * 9.0 / 5.0 + 32.0

    @property
    def label(self) -> str:
        return _wmo_label(self.weather_code)

    @property
    def short_label(self) -> str:
        return _wmo_short(self.weather_code)


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
                    "daily": "uv_index_max,temperature_2m_max",
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
        daily_uv_max = daily.get("uv_index_max", [])
        daily_temp_max = daily.get("temperature_2m_max", [])
        return WeatherData(
            temperature_c=float(cur["temperature_2m"]),
            weather_code=int(cur["weather_code"]),
            uv_index=float(cur.get("uv_index", 0.0)),
            uv_index_max=float(daily_uv_max[0]) if daily_uv_max else 0.0,
            temperature_max_c=float(daily_temp_max[0]) if daily_temp_max else 0.0,
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
        temperature_max_c=26.0,
    )
