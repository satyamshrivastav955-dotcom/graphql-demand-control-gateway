"""
Automated Client Quarantine and Dynamic IP Blacklist Manager.
Auto-quarantines repeat malicious actors who trigger multiple CRITICAL violations,
and provides manual administrative ban/unban capabilities.
"""
import time
import threading
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class QuarantineRecord:
    def __init__(self, key: str, reason: str, duration_seconds: float, last_attack: str = "Unknown"):
        self.key = key
        self.reason = reason
        self.quarantined_at = time.time()
        self.expires_at = self.quarantined_at + duration_seconds
        self.last_attack = last_attack
        self.is_permanent = duration_seconds <= 0

    @property
    def is_expired(self) -> bool:
        if self.is_permanent:
            return False
        return time.time() >= self.expires_at

    @property
    def remaining_seconds(self) -> int:
        if self.is_permanent:
            return -1
        return max(0, int(self.expires_at - time.time()))

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "reason": self.reason,
            "quarantined_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.quarantined_at)),
            "expires_at": "Never" if self.is_permanent else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.expires_at)),
            "remaining_seconds": self.remaining_seconds,
            "last_attack": self.last_attack,
            "is_permanent": self.is_permanent,
        }


class QuarantineManager:
    """
    Manages automated threshold-based client quarantine and explicit IP blacklisting/whitelisting.
    """
    def __init__(
        self,
        violation_threshold: int = 3,
        window_seconds: int = 300,
        quarantine_duration_seconds: int = 900
    ):
        self.violation_threshold = violation_threshold
        self.window_seconds = window_seconds
        self.quarantine_duration_seconds = quarantine_duration_seconds

        self._violations: Dict[str, List[Tuple[float, str]]] = defaultdict(list)
        self._quarantined: Dict[str, QuarantineRecord] = {}
        self._whitelist: set = set()
        self._lock = threading.Lock()

    def record_violation(self, client_id: str, ip: str, attack_type: str = "Attack") -> bool:
        """
        Record a critical security violation.
        If violations within window_seconds >= threshold, auto-quarantines the actor.
        Returns:
            True if actor is now quarantined, False otherwise.
        """
        actor_key = ip if (ip and ip != "unknown") else client_id
        if not actor_key or actor_key == "unknown":
            return False

        with self._lock:
            if actor_key in self._whitelist or client_id in self._whitelist or ip in self._whitelist:
                return False

            now = time.time()
            self._violations[actor_key] = [
                (t, atk) for (t, atk) in self._violations[actor_key]
                if now - t <= self.window_seconds
            ]
            self._violations[actor_key].append((now, attack_type))

            if len(self._violations[actor_key]) >= self.violation_threshold:
                self._quarantined[actor_key] = QuarantineRecord(
                    key=actor_key,
                    reason=f"Repeated critical security violations ({len(self._violations[actor_key])} events in {self.window_seconds}s)",
                    duration_seconds=self.quarantine_duration_seconds,
                    last_attack=attack_type
                )
                return True
            return False

    def is_quarantined(self, client_id: str, ip: str) -> Tuple[bool, Optional[QuarantineRecord]]:
        """
        Check if an actor is currently quarantined or blacklisted.
        Returns (is_quarantined: bool, record: Optional[QuarantineRecord])
        """
        keys = [k for k in (ip, client_id) if k and k != "unknown"]
        if not keys:
            return False, None

        with self._lock:
            for key in keys:
                if key in self._whitelist:
                    return False, None

                record = self._quarantined.get(key)
                if record:
                    if record.is_expired:
                        del self._quarantined[key]
                    else:
                        return True, record

            return False, None

    def blacklist(self, key: str, reason: str = "Manual Administrator Blacklist"):
        """Explicitly add an IP or client ID to permanent blacklist."""
        with self._lock:
            self._whitelist.discard(key)
            self._quarantined[key] = QuarantineRecord(
                key=key,
                reason=reason,
                duration_seconds=0,
                last_attack="AdminBlacklist"
            )

    def whitelist(self, key: str):
        """Exempt an IP or client ID from quarantine."""
        with self._lock:
            self._whitelist.add(key)
            self._quarantined.pop(key, None)
            self._violations.pop(key, None)

    def unban(self, key: str) -> bool:
        """Unban a currently quarantined or blacklisted actor."""
        with self._lock:
            removed = self._quarantined.pop(key, None) is not None
            self._violations.pop(key, None)
            return removed

    def list_quarantined(self) -> List[dict]:
        """List all actively quarantined and blacklisted actors."""
        with self._lock:
            active = []
            now = time.time()
            expired_keys = []

            for key, rec in self._quarantined.items():
                if rec.is_expired:
                    expired_keys.append(key)
                else:
                    active.append(rec.to_dict())

            for k in expired_keys:
                del self._quarantined[k]

            return active
