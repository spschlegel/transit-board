"""
Companion HTTP API + PWA, served from inside the board process.

Runs on the same asyncio loop as the render loop, so handlers must stay
cheap and never block (see CLAUDE.md on frame pacing). Everything under /api/
needs `Authorization: Bearer <BOARD_TOKEN>`; the static PWA files do not (the
page itself asks for the token). Meant for a trusted LAN only — the process
runs as root for GPIO access, so the API deliberately accepts nothing but a
fixed set of small JSON commands: no paths, no shell, no uploads.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

from transit_board.modes import SCENES, Override

if TYPE_CHECKING:
    from transit_board.supervisor import Supervisor

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent / "web"
_MAX_OVERRIDE_MINUTES = 24 * 60
_AUTH_FAIL_DELAY = 0.5  # slows down token guessing on the LAN


def _state_payload(sup: "Supervisor") -> dict[str, Any]:
    control, sched = sup.control, sup.cfg.schedule
    ov = control.override
    if ov is not None and not ov.active:
        ov = None
    return {
        "showing": control.panel_kind,
        "default": {"scene": control.default_scene, "reason": control.default_reason},
        "override": (
            None if ov is None else {"scene": ov.scene, "remaining_secs": ov.remaining_secs}
        ),
        "relevant_games": control.relevant_games,
        "scenes": list(SCENES),
        "override_minutes": sched.override_minutes,
        "transit_min_minutes": sched.transit_min_minutes,
    }


def _health_payload(sup: "Supervisor") -> dict[str, Any]:
    c, now = sup.control, time.time()
    return {
        "uptime_secs": int(now - c.started_at),
        "config_age_secs": int(now - c.config_loaded_at),
        "board_restarts": c.board_restarts,
        "board_last_error": c.board_last_error,
        "sources": {
            name: {
                "age_secs": int(now - c.last_refresh[name]) if name in c.last_refresh else None,
                "error": c.last_error.get(name),
            }
            for name in ("transit", "weather", "sports")
        },
    }


def make_app(sup: "Supervisor", token: str) -> web.Application:
    expected = f"Bearer {token}".encode()

    @web.middleware
    async def auth(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.path.startswith("/api/"):
            supplied = request.headers.get("Authorization", "").encode()
            if not hmac.compare_digest(supplied, expected):
                await asyncio.sleep(_AUTH_FAIL_DELAY)
                return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)

    async def get_state(_: web.Request) -> web.Response:
        return web.json_response(_state_payload(sup))

    async def get_health(_: web.Request) -> web.Response:
        return web.json_response(_health_payload(sup))

    async def set_override(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
        except ValueError as exc:
            return web.json_response({"error": f"bad JSON: {exc}"}, status=400)

        scene = body.get("scene")
        if scene not in SCENES:
            return web.json_response({"error": f"scene must be one of {list(SCENES)}"}, status=400)

        sched = sup.cfg.schedule
        minutes = body.get("minutes", sched.override_minutes)  # explicit null = hold
        if minutes is not None:
            if isinstance(minutes, bool) or not isinstance(minutes, int):
                return web.json_response(
                    {"error": "minutes must be an integer or null"}, status=400
                )
            if not 1 <= minutes <= _MAX_OVERRIDE_MINUTES:
                return web.json_response(
                    {"error": f"minutes must be 1-{_MAX_OVERRIDE_MINUTES}"}, status=400
                )
            if scene == "transit":
                minutes = max(minutes, sched.transit_min_minutes)

        sup.control.override = Override.for_minutes(scene, minutes)
        log.info("Override: %s for %s", scene, "hold" if minutes is None else f"{minutes} min")
        return web.json_response(_state_payload(sup))

    async def clear_override(_: web.Request) -> web.Response:
        sup.control.override = None
        log.info("Override cleared")
        return web.json_response(_state_payload(sup))

    async def reload(_: web.Request) -> web.Response:
        result = sup.reload()
        return web.json_response(result, status=200 if result["ok"] else 400)

    async def restart(_: web.Request) -> web.Response:
        # Respond first; the exec happens after the response has been flushed.
        asyncio.get_running_loop().call_later(0.5, sup.request_restart)
        return web.json_response({"ok": True}, status=202)

    async def index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app = web.Application(middlewares=[auth])
    app.router.add_get("/api/state", get_state)
    app.router.add_get("/api/health", get_health)
    app.router.add_post("/api/override", set_override)
    app.router.add_delete("/api/override", clear_override)
    app.router.add_post("/api/reload", reload)
    app.router.add_post("/api/restart", restart)
    app.router.add_get("/", index)
    app.router.add_static("/", WEB_DIR)
    return app
