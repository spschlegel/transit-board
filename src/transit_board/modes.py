"""
Which "scene" the departures-panel region shows, before sports-relevance and
hybrid layout are applied (those stay in loop._resolve_panel).

Two sources, in priority order:
  1. A manual Override (set from the companion PWA, or by --force-* flags),
     optionally expiring.
  2. The scheduled default: a transit window if one matches, else the night or
     day default.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from transit_board.config import SCENES, ScheduleConfig

__all__ = ["SCENES", "Override", "default_scene", "in_night"]


@dataclass
class Override:
    scene: str
    expires_at: Optional[float] = None  # time.monotonic() deadline; None = hold until cleared

    @property
    def active(self) -> bool:
        return self.expires_at is None or time.monotonic() < self.expires_at

    @property
    def remaining_secs(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        return max(0, int(self.expires_at - time.monotonic()))

    @classmethod
    def for_minutes(cls, scene: str, minutes: Optional[int]) -> "Override":
        return cls(scene, None if minutes is None else time.monotonic() + minutes * 60)


def in_night(sched: ScheduleConfig, now: datetime) -> bool:
    t = now.time()
    if sched.night_start <= sched.night_end:
        return sched.night_start <= t < sched.night_end
    return t >= sched.night_start or t < sched.night_end


def default_scene(sched: ScheduleConfig, now: datetime) -> tuple[str, str]:
    """Return (scene, reason) with reason in {"transit-window", "night", "day"}."""
    if any(w.contains(now) for w in sched.transit_windows):
        return "transit", "transit-window"
    if in_night(sched, now):
        return sched.night_default, "night"
    return sched.day_default, "day"
