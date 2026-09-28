"""Export diagnostic status without aliases, paths, raw errors or log contents."""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from codex_account_manager.core.files import atomic_write
from codex_account_manager.core.paths import paths
from codex_account_manager.diagnostics.doctor import run_diagnostics

_CHECK_NAMES = frozenset(
    {
        "codex_cli",
        "codex_version",
        "shared_codex_home",
        "session_history",
        "database",
        "profile_count",
        "profiles",
        "desktop_running",
        "pending_recovery",
        "timestamp",
    }
)


async def export_bundle(destination: Path | None = None) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    destination = destination or (paths.data_dir / f"diagnostics-{stamp}.zip")
    if destination.suffix.lower() != ".zip":
        raise ValueError("Diagnostics destination must be a .zip file.")

    checks_payload = []
    profile_number = 0
    for check in await run_diagnostics():
        if check.name.startswith("profile:"):
            profile_number += 1
            name = f"profile:{profile_number}"
        elif check.name in _CHECK_NAMES:
            name = check.name
        else:
            continue
        detail = "ready" if check.ok else "needs_attention"
        if name == "codex_version" and re.fullmatch(
            r"codex-cli [0-9]+\.[0-9]+\.[0-9]+", check.detail
        ):
            detail = check.detail
        elif name == "profile_count" and re.fullmatch(r"[0-9]{1,6}", check.detail):
            detail = check.detail
        checks_payload.append({"name": name, "ok": check.ok, "detail": detail})

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("diagnostics.json", json.dumps(checks_payload, indent=2))
        archive.writestr(
            "environment.json",
            json.dumps(
                {
                    "app": "Codex Account Manager",
                    "generated_at": stamp,
                },
                indent=2,
            ),
        )

    atomic_write(destination, buffer.getvalue())
    return destination
