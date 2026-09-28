"""Collect runtime dependency notices for the Windows binary distributions."""

from __future__ import annotations

import sys
from importlib.metadata import distribution, version
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def collect_notices(root: Path) -> Path:
    qt_version = version("PySide6")
    qt_notices = root / "packaging" / "licenses" / f"Qt-{qt_version}.txt"
    if not qt_notices.is_file():
        raise RuntimeError(f"Review Qt {qt_version} notices before building this version.")
    pending = ["codex-account-manager", "pyinstaller"]
    seen = set()
    sections = [
        "Binary dependency notices. Application source remains MIT licensed.",
        qt_notices.read_text(encoding="utf-8"),
    ]
    while pending:
        name = canonicalize_name(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        dist = distribution(name)
        # Include runtime extras for the app, not development dependencies.
        extra = "gui" if name == "codex-account-manager" else ""
        for raw in [] if name == "pyinstaller" else dist.requires or []:
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": extra}):
                pending.append(requirement.name)
        if name == "codex-account-manager":
            continue
        sections.append(f"\n{name} {dist.version}\n")
        for entry in sorted(dist.files or [], key=str):
            if not any(
                word in entry.name.lower()
                for word in ("license", "licence", "copying", "notice", "copyright")
            ):
                continue
            if entry.suffix.lower() not in {"", ".txt", ".md", ".rst"}:
                continue
            path = Path(dist.locate_file(entry))
            sections.append(
                f"--- {entry} ---\n{path.read_text(encoding='utf-8', errors='replace')}"
            )
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    sections.append(
        f"Python {sys.version.split()[0]}\n{python_license.read_text(encoding='utf-8')}"
    )
    output = root / "build" / "binary-notices" / "LICENSES.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sections), encoding="utf-8")
    return output
