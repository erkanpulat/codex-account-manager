"""Quota evaluation: map an account snapshot to an actionable decision."""

from __future__ import annotations

from dataclasses import dataclass

from codex_account_manager.domain.models import AccountSnapshot
from codex_account_manager.domain.states import QuotaState


@dataclass(frozen=True)
class QuotaDecision:
    state: QuotaState
    allowed: bool
    reset_at: int | None
    reason: str


def evaluate_quota(snapshot: AccountSnapshot) -> QuotaDecision:
    if snapshot.ordinary_usage_allowed is True:
        return QuotaDecision(
            state=QuotaState.AVAILABLE,
            allowed=True,
            reset_at=None,
            reason="Backend allows normal usage.",
        )

    resets = [
        v for v in (snapshot.primary_resets_at, snapshot.secondary_resets_at) if v is not None
    ]
    next_reset = min(resets) if resets else None

    if snapshot.ordinary_usage_allowed is False:
        if next_reset is not None:
            return QuotaDecision(
                state=QuotaState.LIMITED_WITH_RESET,
                allowed=False,
                reset_at=next_reset,
                reason="Usage is limited; a reset time is available.",
            )
        return QuotaDecision(
            state=QuotaState.LIMITED_NO_RESET,
            allowed=False,
            reset_at=None,
            reason="Usage is limited and no reset time was reported.",
        )

    return QuotaDecision(
        state=QuotaState.UNKNOWN,
        allowed=False,
        reset_at=next_reset,
        reason="The backend did not report a definitive usage state.",
    )
