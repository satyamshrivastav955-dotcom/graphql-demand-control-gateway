"""
Prometheus Metrics Exporter for GraphQL Sentinel.
Exposes standard Prometheus text exposition format (/metrics) for Grafana dashboards.
"""
import threading
from typing import Dict, Tuple
from collections import defaultdict


class PrometheusExporter:
    """
    Thread-safe Prometheus metric aggregator.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._requests_total: Dict[Tuple[str, str], int] = defaultdict(int)
        self._blocked_total: Dict[str, int] = defaultdict(int)
        self._batch_requests_total: int = 0
        self._batch_operations_total: int = 0
        self._latency_sum: float = 0.0
        self._latency_count: int = 0

    def record_request(self, decision: str, tier: str, latency_seconds: float):
        """Record processed GraphQL request."""
        with self._lock:
            self._requests_total[(decision.upper(), tier.upper())] += 1
            self._latency_sum += max(0.0, latency_seconds)
            self._latency_count += 1

    def record_blocked(self, reason: str):
        """Record blocked query by attack vector reason."""
        with self._lock:
            clean_reason = reason.lower().replace(" ", "_").replace("-", "_")
            self._blocked_total[clean_reason] += 1

    def record_batch(self, batch_size: int):
        """Record HTTP batch query execution."""
        with self._lock:
            self._batch_requests_total += 1
            self._batch_operations_total += max(1, batch_size)

    def generate_metrics(self, quarantined_count: int = 0) -> str:
        """
        Generate Prometheus exposition text format (0.0.4).
        """
        lines = []

        # 1. Total Requests
        lines.append("# HELP sentinel_requests_total Total number of GraphQL queries evaluated by Sentinel.")
        lines.append("# TYPE sentinel_requests_total counter")
        with self._lock:
            if not self._requests_total:
                lines.append('sentinel_requests_total{decision="ALLOW",tier="SAFE"} 0')
            else:
                for (dec, tier), count in sorted(self._requests_total.items()):
                    lines.append(f'sentinel_requests_total{{decision="{dec}",tier="{tier}"}} {count}')

            # 2. Blocked Requests by Reason
            lines.append("\n# HELP sentinel_blocked_total Total blocked attacks categorized by signature reason.")
            lines.append("# TYPE sentinel_blocked_total counter")
            if not self._blocked_total:
                lines.append('sentinel_blocked_total{reason="general"} 0')
            else:
                for reason, count in sorted(self._blocked_total.items()):
                    lines.append(f'sentinel_blocked_total{{reason="{reason}"}} {count}')

            # 3. Latency Histogram / Summary
            lines.append("\n# HELP sentinel_request_duration_seconds Evaluation latency in seconds.")
            lines.append("# TYPE sentinel_request_duration_seconds summary")
            lines.append(f"sentinel_request_duration_seconds_sum {self._latency_sum:.6f}")
            lines.append(f"sentinel_request_duration_seconds_count {self._latency_count}")

            # 4. Batch Requests
            lines.append("\n# HELP sentinel_batch_requests_total Total HTTP batch query arrays evaluated.")
            lines.append("# TYPE sentinel_batch_requests_total counter")
            lines.append(f"sentinel_batch_requests_total {self._batch_requests_total}")
            lines.append(f"sentinel_batch_operations_total {self._batch_operations_total}")

        # 5. Active Quarantined Actors Gauge
        lines.append("\n# HELP sentinel_quarantined_actors Currently active banned or quarantined client actors.")
        lines.append("# TYPE sentinel_quarantined_actors gauge")
        lines.append(f"sentinel_quarantined_actors {quarantined_count}\n")

        return "\n".join(lines)


# Global singleton instance
prometheus_exporter = PrometheusExporter()
