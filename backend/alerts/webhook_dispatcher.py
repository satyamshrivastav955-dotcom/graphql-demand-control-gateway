"""
Asynchronous Security Incident Webhook Alert Dispatcher.
Supports Slack, Discord, and generic JSON webhooks with automatic formatting,
background dispatch, and alert flood rate-limiting.
"""
import time
import logging
import asyncio
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """
    Dispatches rich security incident cards to Slack, Discord, or custom SIEM webhooks.
    """
    def __init__(
        self,
        webhook_url: Optional[str] = None,
        enabled: bool = True,
        min_severity: str = "CRITICAL",
        cooldown_seconds: float = 60.0,
        http_client: Optional[httpx.AsyncClient] = None
    ):
        self.webhook_url = webhook_url
        self.enabled = bool(enabled and webhook_url)
        self.min_severity = min_severity.upper()
        self.cooldown_seconds = cooldown_seconds
        self._http_client = http_client
        self._owns_client = http_client is None
        self._last_alert_times: Dict[str, float] = {}

    def _should_suppress_flood(self, key: str) -> bool:
        """Rate-limit alerts per actor/attack signature to prevent channel flood."""
        now = time.time()
        last = self._last_alert_times.get(key, 0.0)
        if now - last < self.cooldown_seconds:
            return True
        self._last_alert_times[key] = now
        return False

    def build_slack_payload(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format an alert card for Slack Incoming Webhooks."""
        risk_tier = alert_data.get("risk_tier", "CRITICAL")
        color = "#e53e3e" if risk_tier == "CRITICAL" else "#dd6b20"
        return {
            "text": f"🚨 *GraphQL Sentinel Alert: {risk_tier} Attack Blocked*",
            "attachments": [
                {
                    "color": color,
                    "fields": [
                        {"title": "Client IP", "value": str(alert_data.get("ip", "unknown")), "short": True},
                        {"title": "Risk Score", "value": f"{alert_data.get('score', 0):.1f} / 100", "short": True},
                        {"title": "Decision", "value": alert_data.get("decision", "BLOCK"), "short": True},
                        {"title": "Attack Signature", "value": alert_data.get("attack_type", "Unknown"), "short": True},
                        {"title": "Query Preview", "value": f"```{alert_data.get('query', '')[:200]}```", "short": False},
                    ],
                    "footer": "GraphQL Sentinel Enterprise Gateway",
                    "ts": int(time.time())
                }
            ]
        }

    def build_discord_payload(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format an alert card for Discord Webhooks."""
        risk_tier = alert_data.get("risk_tier", "CRITICAL")
        color = 0xFF0000 if risk_tier == "CRITICAL" else 0xFFA500
        return {
            "content": f"🚨 **GraphQL Sentinel Incident: {risk_tier} Blocked**",
            "embeds": [
                {
                    "title": f"Security Violation: {alert_data.get('attack_type', 'Attack')}",
                    "color": color,
                    "fields": [
                        {"name": "Client IP", "value": str(alert_data.get("ip", "unknown")), "inline": True},
                        {"name": "Score", "value": f"{alert_data.get('score', 0):.1f}", "inline": True},
                        {"name": "Decision", "value": alert_data.get("decision", "BLOCK"), "inline": True},
                        {"name": "Query", "value": f"```{alert_data.get('query', '')[:250]}```", "inline": False},
                    ],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
            ]
        }

    def build_generic_payload(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format an alert for generic SIEM / HTTP ingest."""
        return {
            "event": "GRAPHQL_SECURITY_ALERT",
            "timestamp": time.time(),
            "incident": alert_data
        }

    def format_payload(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Select payload structure based on webhook destination URL."""
        url = (self.webhook_url or "").lower()
        if "slack.com" in url:
            return self.build_slack_payload(alert_data)
        elif "discord.com" in url:
            return self.build_discord_payload(alert_data)
        return self.build_generic_payload(alert_data)

    async def send_alert(self, alert_data: Dict[str, Any]) -> bool:
        """
        Send formatted alert to configured webhook.
        Returns True if delivered, False if suppressed or failed.
        """
        if not self.enabled or not self.webhook_url:
            return False

        tier = alert_data.get("risk_tier", "SAFE")
        if self.min_severity == "CRITICAL" and tier != "CRITICAL":
            return False

        actor = alert_data.get("ip") or alert_data.get("client_id") or "unknown"
        attack_type = alert_data.get("attack_type", "General")
        dedup_key = f"{actor}:{attack_type}"

        if self._should_suppress_flood(dedup_key):
            logger.info(f"Alert for {dedup_key} suppressed (flood cooldown active).")
            return False

        payload = self.format_payload(alert_data)
        try:
            client = self._http_client or httpx.AsyncClient(timeout=5.0)
            try:
                resp = await client.post(self.webhook_url, json=payload)
                if resp.status_code in (200, 204):
                    logger.info(f"Security alert dispatched successfully for {dedup_key}.")
                    return True
                else:
                    logger.warning(f"Webhook response status: {resp.status_code}")
                    return False
            finally:
                if self._owns_client and self._http_client is None:
                    await client.aclose()
        except Exception as e:
            logger.error(f"Failed to dispatch webhook alert: {e}")
            return False

    def dispatch_alert_background(self, alert_data: Dict[str, Any]):
        """Non-blocking fire-and-forget alert dispatch from synchronous or async contexts."""
        if not self.enabled or not self.webhook_url:
            return

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.send_alert(alert_data))
        except Exception as e:
            logger.debug(f"Could not dispatch alert task: {e}")
