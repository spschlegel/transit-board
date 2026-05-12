"""Load and validate configuration from config.toml + .env."""

from __future__ import annotations

import os
import tomllib
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class StopConfig:
    id: str
    name: str
    type: str  # "bus" | "subway"


@dataclass
class DisplayConfig:
    brightness: int = 50
    departures_per_stop: int = 3


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
    stops = [StopConfig(**s) for s in raw.get("stops", [])]
    if not stops:
        warnings.warn("No stops configured in config.toml", stacklevel=2)

    disp_raw = raw.get("display", {})
    disp = DisplayConfig(
        brightness=int(disp_raw.get("brightness", 50)),
        departures_per_stop=int(disp_raw.get("departures_per_stop", 3)),
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
        display=DisplayConfig(brightness=50, departures_per_stop=3),
        refresh=RefreshConfig(transit_secs=30, weather_secs=300),
    )
