"""Adapters that isolate Codex-specific details behind stable interfaces.

Anything that talks to the Codex CLI, App Server, Desktop app, or the on-disk
credential file lives here. Swapping Codex versions (or platforms) should mean
changing an adapter, not the core services.
"""
