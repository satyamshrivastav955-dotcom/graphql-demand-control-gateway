"""Typed settings: backend/config/settings.yaml, overridden by environment variables.

Environment overrides:
  * Aliases: SENTINEL_UPSTREAM_URL, SENTINEL_MODE, SENTINEL_INTROSPECTION, SENTINEL_DEBUG,
    SENTINEL_DB_PATH, SENTINEL_CORS_ORIGINS (comma separated), SENTINEL_TRUST_PROXY_HEADERS.
  * Any setting by path: SENTINEL_<SECTION>__<KEY>, e.g. SENTINEL_LIMITS__MAX_DEPTH=10.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_FILE = ROOT / "backend" / "config" / "settings.yaml"


class AppSettings(BaseModel):
    name: str = "GraphQL Sentinel"
    version: str = "1.0.0"
    debug: bool = False
    # Serve the built dashboard/landing page (dashboard/dist) from the gateway, for local use and small deployments.
    serve_dashboard: bool = True
    dashboard_dir: Optional[str] = None


class GatewaySettings(BaseModel):
    mode: Literal["proxy", "simulation"] = "proxy"
    # enforce: block/throttle per policy. shadow: compute and record the real decision but forward everything
    # (report-only rollout). Size limits, parser budgets and the per-IP rate limit still protect the gateway itself.
    enforcement: Literal["enforce", "shadow"] = "enforce"
    upstream_url: Optional[str] = None
    upstream_timeout_seconds: float = 10.0
    max_upstream_response_bytes: int = 5_000_000
    forward_headers: List[str] = ["authorization", "x-request-id"]
    trust_proxy_headers: bool = False
    # When non-empty, /graphql-proxy requires `X-API-Key: <one of these>` (the management token is also accepted).
    client_keys: List[str] = []

    @field_validator("client_keys")
    @classmethod
    def _keys(cls, v: List[str]) -> List[str]:
        keys = [k.strip() for k in v if k and k.strip()]
        if any(len(k) < 16 for k in keys):
            raise ValueError("every gateway client key must be at least 16 characters")
        return keys

    @field_validator("upstream_url")
    @classmethod
    def _url(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("upstream_url must start with http:// or https://")
        return v


class Limits(BaseModel):
    max_body_bytes: int = 100_000
    max_query_length: int = 20_000
    max_depth: int = 15
    max_aliases: int = 50
    max_complexity: int = 20_000
    max_tokens: int = 5_000


class TierThresholds(BaseModel):
    safe: float = 20
    low_risk: float = 40
    medium_risk: float = 65
    high_risk: float = 85


class PolicySettings(BaseModel):
    risk_tier_thresholds: TierThresholds = TierThresholds()
    tier_actions: Dict[str, str] = {
        "SAFE": "ALLOW",
        "LOW_RISK": "ALLOW",
        "MEDIUM_RISK": "ALLOW",
        "HIGH_RISK": "THROTTLE",
        "CRITICAL": "BLOCK",
    }
    # None = use the weight recorded with the trained model (chosen on held-out attack categories).
    ml_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SecuritySettings(BaseModel):
    introspection: Literal["allow", "flag", "block"] = "flag"
    policy: PolicySettings = PolicySettings()


class ThrottleSettings(BaseModel):
    rate_limit: int = 100
    window_seconds: int = 60
    risky_quota: int = 5
    max_tracked_clients: int = 10_000


class StorageSettings(BaseModel):
    db_path: str = "backend/storage/sentinel.db"
    max_events: int = 50_000


class CorsSettings(BaseModel):
    allow_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    allow_credentials: bool = False
    allow_methods: List[str] = ["GET", "POST", "OPTIONS"]
    allow_headers: List[str] = ["*"]


class ApiSettings(BaseModel):
    """Protection of the management API (events, metrics, config, dry-run analysis, live stream)."""
    auth_required: bool = True
    token: Optional[str] = None
    auth_failures: int = 10
    auth_window_seconds: int = 300
    rate_limit_per_minute: int = 120
    max_live_streams: int = 5

    @field_validator("token")
    @classmethod
    def _token(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if len(v) < 16:
            raise ValueError("api.token must be at least 16 characters")
        return v


class AlertSettings(BaseModel):
    """Webhook notifications (Slack-compatible JSON) for blocked or throttled operations."""
    webhook_url: Optional[str] = None
    min_decision: Literal["THROTTLE", "BLOCK"] = "BLOCK"
    include_query: bool = False
    max_per_minute: int = Field(default=30, ge=1, le=600)
    timeout_seconds: float = 5.0

    @field_validator("webhook_url")
    @classmethod
    def _url(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("alerts.webhook_url must start with http:// or https://")
        return v


class Settings(BaseModel):
    app: AppSettings = AppSettings()
    api: ApiSettings = ApiSettings()
    gateway: GatewaySettings = GatewaySettings()
    limits: Limits = Limits()
    security: SecuritySettings = SecuritySettings()
    throttle: ThrottleSettings = ThrottleSettings()
    storage: StorageSettings = StorageSettings()
    cors: CorsSettings = CorsSettings()
    alerts: AlertSettings = AlertSettings()

    def resolved_db_path(self) -> str:
        if self.storage.db_path == ":memory:":
            return ":memory:"
        p = Path(self.storage.db_path)
        return str(p if p.is_absolute() else ROOT / p)


_ALIASES = {
    "SENTINEL_UPSTREAM_URL": ("gateway", "upstream_url"),
    "SENTINEL_MODE": ("gateway", "mode"),
    "SENTINEL_API_TOKEN": ("api", "token"),
    "SENTINEL_TRUST_PROXY_HEADERS": ("gateway", "trust_proxy_headers"),
    "SENTINEL_INTROSPECTION": ("security", "introspection"),
    "SENTINEL_DEBUG": ("app", "debug"),
    "SENTINEL_DB_PATH": ("storage", "db_path"),
    "SENTINEL_CORS_ORIGINS": ("cors", "allow_origins"),
    "SENTINEL_GATEWAY_KEYS": ("gateway", "client_keys"),
    "SENTINEL_ENFORCEMENT": ("gateway", "enforcement"),
    "SENTINEL_ALERT_WEBHOOK_URL": ("alerts", "webhook_url"),
}


def _set(tree: dict, path: tuple, value: Any) -> None:
    for key in path[:-1]:
        tree = tree.setdefault(key, {})
        if not isinstance(tree, dict):
            raise ValueError(f"cannot override {'.'.join(path)}")
    tree[path[-1]] = value


def _coerce(raw: str) -> Any:
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def load_settings(path: Optional[str] = None, env: Optional[Mapping[str, str]] = None) -> Settings:
    env_map: Mapping[str, str] = os.environ if env is None else env
    file = Path(path) if path else DEFAULT_SETTINGS_FILE
    data: dict = {}
    if file.exists():
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}

    for name, target in _ALIASES.items():
        raw = env_map.get(name)
        if raw is None or raw == "":
            continue
        if name in ("SENTINEL_CORS_ORIGINS", "SENTINEL_GATEWAY_KEYS"):
            _set(data, target, [o.strip() for o in raw.split(",") if o.strip()])
        elif name in ("SENTINEL_UPSTREAM_URL", "SENTINEL_DB_PATH", "SENTINEL_MODE", "SENTINEL_INTROSPECTION", "SENTINEL_API_TOKEN",
                      "SENTINEL_ENFORCEMENT", "SENTINEL_ALERT_WEBHOOK_URL"):
            _set(data, target, raw)
        else:
            _set(data, target, _coerce(raw))

    for name, raw in env_map.items():
        if name.startswith("SENTINEL_") and "__" in name and raw != "":
            parts = tuple(p.lower() for p in name[len("SENTINEL_"):].split("__"))
            _set(data, parts, _coerce(raw))

    return Settings.model_validate(data)
