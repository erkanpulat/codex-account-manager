"""Launch and detect the packaged Codex Desktop on Windows."""

from __future__ import annotations

import asyncio
import time

from codex_account_manager.core.logging import get_logger
from codex_account_manager.platform import windows

log = get_logger(__name__)


class WindowsDesktopLauncher:
    def stop(self) -> None:
        windows.stop_desktop()

    def launch(self) -> None:
        windows.launch_desktop()

    def is_running(self) -> bool:
        return windows.is_desktop_running()

    async def wait_ready(self, timeout: float = 30.0) -> bool:
        """Wait for the packaged Desktop process after its launch."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_running():
                return True
            await asyncio.sleep(min(0.5, max(0, deadline - time.monotonic())))
        log.warning("Packaged Codex Desktop process was not observed before timeout.")
        return False
