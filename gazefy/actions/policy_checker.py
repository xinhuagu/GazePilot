"""PolicyChecker: enforce pack safety rules before action execution.

Loads policies/safety.yaml from the active ApplicationPack and checks
every action before execution.

safety.yaml example:
    forbidden_zones:
      - semantic_id: delete_all_button
        reason: "Destructive action — deletes all records"
    confirmation_required:
      - save_button
      - submit_form
    never_retry:
      - delete_record
      - format_disk
    timeouts:
      click: 5.0
      type: 10.0
      scroll: 3.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class PolicyResult(Enum):
    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    DENY = "deny"


@dataclass
class PolicyDecision:
    """Result of a policy check."""

    result: PolicyResult
    reason: str = ""


@dataclass
class PolicyChecker:
    """Enforces pack safety rules on actions."""

    forbidden_zones: dict[str, str] = field(default_factory=dict)  # semantic_id -> reason
    confirmation_required: set[str] = field(default_factory=set)
    never_retry: set[str] = field(default_factory=set)
    timeouts: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, pack_dir: Path) -> PolicyChecker:
        """Load safety policies from pack_dir/policies/safety.yaml."""
        policy_path = pack_dir / "policies" / "safety.yaml"
        if not policy_path.exists():
            logger.debug("No safety.yaml found in %s", pack_dir)
            return cls()

        with open(policy_path) as f:
            raw = yaml.safe_load(f) or {}

        checker = cls()

        # Forbidden zones
        for entry in raw.get("forbidden_zones", []):
            sid = entry.get("semantic_id", "")
            reason = entry.get("reason", "Forbidden by policy")
            if sid:
                checker.forbidden_zones[sid] = reason

        # Confirmation required
        for sid in raw.get("confirmation_required", []):
            checker.confirmation_required.add(sid)

        # Never retry
        for sid in raw.get("never_retry", []):
            checker.never_retry.add(sid)

        # Timeouts
        checker.timeouts = raw.get("timeouts", {})

        logger.info(
            "Loaded policies: %d forbidden, %d confirm, %d no-retry",
            len(checker.forbidden_zones),
            len(checker.confirmation_required),
            len(checker.never_retry),
        )
        return checker

    def check(self, action: dict, semantic_id: str = "") -> PolicyDecision:
        """Check if an action is allowed by policy.

        Args:
            action: Action dict with at least "action" and "target" keys
            semantic_id: The resolved semantic_id of the target element

        Returns:
            PolicyDecision with result and reason
        """
        target = semantic_id or action.get("target", "")

        # Check forbidden zones
        if target in self.forbidden_zones:
            reason = self.forbidden_zones[target]
            return PolicyDecision(
                result=PolicyResult.DENY,
                reason=f"Policy violation: {reason}",
            )

        # Check confirmation required
        if target in self.confirmation_required:
            return PolicyDecision(
                result=PolicyResult.REQUIRE_CONFIRMATION,
                reason=f"Action on '{target}' requires user confirmation",
            )

        return PolicyDecision(result=PolicyResult.ALLOW)

    def can_retry(self, semantic_id: str) -> bool:
        """Check if an action can be automatically retried."""
        return semantic_id not in self.never_retry

    def get_timeout(self, action_type: str) -> float:
        """Get timeout for an action type. Default 5.0s."""
        return self.timeouts.get(action_type, 5.0)

    def save_default(self, pack_dir: Path) -> Path:
        """Create a default safety.yaml template."""
        policy_dir = pack_dir / "policies"
        policy_dir.mkdir(parents=True, exist_ok=True)
        policy_path = policy_dir / "safety.yaml"

        default = {
            "forbidden_zones": [],
            "confirmation_required": [],
            "never_retry": [],
            "timeouts": {
                "click": 5.0,
                "type": 10.0,
                "scroll": 3.0,
                "drag": 5.0,
            },
        }
        with open(policy_path, "w") as f:
            yaml.dump(default, f, default_flow_style=False)

        logger.info("Created default safety.yaml at %s", policy_path)
        return policy_path
