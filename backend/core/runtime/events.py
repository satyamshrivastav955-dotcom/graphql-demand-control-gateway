"""SQLite-backed audit event store (bounded retention, thread-safe)."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple

_SENSITIVE_ARG = re.compile(
    r'(?i)\b(\w*(?:password|passwd|secret|token|ssn|creditcard|cardnumber|apikey|api_key|otp)\w*)\s*:\s*"(?:[^"\\]|\\.)*"'
)
MAX_STORED_QUERY = 10_000

COLUMNS = (
    "id", "timestamp", "client_id", "ip", "operation_name", "operation_type", "query", "decision",
    "enforced", "risk_tier", "score", "rule_score", "ml_score", "features", "explanations",
    "limit_violations", "upstream_status", "latency_ms", "total_latency_ms",
)
JSON_COLUMNS = ("features", "explanations", "limit_violations")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE NOT NULL,
    timestamp TEXT NOT NULL,
    client_id TEXT, ip TEXT, operation_name TEXT, operation_type TEXT, query TEXT,
    decision TEXT NOT NULL, enforced TEXT, risk_tier TEXT,
    score REAL, rule_score REAL, ml_score REAL,
    features TEXT, explanations TEXT, limit_violations TEXT,
    upstream_status INTEGER, latency_ms REAL, total_latency_ms REAL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_decision ON events(decision);
CREATE INDEX IF NOT EXISTS idx_events_client ON events(ip);
"""


def redact_query(query: str) -> str:
    """Mask string literals passed to credential-like arguments before persisting."""
    redacted = _SENSITIVE_ARG.sub(lambda m: f'{m.group(1)}: "[REDACTED]"', query)
    return redacted[:MAX_STORED_QUERY]


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class EventStore:
    def __init__(self, path: str, max_events: int = 50_000):
        self.path = path
        self.max_events = max_events
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            if path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
        self._inserts = 0

    # -- writes -------------------------------------------------------------------------
    def add(self, event: Dict[str, Any]) -> Dict[str, Any]:
        event = dict(event)
        event.setdefault("id", str(uuid.uuid4()))
        event.setdefault("timestamp", utc_now())
        event["query"] = redact_query(event.get("query") or "")
        row = []
        for col in COLUMNS:
            val = event.get(col)
            row.append(json.dumps(val if val is not None else ([] if col != "features" else {}))
                       if col in JSON_COLUMNS else val)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO events ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})", row)
            self._conn.commit()
            self._inserts += 1
            if self._inserts % 200 == 0:
                self._prune()
        return event

    def _prune(self) -> None:
        self._conn.execute(
            "DELETE FROM events WHERE seq <= (SELECT MAX(seq) FROM events) - ?", (self.max_events,))
        self._conn.commit()

    # -- reads --------------------------------------------------------------------------
    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        d = {c: row[c] for c in COLUMNS}
        for col in JSON_COLUMNS:
            d[col] = json.loads(d[col]) if d[col] else ({} if col == "features" else [])
        return d

    def get(self, event_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, limit: int = 50, offset: int = 0, decision: Optional[str] = None,
             tier: Optional[str] = None, q: Optional[str] = None, sort: str = "timestamp",
             order: str = "desc") -> Tuple[List[Dict[str, Any]], int]:
        where, args = [], []
        if decision:
            where.append("decision = ?")
            args.append(decision.upper())
        if tier:
            where.append("risk_tier = ?")
            args.append(tier.upper())
        if q:
            like = f"%{q.replace('%', '').replace('_', '')}%"
            where.append("(query LIKE ? OR client_id LIKE ? OR ip LIKE ? OR operation_name LIKE ?)")
            args += [like] * 4
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        sort_col = "score" if sort == "score" else "seq"
        direction = "ASC" if order.lower() == "asc" else "DESC"
        with self._lock:
            total = self._conn.execute(f"SELECT COUNT(*) FROM events {clause}", args).fetchone()[0]
            rows = self._conn.execute(
                f"SELECT * FROM events {clause} ORDER BY {sort_col} {direction}, seq {direction} LIMIT ? OFFSET ?",
                args + [max(1, min(limit, 500)), max(0, offset)]).fetchall()
        return [self._row(r) for r in rows], total

    def since(self, last_seq: int, limit: int = 200) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT *, seq AS s FROM events WHERE seq > ? ORDER BY seq ASC LIMIT ?", (last_seq, limit)).fetchall()
        newest = rows[-1]["s"] if rows else last_seq
        return [self._row(r) for r in rows], newest

    def max_seq(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]

    def client_timeline(self, ip: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT timestamp, score, decision FROM events WHERE ip = ? ORDER BY seq DESC LIMIT ?",
                (ip, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def window(self, since_iso: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT timestamp, ip, decision, risk_tier, score, latency_ms, explanations FROM events "
                "WHERE timestamp >= ? ORDER BY seq ASC", (since_iso,)).fetchall()
        return [dict(r) for r in rows]

    def ping(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self._conn.close()
