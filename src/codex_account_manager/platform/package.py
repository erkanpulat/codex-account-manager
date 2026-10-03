"""Identify our own MSIX process without mistaking a packaged parent for it."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

STARTUP_TASK_ID = "QuotaCrewStartup"
STORE_UPDATES_URI = "ms-windows-store://downloadsandupdates"


@dataclass(frozen=True)
class PackageIdentity:
    full_name: str
    family_name: str
    path: Path


def _package_string(function_name: str) -> str | None:
    if sys.platform != "win32":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = getattr(kernel, function_name)
    function.argtypes = [ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    function.restype = wintypes.LONG
    length = wintypes.UINT()
    code = function(ctypes.byref(length), None)
    if code == 15700:  # APPMODEL_ERROR_NO_PACKAGE
        return None
    if code != 122 or not 0 < length.value <= 32768:  # ERROR_INSUFFICIENT_BUFFER
        raise OSError(code, "Windows could not read the application package identity.")
    buffer = ctypes.create_unicode_buffer(length.value)
    code = function(ctypes.byref(length), buffer)
    if code:
        raise OSError(code, "Windows could not read the application package identity.")
    return buffer.value


def current_package() -> PackageIdentity | None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    full_name = _package_string("GetCurrentPackageFullName")
    if full_name is None:
        return None
    directory = _package_string("GetCurrentPackagePath")
    if not directory or not Path(sys.executable).resolve().is_relative_to(
        Path(directory).resolve()
    ):
        # An EXE started by Codex may inherit Codex's identity. It is not our MSIX.
        return None
    family_name = _package_string("GetCurrentPackageFamilyName")
    if not family_name:
        raise OSError("Windows could not read the application package family.")
    return PackageIdentity(full_name, family_name, Path(directory))


def is_packaged() -> bool:
    return current_package() is not None


def startup_action(enabled: bool | None) -> bool:
    """Run on a worker thread; never undo a user's DisabledByUser state."""
    import asyncio

    from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
    from winrt.windows.applicationmodel import StartupTask, StartupTaskState

    async def update() -> bool:
        task = await StartupTask.get_async(STARTUP_TASK_ID)
        if enabled is None:
            return task.state == StartupTaskState.ENABLED
        if not enabled:
            task.disable()
            return task.state != StartupTaskState.ENABLED
        return await task.request_enable_async() == StartupTaskState.ENABLED

    async def bounded() -> bool:
        async with asyncio.timeout(10):
            return await update()

    init_apartment(ApartmentType.MULTI_THREADED)
    try:
        return asyncio.run(bounded())
    finally:
        uninit_apartment()
