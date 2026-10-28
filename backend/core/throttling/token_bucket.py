"""
Sliding-Window Token Bucket Rate Limiter.
Provides burst-tolerant, fine-grained rate limiting per client IP or API key.
"""
import time
import threading
from typing import Dict, Tuple, Optional


class TokenBucket:
    """
    Thread-safe Token Bucket for a single client actor.
    Tokens refill continuously at refill_rate (tokens/sec) up to capacity.
    """
    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def _refill(self, now: float):
        elapsed = now - self.last_refill
        if elapsed > 0:
            added = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + added)
            self.last_refill = now

    def consume(self, amount: float = 1.0) -> Tuple[bool, float]:
        """
        Attempt to consume 'amount' tokens.
        Returns:
            (allowed: bool, retry_after: float)
        """
        with self.lock:
            now = time.time()
            self._refill(now)

            if self.tokens >= amount:
                self.tokens -= amount
                return True, 0.0

            # Calculate seconds until enough tokens are replenished
            needed = amount - self.tokens
            retry_after = round(needed / self.refill_rate, 2) if self.refill_rate > 0 else 60.0
            return False, max(0.1, retry_after)

    @property
    def remaining(self) -> float:
        with self.lock:
            self._refill(time.time())
            return round(max(0.0, self.tokens), 2)


class TokenBucketLimiter:
    """
    Multi-client Token Bucket Manager.
    Maps client identifiers (IPs, API tokens, user IDs) to individual token buckets.
    """
    def __init__(self, rate_limit: int = 100, window_seconds: int = 60, burst_multiplier: float = 1.2):
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self.refill_rate = rate_limit / float(window_seconds) if window_seconds > 0 else 1.0
        self.capacity = float(rate_limit) * burst_multiplier
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def check(self, client_id: str, cost: float = 1.0) -> Tuple[bool, dict]:
        """
        Check rate limit for a given client actor.
        Returns:
            (is_allowed: bool, metadata: dict)
        """
        if not client_id:
            client_id = "unknown"

        with self._lock:
            if client_id not in self._buckets:
                self._buckets[client_id] = TokenBucket(
                    capacity=self.capacity,
                    refill_rate=self.refill_rate
                )
            bucket = self._buckets[client_id]

        allowed, retry_after = bucket.consume(cost)
        metadata = {
            "client_id": client_id,
            "allowed": allowed,
            "remaining": bucket.remaining,
            "capacity": self.capacity,
            "retry_after": retry_after,
            "limit": self.rate_limit,
            "window": self.window_seconds
        }
        return allowed, metadata

    def reset(self, client_id: Optional[str] = None):
        """Reset rate limiter state for a client, or all clients."""
        with self._lock:
            if client_id:
                self._buckets.pop(client_id, None)
            else:
                self._buckets.clear()
