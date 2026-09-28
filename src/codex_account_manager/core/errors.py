"""Typed exception hierarchy for Codex Account Manager.

Exceptions never carry secret material. Messages are safe to log and to show in
the UI. Anything credential-shaped must be redacted before it reaches an
exception message (see :mod:`codex_account_manager.core.redaction`).
"""

from __future__ import annotations


class AccountManagerError(Exception):
    """Base class for all Codex Account Manager errors."""

    def __init__(self, message: str):
        from codex_account_manager.core.redaction import redact_text

        super().__init__(redact_text(message))


class CodexNotFoundError(AccountManagerError):
    """The Codex CLI could not be located on PATH."""


class AppServerError(AccountManagerError):
    """The Codex App Server failed to start, respond, or shut down cleanly."""


class DesktopContinuationRequired(AppServerError):
    """The conversation must retain its Desktop-owned tools and runtime."""


class DesktopLaunchError(AccountManagerError):
    """Codex Desktop could not be started or did not become ready in time."""


class AccountRecoveryRequired(AccountManagerError):
    """Stored sign-ins exist but their account catalogue is missing."""


class ProfileNotFoundError(AccountManagerError):
    """No profile matches the requested alias or id."""


class AccountMismatchError(AccountManagerError):
    """The active account does not match the profile's bound account."""


class TransactionError(AccountManagerError):
    """An auth switch transaction failed. Rollback state is described here."""

    def __init__(self, message: str, *, stage: str | None = None, rolled_back: bool = False):
        super().__init__(message)
        self.stage = stage
        self.rolled_back = rolled_back
