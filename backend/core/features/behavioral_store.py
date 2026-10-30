"""Per-client behavioural features (in-memory, bounded)."""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict, deque
from typing import Callable, Deque, Dict, Tuple

EMPTY = {
    "query_rate": 0.0,
    "error_rate": 0.0,
    "repeated_pattern_score": 0.0,
    "request_frequency": 0.0,
    "recent_query_count": 0,
}


class BehavioralStore:
    """Tracks recent operations per client key to derive rate and repetition features.

    At most ``max_clients`` clients and ``max_history`` operations per client are kept, so
    memory stays bounded however many distinct clients connect.
    """

    def __init__(self, window_seconds: int = 60, max_history: int = 100, max_clients: int = 10_000,
                 clock: Callable[[], float] = time.time):
        self.window_seconds = window_seconds
        self.max_history = max_history
        self.max_clients = max_clients
        self._clock = clock
        self._history: OrderedDict[str, Deque[Tuple[float, str, bool]]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def fingerprint(query: str) -> str:
        return hashlib.blake2b(query.encode("utf-8", "ignore"), digest_size=8).hexdigest()

    def record(self, client_key: str, query: str, is_error: bool = False) -> None:
        with self._lock:
            dq = self._history.get(client_key)
            if dq is None:
                dq = deque(maxlen=self.max_history)
                self._history[client_key] = dq
                if len(self._history) > self.max_clients:
                    self._history.popitem(last=False)
            else:
                self._history.move_to_end(client_key)
            dq.append((self._clock(), self.fingerprint(query), is_error))

    def features(self, client_key: str) -> Dict[str, float]:
        now = self._clock()
        with self._lock:
            dq = self._history.get(client_key)
            recent = [e for e in dq if e[0] >= now - self.window_seconds] if dq else []
        if not recent:
            return dict(EMPTY)
        n = len(recent)
        span = max(now - recent[0][0], 1.0)
        errors = sum(1 for _, _, err in recent if err)
        unique = len({h for _, h, _ in recent})
        gaps = [recent[i][0] - recent[i - 1][0] for i in range(1, n)]
        freq = 1.0 / max(sum(gaps) / len(gaps), 0.001) if gaps else 0.0
        return {
            "query_rate": min(n / span, 100.0),
            "error_rate": errors / n,
            "repeated_pattern_score": 1.0 - unique / n,
            "request_frequency": min(freq, 50.0),
            "recent_query_count": n,
        }

    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._history)
