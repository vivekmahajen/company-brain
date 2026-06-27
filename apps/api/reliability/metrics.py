"""In-process request metrics (Phase 7).

Per-route counts, errors, and latency, plus global totals + uptime. In-process means
per-replica — fine for a single instance and a good baseline; a multi-replica deploy
would ship these to Prometheus/OTel (the recorder is the seam for that).
"""
from __future__ import annotations

import threading
import time


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self.requests = 0
        self.errors = 0
        self.routes: dict[str, dict] = {}

    def record(self, route: str, status: int, ms: float) -> None:
        with self._lock:
            self.requests += 1
            if status >= 500:
                self.errors += 1
            r = self.routes.setdefault(route, {"count": 0, "errors": 0, "total_ms": 0.0, "max_ms": 0.0})
            r["count"] += 1
            r["total_ms"] += ms
            r["max_ms"] = max(r["max_ms"], ms)
            if status >= 500:
                r["errors"] += 1

    def snapshot(self) -> dict:
        with self._lock:
            routes = {
                k: {"count": v["count"], "errors": v["errors"],
                    "avg_ms": round(v["total_ms"] / v["count"], 1) if v["count"] else 0.0,
                    "max_ms": round(v["max_ms"], 1)}
                for k, v in sorted(self.routes.items())
            }
            return {"uptime_s": round(time.time() - self.started, 1),
                    "requests": self.requests, "errors": self.errors, "routes": routes}

    def reset(self) -> None:
        with self._lock:
            self.requests = self.errors = 0
            self.routes.clear()


_METRICS = Metrics()


def metrics() -> Metrics:
    return _METRICS
