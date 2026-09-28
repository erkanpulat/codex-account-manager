"""File-based credential store for the shared Codex home.

Codex reads ``auth.json`` from ``~/.codex`` (the shared home). Profiles keep
their own copy of ``auth.json`` under their profile dir. Switching means copying
a profile's ``auth.json`` into the shared home *atomically*.

This module only ever moves opaque bytes. It never parses, logs, or exposes the
credential contents, and it uses ``os.replace`` so the shared ``auth.json`` is
never left half-written.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from codex_account_manager.core.files import atomic_write
from codex_account_manager.core.paths import paths

_AUTH_FILE = "auth.json"
_FILE_AUTH_SETTING = 'cli_auth_credentials_store = "file"'


class FileCredentialStore:
    """Concrete :class:`CredentialStore` for the shared Codex home."""

    def __init__(self, shared_home: Path | None = None):
        self.shared_home = Path(shared_home) if shared_home else paths.shared_codex_home

    def profile_auth_path(self, codex_home: str | Path) -> Path:
        return Path(codex_home) / _AUTH_FILE

    @property
    def active_auth_path(self) -> Path:
        return self.shared_home / _AUTH_FILE

    def read_active(self) -> bytes | None:
        path = self.active_auth_path
        return path.read_bytes() if path.exists() else None

    def write_active_atomic(self, data: bytes) -> None:
        atomic_write(self.active_auth_path, data)

    def copy_profile_to_active(self, codex_home: str | Path) -> bytes | None:
        """Copy a profile's auth into the shared home atomically.

        Returns the previous active bytes (for rollback) or ``None`` if there
        was none. Raises ``FileNotFoundError`` if the profile has no auth.
        """
        source = self.profile_auth_path(codex_home)
        if not source.exists():
            raise FileNotFoundError(f"Profile auth.json not found under {codex_home}")
        previous = self.read_active()
        self.write_active_atomic(source.read_bytes())
        return previous

    def restore_active(self, data: bytes | None) -> None:
        if data is None:
            self.active_auth_path.unlink(missing_ok=True)
            return
        self.write_active_atomic(data)

    def sync_active_to_profile(self, codex_home: str | Path) -> None:
        """Persist the current active auth back into a profile (atomic)."""
        active = self.read_active()
        if active is None:
            return
        dest = self.profile_auth_path(codex_home)
        atomic_write(dest, active)

    def ensure_file_auth_config(self) -> None:
        """Make sure the shared home uses the file credential store."""
        self.shared_home.mkdir(parents=True, exist_ok=True)
        config = self.shared_home / "config.toml"
        text = config.read_text(encoding="utf-8-sig") if config.exists() else ""
        current = tomllib.loads(text)
        if current.get("cli_auth_credentials_store") == "file":
            return
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.lstrip().startswith("["):
                break
            key = line.split("=", 1)[0].strip().strip("\"'")
            if key == "cli_auth_credentials_store":
                lines[index] = _FILE_AUTH_SETTING + "\n"
                break
        updated = "".join(lines)
        if tomllib.loads(updated).get("cli_auth_credentials_store") != "file":
            updated = _FILE_AUTH_SETTING + "\n" + updated
        tomllib.loads(updated)
        atomic_write(config, updated.encode("utf-8"))
