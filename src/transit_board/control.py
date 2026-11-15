"""State shared between the render loop and the web server (single event loop, no locking)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from transit_board.modes import Override


@dataclass
class Control:
    # Manual override from the PWA (or a --force-* flag). Survives a soft reload.
    override: Optional[Override] = None

    # Written by the render loop every frame, read by the server for /api/state.
    default_scene: str = ""
    default_reason: str = ""
    panel_kind: str = ""
    relevant_games: int = 0

    # Written by the render loop's refresh helpers, read for /api/health.
    last_refresh: dict[str, float] = field(default_factory=dict)  # source -> epoch seconds
    last_error: dict[str, str] = field(default_factory=dict)  # source -> last failure text

    # Written by the supervisor.
    started_at: float = field(default_factory=time.time)
    config_loaded_at: float = field(default_factory=time.time)
    board_restarts: int = 0
    board_last_error: str = ""

    def refreshed(self, source: str) -> None:
        self.last_refresh[source] = time.time()
        self.last_error.pop(source, None)

    def failed(self, source: str, exc: object) -> None:
        self.last_error[source] = f"{type(exc).__name__}: {exc}"
