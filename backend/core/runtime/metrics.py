"""Minimal, dependency-free Prometheus metrics (text exposition format 0.0.4)."""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, List, Mapping, Tuple

BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

HELP = {
    "sentinel_requests_total": ("counter", "Operations handled, by policy decision and how it was enforced."),
    "sentinel_hard_limit_violations_total": ("counter", "Hard-limit violations, by limit."),
    "sentinel_analysis_duration_seconds": ("histogram", "Time spent parsing, scoring and deciding (excludes upstream)."),
    "sentinel_request_duration_seconds": ("histogram", "Total time to handle a request including the upstream call."),
    "sentinel_alerts_total": ("counter", "Alert webhook notifications, by result (sent, failed, dropped)."),
}


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(labels: Mapping[str, str]) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{_esc(str(v))}"' for k, v in sorted(labels.items())) + "}"


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = defaultdict(float)
        self._hist: Dict[str, Dict[str, object]] = {}

    def inc(self, name: str, amount: float = 1.0, **labels: str) -> None:
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self._lock:
            self._counters[key] += amount

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            h = self._hist.setdefault(name, {"buckets": [0] * len(BUCKETS), "sum": 0.0, "count": 0})
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    h["buckets"][i] += 1  # type: ignore[index]
            h["sum"] += seconds  # type: ignore[operator]
            h["count"] += 1  # type: ignore[operator]

    def render(self, gauges: Mapping[str, Tuple[str, Mapping[str, str], float]] | None = None) -> str:
        """Render all metrics. ``gauges``: name -> (help, labels, value)."""
        lines: List[str] = []
        with self._lock:
            counters = dict(self._counters)
            hist = {k: {"buckets": list(v["buckets"]), "sum": v["sum"], "count": v["count"]}  # type: ignore[arg-type]
                    for k, v in self._hist.items()}
        for name in sorted({n for n, _ in counters}):
            kind, text = HELP.get(name, ("counter", name))
            lines += [f"# HELP {name} {text}", f"# TYPE {name} {kind}"]
            for (n, labels), value in sorted(counters.items()):
                if n == name:
                    lines.append(f"{n}{_labels(dict(labels))} {value:g}")
        for name, h in sorted(hist.items()):
            kind, text = HELP.get(name, ("histogram", name))
            lines += [f"# HELP {name} {text}", f"# TYPE {name} {kind}"]
            for bound, count in zip(BUCKETS, h["buckets"], strict=True):  # type: ignore[arg-type]
                lines.append(f'{name}_bucket{{le="{bound:g}"}} {count}')
            lines.append(f'{name}_bucket{{le="+Inf"}} {h["count"]}')
            lines.append(f"{name}_sum {h['sum']:.6f}")
            lines.append(f"{name}_count {h['count']}")
        for name, (text, labels, value) in sorted((gauges or {}).items()):
            lines += [f"# HELP {name} {text}", f"# TYPE {name} gauge", f"{name}{_labels(labels)} {value:g}"]
        return "\n".join(lines) + "\n"
