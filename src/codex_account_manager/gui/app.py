"""GUI entry point."""

from __future__ import annotations

import asyncio
import sys

from codex_account_manager.core.errors import AccountRecoveryRequired
from codex_account_manager.core.logging import configure_logging, get_logger
from codex_account_manager.core.windows_shell import set_application_identity
from codex_account_manager.storage.database import initialize_database

log = get_logger(__name__)


def run_gui() -> int:
    configure_logging()
    # Ensure the database is migrated before the UI reads from it.
    try:
        asyncio.run(initialize_database())
    except AccountRecoveryRequired:
        from PySide6.QtCore import QLocale
        from PySide6.QtWidgets import QApplication, QMessageBox

        from codex_account_manager.gui.i18n import set_language, tr

        app = QApplication.instance() or QApplication(sys.argv)
        set_language("tr" if QLocale.system().name().startswith("tr") else "en")
        QMessageBox.critical(
            None,
            tr("Account recovery required"),
            tr(
                "Saved sign-in files exist, but the account list is missing. Startup was stopped to protect your data. Do not reset or delete the data folder. Restore the account database from a verified backup."
            ),
        )
        return 1
    from codex_account_manager.auth.transaction import AuthTransaction

    AuthTransaction().recover()

    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from codex_account_manager.gui.i18n import set_language, tr
    from codex_account_manager.storage.repositories import SettingsRepository

    default_language = "tr" if QLocale.system().name().startswith("tr") else "en"
    selected_language = asyncio.run(SettingsRepository().get("language", default_language))
    set_language(selected_language or default_language)

    from codex_account_manager.gui.async_runner import AsyncRunner
    from codex_account_manager.gui.design import app_icon
    from codex_account_manager.gui.main_window import MainWindow
    from codex_account_manager.gui.theme import stylesheet

    set_application_identity()
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Codex Account Manager")
    app.setApplicationDisplayName(tr("Codex Account Manager"))
    translator = QTranslator(app)
    if selected_language == "tr" and translator.load(
        "qtbase_tr", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    ):
        app.installTranslator(translator)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(stylesheet(dark=True))
    # Keep running in the tray when the window is closed.
    app.setQuitOnLastWindowClosed(not QSystemTrayIcon.isSystemTrayAvailable())

    runner = AsyncRunner()
    window = MainWindow(runner)
    window.show()
    from codex_account_manager.monitoring.watcher import Watcher

    watcher = Watcher(accounts=window.accounts)
    runner.submit(watcher.run())

    try:
        return app.exec()
    finally:
        window.dispose()
        runner.shutdown()


if __name__ == "__main__":
    raise SystemExit(run_gui())
