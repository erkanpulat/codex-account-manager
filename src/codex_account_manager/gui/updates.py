"""Update preferences, release availability and explicit installation."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget

from codex_account_manager import __version__, updates
from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.view_base import setting_row
from codex_account_manager.gui.widgets import ToggleSwitch, label
from codex_account_manager.platform import package
from codex_account_manager.storage.repositories import SettingsRepository


class UpdatesPanel(QWidget):
    available = Signal(str)
    restart_requested = Signal()

    def __init__(self, runner, can_restart):
        super().__init__()
        self.runner = runner
        self._packaged = package.is_packaged()
        self.can_restart = can_restart
        self.release: updates.Release | None = None
        self.installer: Path | None = None
        self._install_lock = None
        self._busy = False
        self.preparing = False
        self.setObjectName("PagePanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        layout.addWidget(label(tr("Application updates"), "H2"))
        layout.addWidget(label(tr("Installed version: {version}", version=__version__), "Caption"))
        self.automatic = ToggleSwitch(tr("Check for updates automatically"))
        self.automatic.setChecked(True)
        setting_row(
            layout,
            tr("Check for updates automatically"),
            tr(
                "Updates for this installation are managed by Microsoft Store."
                if self._packaged
                else "Check GitHub once a day. Download and installation start only when you choose Update."
            ),
            self.automatic,
        )
        self.automatic.toggled.connect(self._save_preference)
        self.status = label(tr("Check for a newer stable release."), "Body")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName(tr("Update progress"))
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.check = QPushButton(tr("Check for updates"))
        self.check.clicked.connect(lambda: self.check_now())
        self.install = QPushButton(tr("Update"))
        self.install.setObjectName("Primary")
        self.install.clicked.connect(self._update)
        self.install.hide()
        self.notes = QPushButton(tr("Release notes"))
        self.notes.clicked.connect(self._open_release)
        buttons.addWidget(self.check)
        buttons.addWidget(self.install)
        buttons.addWidget(self.notes)
        buttons.addStretch()
        layout.addLayout(buttons)
        detail = label(
            tr(
                "Your accounts and settings are preserved. Only QuotaCrew restarts. Active account operations and pending continuations must finish first."
            ),
            "Caption",
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)
        if self._packaged:
            self.automatic.setChecked(False)
            self.automatic.setEnabled(False)
            self.check.setText(tr("Open Microsoft Store"))
            self.status.setText(tr("Updates for this installation are managed by Microsoft Store."))
            detail.setText(tr("Manage automatic updates in Microsoft Store settings."))
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.setInterval(60 * 60 * 1000)
        self.timer.timeout.connect(self._scheduled_check)
        self.runner.submit(SettingsRepository().all(), self._loaded)

    def _loaded(self, values):
        with QSignalBlocker(self.automatic):
            self.automatic.setChecked(
                not self._packaged and values.get("check_updates", "true") == "true"
            )

    def start(self):
        if self._packaged:
            return
        self.runner.submit(asyncio.to_thread(updates.cleanup_downloads))
        if updates.installed_directory() is not None:
            self.timer.start()
            QTimer.singleShot(5000, self, self._scheduled_check)

    def stop(self):
        self.timer.stop()

    def _save_preference(self, enabled):
        if self._packaged:
            return
        self.runner.submit(SettingsRepository().set("check_updates", str(enabled).lower()))

    def _scheduled_check(self):
        if self._busy or not self.automatic.isChecked():
            return

        def loaded(value):
            try:
                due = time.time() - float(value or 0) >= 86400
            except (TypeError, ValueError):
                due = True
            if due and self.automatic.isChecked():
                self.check_now()

        self.runner.submit(SettingsRepository().get("update_checked_at"), loaded)

    def _working(self, busy):
        self._busy = busy
        self.progress.setVisible(busy)
        self.check.setEnabled(not busy)
        self.install.setEnabled(not busy)

    def check_now(self):
        if self._packaged:
            QDesktopServices.openUrl(QUrl(package.STORE_UPDATES_URI))
            return
        if self._busy:
            return
        self._working(True)
        self.status.setText(tr("Checking for updates…"))
        self.runner.submit(asyncio.to_thread(updates.latest_release), self._checked, self._failed)

    def _checked(self, release):
        self._working(False)
        self.release = release
        self.installer = None
        self.runner.submit(SettingsRepository().set("update_checked_at", str(time.time())))
        self.install.setVisible(release is not None)
        if release:
            self.install.setText(
                tr("Update") if updates.installed_directory() else tr("Open downloads")
            )
            self.status.setText(tr("Version {version} is available.", version=release.version))
            self.available.emit(release.version)
        else:
            self.status.setText(tr("No newer stable version is available."))
            self.available.emit("")

    def _open_release(self):
        QDesktopServices.openUrl(QUrl(self.release.url if self.release else updates.RELEASES_URL))

    def _update(self):
        if self._packaged:
            self.check_now()
            return
        if self._busy or self.release is None:
            return
        if updates.installed_directory() is None:
            self._open_release()
            return
        if not self.can_restart():
            self.status.setText(
                tr("Finish the account operation or cancel the shutdown plan before updating.")
            )
            return
        self._working(True)
        if self.installer is not None:
            self._downloaded(self.installer)
        else:
            self.status.setText(tr("Downloading and verifying the update…"))
            self.runner.submit(updates.download(self.release), self._downloaded, self._failed)

    def _downloaded(self, installer):
        if self.release is None:
            self._failed(RuntimeError("Check for a newer stable release."))
            return
        self.installer = installer
        if not self.can_restart():
            self._failed(
                RuntimeError(
                    "The update is ready. Finish active operations, then choose Update again."
                )
            )
            return
        self.status.setText(tr("Preparing the update. QuotaCrew will restart…"))
        self.preparing = True
        self.runner.submit(
            asyncio.to_thread(updates.begin_install, self.release, installer),
            self._installing,
            self._failed,
        )

    def _installing(self, lock):
        self._install_lock = lock
        self.preparing = False
        self.restart_requested.emit()

    def _failed(self, error):
        self.preparing = False
        self._working(False)
        self.status.setText(tr(str(error)))
