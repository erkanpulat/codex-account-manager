"""User-scoped Windows DPAPI envelopes for application-owned secrets.

The Windows release never falls back to plaintext if DPAPI fails. Non-Windows
source/test environments retain their existing file-permission storage model.
"""

from __future__ import annotations

import sys

from codex_account_manager.core.errors import AccountManagerError

MAGIC = b"QuotaCrew-DPAPI-v1\x00"


class CredentialProtectionError(AccountManagerError):
    pass


def available() -> bool:
    return sys.platform == "win32"


def protect(data: bytes, purpose: bytes) -> bytes:
    if not available():
        return data
    try:
        import win32crypt

        # UI_FORBIDDEN only: deliberately never use LOCAL_MACHINE scope.
        encrypted = win32crypt.CryptProtectData(data, "QuotaCrew", purpose, None, None, 1)
        result = MAGIC + encrypted
        if unprotect(result, purpose) != data:
            raise ValueError("Protection verification failed")
        return result
    except Exception:
        raise CredentialProtectionError(
            "Windows could not protect the sign-in data. The original was retained."
        ) from None


def unprotect(data: bytes, purpose: bytes) -> bytes:
    if not available() and not data.startswith(MAGIC):
        return data
    if not data.startswith(MAGIC):
        raise CredentialProtectionError("The protected sign-in file has an invalid format.")
    try:
        import win32crypt

        return win32crypt.CryptUnprotectData(data[len(MAGIC) :], purpose, None, None, 1)[1]
    except Exception:
        raise CredentialProtectionError(
            "Windows could not unlock the sign-in data. Use the original Windows user account or sign in again."
        ) from None
