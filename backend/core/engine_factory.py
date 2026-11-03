"""Build the reusable decision engine from gateway settings (shared by the HTTP gateway and the Envoy ext_proc)."""
from __future__ import annotations

from typing import Optional, Tuple

from sentinel_core.cost import SchemaCost
from sentinel_core.engine import Engine
from sentinel_core.persisted import Allowlist
from sentinel_core.scoring import SecurityScorer

from .config import Settings


def build_engine(settings: Settings, scorer: SecurityScorer) -> Tuple[Engine, Optional[Allowlist]]:
    schema = None
    if settings.graphql_schema.path:
        schema = SchemaCost.from_file(settings.graphql_schema.path, settings.graphql_schema.default_list_size)
    allowlist: Optional[Allowlist] = None
    pq = settings.persisted_queries
    if pq.mode != "off":
        if not pq.manifest:
            raise ValueError("persisted_queries.manifest is required when persisted_queries.mode is not 'off'")
        allowlist = Allowlist.from_file(pq.manifest, pq.mode)
    engine = Engine(settings.limits, settings.security.policy, settings.security.introspection, scorer, schema,
                    allowlist, subscriptions="block", batching=settings.gateway.batching)
    return engine, allowlist
