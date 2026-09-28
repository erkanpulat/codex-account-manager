import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from scripts.render_preview import PreviewRunner, sample_profiles

from codex_account_manager.gui.async_runner import AsyncRunner
from codex_account_manager.gui.main_window import MainWindow
from codex_account_manager.gui.theme import stylesheet


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())
    yield app


@pytest.fixture
def window(app):
    window = MainWindow(PreviewRunner())
    window.dashboard._render(sample_profiles())
    yield window
    window.dispose()
    window.close()
    app.processEvents()


def test_all_screens_and_theme_switches(window, app):
    for dark in (True, False):
        window._apply_theme(dark)
        for row in range(7):
            window.nav.setCurrentRow(row)
            app.processEvents()
            assert window.stack.currentIndex() == row
    assert window.dashboard.palette_ == window.settings.palette_


def test_filter_and_empty_state(window):
    window.dashboard.search.setText("studio")
    assert set(window.dashboard._cards) == {"Studio"}
    window.dashboard.search.setText("no match")
    assert not window.dashboard._cards
    window.dashboard._render([])
    assert "0 accounts" in window.dashboard.summary.text()


def test_active_account_cannot_be_switched(window):
    assert not window.dashboard._cards["Personal"]._switch_btn.isEnabled()
    assert window.dashboard._cards["Studio"]._switch_btn.isEnabled()


def test_profile_actions_disabled_without_selection(window):
    assert all(not button.isEnabled() for button in window.accounts_view._profile_actions)


def test_async_callbacks_run_on_gui_thread_and_errors_are_visible(app):
    runner = AsyncRunner()
    main_thread = threading.get_ident()
    deliveries = []
    failures = []
    runner.failed.connect(failures.append)

    async def success():
        return threading.get_ident()

    async def failure():
        raise ValueError("password=short-secret")

    runner.submit(success(), lambda worker: deliveries.append((worker, threading.get_ident())))
    runner.submit(failure())
    deadline = time.monotonic() + 3
    while (not deliveries or not failures) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    runner.shutdown()
    assert deliveries and deliveries[0][0] != main_thread
    assert deliveries[0][1] == main_thread
    assert failures and "short-secret" not in failures[0]
    assert not runner._thread.is_alive()


def test_turkish_navigation_and_settings_use_stable_ids(app):
    from codex_account_manager.gui.i18n import set_language

    set_language("tr")
    window = MainWindow(PreviewRunner())
    try:
        assert window.nav.item(0).text().strip() == "Genel Bakış"
        assert window.nav.item(6).text().strip() == "Hakkında"
        assert window.settings.policy.itemData(0) == "manual"
        assert window.settings.policy.itemData(2) == "availability_failover"
        window.settings._loaded({"switch_policy": "confirm", "theme": "light"})
        assert window.settings.policy.currentData() == "confirm"
        assert "Onaylı mod" in window.dashboard.mode_label.text()
        assert window.settings.theme.currentData() == "light"
        window.dashboard._render([])
        assert window.dashboard.summary.isHidden()
        assert window.dashboard.hero.isHidden()
    finally:
        window.dispose()
        window.close()
        app.processEvents()
        set_language("en")


def test_conversation_filters_full_paths_and_resizable_columns(window):
    from PySide6.QtWidgets import QHeaderView

    from codex_account_manager.domain.models import ThreadRecord

    view = window.conversations
    long_path = "C:/Work/An example project with a long name/packages/application"
    view._render_threads(
        [
            ThreadRecord(
                id="one", title="Improve navigation", cwd=long_path, source="vscode", project_id="a"
            ),
            ThreadRecord(
                id="two", title="Check CLI", cwd="C:/Work/cli", source="cli", project_id="b"
            ),
            ThreadRecord(
                id="three",
                title="Review navigation",
                cwd=long_path,
                source="subAgent",
                project_id="a",
            ),
        ]
    )
    assert view.table.rowCount() == 2
    view.source.setCurrentIndex(view.source.findData(""))
    assert view.table.rowCount() == 3
    view.project.setCurrentIndex(view.project.findData("a"))
    assert view.table.rowCount() == 2
    view.source.setCurrentIndex(view.source.findData("vscode"))
    assert view.table.rowCount() == 1
    assert view.table.item(0, 4).toolTip() == long_path
    assert view.table.horizontalHeader().sectionResizeMode(4) == QHeaderView.ResizeMode.Interactive
    view.table.selectRow(0)
    assert long_path in view.details.toPlainText()
    assert all(button.isEnabled() for button in view._actions)
    view.search.setText("no matching conversation")
    assert view.table.rowCount() == 0
    assert all(not button.isEnabled() for button in view._actions)


