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
    assert not dialog.ide_refresh.isEnabled()
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
