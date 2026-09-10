"""Small local sliding-window limiter; replaceable by Redis in a scaled deployment."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    def __init__(self, per_minute: int):
        if per_minute < 1:
            raise ValueError("LMPC_RATE_LIMIT_PER_MIN must be positive")
        self.limit = per_minute
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def take(self, key: str, now: float | None = None) -> tuple[bool, int, int]:
        current = now if now is not None else time.monotonic()
        cutoff = current - 60
        with self.lock:
            events = self.events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(61 - (current - events[0])))
                return False, 0, retry_after
            events.append(current)
            return True, self.limit - len(events), 0
