import pytest
from backend.core.quarantine.manager import QuarantineManager
from backend.api.gateway import GraphQLGateway

def test_quarantine_manager_violation_threshold():
    qm = QuarantineManager(violation_threshold=3, window_seconds=60, quarantine_duration_seconds=300)
    # 2 violations -> not quarantined yet
    assert qm.record_violation("client_1", "10.0.0.1", "SQLi") is False
    assert qm.record_violation("client_1", "10.0.0.1", "SQLi") is False
    is_q, _ = qm.is_quarantined("client_1", "10.0.0.1")
    assert is_q is False

    # 3rd violation -> quarantined
    quarantined = qm.record_violation("client_1", "10.0.0.1", "SQLi")
    assert quarantined is True
    is_q, record = qm.is_quarantined("client_1", "10.0.0.1")
    assert is_q is True
    assert record.remaining_seconds > 0

def test_quarantine_manager_whitelist_and_unban():
    qm = QuarantineManager(violation_threshold=1)
    qm.record_violation("safe_client", "10.0.0.2")
    is_q, _ = qm.is_quarantined("safe_client", "10.0.0.2")
    assert is_q is True

    # Unban
    assert qm.unban("10.0.0.2") is True
    is_q2, _ = qm.is_quarantined("safe_client", "10.0.0.2")
    assert is_q2 is False

def test_quarantine_manager_blacklist():
    qm = QuarantineManager()
    qm.blacklist("bad_ip", reason="Known malicious scanner")
    is_q, record = qm.is_quarantined("bad_client", "bad_ip")
    assert is_q is True
    assert record.is_permanent is True

@pytest.mark.anyio
async def test_gateway_automated_quarantine_flow():
    config = {
        "security": {
            "throttling": {"rate_limit": 100, "window": 60},
            "policy": {"default_action": "ALLOW"}
        },
        "logging": {"save_path": "backend/storage/logs/test_decisions.jsonl"}
    }
    gateway = GraphQLGateway(config, {})
    # Lower quarantine threshold for testing
    gateway.quarantine_manager.violation_threshold = 2
    client_info = {"ip": "192.168.99.99", "client_id": "attacker"}
    critical_attack_query = {"query": "query { a { b { c { d { e { f { g { h { i { j { k { l { m { n { o } } } } } } } } } } } } } } }"}

    # 1st attack: blocked with CRITICAL
    res1 = await gateway.process_request(critical_attack_query, client_info)
    assert res1["extensions"]["security"]["decision"] == "BLOCK"
    assert res1["extensions"]["security"]["risk_tier"] == "CRITICAL"

    # 2nd attack: triggers auto-quarantine threshold
    res2 = await gateway.process_request(critical_attack_query, client_info)
    assert res2["extensions"]["security"]["decision"] == "BLOCK"

    # 3rd request (even a benign SAFE query) should be immediately blocked due to quarantine
    safe_query = {"query": "query { user { id } }"}
    res3 = await gateway.process_request(safe_query, client_info)
    assert res3["extensions"]["security"]["decision"] == "BLOCK"
    assert res3["extensions"]["security"].get("quarantined") is True
    assert "quarantined" in res3["errors"][0]["message"].lower()
