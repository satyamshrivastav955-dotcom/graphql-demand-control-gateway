"""Subscriptions over WebSocket (graphql-transport-ws): a policy-enforcing proxy.

Each ``subscribe`` message a client sends is analysed by the same engine as an HTTP operation before it is relayed.
Blocked operations are answered with an ``error`` message and never reach the upstream; the connection stays open so a
well-behaved client is unaffected. A connection may run at most ``websocket.max_subscriptions`` concurrent
subscriptions. All other messages (``connection_init``, ``ping``, ``complete``...) are relayed unchanged.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .gateway import ClientInfo, GraphQLGateway

logger = logging.getLogger(__name__)
router = APIRouter()
PROTOCOL = "graphql-transport-ws"


def upstream_ws_url(http_url: Optional[str], explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit
    if not http_url:
        return None
    return "ws" + http_url[4:] if http_url.startswith("http") else http_url


def _error(op_id: Any, message: str) -> str:
    return json.dumps({"id": op_id, "type": "error", "payload": [{"message": message}]})


@router.websocket("/graphql-ws")
async def graphql_ws(ws: WebSocket):
    gw: GraphQLGateway = ws.app.state.gateway
    cfg = gw.settings.websocket
    url = upstream_ws_url(gw.settings.gateway.upstream_url, gw.settings.gateway.upstream_ws_url)
    if not cfg.enabled or not url or gw.settings.gateway.mode == "simulation":
        await ws.close(code=1008)
        return
    client = ClientInfo(ip=ws.client.host if ws.client else "unknown", headers=dict(ws.headers))
    if gw.settings.gateway.trust_proxy_headers:
        fwd = ws.headers.get("x-forwarded-for", "")
        if fwd:
            client.ip = fwd.split(",")[0].strip() or client.ip
    try:
        gw.auth.require_client_key(ws, client.ip)  # type: ignore[arg-type] - same header API as Request
    except Exception:  # noqa: BLE001 - HTTPException from the auth helper
        await ws.close(code=1008)
        return
    await ws.accept(subprotocol=PROTOCOL if PROTOCOL in (ws.headers.get("sec-websocket-protocol") or "") else None)

    import websockets  # imported lazily: only needed when the endpoint is used

    active: Set[Any] = set()
    try:
        async with websockets.connect(url, subprotocols=[PROTOCOL], max_size=cfg.max_message_bytes,
                                      open_timeout=gw.settings.gateway.upstream_timeout_seconds) as up:

            async def client_to_upstream():
                while True:
                    raw = await ws.receive_text()
                    if len(raw) > cfg.max_message_bytes:
                        await ws.close(code=1009)
                        return
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        await ws.close(code=4400)
                        return
                    kind = msg.get("type") if isinstance(msg, dict) else None
                    if kind == "subscribe":
                        if await _admit(gw, ws, msg, client, active, cfg.max_subscriptions):
                            await up.send(raw)
                        continue
                    if kind == "complete":
                        active.discard(msg.get("id"))
                    await up.send(raw)

            async def upstream_to_client():
                async for raw in up:
                    with contextlib.suppress(ValueError, TypeError):
                        m = json.loads(raw)
                        if isinstance(m, dict) and m.get("type") == "complete":
                            active.discard(m.get("id"))
                    await ws.send_text(raw if isinstance(raw, str) else raw.decode())

            tasks = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in done:
                exc = t.exception()
                if exc and not isinstance(exc, (WebSocketDisconnect, websockets.ConnectionClosed)):
                    logger.warning("WebSocket proxy error: %s", exc)
    except (OSError, websockets.WebSocketException):
        logger.warning("Upstream WebSocket connection failed", exc_info=True)
        with contextlib.suppress(Exception):
            await ws.close(code=1011)
    finally:
        with contextlib.suppress(Exception):
            await ws.close()


async def _admit(gw: GraphQLGateway, ws: WebSocket, msg: Dict[str, Any], client: ClientInfo, active: Set[Any],
                 max_subscriptions: int) -> bool:
    """Analyse one subscribe message. Returns True if it may be relayed."""
    op_id = msg.get("id")
    payload = msg.get("payload")
    query = payload.get("query") if isinstance(payload, dict) else None
    if not isinstance(query, str) or not query.strip():
        await ws.send_text(_error(op_id, "A non-empty 'query' string is required"))
        return False
    if op_id in active or len(active) >= max_subscriptions:
        v_msg = "Too many concurrent subscriptions on this connection" if op_id not in active else "Subscriber for this id already exists"
        await ws.send_text(_error(op_id, v_msg))
        gw.metrics.inc("sentinel_requests_total", decision="BLOCK", enforced="blocked")
        return False
    verdict = gw.evaluate(query, payload.get("operationName"), payload.get("variables"), behavior_key=client.ip, transport="ws")
    gw.behavior.record(client.ip, query, is_error=verdict.decision in ("BLOCK", "ERROR"))
    allowed = verdict.decision == "ALLOW"
    enforced = "forwarded" if allowed else "blocked"
    if verdict.decision == "THROTTLE":
        ok, _ = gw.risky_limiter.check(client.ip)
        allowed, enforced = ok, "forwarded" if ok else "rate_limited"
    shadow = gw.settings.gateway.enforcement == "shadow" and verdict.decision in ("BLOCK", "THROTTLE")
    if shadow:
        allowed, enforced = True, "shadow"
    t0 = time.perf_counter()
    await gw._record(client, query, verdict, enforced, None, t0)
    if not allowed:
        text = verdict.error if verdict.decision == "ERROR" else "Operation blocked by security policy"
        await ws.send_text(_error(op_id, text or "Invalid GraphQL operation"))
        return False
    active.add(op_id)
    return True
