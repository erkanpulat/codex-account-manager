"""Non-forcing Windows shutdown; countdown and cancellation live in the GUI."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


def shutdown_windows() -> None:
    if sys.platform != "win32":
        raise OSError("Automatic shutdown requires Windows.")
    # Resolve the real system directory, never a PATH or environment-supplied binary.
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise OSError("The Windows system directory could not be verified.")
    command = Path(buffer.value) / "shutdown.exe"
    subprocess.run(
        [str(command), "/s", "/t", "0"],
        check=True,
        timeout=10,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
