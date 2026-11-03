"""Generate deploy/observability/grafana/dashboards/sentinel.json (Prometheus datasource, uid "prometheus").

    python scripts/build_grafana_dashboard.py

Every panel is a PromQL query over metrics the gateway exports at /metrics (and the ext_proc exports on :9102).
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "deploy" / "observability" / "grafana" / "dashboards" / "sentinel.json"
DS = {"type": "prometheus", "uid": "prometheus"}
_id = 0


def _panel(kind: str, title: str, x: int, y: int, w: int, h: int, targets: list, **extra) -> dict:
    global _id
    _id += 1
    return {"id": _id, "type": kind, "title": title, "datasource": DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [{"datasource": DS, "refId": chr(65 + i), **t} for i, t in enumerate(targets)], **extra}


def stat(title, expr, x, y, w=4, h=4, unit="short", **fc):
    return _panel("stat", title, x, y, w, h, [{"expr": expr}],
                  fieldConfig={"defaults": {"unit": unit, **fc}, "overrides": []},
                  options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "area"})


def series(title, targets, x, y, w=12, h=8, unit="short", stack=False):
    custom = {"drawStyle": "line", "fillOpacity": 18, "lineWidth": 2, "showPoints": "never"}
    if stack:
        custom["stacking"] = {"mode": "normal"}
    return _panel("timeseries", title, x, y, w, h, targets,
                  fieldConfig={"defaults": {"unit": unit, "custom": custom}, "overrides": []},
                  options={"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}})


def bars(title, expr, legend, x, y, w=12, h=8):
    return _panel("bargauge", title, x, y, w, h, [{"expr": expr, "legendFormat": legend, "instant": True}],
                  fieldConfig={"defaults": {"unit": "short", "min": 0}, "overrides": []},
                  options={"orientation": "horizontal", "displayMode": "gradient", "reduceOptions": {"calcs": ["lastNotNull"]}})


def quantiles(metric):
    return [{"expr": f"histogram_quantile({q}, sum by (le) (rate({metric}_bucket[$__rate_interval])))", "legendFormat": f"p{int(q * 100)}"}
            for q in (0.5, 0.95, 0.99)]


panels = [
    stat("Requests / s", 'sum(rate(sentinel_requests_total[$__rate_interval]))', 0, 0, unit="reqps"),
    stat("Block ratio", 'sum(rate(sentinel_requests_total{decision="BLOCK"}[$__rate_interval])) / clamp_min(sum(rate(sentinel_requests_total[$__rate_interval])), 1e-9)',
         4, 0, unit="percentunit", thresholds={"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 0.2}, {"color": "red", "value": 0.5}]}),
    stat("Throttled / s", 'sum(rate(sentinel_requests_total{decision="THROTTLE"}[$__rate_interval]))', 8, 0, unit="reqps"),
    stat("p99 analysis time", 'histogram_quantile(0.99, sum by (le) (rate(sentinel_analysis_duration_seconds_bucket[$__rate_interval])))', 12, 0, unit="s"),
    stat("Hard-limit hits (range)", 'sum(increase(sentinel_hard_limit_violations_total[$__range]))', 16, 0),
    stat("Model loaded", 'max(sentinel_model_loaded)', 20, 0, mappings=[{"type": "value", "options": {"0": {"text": "rules only"}, "1": {"text": "ML on"}}}]),
    series("Decisions", [{"expr": 'sum by (decision) (rate(sentinel_requests_total[$__rate_interval]))', "legendFormat": "{{decision}}"}], 0, 4, unit="reqps", stack=True),
    series("How decisions were enforced", [{"expr": 'sum by (enforced) (rate(sentinel_requests_total[$__rate_interval]))', "legendFormat": "{{enforced}}"}], 12, 4, unit="reqps", stack=True),
    series("Analysis latency (parse, cost, score, decide)", quantiles("sentinel_analysis_duration_seconds"), 0, 12, unit="s"),
    series("End-to-end request latency (includes upstream)", quantiles("sentinel_request_duration_seconds"), 12, 12, unit="s"),
    bars("Rule hits by OWASP API Top 10 (2023) category", 'sum by (owasp) (increase(sentinel_rule_hits_total[$__range]))', "{{owasp}}", 0, 20),
    bars("Top rules", 'topk(10, sum by (rule) (increase(sentinel_rule_hits_total[$__range])))', "{{rule}}", 12, 20),
    bars("Hard limits hit", 'sum by (limit) (increase(sentinel_hard_limit_violations_total[$__range]))', "{{limit}}", 0, 28),
    series("Alert webhooks", [{"expr": 'sum by (result) (rate(sentinel_alerts_total[$__rate_interval]))', "legendFormat": "{{result}}"}], 12, 28, unit="ops"),
]

dashboard = {
    "uid": "sentinel-overview", "title": "GraphQL Sentinel", "tags": ["graphql", "security", "owasp"],
    "schemaVersion": 39, "version": 1, "editable": True, "refresh": "10s", "time": {"from": "now-30m", "to": "now"},
    "templating": {"list": []}, "annotations": {"list": []}, "panels": panels,
    "description": "Decisions, latency and rule hits mapped to OWASP API Security Top 10 (2023).",
}

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dashboard, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(panels)} panels)")
