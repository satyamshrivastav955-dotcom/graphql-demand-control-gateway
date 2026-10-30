"""Bearer-token protection for the management API (`/api/*` except health, readiness and evaluation).

* The token comes from `SENTINEL_API_TOKEN` (min. 16 characters). If auth is required and no token is configured,
  protected endpoints answer 503 (fail closed) rather than being open.
* Comparison is constant-time on SHA-256 digests.
* Failed attempts are counted per client IP; after `auth_failures` in the window the IP is locked out (429)
  even if it then presents the right token.
* Authenticated calls are rate limited per IP, and concurrent live streams are capped.
"""
from __future__ import annotations

import hashlib
import hmac
import threading
from typing import List, Optional

from fastapi import HTTPException, Request

from ..core.runtime.limiter import SlidingWindowLimiter


class AdminAuth:
    def __init__(self, token: Optional[str], required: bool, failures: int, window: int,
                 api_rate: int, max_streams: int, client_keys: Optional[List[str]] = None):
        self.required = required
        self._key_digests = [hashlib.sha256(k.encode()).digest() for k in (client_keys or [])]
        self._digest = hashlib.sha256(token.encode()).digest() if token else None
        self.failed = SlidingWindowLimiter(failures, window)
        self.key_failed = SlidingWindowLimiter(failures, window)  # separate: scanners must not lock out the operator
        self.api_rate = SlidingWindowLimiter(api_rate, 60)
        self._streams = 0
        self._max_streams = max_streams
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return self._digest is not None

    def is_authorised(self, request: Request, client_ip: str) -> bool:
        """True if the request carries a valid token (or auth is disabled). Never raises."""
        if not self.required:
            return True
        if self._digest is None or not self.failed.check(client_ip, consume=False)[0]:
            return False
        header = request.headers.get("authorization", "")
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not supplied:
            return False
        ok = hmac.compare_digest(hashlib.sha256(supplied.strip().encode()).digest(), self._digest)
        if not ok:
            self.failed.check(client_ip)  # consume one failure slot
        return ok

    def require(self, request: Request, client_ip: str) -> None:
        if not self.required:
            return
        if self._digest is None:
            raise HTTPException(status_code=503, detail="Management API token is not configured")
        allowed, retry = self.failed.check(client_ip, consume=False)
        if not allowed:
            raise HTTPException(status_code=429, detail="Too many failed attempts",
                                headers={"Retry-After": str(int(retry) + 1)})
        if not self.is_authorised(request, client_ip):
            raise HTTPException(status_code=401, detail="Invalid or missing bearer token",
                                headers={"WWW-Authenticate": "Bearer"})
        ok, retry = self.api_rate.check(client_ip)
        if not ok:
            raise HTTPException(status_code=429, detail="Management API rate limit exceeded",
                                headers={"Retry-After": str(int(retry) + 1)})

    @property
    def client_key_required(self) -> bool:
        return bool(self._key_digests)

    def require_client_key(self, request: Request, client_ip: str) -> None:
        """Gate for the enforcing endpoint. No-op unless gateway client keys are configured.

        Accepts any configured client key, or the management token, in `X-API-Key`.
        """
        if not self._key_digests:
            return
        allowed, retry = self.key_failed.check(client_ip, consume=False)
        if not allowed:
            raise HTTPException(status_code=429, detail="Too many failed attempts",
                                headers={"Retry-After": str(int(retry) + 1)})
        supplied = request.headers.get("x-api-key", "").strip()
        if supplied:
            digest = hashlib.sha256(supplied.encode()).digest()
            candidates = list(self._key_digests) + ([self._digest] if self._digest else [])
            matched = False
            for d in candidates:  # no early exit: constant work per candidate
                matched |= hmac.compare_digest(digest, d)
            if matched:
                return
        self.key_failed.check(client_ip)
        raise HTTPException(status_code=401, detail="A valid X-API-Key is required")

    def open_stream(self) -> bool:
        with self._lock:
            if self._streams >= self._max_streams:
                return False
            self._streams += 1
            return True

    def close_stream(self) -> None:
        with self._lock:
            self._streams = max(0, self._streams - 1)
