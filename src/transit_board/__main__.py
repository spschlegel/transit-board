"""Entry point: python -m transit_board [--dev]"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="transit-board",
        description="RGB LED Matrix transit departure board",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Dev mode: mock data, pygame preview window, no matrix hardware required",
    )
    parser.add_argument(
        "--config",
        default="config.toml",
        metavar="PATH",
        help="Path to config.toml (default: config.toml)",
    )
    parser.add_argument(
        "--force-idle",
        action="store_true",
        help="Always render the idle moon/starfield widget, regardless of time of day "
        "(for previewing it without waiting for the actual idle window)",
    )
    parser.add_argument(
        "--force-sports",
        action="store_true",
        help="Always render the full-takeover sports scores view, regardless of "
        "relevant-game count (for previewing in `make dev`). Wins over --force-idle.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        metavar="LEVEL",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx logs one INFO line per HTTP request ("HTTP Request: GET ... 200 OK") —
    # with transit refreshing every refresh.transit_secs per stop, that drowns out
    # our own logs at INFO level. Keep it at WARNING regardless of --log-level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    log = logging.getLogger(__name__)

    # Load config
    from transit_board import config as cfg_mod

    try:
        cfg = cfg_mod.load(Path(args.config))
    except FileNotFoundError as exc:
        if args.dev:
            log.warning("%s — using built-in defaults for dev mode", exc)
            cfg = cfg_mod.dev_default()
        else:
            log.error("%s", exc)
            sys.exit(1)

    # Import all modules before matrix init — rgbmatrix drop_privileges drops
    # the process back to the invoking user after hardware init, which can
    # disrupt subsequent imports from the venv.
    from transit_board.control import Control
    from transit_board.display.matrix import MatrixDisplay
    from transit_board.modes import Override
    from transit_board.supervisor import Supervisor

    try:
        matrix = MatrixDisplay(
            dev=args.dev,
            brightness=cfg.display.brightness_for(),
            rotation=cfg.display.rotation,
            y_offset=cfg.display.y_offset,
        )
    except RuntimeError as exc:
        log.error("%s", exc)
        sys.exit(1)

    event_loop = asyncio.new_event_loop()

    def _shutdown(sig: int, _frame: object) -> None:
        name = signal.Signals(sig).name
        log.info("Signal %s received — shutting down…", name)
        for task in asyncio.all_tasks(event_loop):
            task.cancel()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # --force-* are just a held manual override, same mechanism as the PWA's.
    control = Control()
    if args.force_sports:
        control.override = Override("sports")
    elif args.force_idle:
        control.override = Override("idle")

    supervisor = Supervisor(Path(args.config), cfg, matrix, control, dev=args.dev)

    try:
        event_loop.run_until_complete(supervisor.run_forever())
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        matrix.close()
        event_loop.close()
        log.info("Goodbye.")

    if supervisor.restart_requested:
        # Re-exec in place (same tty/tmux pane, same PID): picks up code changes and
        # re-initialises the matrix hardware from scratch. Only reached on a clean
        # shutdown, after matrix.close() above.
        log.info("Restarting…")
        logging.shutdown()
        os.execv(sys.executable, [sys.executable, "-m", "transit_board", *sys.argv[1:]])


if __name__ == "__main__":
    main()
