# Changelog

## 0.1.1 — 2026-09-28

- Display usage reset credits on each account card. Shows available count and per-credit details (status, scope, granted/expiry times, description) in a plain-text dialog. Credit IDs are never stored or displayed; no credit is consumed by the app. Users are directed to Codex to redeem credits.
- Updated account overview text, English/Turkish README and synthetic screenshots for clarity.
- Keep installer and application versions aligned with an automated regression check.

## 0.1.0 — 2026-09-28

- Windows desktop application and CLI for managing multiple OpenAI Codex accounts.
- Quota monitoring with automatic switching, confirmation and manual modes; configurable 30–3600 second checks.
- Local conversation browser with project/source filters, search, resizable columns and full-path details.
- Turkish and English interface, dark/light themes, system tray, readable account/goal dialogs and optional Windows startup.
- Local goal notes and read-only native goal inspection. Verified usage-limit interruptions can initiate guarded automatic continuation after a committed handoff; approval/input requests still stop for the user.
- Identity verification, protected credential writes, account operation locks and recovery from interrupted switches. Current packaged Codex Desktop process detection, failed-switch retry backoff, and separate reporting when a conversation cannot load after a verified switch.
- Automated tests, dependency/secret scanning, Windows/Linux CI and Windows packaging tools.
