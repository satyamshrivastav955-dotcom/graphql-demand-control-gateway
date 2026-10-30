"""Webhook alerts for blocked / throttled operations.

Slack-compatible (`text` plus a structured `event`). The queue is bounded and sending is rate limited, so a flood of
attacks cannot turn the gateway into an alert amplifier; overflow is counted, not retried. The webhook URL is a
secret: it is never logged or exposed through the API.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from ..config import AlertSettings
from .limiter import SlidingWindowLimiter
from .metrics import Metrics

logger = logging.getLogger(__name__)
QUEUE_SIZE = 100


class AlertDispatcher:
    def __init__(self, settings: AlertSettings, metrics: Metrics, client: Optional[httpx.AsyncClient] = None):
        self.settings = settings
        self.metrics = metrics
        self._client = client
        self._owns_client = client is None
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._limiter = SlidingWindowLimiter(max(1, settings.max_per_minute), 60)
        self._task: Optional[asyncio.Task] = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.webhook_url)

    def wants(self, event: Dict[str, Any]) -> bool:
        if not self.enabled or event.get("enforced") == "rate_limited":
            return False  # rate-limit rejections are noise, not incidents
        decision = event.get("decision")
        return decision == "BLOCK" or (decision == "THROTTLE" and self.settings.min_decision == "THROTTLE")

    def submit(self, event: Dict[str, Any]) -> None:
        """Queue an alert without blocking the request path."""
        if not self.wants(event):
            return
        if not self._limiter.check("alerts")[0]:
            self.metrics.inc("sentinel_alerts_total", result="dropped")
            return
        try:
            self._queue.put_nowait(self._payload(event))
        except asyncio.QueueFull:
            self.metrics.inc("sentinel_alerts_total", result="dropped")

    def _payload(self, event: Dict[str, Any]) -> Dict[str, Any]:
        rules = [e["rule"] for e in (event.get("explanations") or []) if e.get("points", 0) > 0 or e.get("rule") == "hard_limit"][:4]
        body: Dict[str, Any] = {
            "id": event.get("id"), "timestamp": event.get("timestamp"), "decision": event.get("decision"),
            "enforced": event.get("enforced"), "risk_tier": event.get("risk_tier"), "score": event.get("score"),
            "ip": event.get("ip"), "operation_name": event.get("operation_name"), "rules": rules,
            "limit_violations": event.get("limit_violations") or [],
        }
        if self.settings.include_query:
            body["query"] = (event.get("query") or "")[:500]  # already credential-redacted by the event store
        text = (f"GraphQL Sentinel: {event.get('decision')} ({event.get('enforced')}) from {event.get('ip')}, "
                f"score {event.get('score')}, rules: {', '.join(rules) or 'n/a'}")
        return {"text": text, "event": body}

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.settings.timeout_seconds, follow_redirects=False)
        self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _worker(self) -> None:
        assert self._client is not None and self.settings.webhook_url
        while True:
            payload = await self._queue.get()
            try:
                resp = await self._client.post(self.settings.webhook_url, json=payload)
                self.metrics.inc("sentinel_alerts_total", result="sent" if resp.status_code < 300 else "failed")
            except Exception:  # noqa: BLE001 - never log the URL or exception text (may contain the secret)
                self.metrics.inc("sentinel_alerts_total", result="failed")
                logger.warning("Alert webhook delivery failed")