def test_tracking_failure_is_visible_and_not_replaced_by_empty_snapshot(window):
    view = window.conversations
    view.show_tracking_status({"state": "timed_out"})
    view._render_tracking(([], {}))
    assert "timed out" in view.tracking_status.text()
    assert view.check_tracking.isEnabled()
    view.show_tracking_status({"state": "checking"})
    assert not view.check_tracking.isEnabled()
    view.show_tracking_status(
        {"state": "partial", "checked": 3, "unavailable": 2, "checked_at": "12:00:00"}
    )
    assert "2 conversations" in view.tracking_status.text()
    assert "12:00:00" in view.tracking_status.text()


def test_tracked_work_explains_turn_and_goal_without_storing_objective(window):
    from codex_account_manager.continuity.tracking import ObservedWork

    view = window.conversations
    view._render_tracking(
        (
            [
                ObservedWork(
                    "thread-a", "account-hash", "failed", "usageLimited", True, True, 1_800_000_000
                )
            ],
            {"account-hash": "Work"},
        )
    )
    assert view.tracked_table.rowCount() == 1
    assert view.tracked_table.item(0, 1).text() == "Work"
    assert view.tracked_table.item(0, 2).text() == "Limit reached"
    assert "usage" in view.tracked_table.item(0, 3).text().lower()
    assert view.tracked_empty.isHidden()
    view.tracked_table.selectRow(0)
    assert view.tracked_goal.isEnabled()


def test_conversation_refresh_failure_keeps_rows_and_unlocks_button(window):
    from codex_account_manager.domain.models import ThreadRecord

    view = window.conversations
    view._render_threads([ThreadRecord(id="one", title="Previous result")])
    view._sync()
    assert not view.sync.isEnabled()
    view._sync_failed(RuntimeError("Unavailable"))
    assert view.sync.isEnabled()
    assert view.table.rowCount() == 1
    assert "Unavailable" in view.status.text()


def test_settings_defaults_and_minimal_navigation(window):
    window.settings._loaded({})
    assert window.settings.policy.currentData() == "availability_failover"
    assert window.settings.interval.value() == 60
    assert window.settings.auto_continue.isChecked()
    assert window.settings.interval.minimum() == 30
    assert window.settings.interval.maximum() == 3600
    assert window.nav.item(3).isHidden()
    assert window.nav.item(4).isHidden()
    window._open_tool(4)
    assert window.stack.currentIndex() == 4


def test_small_window_and_keyboard_search(window, app):
    window.resize(1180, 760)
    window.show()
    app.processEvents()
    assert window.width() == 1180 and window.height() == 760
    window._focus_search()
    assert window.focusWidget() is window.dashboard.search
    window.nav.setCurrentRow(5)
    app.processEvents()
    assert window.settings.interval.isVisible()
    window._open_tool(3)
    assert not window.back_to_settings.isHidden()
    window.back_to_settings.click()
    assert window.stack.currentIndex() == 5


def test_refresh_preserves_selected_conversation_and_column_width(window):
    from datetime import UTC, datetime

    from codex_account_manager.domain.models import ThreadRecord

    view = window.conversations
    rows = [ThreadRecord(id="selected", title="Chosen conversation"), ThreadRecord(id="other")]
    view._render_threads(rows)
    view.table.selectRow(
        next(
            i
            for i in range(view.table.rowCount())
            if view.table.item(i, 0).text() == "Chosen conversation"
        )
    )
    view.table.setColumnWidth(4, 450)
    rows.append(ThreadRecord(id="newest", updated_at=datetime(2090, 1, 1, tzinfo=UTC)))
    view._render_threads(rows)
    assert view._current().id == "selected"
    assert view.table.columnWidth(4) == 450
    view._render_threads([row for row in rows if row.id != "selected"])
    assert view._current() is None
    assert view.action_host.isHidden()


