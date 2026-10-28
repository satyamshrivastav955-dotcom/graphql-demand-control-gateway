import pytest
import httpx
from backend.alerts.webhook_dispatcher import WebhookDispatcher

def test_slack_payload_formatting():
    dispatcher = WebhookDispatcher(webhook_url="https://hooks.slack.com/services/TEST/SLACK/WEBHOOK")
    alert_data = {
        "ip": "1.2.3.4",
        "score": 95.0,
        "risk_tier": "CRITICAL",
        "decision": "BLOCK",
        "attack_type": "sql_injection",
        "query": "query { user(name: \"' OR 1=1\") { id } }"
    }
    payload = dispatcher.format_payload(alert_data)
    assert "attachments" in payload
    assert "text" in payload
    assert payload["attachments"][0]["color"] == "#e53e3e"
    fields = {f["title"]: f["value"] for f in payload["attachments"][0]["fields"]}
    assert fields["Client IP"] == "1.2.3.4"
    assert fields["Attack Signature"] == "sql_injection"

def test_discord_payload_formatting():
    dispatcher = WebhookDispatcher(webhook_url="https://discord.com/api/webhooks/123/ABC")
    alert_data = {
        "ip": "5.6.7.8",
        "score": 90.0,
        "risk_tier": "CRITICAL",
        "decision": "BLOCK",
        "attack_type": "circular_fragment_loop",
        "query": "query { user { ...A } }"
    }
    payload = dispatcher.format_payload(alert_data)
    assert "embeds" in payload
    assert payload["embeds"][0]["color"] == 0xFF0000

def test_generic_payload_formatting():
    dispatcher = WebhookDispatcher(webhook_url="https://siem.internal.company.com/ingest")
    alert_data = {"ip": "10.0.0.1", "score": 88.0, "risk_tier": "HIGH_RISK"}
    payload = dispatcher.format_payload(alert_data)
    assert payload["event"] == "GRAPHQL_SECURITY_ALERT"
    assert payload["incident"]["ip"] == "10.0.0.1"

def test_alert_cooldown_deduplication():
    dispatcher = WebhookDispatcher(
        webhook_url="https://hooks.slack.com/services/DEDUP",
        cooldown_seconds=60.0
    )
    # 1st alert should pass deduplication check
    assert dispatcher._should_suppress_flood("192.168.1.1:SQLi") is False
    # Immediate 2nd alert for same signature should be suppressed
    assert dispatcher._should_suppress_flood("192.168.1.1:SQLi") is True
    # Different actor should pass
    assert dispatcher._should_suppress_flood("192.168.1.2:SQLi") is False

@pytest.mark.anyio
async def test_alert_dispatch_mock_http():
    # Use custom mock transport to simulate webhook endpoint
    def mock_handler(request: httpx.Request):
        assert request.url == "https://hooks.slack.com/services/TEST"
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        dispatcher = WebhookDispatcher(
            webhook_url="https://hooks.slack.com/services/TEST",
            enabled=True,
            cooldown_seconds=0.0,
            http_client=mock_client
        )
        sent = await dispatcher.send_alert({
            "ip": "10.10.10.10",
            "score": 99.0,
            "risk_tier": "CRITICAL",
            "decision": "BLOCK",
            "attack_type": "sql_injection"
        })
        assert sent is True
