"""Core, UI-agnostic foundation for QuotaCrew.

This package holds cross-cutting concerns used by every other layer:
paths, settings, structured logging with secret redaction, the single-instance
lock and the in-process event bus. Nothing here knows about Codex, the CLI or
the GUI.
"""

from codex_account_manager.core.errors import (
    AccountManagerError,
    AccountMismatchError,
    AppServerError,
    CodexNotFoundError,
    DesktopLaunchError,
    ProfileNotFoundError,
    TransactionError,
)
from codex_account_manager.core.paths import Paths, paths

__all__ = [
    "AccountMismatchError",
    "AppServerError",
    "CodexNotFoundError",
    "DesktopLaunchError",
    "ProfileNotFoundError",
    "AccountManagerError",
    "TransactionError",
    "Paths",
    "paths",
]