def test_transaction_detail_does_not_duplicate_switch_failure_dialog(window, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    report = Mock()
    monkeypatch.setattr(window, "_switch_failed", report)
    window._domain_event(
        SimpleNamespace(topic="switch.failed", payload={"alias": "example", "detail": "Failure"})
    )
    report.assert_not_called()
    window._domain_event(SimpleNamespace(topic="switch.failed", payload={"detail": "Failure"}))
    assert report.call_count == 1


def test_about_explains_purpose_and_local_storage(window):
    from PySide6.QtWidgets import QLabel

    text = " ".join(label.text() for label in window.about.findChildren(QLabel)).casefold()
    assert "multiple codex accounts" in text
    assert "account" in text and "local" in text


def test_error_callback_failure_is_visible_and_redacted(app):
    runner = AsyncRunner()
    failures = []
    runner.failed.connect(failures.append)

    def broken_callback(_error):
        raise ValueError("password=callback-secret")

    try:
        runner._deliver_error(broken_callback, ValueError("original"))
        assert len(failures) == 1 and "callback-secret" not in failures[0]
    finally:
        runner.shutdown()


def test_switch_confirmation_does_not_open_nested_dialogs(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    calls = []

    def question(*_args):
        calls.append(True)
        window._switch("Another account")
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", question)
    window._switch("Example")
    assert len(calls) == 1
    assert not window._switching


def test_login_error_is_translated_and_allows_retry(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from codex_account_manager.gui.i18n import set_language

    view = window.accounts_view
    from codex_account_manager.domain.models import Profile

    view._render([Profile(alias="test", codex_home="unused")])
    view.table.selectRow(0)
    view._login_busy = True
    view._selection_changed()
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    try:
        set_language("tr")
        view._login_failed(
            RuntimeError(
                "Codex sign-in failed. Check Codex in Settings > System check, then try again."
            )
        )
        assert "Ayarlar > Sistem Kontrolü" in messages[0]
        assert not view._login_busy
        assert all(button.isEnabled() for button in view._profile_actions)
    finally:
        set_language("en")


def test_automatic_continuation_setting_and_status_are_visible(window):
    from codex_account_manager.core.events import Event
    from codex_account_manager.gui.i18n import set_language

    window.settings._loaded({"auto_continue": "false"})
    assert not window.settings.auto_continue.isChecked()
    try:
        set_language("tr")
        window._domain_event(Event("continuation.status", {"state": "running"}))
        assert "otomatik devam" in window.statusBar().currentMessage()
        window._domain_event(Event("continuation.status", {"state": "needs_user"}))
        assert "müdahaleniz gerekiyor" in window.statusBar().currentMessage()
    finally:
        set_language("en")


def test_account_menu_rename_preserves_selection_and_locks_during_login(window, monkeypatch):
    from unittest.mock import AsyncMock

    from codex_account_manager.domain.models import Profile
    from codex_account_manager.gui.i18n import tr

    view = window.accounts_view
    profiles = [Profile(alias=name, codex_home="unused") for name in ("First", "Second")]
    view._render(profiles)
    view.table.selectRow(1)
    view._render(list(reversed(profiles)))
    assert view._selected_alias() == "Second"
    assert view.selection_label.text() == "Second"
    rename = AsyncMock()
    monkeypatch.setattr(view.accounts, "rename_profile", rename)
    monkeypatch.setattr(
        "codex_account_manager.gui.accounts.prompt_text", lambda *args, **kwargs: "Renamed"
    )
    action = next(action for action in view.more.menu().actions() if action.text() == tr("Rename"))
    action.trigger()
    rename.assert_called_once_with("Second", "Renamed")
    view._login_busy = True
    view._selection_changed()
    assert not view.more.isEnabled()
    assert all(not action.isEnabled() for action in view._profile_actions)
    view._login_busy = False
    view.table.clearSelection()
    assert view._selected_alias() is None
    assert all(not action.isEnabled() for action in view._profile_actions)
    view._render([])
    assert not view.guide.isHidden()


def test_conversation_menu_actions_and_optional_details(window, monkeypatch):
    from unittest.mock import AsyncMock

    from PySide6.QtGui import QAction

    from codex_account_manager.continuity.service import ContinuityService
    from codex_account_manager.domain.models import ThreadRecord
    from codex_account_manager.gui.i18n import tr

    view = window.conversations
    view._render_threads([ThreadRecord(id="chosen", title="Example", cwd="C:/Example/project")])
    view.table.selectRow(0)
    assert view.details.isHidden()
    view.details_toggle.trigger()
    assert not view.details.isHidden()
    assert "C:/Example/project" in view.details.toPlainText()
    notes = []
    monkeypatch.setattr(window.goals, "save_for_thread", notes.append)
    read_goal = AsyncMock()
    opened = []
    monkeypatch.setattr(view, "open_desktop", opened.append)
    load = AsyncMock()
    monkeypatch.setattr(ContinuityService, "read_native_goal", read_goal)
    monkeypatch.setattr(ContinuityService, "resume_conversation", load)
    for title in ("Read Codex goal", "Save local goal note"):
        next(
            action for action in view.findChildren(QAction) if action.text() == tr(title)
        ).trigger()
    view._actions[0].click()
    read_goal.assert_called_once_with("chosen")
    load.assert_not_called()
    assert opened == ["chosen"]
    assert notes == ["chosen"]
    view.table.clearSelection()
    assert view._current() is None
    assert view.details.isHidden() and view.action_host.isHidden()


@pytest.mark.parametrize("locale", ["tr", "en"])
@pytest.mark.parametrize("dark", [True, False])
def test_settings_controls_fit_minimum_window_and_remain_reachable(app, locale, dark):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QScrollArea

    from codex_account_manager.gui.i18n import set_language

    set_language(locale)
    window = MainWindow(PreviewRunner())
    try:
        window.resize(1040, 700)
        window.nav.setCurrentRow(5)
        window.settings._loaded({"theme": "dark" if dark else "light"})
        window.show()
        app.processEvents()
        assert window.size().width() == 1040 and window.size().height() == 700
        scroll = window.settings.findChild(QScrollArea)
        assert scroll.horizontalScrollBar().maximum() == 0
        for control in (
            window.settings.policy,
            window.settings.auto_continue,
            window.settings.interval,
            window.settings.theme,
            window.settings.language,
            window.settings.startup,
        ):
            scroll.ensureWidgetVisible(control)
            app.processEvents()
            top_left = control.mapTo(scroll.viewport(), QPoint(0, 0))
            bottom_right = control.mapTo(scroll.viewport(), control.rect().bottomRight())
            assert scroll.viewport().rect().contains(top_left)
            assert scroll.viewport().rect().contains(bottom_right)
    finally:
        window.dispose()
        window.close()
        app.processEvents()
        set_language("en")


def test_initial_account_loading_is_distinct_from_empty_and_failed(app):
    from PySide6.QtWidgets import QLabel

    from codex_account_manager.gui.i18n import tr

    window = MainWindow(PreviewRunner())
    try:
        view = window.dashboard

        def labels():
            return [item.text() for item in view._grid_host.findChildren(QLabel)]

        assert not view._loaded
        assert tr("Loading accounts…") in labels()
        assert window.accounts_view.guide.isHidden()
        assert window.accounts_view.operation_status.text() == tr("Loading saved accounts…")
        view._on_error(RuntimeError("offline"))
        assert tr("Accounts could not be loaded") in labels()
        assert tr("Bring your first account") not in labels()
        view._render([])
        assert tr("Bring your first account") in labels()
        window.accounts_view._render([])
        assert not window.accounts_view.guide.isHidden()
        assert not window.accounts_view.operation_status.text()
    finally:
        window.dispose()
        window.close()
        app.processEvents()


def test_desktop_open_uses_native_link_and_reports_handler_failure(window, monkeypatch):
    from codex_account_manager.platform import windows

    opened = []
    monkeypatch.setattr(windows, "open_conversation", opened.append)
    view = window.conversations
    view.open_desktop("thread-a")
    assert opened == ["thread-a"]

    def missing_handler(_thread_id):
        raise OSError("no registered handler")

    monkeypatch.setattr(windows, "open_conversation", missing_handler)
    view.open_desktop("thread-a")
    assert "could not be opened" in view.tracking_status.text()


def test_tracking_selection_follows_identity_after_refresh(window):
    from codex_account_manager.continuity.tracking import ObservedWork

    view = window.conversations
    first = ObservedWork("first", "account", "inProgress", None, False, False, 1)
    second = ObservedWork("second", "account", "awaitingDesktop", None, False, False, 2)
    view._render_tracking(([first, second], {}))
    view.tracked_table.selectRow(0)
    view._render_tracking(([second, first], {}))
    assert view.tracked_table.currentRow() == 1
    assert view.tracked_open.isEnabled()
    view._render_tracking(([second], {}))
    assert not view.tracked_table.selectedItems()
    assert not view.tracked_open.isEnabled()


def test_missing_account_catalogue_shows_recovery_dialog_before_starting(app, monkeypatch):
    from unittest.mock import AsyncMock

    from PySide6.QtWidgets import QMessageBox

    from codex_account_manager.core.errors import AccountRecoveryRequired
    from codex_account_manager.gui import app as entry

    messages = []
    monkeypatch.setattr(
        entry,
        "initialize_database",
        AsyncMock(side_effect=AccountRecoveryRequired("missing catalogue")),
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(args))
    assert entry.run_gui() == 1
    assert len(messages) == 1
    assert messages[0][0] is None


@pytest.mark.parametrize("reason", ["Trigger", "DoubleClick"])
def test_tray_restores_hidden_minimized_window(window, app, reason):
    from PySide6.QtWidgets import QSystemTrayIcon

    window.showMinimized()
    window.hide()
    app.processEvents()
    window._on_tray_activated(getattr(QSystemTrayIcon.ActivationReason, reason))
    app.processEvents()
    assert window.isVisible()
    assert not window.isMinimized()
    assert window.tray.contextMenu().parent() is window
