"""An explicit optional desktop shortcut, shared by setup and settings."""

import asyncio
import sys

from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout

from codex_account_manager.core.windows_shell import create_desktop_shortcut
from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.widgets import label


class ShortcutPanel(QFrame):
    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        self.setObjectName("SetupCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        self.note = label(
            tr(
                "Open QuotaCrew from the Windows Start menu. A desktop shortcut is optional and is created only when you press this button."
            ),
            "Caption",
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.button = QPushButton(tr("Create desktop shortcut"))
        self.button.setEnabled(sys.platform == "win32")
        self.button.clicked.connect(self._create)
        layout.addWidget(self.button)

    def _create(self):
        if not self.button.isEnabled():
            return
        self.button.setEnabled(False)
        self.note.setText(tr("Creating desktop shortcut…"))
        self.runner.submit(asyncio.to_thread(create_desktop_shortcut), self._created, self._failed)

    def _created(self, _path):
        self.note.setText(tr("Desktop shortcut created. You can also open QuotaCrew from Start."))

    def _failed(self, error):
        if isinstance(error, FileExistsError):
            self.note.setText(tr("A QuotaCrew desktop shortcut already exists."))
        else:
            self.note.setText(
                tr(
                    "The desktop shortcut could not be created. You can still open QuotaCrew from Start and retry here."
                )
            )
            self.button.setEnabled(True)
