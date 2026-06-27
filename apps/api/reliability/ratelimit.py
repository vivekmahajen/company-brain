"""Per-key fixed-window rate limiter (Phase 7).

Keyed by credential (or client IP). Disabled by default (limit 0); set
RATE_LIMIT_PER_MIN to enable. In-process (per replica) — a multi-replica deploy
would back this with Redis; the interface stays the same.
"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, int]] = {}  # key -> (window_minute, count)

    def allow(self, key: str, limit: int) -> tuple[bool, int]:
        """Return (allowed, retry_after_s). limit<=0 disables limiting."""
        if limit <= 0:
            return True, 0
        now = int(time.time())
        window = now // 60
        with self._lock:
            w, c = self._state.get(key, (window, 0))
            if w != window:
                w, c = window, 0
            c += 1
            self._state[key] = (w, c)
            if c > limit:
                return False, 60 - (now % 60)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._state.clear()


_LIMITER = RateLimiter()


def limiter() -> RateLimiter:
    return _LIMITER
