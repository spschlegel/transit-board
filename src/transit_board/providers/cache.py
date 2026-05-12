"""Simple single-value TTL cache."""

from __future__ import annotations

import time
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Thread-safe-ish single-value cache with a time-to-live."""

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._value: Optional[T] = None
        self._expires: float = 0.0

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self._expires

    def get(self) -> Optional[T]:
        """Return cached value if not expired, else None."""
        if not self.expired:
            return self._value
        return None

    def set(self, value: T) -> None:
        """Store *value* and reset expiry timer."""
        self._value = value
        self._expires = time.monotonic() + self._ttl

    def invalidate(self) -> None:
        """Force expiry on next access."""
        self._expires = 0.0
