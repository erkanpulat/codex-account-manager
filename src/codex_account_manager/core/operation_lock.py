"""Non-blocking interprocess lock, released by the OS even after a crash."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from codex_account_manager.core.errors import TransactionError


class OperationLock:
    def __init__(self, path: Path):
        self.path = path
        self._fd: int | None = None

    def __enter__(self) -> OperationLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise TransactionError(
                "Another operation is in progress. Retry after it completes.", stage="prepare"
            ) from exc
        self._fd = fd
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
