import os
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent
from scripts.render_preview import PreviewRunner

from codex_account_manager.gui import updates as gui_updates
from codex_account_manager.gui.onboarding import SetupDialog
from codex_account_manager.platform import package


def test_store_updater_opens_store_without_submitting_downloads_or_preferences(qt_app, monkeypatch):
    monkeypatch.setattr(package, "is_packaged", lambda: True)
    runner = PreviewRunner()
    panel = gui_updates.UpdatesPanel(runner, lambda: True)
    try:
        panel._loaded({"check_updates": "true"})
        assert not panel.automatic.isChecked()
        assert not panel.automatic.isEnabled()
        submit = Mock()
        monkeypatch.setattr(runner, "submit", submit)
        opened = Mock()
        monkeypatch.setattr(gui_updates.QDesktopServices, "openUrl", opened)
        panel.start()
        panel._save_preference(False)
        panel._scheduled_check()
        assert not panel.timer.isActive()
        panel.check_now()
        panel._update()
        assert opened.call_count == 2
        assert opened.call_args.args[0].toString() == package.STORE_UPDATES_URI
        submit.assert_not_called()
    finally:
        panel.close()
        panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_store_onboarding_preserves_direct_download_update_preferences(qt_app, monkeypatch):
    monkeypatch.setattr(package, "is_packaged", lambda: True)
    dialog = SetupDialog(PreviewRunner())
    try:
        assert not dialog.check_updates.isEnabled()
        assert "check_updates" not in dialog.values()
        assert dialog.values()["setup_completed"] == "true"
        assert dialog.values()["store_setup_completed"] == "true"
        assert dialog.values()["switch_policy"] == "availability_failover"
        assert dialog.values()["auto_continue"] == "true"
        assert dialog.values()["ide_continue"] == "true"
        assert dialog.values()["ide_refresh"] == "true"
    finally:
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
