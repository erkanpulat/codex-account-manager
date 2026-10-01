"""CLI detection and an explicit install action shared by setup and settings."""

import asyncio

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from codex_account_manager.codex.setup import DOCS_URL, cli_version, install_cli
from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.widgets import label


class CliSetup(QWidget):
    ready = Signal(bool)

    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        self.busy = False
        self.installing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label(tr("Codex CLI"), "H2"))
        description = label(
            tr(
                "Python is included in the Windows package. Codex CLI connects this app to your accounts and conversations. Existing CLI installations are preserved."
            ),
            "Body",
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status = label(tr("Checking Codex CLI…"), "Caption")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.install = QPushButton(tr("Install Codex CLI"))
        self.install.setObjectName("Primary")
        self.install.hide()
        self.install.clicked.connect(self._install)
        self.check = QPushButton(tr("Check again"))
        self.check.clicked.connect(self.refresh)
        guide = QPushButton(tr("Official installation guide"))
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DOCS_URL)))
        for button in (self.install, self.check, guide):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.refresh()

    def _working(self, busy):
        self.busy = busy
        self.check.setEnabled(not busy)
        self.install.setEnabled(not busy)

    def refresh(self):
        if self.busy:
            return
        self._working(True)
        self.runner.submit(asyncio.to_thread(cli_version), self._checked, self._failed)

    def _checked(self, version):
        self.installing = False
        self._working(False)
        self.install.setVisible(version is None)
        self.status.setText(
            tr("Codex CLI {version} is ready.", version=version)
            if version
            else tr("Codex CLI is required. Install it to connect your accounts.")
        )
        self.ready.emit(bool(version))

    def _install(self):
        if self.busy:
            return
        if (
            QMessageBox.question(
                self,
                tr("Install Codex CLI"),
                tr(
                    "Download and run OpenAI's official Windows installer? It installs Codex CLI for your Windows user and adds its folder to your user PATH. Node.js is not required. No account sign-in or model task will be started."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.installing = True
        self._working(True)
        self.status.setText(tr("Installing Codex CLI… This may take a few minutes."))
        self.runner.submit(asyncio.to_thread(install_cli), self._checked, self._failed)

    def _failed(self, error):
        self.installing = False
        self._working(False)
        self.status.setText(tr(str(error)))
        self.ready.emit(False)
