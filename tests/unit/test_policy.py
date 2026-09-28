from datetime import UTC, datetime

from codex_account_manager.continuity.policy import (
    AvailabilityFailoverPolicy,
    ConfirmPolicy,
    SwitchPolicy,
    resolve_policy,
)
from codex_account_manager.domain.models import ProfileHealth
from codex_account_manager.domain.states import QuotaState, SwitchPolicyKind


def _health(
    alias,
    *,
    active=False,
    allowed=True,
    quota=QuotaState.AVAILABLE,
    match=True,
    primary=0.0,
    secondary=0.0,
):
    return ProfileHealth(
        alias=alias,
        profile_id=alias,
        plan_type="plus",
        primary_used_percent=primary,
        secondary_used_percent=secondary,
        primary_resets_at=None,
        secondary_resets_at=None,
        ordinary_usage_allowed=allowed,
        auth_present=True,
        account_match=match,
        is_active=active,
        quota_state=quota,
        last_checked_at=datetime.now(UTC),
    )


def test_manual_never_switches():
    policy = SwitchPolicy()
    current = _health("a", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET)
    decision = policy.decide(current, [current, _health("b")])
    assert decision.should_switch is False


def test_confirm_suggests_when_limited():
    policy = ConfirmPolicy()
    current = _health("a", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET)
    other = _health("b", secondary=10.0)
    decision = policy.decide(current, [current, other])
    assert decision.should_switch is True
    assert decision.requires_confirmation is True
    assert decision.target.alias == "b"


def test_failover_switches_without_confirmation():
    policy = AvailabilityFailoverPolicy()
    current = _health("a", active=True, allowed=False, quota=QuotaState.LIMITED_NO_RESET)
    good = _health("b", secondary=5.0)
    busy = _health("c", secondary=95.0, allowed=False, quota=QuotaState.LIMITED_WITH_RESET)
    decision = policy.decide(current, [current, busy, good])
    assert decision.should_switch is True
    assert decision.requires_confirmation is False
    assert decision.target.alias == "b"  # most headroom


def test_failover_no_target_when_all_limited():
    policy = AvailabilityFailoverPolicy()
    current = _health("a", active=True, allowed=False, quota=QuotaState.LIMITED_WITH_RESET)
    other = _health("b", allowed=False, quota=QuotaState.LIMITED_WITH_RESET)
    decision = policy.decide(current, [current, other])
    assert decision.should_switch is False


def test_resolve_policy_by_kind():
    assert isinstance(resolve_policy(SwitchPolicyKind.MANUAL), SwitchPolicy)
    assert isinstance(resolve_policy("confirm"), ConfirmPolicy)
    assert isinstance(resolve_policy("availability_failover"), AvailabilityFailoverPolicy)
