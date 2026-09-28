"""Render the real Qt interface using synthetic profiles and no external services."""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDialog

from codex_account_manager.continuity.tracking import ObservedWork, account_hash
from codex_account_manager.domain.models import (
    ProfileHealth,
    ResetCredit,
    ResetCredits,
    ThreadRecord,
)
from codex_account_manager.domain.states import QuotaState
from codex_account_manager.gui.i18n import set_language, tr
from codex_account_manager.gui.main_window import MainWindow
from codex_account_manager.gui.theme import stylesheet


class PreviewRunner(QObject):
    failed = Signal(str)

    def submit(self, coro, on_result=None, on_error=None):
        coro.close()


def sample_profiles() -> list[ProfileHealth]:
    return [
        ProfileHealth(
            alias=name,
            profile_id=name,
            plan_type=plan,
            primary_used_percent=primary,
            secondary_used_percent=secondary,
            primary_resets_at=1790856000,
            secondary_resets_at=1791028800,
            ordinary_usage_allowed=primary < 100,
            auth_present=True,
            account_match=True,
            is_active=active,
            quota_state=QuotaState.AVAILABLE if primary < 100 else QuotaState.LIMITED_WITH_RESET,
            last_checked_at=datetime.now(UTC),
            reset_credits=ResetCredits(
                available_count=1 if active else 0,
                credits=(
                    ResetCredit(
                        status="available",
                        reset_type="codexRateLimits",
                        granted_at=1790553600,
                        expires_at=1791158400,
                    ),
                )
                if active
                else (),
            )
            if name != "Open source"
            else None,
        )
        for name, plan, primary, secondary, active in (
            ("Personal", "plus", 28, 46, True),
            ("Studio", "pro", 12, 24, False),
            ("Client workspace", "business", 100, 78, False),
            ("Open source", "plus", 64, 32, False),
        )
    ]


def sample_threads() -> list[ThreadRecord]:
    return [
        ThreadRecord(
            id=f"example-{index}",
            title=title,
            cwd=folder,
            workspace=folder,
            source=source,
            project_id=project,
            preview="Example conversation for the public preview. All data is synthetic.",
            updated_at=datetime(2026, 9, 26, 9, 30 - index, tzinfo=UTC),
        )
        for index, (title, folder, source, project) in enumerate(
            (
                (
                    "Hesap ayarlarını sadeleştir",
                    "C:/Work/codex-account-manager",
                    "vscode",
                    "manager",
                ),
                (
                    "Proje aramasını geliştir",
                    "C:/Work/customer-portal/packages/web/application",
                    "vscode",
                    "portal",
                ),
                (
                    "Komut satırı testlerini çalıştır",
                    "C:/Work/codex-account-manager",
                    "cli",
                    "manager",
                ),
                (
                    "Giriş ekranının erişilebilirliğini incele",
                    "C:/Work/customer-portal/packages/web/application",
                    "subAgent",
                    "portal",
                ),
                ("Yayın belgelerini tamamla", "C:/Work/codex-account-manager", "vscode", "manager"),
                (
                    "Veri tabanı yükseltmesini doğrula",
                    "C:/Work/customer-portal/services/api",
                    "appServer",
                    "portal",
                ),
            )
        )
    ]


def main() -> None:
    app = QApplication.instance() or QApplication([])
    from PySide6.QtGui import QFontDatabase

    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        if (font_dir / font).exists():
            QFontDatabase.addApplicationFont(str(font_dir / font))
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())
    window = MainWindow(PreviewRunner())
    window.tray.hide()
    window.dashboard._render(sample_profiles())
    window.resize(1500, 1180)
    window.show()
    output = Path(__file__).resolve().parents[1] / "docs" / "images"
    output.mkdir(parents=True, exist_ok=True)
    review = Path(__file__).resolve().parents[1] / ".ruff_cache" / "previews"
    review.mkdir(parents=True, exist_ok=True)
    for dark, name in ((True, "overview-dark"), (False, "overview-light")):
        window._apply_theme(dark)
        app.processEvents()
        window.grab().save(str(output / f"{name}.png"))
    window.dashboard._render([])
    app.processEvents()
    window.grab().save(str(review / "onboarding.png"))
    window.dispose()
    window.close()
    set_language("tr")
    window = MainWindow(PreviewRunner())
    window.tray.hide()
    window.resize(1500, 1180)
    window.show()
    window._apply_theme(True)
    window.dashboard._render([])
    app.processEvents()
    window.grab().save(str(output / "onboarding-tr.png"))
    window.dashboard._render(sample_profiles())
    app.processEvents()
    window.grab().save(str(output / "overview-tr.png"))
    from codex_account_manager.gui.widgets import AccountCard

    def capture_credit_dialog():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                widget.grab().save(str(output / "reset-credits-tr.png"))
                widget.accept()

    card = AccountCard(sample_profiles()[0])
    QTimer.singleShot(100, capture_credit_dialog)
    card._show_reset_credits(sample_profiles()[0])
    card.deleteLater()
    window.nav.setCurrentRow(1)
    window.conversations._render_threads(sample_threads())
    source_account = account_hash("preview-personal-account")
    window.conversations._render_tracking(
        (
            [
                ObservedWork(
                    thread_id="example-1",
                    account_hash=source_account,
                    turn_status="inProgress",
                    goal_status="active",
                    goal_present=True,
                    limited=False,
                    observed_at=time.time(),
                ),
            ],
            {source_account: "Personal"},
        )
    )
    window.conversations.status.setText(
        tr(
            "{shown} of {total} conversations · Local Codex: {path}",
            shown=5,
            total=6,
            path="C:/Example/.codex",
        )
    )
    window.conversations.show_tracking_status(
        {"state": "ready", "checked": 5, "checked_at": "12:30:00"}
    )
    window.conversations.tracked_table.selectRow(0)
    window.conversations.table.selectRow(1)
    app.processEvents()
    window.grab().save(str(output / "conversations-tr.png"))
    from codex_account_manager.gui.dialogs import EntryDialog

    dialog = EntryDialog(
        window,
        tr("Add profile"),
        tr("Account name"),
        tr("Choose a name you will recognize, such as Personal or Work."),
        maximum=64,
        action="Add account",
    )
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(output / "add-account-tr.png"))
    dialog.close()
    for row, name in ((5, "settings-tr"), (6, "about-tr")):
        window.nav.setCurrentRow(row)
        app.processEvents()
        window.grab().save(str(review / f"{name}.png"))
    window.dispose()
    window.close()
    set_language("en")


if __name__ == "__main__":
    main()
