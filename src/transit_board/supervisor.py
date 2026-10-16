"""
Owns the render loop as a restartable task, next to the web server.

  * Crash isolation — if the render loop raises, log it and start it again
    (with backoff) instead of taking the process, and the PWA, down with it.
  * Soft reload — re-read config.toml, validate it, then swap the render-loop
    task. The server, the manual override and the MatrixDisplay all stay up.
    Options applied once at hardware init (rotation, y_offset) and the server
    bind address/port are NOT picked up; those need a full restart.
  * Full restart — stop everything and let __main__ re-exec the interpreter,
    which also picks up code changes.
"""

from __future__ import annotations

import asyncio
import logging
import time
import warnings
from pathlib import Path
from typing import Any, Optional

from aiohttp import web

from transit_board import config as cfg_mod
from transit_board.config import Config
from transit_board.control import Control
from transit_board.display.matrix import MatrixDisplay
from transit_board.loop import run
from transit_board.server import make_app

log = logging.getLogger(__name__)

_MAX_BACKOFF = 30.0
_HEALTHY_AFTER = 60.0  # a loop that ran this long before failing resets the backoff


class Supervisor:
    def __init__(
        self,
        config_path: Path,
        cfg: Config,
        matrix: MatrixDisplay,
        control: Control,
        dev: bool,
    ) -> None:
        self.config_path = config_path
        self.cfg = cfg
        self.matrix = matrix
        self.control = control
        self.dev = dev
        self.restart_requested = False
        self._pending_cfg: Optional[Config] = None
        self._wake = asyncio.Event()  # set by reload() / request_restart()
        self._stopping = False

    # ── Called from the web server ───────────────────────────────────────────

    def reload(self) -> dict[str, Any]:
        """Validate config.toml and schedule a render-loop swap. Never raises."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                new = cfg_mod.load(self.config_path)
            except FileNotFoundError:
                if not self.dev:
                    return {"ok": False, "error": f"{self.config_path} not found"}
                new = cfg_mod.dev_default()
            except Exception as exc:  # bad TOML, wrong types, ...
                log.warning("Config reload rejected: %s", exc)
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        notes = [str(w.message) for w in caught]
        if (new.display.rotation, new.display.y_offset) != (
            self.cfg.display.rotation,
            self.cfg.display.y_offset,
        ):
            notes.append("display.rotation / y_offset changed — needs a full restart to apply")
        if (new.server.host, new.server.port) != (self.cfg.server.host, self.cfg.server.port):
            notes.append("server.host / port changed — needs a full restart to apply")

        self._pending_cfg = new
        self._wake.set()
        log.info("Config reload scheduled")
        return {"ok": True, "notes": notes}

    def request_restart(self) -> None:
        log.info("Full restart requested")
        self.restart_requested = True
        self._stopping = True
        self._wake.set()

    # ── Main entry ───────────────────────────────────────────────────────────

    async def run_forever(self) -> None:
        runner = await self._start_server()
        backoff = 1.0
        try:
            while not self._stopping:
                started = time.monotonic()
                board = asyncio.create_task(
                    run(self.cfg, self.matrix, self.control, dev=self.dev), name="board"
                )
                wake = asyncio.create_task(self._wake.wait(), name="wake")
                try:
                    await asyncio.wait({board, wake}, return_when=asyncio.FIRST_COMPLETED)
                except asyncio.CancelledError:
                    await self._cancel(board, wake)
                    raise

                if self._wake.is_set():
                    self._wake.clear()
                    await self._cancel(board, wake)
                    if self._pending_cfg is not None:
                        self.cfg, self._pending_cfg = self._pending_cfg, None
                        self.control.config_loaded_at = time.time()
                        log.info("Config reloaded — render loop restarted")
                    continue

                # The render loop ended on its own: it crashed (run() swallows only cancellation).
                wake.cancel()
                exc = None if board.cancelled() else board.exception()
                self.control.board_restarts += 1
                self.control.board_last_error = f"{type(exc).__name__}: {exc}" if exc else "exited"
                log.error(
                    "Render loop stopped (%s); restarting in %.0fs",
                    exc or "exited",
                    backoff,
                    exc_info=exc,
                )
                if time.monotonic() - started > _HEALTHY_AFTER:
                    backoff = 1.0
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)
        finally:
            if runner is not None:
                await runner.cleanup()

    @staticmethod
    async def _cancel(*tasks: "asyncio.Task[Any]") -> None:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _start_server(self) -> Optional[web.AppRunner]:
        scfg = self.cfg.server
        if not scfg.enabled:
            return None
        if not scfg.token:
            log.warning("BOARD_TOKEN not set in .env — companion server disabled")
            return None
        runner = web.AppRunner(make_app(self, scfg.token), access_log=None)
        try:
            await runner.setup()
            await web.TCPSite(runner, scfg.host, scfg.port).start()
        except OSError as exc:
            # Never let a port clash stop the board itself.
            log.error("Companion server could not bind %s:%d: %s", scfg.host, scfg.port, exc)
            await runner.cleanup()
            return None
        log.info("Companion server on http://%s:%d", scfg.host, scfg.port)
        return runner
