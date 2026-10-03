"""Explain the separate Desktop dependency and check it without starting it."""

import asyncio

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout

from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.widgets import label
from codex_account_manager.platform.windows import CODEX_DESKTOP_DOWNLOAD_URL, is_desktop_installed


class DesktopSetup(QFrame):
    availability_changed = Signal(object)

    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        self.setObjectName("SetupCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(label(tr("Codex Desktop / ChatGPT"), "H2"))
        hint = label(
            tr(
                "Optional for Desktop conversations. Account switching, quota monitoring and VS Code work independently. The official ChatGPT desktop app includes Codex."
            ),
            "Caption",
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = label("", "Caption")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.download = QPushButton(tr("Official download"))
        self.download.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(CODEX_DESKTOP_DOWNLOAD_URL))
        )
        self.check = QPushButton(tr("Check again"))
        self.check.clicked.connect(self.refresh)
        row.addWidget(self.download)
        row.addWidget(self.check)
        row.addStretch()
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        if not self.check.isEnabled():
            return
        self.check.setEnabled(False)
        self.status.setText(tr("Checking Desktop installation…"))
        self.runner.submit(asyncio.to_thread(is_desktop_installed), self._checked, self._failed)

    def _checked(self, installed):
        self.check.setEnabled(True)
        self.download.setVisible(not installed)
        self.status.setText(
            tr("Desktop is installed. Its live connection is verified before continuing work.")
            if installed
            else tr(
                "Desktop is not installed. Desktop continuation waits for setup; account switching and VS Code remain available."
            )
        )
        self.availability_changed.emit(bool(installed))

    def _failed(self, _error):
        self.check.setEnabled(True)
        self.status.setText(
            tr(
                "Desktop installation could not be checked. Retry; account sign-in and quota monitoring remain available."
            )
        )
        self.availability_changed.emit(None)


class IDESetup(QFrame):
    availability_changed = Signal(object)

    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        self.setObjectName("SetupCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(label("VS Code / Codex", "H2"))
        hint = label(
            tr(
                "Optional for IDE conversations. Requires local VS Code and the official Codex extension. Desktop is not required. Installation detection does not verify that the extension is enabled or connected."
            ),
            "Caption",
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = label("", "Caption")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.guide = QPushButton(tr("Installation guide"))
        self.guide.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://developers.openai.com/codex/ide/"))
        )
        self.check = QPushButton(tr("Check again"))
        self.check.clicked.connect(self.refresh)
        row.addWidget(self.guide)
        row.addWidget(self.check)
        row.addStretch()
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        from codex_account_manager.platform.editors import vscode_connection_status

        if not self.check.isEnabled():
            return
        self.check.setEnabled(False)
        self.status.setText(tr("Checking VS Code and Codex extension…"))
        self.runner.submit(asyncio.to_thread(vscode_connection_status), self._checked, self._failed)

    def _checked(self, status):
        self.check.setEnabled(True)
        self.status.setText(
            tr(
                {
                    "missing_editor": "VS Code was not found in supported local locations. IDE continuation waits for setup; Desktop remains available.",
                    "extension_undetected": "VS Code was found; the Codex extension was not detected. Install or enable it in VS Code. Custom extension locations require a manual check.",
                    "installed": "VS Code and the Codex extension were found. The live conversation connection is verified before continuing work.",
                }[status]
            )
        )
        # Extension detection cannot prove enabled/connected state. Native owner
        # verification supplies that at the point of use, also for custom paths.
        self.availability_changed.emit(
            False if status == "missing_editor" else True if status == "installed" else None
        )

    def _failed(self, _error):
        self.check.setEnabled(True)
        self.status.setText(
            tr(
                "IDE installation could not be checked. Retry; Desktop and quota monitoring remain available."
            )
        )
        self.availability_changed.emit(None)
