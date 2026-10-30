"""Shared fixtures: a gateway wired to a recording stub upstream (no network)."""
from __future__ import annotations

import copy
from typing import Callable, Dict, List, Optional

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api.gateway import GraphQLGateway
from backend.core.config import Settings
from backend.core.runtime.events import EventStore
from backend.core.security_engine.scorer import SecurityScorer
from backend.main import create_app

UPSTREAM_URL = "http://upstream.test/graphql"
TOKEN = "test-token-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def deep_query(levels: int) -> str:
    return "{ " + "a { " * (levels - 1) + "x" + " }" * (levels - 1) + " }"


def alias_query(n: int) -> str:
    return "{ " + " ".join(f"u{i}: user(id: {i}) {{ name }}" for i in range(n)) + " }"


def merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = merge(out.get(k, {}), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


class Harness:
    def __init__(self, client: TestClient, calls: List[httpx.Request], gateway: GraphQLGateway, store: EventStore,
                 alert_calls: Optional[List[httpx.Request]] = None):
        self.client, self.calls, self.gateway, self.store = client, calls, gateway, store
        self.alert_calls = alert_calls if alert_calls is not None else []

    def post(self, query: str, **extra):
        headers = extra.pop("headers", None)
        return self.client.post("/graphql-proxy", json={"query": query, **extra}, headers=headers)

    def events(self, **params):
        return self.client.get("/api/events", params=params).json()


@pytest.fixture
def make_harness():
    stack: List[TestClient] = []

    def factory(overrides: Optional[dict] = None, handler: Optional[Callable[[httpx.Request], httpx.Response]] = None,
                use_model: bool = False, upstream: Optional[str] = UPSTREAM_URL,
                alert_handler: Optional[Callable[[httpx.Request], httpx.Response]] = None) -> Harness:
        base: Dict = {"gateway": {"upstream_url": upstream}, "api": {"token": TOKEN}, "throttle": {"rate_limit": 1000, "risky_quota": 1000},
                      "storage": {"db_path": ":memory:"}}
        settings = Settings.model_validate(merge(base, overrides or {}))
        calls: List[httpx.Request] = []

        def default_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"echo": "from-upstream"}})

        def recording(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return (handler or default_handler)(request)

        http = httpx.AsyncClient(transport=httpx.MockTransport(recording))
        alert_calls: List[httpx.Request] = []

        def alert_recording(request: httpx.Request) -> httpx.Response:
            alert_calls.append(request)
            return (alert_handler or (lambda r: httpx.Response(200)))(request)

        alert_http = httpx.AsyncClient(transport=httpx.MockTransport(alert_recording))
        store = EventStore(":memory:")
        scorer = SecurityScorer(settings.security.policy, settings.security.introspection, use_model=use_model)
        gw = GraphQLGateway(settings, store, scorer=scorer, http_client=http, alert_client=alert_http)
        client = TestClient(create_app(settings, gw))
        client.headers.update(AUTH)
        client.__enter__()
        stack.append(client)
        return Harness(client, calls, gw, store, alert_calls)

    yield factory
    for c in stack:
        c.__exit__(None, None, None)
