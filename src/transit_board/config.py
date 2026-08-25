"""Load and validate configuration from config.toml + .env."""

from __future__ import annotations

import os
import tomllib
import warnings
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class StopConfig:
    id: str
    name: str
    type: str  # "bus" | "subway"
    walk_minutes: int | None = None  # auto-calculated from coords; user can override in config.toml


@dataclass
class DisplayConfig:
    departures_per_stop: int = 3
    rotation: int = 0  # 0 or 180 — set to 180 if the panel is mounted upside down
    y_offset: int = 2  # px to shift the whole frame down (content sits tight against top edge)

    # Brightness is scheduled rather than fixed — dimmer at night, brighter during the
    # day, re-evaluated continuously by loop.py (see DisplayConfig.brightness_for).
    brightness_day: int = 90
    brightness_night: int = 60
    day_start: time = field(default_factory=lambda: time(6, 30))
    night_start: time = field(default_factory=lambda: time(21, 0))

    def brightness_for(self, now: datetime | None = None) -> int:
        """Return the scheduled brightness % for *now* (default: current local time)."""
        t = (now or datetime.now()).time()
        if self.day_start <= t < self.night_start:
            return self.brightness_day
        return self.brightness_night


@dataclass
class RefreshConfig:
    transit_secs: int = 30
    weather_secs: int = 300


@dataclass
class Config:
    mbta_api_key: str
    stops: list[StopConfig]
    lat: float
    lon: float
    display: DisplayConfig = field(default_factory=DisplayConfig)
    refresh: RefreshConfig = field(default_factory=RefreshConfig)
    walk_speed_kmh: float = 5.0  # walking speed for "when to leave" auto-calculation


_DEFAULT_CONFIG = Path("config.toml")


def load(path: Path = _DEFAULT_CONFIG) -> Config:
    """Load config from *path* (TOML) + env vars."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy config.toml.example → config.toml and fill in your stop IDs."
        )

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    api_key = os.environ.get("MBTA_API_KEY") or raw.get("mbta_api_key", "")
    if not api_key:
        warnings.warn(
            "MBTA_API_KEY not set — real-time API calls may be rate-limited. "
            "Get a free key at https://api-v3.mbta.com",
            stacklevel=2,
        )

    loc = raw.get("location", {})
    stops = [
        StopConfig(
            id=s["id"],
            name=s["name"],
            type=s["type"],
            walk_minutes=int(s["walk_minutes"]) if "walk_minutes" in s else None,
        )
        for s in raw.get("stops", [])
    ]
    if not stops:
        warnings.warn("No stops configured in config.toml", stacklevel=2)

    disp_raw = raw.get("display", {})
    rotation = int(disp_raw.get("rotation", 0))
    if rotation not in (0, 180):
        warnings.warn(
            f"display.rotation={rotation} not supported (only 0 or 180) — using 0",
            stacklevel=2,
        )
        rotation = 0
    defaults = DisplayConfig()
    disp = DisplayConfig(
        departures_per_stop=int(disp_raw.get("departures_per_stop", 3)),
        rotation=rotation,
        y_offset=int(disp_raw.get("y_offset", 2)),
        brightness_day=int(disp_raw.get("brightness_day", defaults.brightness_day)),
        brightness_night=int(disp_raw.get("brightness_night", defaults.brightness_night)),
        day_start=disp_raw.get("day_start", defaults.day_start),
        night_start=disp_raw.get("night_start", defaults.night_start),
    )

    ref_raw = raw.get("refresh", {})
    ref = RefreshConfig(
        transit_secs=int(ref_raw.get("transit_secs", 30)),
        weather_secs=int(ref_raw.get("weather_secs", 300)),
    )

    return Config(
        mbta_api_key=api_key,
        stops=stops,
        lat=float(loc.get("lat", 42.3601)),
        lon=float(loc.get("lon", -71.0589)),
        display=disp,
        refresh=ref,
        walk_speed_kmh=float(loc.get("walk_speed_kmh", 5.0)),
    )


def dev_default() -> Config:
    """Return a default config suitable for --dev mode (no config.toml needed)."""
    return Config(
        mbta_api_key="",
        stops=[
            StopConfig(id="64", name="Bus", type="bus"),
            StopConfig(id="place-rugg", name="Orange", type="subway"),
        ],
        lat=42.3601,
        lon=-71.0589,
        display=DisplayConfig(departures_per_stop=3),
        refresh=RefreshConfig(transit_secs=30, weather_secs=300),
        walk_speed_kmh=5.0,
    )
