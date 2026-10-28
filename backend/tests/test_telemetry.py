import pytest
from backend.telemetry.prometheus import PrometheusExporter
from backend.api.gateway import GraphQLGateway

def test_prometheus_exporter_records_and_formats():
    exporter = PrometheusExporter()
    exporter.record_request("ALLOW", "SAFE", 0.015)
    exporter.record_request("BLOCK", "CRITICAL", 0.005)
    exporter.record_blocked("sql_injection")
    exporter.record_batch(5)

    metrics = exporter.generate_metrics(quarantined_count=2)
    assert 'sentinel_requests_total{decision="ALLOW",tier="SAFE"} 1' in metrics
    assert 'sentinel_requests_total{decision="BLOCK",tier="CRITICAL"} 1' in metrics
    assert 'sentinel_blocked_total{reason="sql_injection"} 1' in metrics
    assert "sentinel_batch_requests_total 1" in metrics
    assert "sentinel_batch_operations_total 5" in metrics
    assert "sentinel_quarantined_actors 2" in metrics
    assert "sentinel_request_duration_seconds_count 2" in metrics

@pytest.mark.anyio
async def test_gateway_records_telemetry_on_query():
    config = {
        "security": {
            "throttling": {"rate_limit": 100, "window": 60},
            "policy": {"default_action": "ALLOW"}
        },
        "logging": {"save_path": "backend/storage/logs/test_decisions.jsonl"}
    }
    gateway = GraphQLGateway(config, {})
    client_info = {"ip": "127.0.0.1", "client_id": "metrics_client"}
    
    # Process safe query
    await gateway.process_request({"query": "query { user { id } }"}, client_info)
    metrics = gateway.telemetry.generate_metrics()
    assert 'sentinel_requests_total{decision="ALLOW",tier="SAFE"}' in metrics
