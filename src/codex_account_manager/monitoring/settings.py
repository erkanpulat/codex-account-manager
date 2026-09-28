"""Validated monitoring defaults shared by the watcher and desktop settings."""

from codex_account_manager.domain.states import SwitchPolicyKind

DEFAULT_POLICY = SwitchPolicyKind.AVAILABILITY_FAILOVER
DEFAULT_POLL_SECONDS = 60
MIN_POLL_SECONDS = 30
MAX_POLL_SECONDS = 3600


def poll_interval(value: object) -> int:
    try:
        interval = int(str(value))
    except (ValueError, TypeError):
        return DEFAULT_POLL_SECONDS
    return interval if MIN_POLL_SECONDS <= interval <= MAX_POLL_SECONDS else DEFAULT_POLL_SECONDS
