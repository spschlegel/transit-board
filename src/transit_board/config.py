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
    sports_secs: int = 120


@dataclass
class SportsConfig:
    nfl_enabled: bool = True
    bayern_enabled: bool = True
    tennis_enabled: bool = True
    red_sox_enabled: bool = True
    post_game_window_minutes: int = 60  # how long a finished game stays on screen
    replaceable_stop_index: int = 1  # which of stops[:2] "auto" hybrid mode may replace (0 or 1)
    hybrid_compact_max_games: int = 2  # <= this many games -> half-panel; more -> full takeover
    prefer_scores_over_idle: bool = True  # live games pre-empt the night idle default


# What the departures-panel region shows. "auto" = sports (hybrid or full) while any game is
# relevant, else ScheduleConfig.auto_fallback.
SCENES = ("transit", "sports", "idle", "auto")
_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass
class TransitWindow:
    days: frozenset[int]  # 0 = Monday
    start: time
    end: time  # end < start means the window wraps past midnight

    def contains(self, now: datetime) -> bool:
        t = now.time()
        if self.start <= self.end:
            return now.weekday() in self.days and self.start <= t < self.end
        # Wrapping window: the evening half belongs to the listed weekday, the
        # after-midnight half to the day after it.
        if t >= self.start:
            return now.weekday() in self.days
        return t < self.end and (now.weekday() - 1) % 7 in self.days


@dataclass
class ScheduleConfig:
    day_default: str = "auto"
    night_default: str = "idle"
    auto_fallback: str = "idle"  # what "auto" shows when no game is relevant (not "auto")
    # Night = the span night_default applies in (and what the idle animation used to be
    # hard-wired to). Independent of display.night_start, which only schedules brightness.
    night_start: time = field(default_factory=lambda: time(21, 0))
    night_end: time = field(default_factory=lambda: time(6, 0))
    transit_windows: list[TransitWindow] = field(default_factory=list)
    override_minutes: int = 15  # default duration of a manual override from the PWA
    transit_min_minutes: int = 15  # a manual "show transit" never lasts less than this


@dataclass
class ServerConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    token: str = ""  # from env BOARD_TOKEN, never config.toml


@dataclass
class Config:
    mbta_api_key: str
    stops: list[StopConfig]
    lat: float
    lon: float
    display: DisplayConfig = field(default_factory=DisplayConfig)
    refresh: RefreshConfig = field(default_factory=RefreshConfig)
    sports: SportsConfig = field(default_factory=SportsConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
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
        y_offset=int(disp_raw.get("y_offset", defaults.y_offset)),
        brightness_day=int(disp_raw.get("brightness_day", defaults.brightness_day)),
        brightness_night=int(disp_raw.get("brightness_night", defaults.brightness_night)),
        day_start=disp_raw.get("day_start", defaults.day_start),
        night_start=disp_raw.get("night_start", defaults.night_start),
    )

    ref_raw = raw.get("refresh", {})
    ref = RefreshConfig(
        transit_secs=int(ref_raw.get("transit_secs", 30)),
        weather_secs=int(ref_raw.get("weather_secs", 300)),
        sports_secs=int(ref_raw.get("sports_secs", 120)),
    )

    sports_raw = raw.get("sports", {})
    sports_defaults = SportsConfig()
    sports = SportsConfig(
        nfl_enabled=bool(sports_raw.get("nfl_enabled", sports_defaults.nfl_enabled)),
        bayern_enabled=bool(sports_raw.get("bayern_enabled", sports_defaults.bayern_enabled)),
        tennis_enabled=bool(sports_raw.get("tennis_enabled", sports_defaults.tennis_enabled)),
        red_sox_enabled=bool(sports_raw.get("red_sox_enabled", sports_defaults.red_sox_enabled)),
        post_game_window_minutes=int(
            sports_raw.get("post_game_window_minutes", sports_defaults.post_game_window_minutes)
        ),
        replaceable_stop_index=int(
            sports_raw.get("replaceable_stop_index", sports_defaults.replaceable_stop_index)
        ),
        hybrid_compact_max_games=int(
            sports_raw.get("hybrid_compact_max_games", sports_defaults.hybrid_compact_max_games)
        ),
        prefer_scores_over_idle=bool(
            sports_raw.get("prefer_scores_over_idle", sports_defaults.prefer_scores_over_idle)
        ),
    )

    return Config(
        mbta_api_key=api_key,
        stops=stops,
        lat=float(loc.get("lat", 42.3601)),
        lon=float(loc.get("lon", -71.0589)),
        display=disp,
        refresh=ref,
        sports=sports,
        schedule=_load_schedule(raw.get("schedule", {})),
        server=_load_server(raw.get("server", {})),
        walk_speed_kmh=float(loc.get("walk_speed_kmh", 5.0)),
    )


def _scene(raw: dict, key: str, default: str, allowed: tuple[str, ...]) -> str:
    value = raw.get(key, default)
    if value not in allowed:
        warnings.warn(
            f"schedule.{key}={value!r} not supported (one of {', '.join(allowed)}) "
            f"— using {default!r}",
            stacklevel=3,
        )
        return default
    return value


def _load_schedule(raw: dict) -> ScheduleConfig:
    d = ScheduleConfig()
    windows: list[TransitWindow] = []
    for w in raw.get("transit_windows", []):
        names = [str(n).lower()[:3] for n in w.get("days", _WEEKDAYS)]
        bad = [n for n in names if n not in _WEEKDAYS]
        if bad or "start" not in w or "end" not in w:
            warnings.warn(f"schedule.transit_windows entry {w!r} invalid — skipped", stacklevel=2)
            continue
        windows.append(
            TransitWindow(
                days=frozenset(_WEEKDAYS[n] for n in names), start=w["start"], end=w["end"]
            )
        )
    return ScheduleConfig(
        day_default=_scene(raw, "day_default", d.day_default, SCENES),
        night_default=_scene(raw, "night_default", d.night_default, SCENES),
        auto_fallback=_scene(raw, "auto_fallback", d.auto_fallback, ("transit", "sports", "idle")),
        night_start=raw.get("night_start", d.night_start),
        night_end=raw.get("night_end", d.night_end),
        transit_windows=windows,
        override_minutes=int(raw.get("override_minutes", d.override_minutes)),
        transit_min_minutes=int(raw.get("transit_min_minutes", d.transit_min_minutes)),
    )


def _load_server(raw: dict) -> ServerConfig:
    d = ServerConfig()
    return ServerConfig(
        enabled=bool(raw.get("enabled", d.enabled)),
        host=str(raw.get("host", d.host)),
        port=int(raw.get("port", d.port)),
        token=os.environ.get("BOARD_TOKEN", ""),
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
        refresh=RefreshConfig(transit_secs=30, weather_secs=300, sports_secs=120),
        sports=SportsConfig(),
        schedule=ScheduleConfig(),
        server=ServerConfig(host="127.0.0.1", token=os.environ.get("BOARD_TOKEN", "dev")),
        walk_speed_kmh=5.0,
    )
