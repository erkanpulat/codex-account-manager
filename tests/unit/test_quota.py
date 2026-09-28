from codex_account_manager.codex.quota import evaluate_quota
from codex_account_manager.domain.models import AccountSnapshot
from codex_account_manager.domain.states import QuotaState


def _snap(allowed, primary_reset=None, secondary_reset=None):
    return AccountSnapshot(
        account_id="a",
        account_type="chatgpt",
        email=None,
        plan_type="plus",
        ordinary_usage_allowed=allowed,
        primary_used_percent=0.0,
        primary_resets_at=primary_reset,
        primary_window_minutes=300,
        secondary_used_percent=0.0,
        secondary_resets_at=secondary_reset,
        secondary_window_minutes=10080,
    )


def test_available():
    d = evaluate_quota(_snap(True))
    assert d.state == QuotaState.AVAILABLE
    assert d.allowed is True


def test_limited_with_reset():
    d = evaluate_quota(_snap(False, primary_reset=123, secondary_reset=456))
    assert d.state == QuotaState.LIMITED_WITH_RESET
    assert d.allowed is False
    assert d.reset_at == 123


def test_limited_no_reset():
    d = evaluate_quota(_snap(False))
    assert d.state == QuotaState.LIMITED_NO_RESET
    assert d.allowed is False


def test_unknown():
    d = evaluate_quota(_snap(None))
    assert d.state == QuotaState.UNKNOWN
    assert d.allowed is False
