from __future__ import annotations

from typing import Dict, List, Optional

from ..config import PolicySettings

VALID_ACTIONS = ("ALLOW", "THROTTLE", "BLOCK")


class SecurityPolicy:
    """Maps a risk tier to ALLOW / THROTTLE / BLOCK. Hard-limit violations always BLOCK."""

    def __init__(self, settings: Optional[PolicySettings] = None):
        self.settings = settings or PolicySettings()
        self.tier_actions: Dict[str, str] = dict(self.settings.tier_actions)
        for tier, action in self.tier_actions.items():
            if action not in VALID_ACTIONS:
                raise ValueError(f"Invalid action {action!r} for tier {tier}")

    def decide(self, risk_tier: str, violations: Optional[List[str]] = None) -> str:
        if violations:
            return "BLOCK"
        # Unknown tiers fail closed to the most restrictive configured action.
        return self.tier_actions.get(risk_tier, "BLOCK")
