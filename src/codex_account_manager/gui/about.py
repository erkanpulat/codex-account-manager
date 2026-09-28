"""About screen."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.gui.design import DARK
from codex_account_manager.gui.i18n import (
    tr,
)
from codex_account_manager.gui.view_base import BaseView, view_header
from codex_account_manager.gui.widgets import label


class AboutView(BaseView):
    def __init__(self, palette=DARK):
        super().__init__(palette)
        self._root.addWidget(
            view_header(
                tr("About this application"),
                tr("Codex Account Manager · Independent, open-source desktop utility"),
            )
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("GridHost")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        for title, description in (
            (
                tr("What does it do?"),
                tr(
                    "Manage multiple Codex accounts on one device, monitor their usage quotas, and switch the account used by Codex Desktop. Browse local conversations by project and choose automatic, confirmation or manual switching."
                ),
            ),
            (
                tr("Does it work automatically?"),
                tr(
                    "Automatic switching is the default for new installations. When the active account reaches its usage limit, the application can switch to a verified account with capacity. Choose manual or confirmation mode in Settings. The check interval is adjustable from 30 to 3600 seconds; the default is 60 seconds. Monitoring requires the application to remain open, including in the system tray."
                ),
            ),
            (
                tr("What happens during a switch?"),
                tr(
                    "The target account is checked, the current login is saved for recovery, and Codex Desktop restarts. Conversation files stay in the shared Codex folder. Save your work first. If a switch fails, the application attempts to restore the previous login; any recovery failure is reported."
                ),
            ),
            (
                tr("Will my conversation continue by itself?"),
                tr(
                    "When enabled, a verified usage-limit interruption can continue after an account switch. The application sends a continuation message and follows an active goal until it completes or needs attention. Stop automatic work in Settings. Merely opening a conversation or saving a goal note does not start work."
                ),
            ),
            (
                tr("Where is my information stored?"),
                tr(
                    "Account credentials and settings are stored locally. This application has no telemetry or credential proxy. Codex connects to OpenAI for sign-in and account information. Diagnostic exports include check statuses, the CLI version and profile count. They exclude account labels, local paths, credentials and conversation content."
                ),
            ),
            (
                tr("Independent project"),
                tr(
                    "This project is not an official OpenAI product and is not affiliated with OpenAI. It does not increase account limits or provide extra capacity. Each account remains subject to its own plan and service terms."
                ),
            ),
        ):
            panel = QWidget()
            box = QVBoxLayout(panel)
            box.setContentsMargins(0, 8, 12, 12)
            box.setSpacing(10)
            box.addWidget(label(title, "H2"))
            body = label(description, "Body")
            body.setWordWrap(True)
            box.addWidget(body)
            layout.addWidget(panel)
        layout.addStretch()
        scroll.setWidget(content)
        self._root.addWidget(scroll, 1)
