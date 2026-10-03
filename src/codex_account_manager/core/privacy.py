"""The same offline privacy policy is available in source and binary installs."""

from __future__ import annotations

import sys
from pathlib import Path


def policy_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(vars(sys)["_MEIPASS"]) / "privacy/PRIVACY.html"
    source = Path(__file__).resolve().parents[3] / "PRIVACY.html"
    return source if source.is_file() else Path(sys.prefix) / "share/quotacrew/PRIVACY.html"
