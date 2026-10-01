"""First-run preferences and an optional tour of the real application pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.view_base import setting_row
from codex_account_manager.gui.widgets import ComboBox, ToggleSwitch, label
from codex_account_manager.storage.repositories import ProfileRepository, SettingsRepository


async def needs_setup() -> bool:
    settings = SettingsRepository()
    values = await settings.all()
    if values.get("setup_completed") == "true":
        return False
    if values or await ProfileRepository().list():
        await settings.set("setup_completed", "true")
        return False
    return True


class SetupDialog(QDialog):
    def __init__(self, runner):
        super().__init__()
        self.setWindowTitle(tr("Welcome to QuotaCrew"))
        self.resize(760, 600)
        self.setMinimumSize(640, 480)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        self.progress = label("", "Caption")
        self.title = label("", "H1")
        self.title.setWordWrap(True)
        root.addWidget(self.progress)
        root.addWidget(self.title)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        from codex_account_manager.gui.cli_setup import CliSetup

        prerequisites = self._page(
            "Let's check the connection tools before choosing your preferences."
        )
        self.cli = CliSetup(runner)
        self.cli_ready = False
        self.cli.ready.connect(self._cli_ready)
        prerequisites.addWidget(self.cli)
        prerequisites.addStretch()
        general = self._page(
            "Choose how the app works. Nothing starts until you save these preferences. You can change them later in Settings."
        )
        self.monitoring = ToggleSwitch(tr("Background monitoring"))
        self.monitoring.setChecked(True)
        setting_row(
            general,
            tr("Background monitoring"),
            tr("Check account usage every 60 seconds."),
            self.monitoring,
        )
        self.policy = ComboBox()
        for title, value in (
            ("Automatic when usage is limited", "availability_failover"),
            ("Ask before switching", "confirm"),
            ("Manual — I choose", "manual"),
        ):
            self.policy.addItem(tr(title), value)
        setting_row(
            general, tr("Switch policy"), tr("Switching restarts Codex Desktop."), self.policy
        )
        self.auto_continue = ToggleSwitch(tr("Automatic continuation"))
        self.auto_continue.setChecked(True)
        setting_row(
            general,
            tr("Automatic continuation"),
            tr(
                "Continue verified quota-interrupted conversations after switching. Pauses and approvals remain yours."
            ),
            self.auto_continue,
        )
        self.background = ToggleSwitch(tr("Keep running in the tray"))
        setting_row(
            general,
            tr("Keep running in the tray"),
            tr("Closing the window quits unless this is enabled."),
            self.background,
        )
        self.check_updates = ToggleSwitch(tr("Check for updates automatically"))
        self.check_updates.setChecked(True)
        setting_row(
            general,
            tr("Check for updates automatically"),
            tr(
                "Check GitHub once a day. Download and installation start only when you choose Update."
            ),
            self.check_updates,
        )
        general.addStretch()
        ide = self._page(
            "IDE continuation is experimental. Enable it if you use the Codex extension in local VS Code."
        )
        self.ide_continue = ToggleSwitch(tr("IDE continuation"))
        setting_row(
            ide,
            tr("IDE continuation · Experimental"),
            tr("Continue in the existing IDE conversation with its tools."),
            self.ide_continue,
        )
        self.ide_refresh = ToggleSwitch(tr("Refresh VS Code after switching"))
        self.ide_refresh.setEnabled(False)
        self.ide_continue.toggled.connect(self._ide_changed)
        setting_row(
            ide,
            tr("Refresh VS Code after switching"),
            tr(
                "Close and reopen one local VS Code window to reload its account. Save prompts and other running IDE work are respected."
            ),
            self.ide_refresh,
        )
        note = label(
            tr(
                "Windows startup can be selected in the installer or Settings. Automatic shutdown stays off and must be enabled separately for each session."
            ),
            "Muted",
        )
        note.setWordWrap(True)
        ide.addWidget(note)
        ide.addStretch()
        summary = self._page(
            "Review your choices. Account sign-in opens only when you add an account."
        )
        self.summary = label("", "Body")
        self.summary.setWordWrap(True)
        summary.addWidget(self.summary)
        self.tour = QCheckBox(tr("Show me around after setup"))
        self.tour.setChecked(True)
        summary.addWidget(self.tour)
        summary.addStretch()
        footer = QHBoxLayout()
        self.back = QPushButton(tr("Back"))
        self.next = QPushButton(tr("Next"))
        self.next.setObjectName("Primary")
        self.back.clicked.connect(lambda: self._step(-1))
        self.next.clicked.connect(self._advance)
        footer.addWidget(self.back)
        footer.addStretch()
        footer.addWidget(self.next)
        root.addLayout(footer)
        self._step(0)

    def _page(self, description: str) -> QVBoxLayout:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("GridHost")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 12, 0)
        body = label(tr(description), "Muted")
        body.setWordWrap(True)
        layout.addWidget(body)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        return layout

    def _ide_changed(self, enabled: bool) -> None:
        self.ide_refresh.setEnabled(enabled)
        if not enabled:
            self.ide_refresh.setChecked(False)

    def values(self) -> dict[str, str]:
        return {
            "monitor_enabled": str(self.monitoring.isChecked()).lower(),
            "switch_policy": self.policy.currentData(),
            "auto_continue": str(self.auto_continue.isChecked()).lower(),
            "ide_continue": str(self.ide_continue.isChecked()).lower(),
            "ide_refresh": str(
                self.ide_continue.isChecked() and self.ide_refresh.isChecked()
            ).lower(),
            "keep_in_tray": str(self.background.isChecked()).lower(),
            "poll_seconds": "60",
            "setup_completed": "true",
            "check_updates": str(self.check_updates.isChecked()).lower(),
        }

    def _step(self, delta: int) -> None:
        index = self.pages.currentIndex() + delta
        self.pages.setCurrentIndex(index)
        self.progress.setText(tr("Step {current} of {total}", current=index + 1, total=4))
        self.title.setText(
            tr(
                ("Connection tools", "Make it yours", "Continue in your IDE", "Ready when you are")[
                    index
                ]
            )
        )
        self.back.setEnabled(index > 0)
        self.next.setEnabled(index != 0 or self.cli_ready)
        self.next.setText(tr("Save and start") if index == 3 else tr("Next"))
        if index == 3:
            rows = [
                (tr("Switch policy"), self.policy.currentText()),
                (tr("Check interval"), tr("60 seconds")),
            ]
            for title, control in (
                ("Background monitoring", self.monitoring),
                ("Automatic continuation", self.auto_continue),
                ("IDE continuation", self.ide_continue),
                ("Refresh VS Code after switching", self.ide_refresh),
                ("Keep running in the tray", self.background),
                ("Check for updates automatically", self.check_updates),
            ):
                rows.append((tr(title), tr("On") if control.isChecked() else tr("Off")))
            self.summary.setText("\n\n".join(f"{title}: {value}" for title, value in rows))

    def _advance(self) -> None:
        if self.pages.currentIndex() == 0 and not self.cli_ready:
            return
        if self.pages.currentIndex() == 3:
            self.accept()
        else:
            self._step(1)

    def _cli_ready(self, ready: bool) -> None:
        self.cli_ready = ready
        if self.pages.currentIndex() == 0:
            self.next.setEnabled(ready)

    def reject(self) -> None:
        if self.cli.busy:
            return
        super().reject()


class ProductTour(QDialog):
    STEPS = (
        (
            0,
            "Overview",
            "See account capacity and monitoring status here. Start or pause monitoring from the top bar.",
        ),
        (
            1,
            "Accounts",
            "Add an account to open sign-in. Use its row menu to switch, rename or remove it.",
        ),
        (
            2,
            "Jobs",
            "Follow observed conversations and check each conversation's continuation details from its row menu.",
        ),
        (
            6,
            "Settings",
            "Change switching, continuation and tray preferences here. IDE continuation and VS Code refresh are separate choices.",
        ),
        (
            8,
            "Automatic shutdown",
            "Choose a condition and a countdown in minutes. Shutdown stays off until you explicitly enable it.",
        ),
    )

    def __init__(self, window):
        super().__init__(window)
        self.host_window = window
        self.original_page = window.stack.currentIndex()
        self.index = 0
        self.setWindowTitle(tr("Quick tour"))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(500, 240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        self.progress = label("", "Caption")
        self.title = label("", "H2")
        self.body = QLabel()
        self.body.setWordWrap(True)
        layout.addWidget(self.progress)
        layout.addWidget(self.title)
        layout.addWidget(self.body, 1)
        footer = QHBoxLayout()
        skip = QPushButton(tr("Skip tour"))
        skip.clicked.connect(self.reject)
        self.back = QPushButton(tr("Back"))
        self.back.clicked.connect(lambda: self._show_step(-1))
        self.next = QPushButton(tr("Next"))
        self.next.setObjectName("Primary")
        self.next.clicked.connect(self._advance)
        footer.addWidget(skip)
        footer.addStretch()
        footer.addWidget(self.back)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        self.finished.connect(lambda _: window.nav.setCurrentRow(self.original_page))
        self._show_step(0)

    def _show_step(self, delta: int) -> None:
        self.index += delta
        page, title, body = self.STEPS[self.index]
        self.host_window.nav.setCurrentRow(page)
        self.progress.setText(
            tr("Step {current} of {total}", current=self.index + 1, total=len(self.STEPS))
        )
        self.title.setText(tr(title))
        self.body.setText(tr(body))
        self.back.setEnabled(self.index > 0)
        self.next.setText(tr("Finish") if self.index == len(self.STEPS) - 1 else tr("Next"))

    def _advance(self) -> None:
        if self.index == len(self.STEPS) - 1:
            self.accept()
        else:
            self._show_step(1)
