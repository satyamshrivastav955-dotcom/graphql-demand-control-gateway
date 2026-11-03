"""Persisted-operation allowlist (safelist).

Accepted manifest formats:

* Apollo / Relay style: ``{"operations": [{"id": "<sha256>", "body": "query ..."}]}``
* A plain object ``{"<sha256>": "query ...", ...}``
* A list of query strings (hashes are computed)

An operation matches by the SHA-256 of its exact text or of its normalised form (parsed and re-printed, which
ignores whitespace and comments). Clients that send only ``extensions.persistedQuery.sha256Hash`` are resolved to the
registered body, so the gateway forwards text it has already vetted.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Optional, Tuple

from graphql import GraphQLError, parse, print_ast


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(query: str) -> Optional[str]:
    try:
        return print_ast(parse(query, no_location=True))
    except (GraphQLError, RecursionError):
        return None


class Allowlist:
    def __init__(self, operations: Optional[Dict[str, str]] = None, mode: str = "off"):
        if mode not in ("off", "log", "enforce"):
            raise ValueError("persisted-query mode must be off, log or enforce")
        self.mode = mode
        self.by_hash: Dict[str, str] = {}
        self._normalized: set = set()
        for h, body in (operations or {}).items():
            self.add(body, h)

    def add(self, body: str, op_id: Optional[str] = None) -> str:
        h = (op_id or sha256(body)).lower()
        self.by_hash[h] = body
        norm = normalize(body)
        if norm:
            self._normalized.add(sha256(norm))
        return h

    def __len__(self) -> int:
        return len(self.by_hash)

    @classmethod
    def from_file(cls, path: str, mode: str = "enforce") -> Allowlist:
        with open(path, encoding="utf-8") as fh:
            return cls.from_manifest(json.load(fh), mode)

    @classmethod
    def from_manifest(cls, data: Any, mode: str = "enforce") -> Allowlist:
        al = cls(mode=mode)
        if isinstance(data, dict) and isinstance(data.get("operations"), list):
            for op in data["operations"]:
                al.add(op["body"], op.get("id") or op.get("sha256Hash"))
        elif isinstance(data, dict):
            for h, body in data.items():
                al.add(body, h)
        elif isinstance(data, list):
            for body in data:
                al.add(body)
        else:
            raise ValueError("unsupported allowlist manifest")
        return al

    def contains(self, query: str) -> bool:
        if sha256(query) in self.by_hash:
            return True
        norm = normalize(query)
        return bool(norm) and sha256(norm) in self._normalized

    def resolve(self, query: Optional[str], extensions: Optional[dict]) -> Tuple[Optional[str], Optional[str]]:
        """Return ``(query_text, error)`` for a request that may carry only a persisted-query hash."""
        ext = (extensions or {}).get("persistedQuery") if isinstance(extensions, dict) else None
        if not isinstance(ext, dict):
            return query, None
        h = str(ext.get("sha256Hash", "")).lower()
        if query:
            if h and sha256(query) != h and self.mode == "enforce":
                return query, "PersistedQuery hash does not match the query"
            return query, None
        body = self.by_hash.get(h)
        if body is None:
            return None, "PersistedQueryNotFound"
        return body, None


def build_manifest(queries: Iterable[str]) -> dict:
    """Manifest for ``queries`` in the Apollo operation-manifest shape."""
    return {"version": 1, "operations": [{"id": sha256(q), "body": q} for q in queries]}
