"""Settings screen."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.gui.async_runner import AsyncRunner
from codex_account_manager.gui.design import DARK
from codex_account_manager.gui.i18n import (
    language,
    tr,
)
from codex_account_manager.gui.view_base import BaseView, view_header
from codex_account_manager.gui.widgets import ComboBox, label


class SettingsView(BaseView):
    policy_changed = Signal(str)
    diagnostics_requested = Signal()
    notes_requested = Signal()

    def __init__(self, runner: AsyncRunner, on_theme_toggle: Callable[[bool], None], palette=DARK):
        super().__init__(palette)
        self.runner = runner
        self._on_theme_toggle = on_theme_toggle
        self._root.addWidget(
            view_header(tr("Settings"), tr("Preferences are stored locally · no telemetry"))
        )

        panel = QWidget()
        panel.setObjectName("GridHost")
        form = QVBoxLayout(panel)
        form.setSpacing(0)
        form.setContentsMargins(0, 0, 8, 0)

        self.policy = ComboBox()
        for title, value in (
            (tr("Manual — I choose"), "manual"),
            (tr("Ask before switching"), "confirm"),
            (tr("Automatic when usage is limited"), "availability_failover"),
        ):
            self.policy.addItem(title, value)
        self.policy.setCurrentIndex(self.policy.findData("availability_failover"))
        self._section(form, tr("Automation"))
        self._setting_row(
            form, tr("Switch policy"), tr("Switching restarts Codex Desktop."), self.policy
        )

        self.auto_continue = QCheckBox(tr("Enabled"))
        self.auto_continue.setAccessibleName(tr("Continue interrupted work after switching"))
        self.auto_continue.setToolTip(
            tr(
                "After a verified usage-limit interruption, continue the same conversation and its active goal. Pauses, goal budgets and approval requests are respected. Turn this off to stop automatic work."
            )
        )
        self.auto_continue.setChecked(True)
        self.auto_continue.toggled.connect(self._save_auto_continue)
        self._setting_row(
            form,
            tr("Automatic continuation"),
            tr(
                "Desktop conversations continue through the native Desktop connection. If verification fails, no message is sent."
            ),
            self.auto_continue,
        )

        self.interval = QSpinBox()
        self.interval.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.interval.setRange(30, 3600)
        self.interval.setSingleStep(30)
        self.interval.setSuffix(tr(" seconds"))
        self.interval.setValue(60)
        self.interval.editingFinished.connect(self._save_interval)
        self._setting_row(
            form,
            tr("Check interval"),
            tr("30–3600 seconds. Changes apply immediately."),
            self.interval,
        )

        self._section(form, tr("Application"))
        self.theme = ComboBox()
        self.theme.addItem(tr("Dark"), "dark")
        self.theme.addItem(tr("Light"), "light")
        self.theme.currentIndexChanged.connect(self._save_theme)
        self._setting_row(form, tr("Appearance"), "", self.theme)

        self.language = ComboBox()
        self.language.addItem("Türkçe", "tr")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(language()))
        self.language.currentIndexChanged.connect(self._save_language)
        self._setting_row(
            form, tr("Language"), tr("Restart the application to apply."), self.language
        )

        self.startup = QPushButton(tr("Enable start with Windows"))
        self.startup.clicked.connect(self._toggle_startup)
        self._setting_row(
            form,
            tr("Start with Windows"),
            tr("Keep monitoring available after you sign in."),
            self.startup,
        )
        self._section(form, tr("Tools"))
        tools = QHBoxLayout()
        tools.setSpacing(10)
        for title, signal in (
            ("Diagnostics", self.diagnostics_requested),
            ("Goals", self.notes_requested),
        ):
            button = QPushButton(tr(title))
            button.clicked.connect(signal.emit)
            tools.addWidget(button)
        tools.addStretch()
        form.addLayout(tools)
        form.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        self._root.addWidget(scroll, 1)
        self._load()

    @staticmethod
    def _section(form: QVBoxLayout, title: str) -> None:
        heading = label(title, "Section")
        heading.setContentsMargins(0, 18, 0, 10)
        form.addWidget(heading)

    @staticmethod
    def _setting_row(form: QVBoxLayout, title: str, hint: str, control: QWidget) -> None:
        row = QFrame()
        row.setObjectName("SettingRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(24)
        text = QVBoxLayout()
        text.setSpacing(4)
        heading = label(title, "FieldTitle")
        heading.setWordWrap(True)
        heading.setBuddy(control)
        text.addWidget(heading)
        if hint:
            explanation = label(hint, "Caption")
            explanation.setWordWrap(True)
            text.addWidget(explanation)
        control.setAccessibleName(title)
        control.setFixedWidth(310)
        layout.addLayout(text, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(row)

    def _load(self) -> None:
        from codex_account_manager.storage.repositories import SettingsRepository

        self.runner.submit(SettingsRepository().all(), self._loaded)
        self.policy.currentIndexChanged.connect(self._save_policy)
        self._refresh_startup()

    def _loaded(self, values: dict[str, str]) -> None:
        with QSignalBlocker(self.policy):
            self.policy.setCurrentIndex(
                max(0, self.policy.findData(values.get("switch_policy", "availability_failover")))
            )
        from codex_account_manager.monitoring.settings import poll_interval

        with QSignalBlocker(self.interval):
            self.interval.setValue(poll_interval(values.get("poll_seconds")))
        with QSignalBlocker(self.auto_continue):
            self.auto_continue.setChecked(values.get("auto_continue", "true") == "true")
        dark = values.get("theme", "dark") == "dark"
        with QSignalBlocker(self.theme):
            self.theme.setCurrentIndex(0 if dark else 1)
        self._on_theme_toggle(dark)
        self.policy_changed.emit(self.policy.currentData())

    def _save_auto_continue(self, enabled: bool) -> None:
        from codex_account_manager.core.events import bus
        from codex_account_manager.storage.repositories import SettingsRepository

        def saved(_result) -> None:
            if not enabled:
                bus.publish("continuation.stop")
            self._monitor_saved()

        self.runner.submit(SettingsRepository().set("auto_continue", str(enabled).lower()), saved)

    def _save_policy(self, _index: int) -> None:
        from codex_account_manager.storage.repositories import SettingsRepository

        value = self.policy.currentData()
        self.runner.submit(
            SettingsRepository().set("switch_policy", value),
            lambda _: self._monitor_saved(value),
        )

    def _monitor_saved(self, policy: str | None = None) -> None:
        from codex_account_manager.core.events import bus

        if policy:
            self.policy_changed.emit(policy)
        bus.publish("monitor.settings_changed")

    def _save_interval(self) -> None:
        from codex_account_manager.storage.repositories import SettingsRepository

        self.runner.submit(
            SettingsRepository().set("poll_seconds", str(self.interval.value())),
            lambda _: self._monitor_saved(),
        )

    def _save_theme(self, _index: int) -> None:
        from codex_account_manager.storage.repositories import SettingsRepository

        value = self.theme.currentData()
        self._on_theme_toggle(value == "dark")
        self.runner.submit(SettingsRepository().set("theme", value.lower()))

    def _save_language(self, _index: int) -> None:
        from codex_account_manager.storage.repositories import SettingsRepository

        self.runner.submit(SettingsRepository().set("language", self.language.currentData()))

    def _refresh_startup(self) -> None:
        import sys

        if sys.platform != "win32":
            self.startup.setEnabled(False)
            self.startup.setText(tr("Startup is available on Windows"))
            return
        import asyncio

        from codex_account_manager.platform import startup

        self.runner.submit(
            asyncio.to_thread(startup.is_start_with_windows_enabled), self._startup_loaded
        )

    def _startup_loaded(self, enabled: bool) -> None:
        self._startup_enabled = enabled
        self.startup.setText(
            tr("Disable start with Windows") if enabled else tr("Enable start with Windows")
        )

    def _toggle_startup(self) -> None:
        import asyncio
        import subprocess
        import sys

        from codex_account_manager.platform import startup

        args = (
            [sys.executable]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "codex_account_manager.gui.tray_main"]
        )
        action = (
            startup.disable_start_with_windows
            if getattr(self, "_startup_enabled", False)
            else lambda: startup.enable_start_with_windows(subprocess.list2cmdline(args))
        )
        self.runner.submit(asyncio.to_thread(action), self._startup_done)

    def _startup_done(self, success: bool) -> None:
        if not success:
            QMessageBox.warning(
                self, tr("Startup"), tr("Windows could not update the startup task.")
            )
        self._refresh_startup()
