"""Maps a risk tier to ALLOW / THROTTLE / BLOCK. Hard-limit violations always BLOCK."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .config import PolicyConfig

VALID_ACTIONS = ("ALLOW", "THROTTLE", "BLOCK")


class SecurityPolicy:
    def __init__(self, settings: Optional[Any] = None):
        self.settings = settings or PolicyConfig()
        self.tier_actions: Dict[str, str] = dict(self.settings.tier_actions)
        for tier, action in self.tier_actions.items():
            if action not in VALID_ACTIONS:
                raise ValueError(f"Invalid action {action!r} for tier {tier}")

    def decide(self, risk_tier: str, violations: Optional[List[str]] = None) -> str:
        if violations:
            return "BLOCK"
        # Unknown tiers fail closed to the most restrictive configured action.
        return self.tier_actions.get(risk_tier, "BLOCK")
