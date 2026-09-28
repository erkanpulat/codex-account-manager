"""Startup entry point used by the Windows logon task.

Enforces a single instance and launches the GUI (which lives in the tray).
"""

from __future__ import annotations

import sys

from codex_account_manager.core.single_instance import SingleInstance


def main() -> int:
    lock = SingleInstance()
    if not lock.acquire():
        # Another instance already owns the tray.
        return 0
    try:
        from codex_account_manager.gui.app import run_gui

        return run_gui()
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
