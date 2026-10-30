"""Bounded, thread-safe sliding-window rate limiter."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Callable, Deque, Tuple


class SlidingWindowLimiter:
    """Allow at most ``limit`` events per ``window`` seconds for each key.

    Memory is bounded twice: each key stores at most ``limit`` timestamps and at most
    ``max_keys`` keys are tracked (least recently used keys are evicted).
    """

    def __init__(self, limit: int, window: float, max_keys: int = 10_000,
                 clock: Callable[[], float] = time.monotonic):
        if limit < 1 or window <= 0:
            raise ValueError("limit must be >= 1 and window > 0")
        self.limit = limit
        self.window = float(window)
        self.max_keys = max_keys
        self._clock = clock
        self._hits: OrderedDict[str, Deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def _prune(self, dq: Deque[float], now: float) -> None:
        cutoff = now - self.window
        while dq and dq[0] <= cutoff:
            dq.popleft()

    def check(self, key: str, consume: bool = True) -> Tuple[bool, float]:
        """Return ``(allowed, retry_after_seconds)``; consumes a slot when allowed."""
        now = self._clock()
        with self._lock:
            dq = self._hits.get(key)
            if dq is None:
                dq = deque(maxlen=self.limit)
                self._hits[key] = dq
                if len(self._hits) > self.max_keys:
                    self._hits.popitem(last=False)
            else:
                self._hits.move_to_end(key)
            self._prune(dq, now)
            if len(dq) >= self.limit:
                return False, max(0.0, dq[0] + self.window - now)
            if consume:
                dq.append(now)
            return True, 0.0

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._hits)
