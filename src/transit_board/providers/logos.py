"""
Runtime-fetched, disk-cached team/player logo images for the sports widget.

Widgets are synchronous and run inline in the per-frame render loop — they
can't await a network fetch. So `ensure()` does all I/O (download, decode,
resize, disk-cache) during the async refresh phase (loop.py's
_refresh_sports), and `get_sync()` is a cheap in-memory dict lookup a widget
can call every frame. A URL that fails to fetch caches a `None` sentinel so
it isn't retried every refresh cycle — the widget's job is to fall back to a
text abbreviation whenever get_sync() returns None, whether that's because
the URL was never given to ensure(), or because the fetch failed.
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional

import httpx
from PIL import Image

log = logging.getLogger(__name__)

# Not under assets/ (shipped/bundled files) — this is a runtime cache, kept
# cwd-independent the same way renderer.py resolves _FONT_DIR, so it behaves
# the same under `make dev`, `make run`, or any future service wrapper.
_CACHE_DIR = Path(__file__).resolve().parent.parent / "_cache" / "logos"


class LogoCache:
    def __init__(self, size: tuple[int, int] = (14, 14), cache_dir: Optional[Path] = None) -> None:
        self._size = size
        self._dir = cache_dir or _CACHE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._http = httpx.AsyncClient(timeout=10.0)
        self._mem: dict[str, Optional[Image.Image]] = {}

    def _disk_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return self._dir / f"{key}.png"

    async def ensure(self, urls: Iterable[str]) -> None:
        """Fetch+decode+resize+cache any *urls* not already resolved this run."""
        for url in urls:
            if not url or url in self._mem:
                continue
            self._mem[url] = await self._load(url)

    async def _load(self, url: str) -> Optional[Image.Image]:
        disk_path = self._disk_path(url)
        if disk_path.exists():
            try:
                return Image.open(disk_path).convert("RGBA")
            except Exception as exc:
                log.warning("Corrupt cached logo %s, refetching: %s", disk_path, exc)

        try:
            r = await self._http.get(url)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            img = img.resize(self._size, Image.LANCZOS)
            img.save(disk_path)
            return img
        except Exception as exc:
            log.warning("Logo fetch failed for %s: %s", url, exc)
            return None

    def get_sync(self, url: Optional[str]) -> Optional[Image.Image]:
        """Cached, pre-resized image for *url* — None means "not available,
        fall back to text" (never fetched, or the fetch failed)."""
        if not url:
            return None
        return self._mem.get(url)

    async def aclose(self) -> None:
        await self._http.aclose()
