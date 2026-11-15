"""
Sun position and sunrise/sunset, computed locally from lat/lon (no API).

Uses the standard low-precision solar-position formulas (good to well under a
degree — minutes of sunrise/sunset, plenty for an ambient display). Sunrise
and sunset are found by scanning the local day for the elevation crossing
SUN_RISE_SET_DEG, then cached per (lat, lon, date).

All datetimes passed in or returned are tz-aware. Naive local times are
converted with datetime.astimezone() (which assumes local time), matching how
the rest of the app treats naive `datetime.now()`.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Optional

# Apparent sunrise/sunset: the sun's upper limb on the horizon, with atmospheric refraction.
SUN_RISE_SET_DEG = -0.833


def solar_elevation_deg(lat: float, lon: float, when: datetime) -> float:
    """Elevation of the sun above the horizon in degrees (negative = below)."""
    utc = when.astimezone(timezone.utc)
    jd = utc.timestamp() / 86400.0 + 2440587.5  # Unix epoch is JD 2440587.5
    n = jd - 2451545.0
    mean_lon = (280.460 + 0.9856474 * n) % 360
    anomaly = math.radians((357.528 + 0.9856003 * n) % 360)
    ecl_lon = math.radians(mean_lon + 1.915 * math.sin(anomaly) + 0.020 * math.sin(2 * anomaly))
    obliquity = math.radians(23.439 - 0.0000004 * n)

    declination = math.asin(math.sin(obliquity) * math.sin(ecl_lon))
    right_asc = math.atan2(math.cos(obliquity) * math.sin(ecl_lon), math.cos(ecl_lon))
    gmst = (280.46061837 + 360.98564736629 * n) % 360
    hour_angle = math.radians((gmst + lon) % 360) - right_asc

    lat_r = math.radians(lat)
    sin_el = math.sin(lat_r) * math.sin(declination) + math.cos(lat_r) * math.cos(
        declination
    ) * math.cos(hour_angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))


@lru_cache(maxsize=16)
def _sun_times(lat: float, lon: float, day: date) -> tuple[Optional[datetime], Optional[datetime]]:
    start = datetime.combine(day, time.min).astimezone()  # local midnight, tz-aware
    rise: Optional[datetime] = None
    sett: Optional[datetime] = None
    prev = solar_elevation_deg(lat, lon, start)
    for minute in range(1, 24 * 60 + 1):
        t = start + timedelta(minutes=minute)
        el = solar_elevation_deg(lat, lon, t)
        if rise is None and prev < SUN_RISE_SET_DEG <= el:
            rise = (
                t.astimezone()
            )  # re-localise: `start` has a fixed offset, wrong across a DST change
        elif sett is None and prev >= SUN_RISE_SET_DEG > el:
            sett = t.astimezone()
        prev = el
    return rise, sett


def sun_times(lat: float, lon: float, day: date) -> tuple[Optional[datetime], Optional[datetime]]:
    """(sunrise, sunset) on local calendar *day*; None where the sun never crosses (polar)."""
    return _sun_times(round(lat, 3), round(lon, 3), day)
