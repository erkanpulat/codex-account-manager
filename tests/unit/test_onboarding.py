import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QMessageBox
from scripts.render_preview import PreviewRunner

from codex_account_manager.gui.onboarding import SetupDialog, needs_setup
from codex_account_manager.storage.repositories import SettingsRepository


@pytest.fixture
def dialog(qt_app):
    setup = SetupDialog(PreviewRunner())
    setup.cli._checked("0.143.0")
    yield setup
    setup.close()
    setup.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


async def test_fresh_setup_defers_preferences_until_explicit_save(migrated_db, dialog):
    assert await needs_setup()
    assert not await SettingsRepository().all()
    dialog.monitoring.setChecked(False)
    dialog.reject()
    assert not await SettingsRepository().all()
    await SettingsRepository().set_many(dialog.values())
    assert not await needs_setup()
    assert await SettingsRepository().get("monitor_enabled") == "false"


async def test_existing_preferences_are_preserved_without_forcing_setup(migrated_db):
    await SettingsRepository().set("ide_continue", "true")
    assert not await needs_setup()
    assert await SettingsRepository().get("ide_continue") == "true"


async def test_setup_and_tracking_reset_leave_shared_codex_files_untouched(migrated_db):
    from codex_account_manager.continuity.tracking import WorkTracker
    from codex_account_manager.storage.database import initialize_database

    shared = migrated_db.shared_codex_home
    shared.mkdir(parents=True, exist_ok=True)
    session = shared / "sessions" / "synthetic.jsonl"
    session.parent.mkdir()
    session.write_bytes(b'{"synthetic":"conversation"}\n')
    (shared / "auth.json").write_bytes(b"synthetic credentials")
    before = {p.relative_to(shared): p.read_bytes() for p in shared.rglob("*") if p.is_file()}
    await initialize_database()
    await needs_setup()
    await WorkTracker().forget()
    assert {
        p.relative_to(shared): p.read_bytes() for p in shared.rglob("*") if p.is_file()
    } == before


def test_cli_and_ide_preferences_have_explicit_dependencies(dialog):
    dialog.cli._checked(None)
    assert not dialog.next.isEnabled()
    dialog._advance()
    assert dialog.pages.currentIndex() == 0
    dialog.cli._checked("0.143.0")
    dialog._advance()
    assert dialog.pages.currentIndex() == 1
    assert dialog.ide_refresh.isEnabled()
    assert dialog.values()["auto_continue"] == "true"
    assert dialog.values()["ide_continue"] == "true"
    assert dialog.values()["ide_refresh"] == "true"
    dialog.ide_continue.setChecked(True)
    dialog.ide_refresh.setChecked(True)
    dialog.ide_continue.setChecked(False)
    assert dialog.values()["ide_refresh"] == "false"
    assert dialog.values()["check_updates"] == "true"
    dialog._advance()
    dialog._advance()
    assert "Switch policy" in dialog.summary.text()


def test_cli_install_cannot_start_without_confirmation(dialog, monkeypatch):
    from unittest.mock import Mock

    dialog.cli._checked(None)
    submit = Mock()
    monkeypatch.setattr(dialog.cli.runner, "submit", submit)
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No)
    dialog.cli._install()
    submit.assert_not_called()


def test_cli_progress_survives_silent_installer_and_recovers_on_failure(dialog, monkeypatch):
    import time

    calls = []

    def submit(coro, on_result=None, on_error=None):
        coro.close()
        calls.append((on_result, on_error))

    dialog.cli._checked(None)
    monkeypatch.setattr(dialog.cli.runner, "submit", submit)
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes)
    dialog.cli._install()
    assert dialog.cli.busy and dialog.cli.timer.isActive()
    assert not dialog.next.isEnabled()
    assert dialog.cli.progress.maximum() == 0
    assert not dialog.cli.progress.isHidden()
    dialog.cli.started_at = time.monotonic() - 65
    dialog.cli._tick()
    assert "01:05" in dialog.cli.elapsed.text()
    dialog.cli.stage_changed.emit("install")
    assert dialog.cli.phase_rows[0][1].property("state") == "done"
    assert dialog.cli.phase_rows[1][1].property("state") == "current"
    dialog.cli.refresh()
    dialog.cli._install()
    assert len(calls) == 1
    calls[0][1](
        RuntimeError(
            "Codex CLI installation did not finish. Retry or use the official installation guide."
        )
    )
    assert not dialog.cli.busy and not dialog.cli.timer.isActive()
    assert dialog.cli.progress.isHidden()
    assert dialog.cli.install.isEnabled() and not dialog.cli.install.isHidden()
    assert not dialog.next.isEnabled()
    dialog.cli._install()
    calls[1][0]("0.143.0")
    assert dialog.next.isEnabled()
    assert dialog.cli.install.isHidden()
    assert not dialog.cli.timer.isActive()


def test_tr_setup_has_translations_for_visible_first_run_text(qt_app):
    from PySide6.QtWidgets import QLabel, QPushButton

    from codex_account_manager.gui.i18n import EN, TR, set_language

    set_language("tr")
    setup = SetupDialog(PreviewRunner())
    try:
        setup.cli._checked("0.143.0")
        setup.desktop._checked(False)
        known_english = (set(TR) | set(EN)) - {key for key, value in TR.items() if key == value}
        for widget in setup.findChildren(QLabel) + setup.findChildren(QPushButton):
            assert widget.text() not in known_english, widget.text()
    finally:
        setup.cli._checked(None)
        setup.close()
        setup.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        set_language("en")


def test_desktop_dependency_is_visible_without_blocking_quota_only_setup(dialog):
    dialog.desktop._checked(False)
    assert "not installed" in dialog.desktop.status.text()
    assert "VS Code remain available" in dialog.desktop.status.text()
    assert not dialog.desktop.download.isHidden()
    assert dialog.next.isEnabled()
    dialog.desktop._checked(True)
    assert dialog.desktop.download.isHidden()
    assert "installed" in dialog.desktop.status.text()
