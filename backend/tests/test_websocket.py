"""Subscriptions over WebSocket: each subscribe message is analysed before it is relayed."""
import asyncio
import json
import threading

import pytest

websockets = pytest.importorskip("websockets")

from .conftest import deep_query  # noqa: E402


class FakeUpstream:
    """A minimal graphql-transport-ws server that records what reaches it."""

    def __init__(self):
        self.received = []
        self.url = None
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    async def _handler(self, conn):
        async for raw in conn:
            msg = json.loads(raw)
            self.received.append(msg)
            if msg["type"] == "connection_init":
                await conn.send(json.dumps({"type": "connection_ack"}))
            elif msg["type"] == "subscribe":
                await conn.send(json.dumps({"id": msg["id"], "type": "next", "payload": {"data": {"tick": 1}}}))
                if "keep" not in msg["id"]:
                    await conn.send(json.dumps({"id": msg["id"], "type": "complete"}))

    def _run(self):
        asyncio.set_event_loop(self._loop)

        async def main():
            async with websockets.serve(self._handler, "127.0.0.1", 0, subprotocols=["graphql-transport-ws"]) as server:
                self.url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
                self._stop = asyncio.get_running_loop().create_future()
                self._ready.set()
                await self._stop

        try:
            self._loop.run_until_complete(main())
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self):
        self._thread.start()
        assert self._ready.wait(5)
        return self

    def __exit__(self, *_exc):
        self._loop.call_soon_threadsafe(self._stop.set_result, None)
        self._thread.join(5)


def sub(op_id, query):
    return json.dumps({"id": op_id, "type": "subscribe", "payload": {"query": query}})


def test_allowed_subscription_is_relayed_and_blocked_ones_never_reach_the_upstream(make_harness):
    with FakeUpstream() as up:
        h = make_harness({"gateway": {"upstream_ws_url": up.url}})
        with h.client.websocket_connect("/graphql-ws", subprotocols=["graphql-transport-ws"]) as ws:
            ws.send_text(json.dumps({"type": "connection_init"}))
            assert json.loads(ws.receive_text())["type"] == "connection_ack"
            ws.send_text(sub("1", "subscription { tick }"))
            assert json.loads(ws.receive_text())["type"] == "next"
            assert json.loads(ws.receive_text())["type"] == "complete"
            ws.send_text(sub("2", deep_query(25)))
            err = json.loads(ws.receive_text())
            assert err["type"] == "error" and err["id"] == "2"
        subs = [m for m in up.received if m["type"] == "subscribe"]
        assert [m["id"] for m in subs] == ["1"]
        decisions = [e["decision"] for e in h.events()["items"]]
        assert "BLOCK" in decisions and "ALLOW" in decisions


def test_concurrent_subscription_limit(make_harness):
    with FakeUpstream() as up:
        h = make_harness({"gateway": {"upstream_ws_url": up.url}, "websocket": {"max_subscriptions": 2}})
        with h.client.websocket_connect("/graphql-ws", subprotocols=["graphql-transport-ws"]) as ws:
            ws.send_text(json.dumps({"type": "connection_init"}))
            ws.receive_text()
            for i in range(2):
                ws.send_text(sub(f"keep{i}", "subscription { tick }"))
                assert json.loads(ws.receive_text())["type"] == "next"
            ws.send_text(sub("keep3", "subscription { tick }"))
            err = json.loads(ws.receive_text())
            assert err["type"] == "error" and "Too many" in err["payload"][0]["message"]
            ws.send_text(json.dumps({"id": "keep0", "type": "complete"}))
            ws.send_text(sub("keep4", "subscription { tick }"))
            assert json.loads(ws.receive_text())["type"] == "next"  # a slot was freed


def test_invalid_subscribe_payload_is_answered_with_an_error(make_harness):
    with FakeUpstream() as up:
        h = make_harness({"gateway": {"upstream_ws_url": up.url}})
        with h.client.websocket_connect("/graphql-ws", subprotocols=["graphql-transport-ws"]) as ws:
            ws.send_text(json.dumps({"id": "1", "type": "subscribe", "payload": {}}))
            assert json.loads(ws.receive_text())["type"] == "error"
        assert up.received == []


def test_http_endpoint_blocks_subscription_operations(make_harness):
    h = make_harness()
    r = h.post("subscription { tick }")
    assert r.status_code == 403 and "subscriptions_disabled" in r.json()["extensions"]["security"]["limit_violations"]
    assert h.calls == []


def test_websocket_can_be_disabled(make_harness):
    from starlette.websockets import WebSocketDisconnect
    h = make_harness({"websocket": {"enabled": False}})
    with pytest.raises(WebSocketDisconnect), h.client.websocket_connect("/graphql-ws"):
        pass
