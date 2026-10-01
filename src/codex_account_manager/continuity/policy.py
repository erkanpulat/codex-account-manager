"""Choose verified accounts according to the configured switching policy."""

from __future__ import annotations

from dataclasses import dataclass

from codex_account_manager.domain.models import ProfileHealth
from codex_account_manager.domain.states import QuotaState, SwitchPolicyKind


@dataclass(frozen=True)
class SwitchDecision:
    should_switch: bool
    requires_confirmation: bool
    target: ProfileHealth | None
    reason: str


class SwitchPolicy:
    """Base policy: never switch automatically."""

    kind = SwitchPolicyKind.MANUAL

    def decide(
        self, current: ProfileHealth | None, candidates: list[ProfileHealth]
    ) -> SwitchDecision:
        return SwitchDecision(False, False, None, "Manual policy: no automatic switch.")

    @staticmethod
    def _is_available(h: ProfileHealth) -> bool:
        if h.error is not None or h.stale or h.reauth_required:
            return False
        if h.account_match is not True:
            return False
        if not h.auth_present:
            return False
        if h.quota_state in (QuotaState.LIMITED_WITH_RESET, QuotaState.LIMITED_NO_RESET):
            return False
        if h.ordinary_usage_allowed is False:
            return False
        return h.quota_state == QuotaState.AVAILABLE

    @staticmethod
    def _current_limited(current: ProfileHealth | None) -> bool:
        if current is None:
            return False
        return current.ordinary_usage_allowed is False or current.quota_state in (
            QuotaState.LIMITED_WITH_RESET,
            QuotaState.LIMITED_NO_RESET,
        )

    def _best_candidate(
        self, current: ProfileHealth | None, candidates: list[ProfileHealth]
    ) -> ProfileHealth | None:
        available = [
            c
            for c in candidates
            if self._is_available(c) and (current is None or c.profile_id != current.profile_id)
        ]
        if not available:
            return None
        # Prefer the profile with the most headroom (lowest peak usage).
        return min(available, key=_peak_usage)


class ConfirmPolicy(SwitchPolicy):
    """Propose a switch when the current profile is limited; wait for the user."""

    kind = SwitchPolicyKind.CONFIRM

    def decide(
        self, current: ProfileHealth | None, candidates: list[ProfileHealth]
    ) -> SwitchDecision:
        if not self._current_limited(current):
            return SwitchDecision(False, False, None, "Current profile still has capacity.")
        target = self._best_candidate(current, candidates)
        if target is None:
            return SwitchDecision(
                False, False, None, "No authorized, available profile to switch to."
            )
        return SwitchDecision(
            True, True, target, f"Current profile is usage-limited; suggest '{target.alias}'."
        )


class AvailabilityFailoverPolicy(SwitchPolicy):
    """Automatically fail over to an available authorized profile when limited."""

    kind = SwitchPolicyKind.AVAILABILITY_FAILOVER

    def decide(
        self, current: ProfileHealth | None, candidates: list[ProfileHealth]
    ) -> SwitchDecision:
        if not self._current_limited(current):
            return SwitchDecision(False, False, None, "Current profile still has capacity.")
        target = self._best_candidate(current, candidates)
        if target is None:
            return SwitchDecision(
                False, False, None, "No authorized, available profile to fail over to."
            )
        return SwitchDecision(
            True, False, target, f"Failing over to available profile '{target.alias}'."
        )


def _peak_usage(h: ProfileHealth) -> float:
    return max(h.primary_used_percent or 0.0, h.secondary_used_percent or 0.0)


_POLICIES: dict[SwitchPolicyKind, type[SwitchPolicy]] = {
    SwitchPolicyKind.MANUAL: SwitchPolicy,
    SwitchPolicyKind.CONFIRM: ConfirmPolicy,
    SwitchPolicyKind.AVAILABILITY_FAILOVER: AvailabilityFailoverPolicy,
}


def resolve_policy(kind: SwitchPolicyKind | str) -> SwitchPolicy:
    if isinstance(kind, str):
        kind = SwitchPolicyKind(kind)
    return _POLICIES[kind]()
