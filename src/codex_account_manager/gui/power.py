"""Visible, session-only shutdown controls. No shutdown runs in widget tests."""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QSignalBlocker, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from codex_account_manager.gui.design import DARK
from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.view_base import BaseView, setting_row, view_header
from codex_account_manager.gui.widgets import CompactSwitch, label
from codex_account_manager.monitoring.power import (
    MAX_COUNTDOWN_MINUTES,
    PowerChecks,
    PowerEvidence,
    PowerTarget,
    ShutdownPlan,
)


class PowerControls(QFrame):
    status_changed = Signal(str, bool)
    countdown_started = Signal()

    def __init__(self, runner, accounts, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.runner = runner
        self.checks = PowerChecks(accounts)
        self.plan = ShutdownPlan()
        self._busy = False
        self._next_check = 0.0
        self._preparing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(label(tr("Automatic shutdown"), "H2"), 1)
        self.enable_toggle = CompactSwitch(tr("Automatic shutdown"))
        self.enable_toggle.setEnabled(sys.platform == "win32")
        self.enable_toggle.toggled.connect(self._toggle)
        heading.addWidget(self.enable_toggle)
        layout.addLayout(heading)
        hint = label(
            tr(
                "Off by default and only active for this session. When the condition is verified, a visible countdown starts. You can cancel it at any time; open applications are not forcibly closed."
            ),
            "Caption",
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = label(tr("Shutdown is off."), "Muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.condition = label(
            tr("When all saved accounts reach their usage limits."), "FieldTitle"
        )
        self.condition.setWordWrap(True)
        setting_row(
            layout,
            tr("Shutdown condition"),
            tr("A fresh check must confirm the condition before the countdown begins."),
            self.condition,
        )
        self.countdown_minutes = QSpinBox()
        self.countdown_minutes.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.countdown_minutes.setRange(1, MAX_COUNTDOWN_MINUTES)
        self.countdown_minutes.setValue(2)
        self.countdown_minutes.setSuffix(tr(" minutes"))
        self.countdown_minutes.setAccessibleName(tr("Shutdown countdown (minutes)"))
        self.countdown_minutes.valueChanged.connect(self._countdown_changed)
        setting_row(
            layout,
            tr("Shutdown countdown (minutes)"),
            tr("Enter minutes: 120 = 2 hours, 180 = 3 hours. Range: 1–1440 minutes."),
            self.countdown_minutes,
        )
        buttons = QHBoxLayout()
        self.cancel_button = QPushButton(tr("Cancel shutdown"))
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        note = label(
            tr(
                "For a specific conversation, choose ‘Shut down after this work’ from its actions. Other verified Codex work prevents shutdown."
            ),
            "Caption",
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

    def _countdown_changed(self, minutes: int) -> None:
        if self.plan.target is None:
            self.plan.set_seconds(minutes * 60)

    def _toggle(self, enabled: bool) -> None:
        if enabled:
            self.arm(PowerTarget("limits"))
        else:
            self.cancel()

    def arm_work(self, thread_id: str) -> None:
        if self._preparing or self.plan.target is not None:
            return
        self._preparing = True
        generation = self.plan.generation

        def ready(target):
            self._preparing = False
            if generation == self.plan.generation:
                self.arm(target)

        def failed(_error):
            self._preparing = False
            if generation == self.plan.generation:
                self.status.setText(tr("Select a verified running conversation first."))

        self.runner.submit(self.checks.work_target(thread_id), ready, failed)

    def arm(self, target: PowerTarget) -> None:
        if sys.platform != "win32" or self.plan.target is not None:
            return
        condition = (
            "When all saved accounts reach their usage limits."
            if target.mode == "limits"
            else "When the selected work is complete."
        )
        if (
            QMessageBox.question(
                self,
                tr("Schedule shutdown"),
                tr(
                    "Enable shutdown for this session? Condition: {condition} Countdown: {minutes} minutes. Save work in other applications.",
                    condition=tr(condition),
                    minutes=self.countdown_minutes.value(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            with QSignalBlocker(self.enable_toggle):
                self.enable_toggle.setChecked(False)
            return
        self.plan.arm(target)
        with QSignalBlocker(self.enable_toggle):
            self.enable_toggle.setChecked(True)
        self.condition.setText(tr(condition))
        self.countdown_minutes.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._next_check = 0.0
        self.timer.start()
        self._tick()

    def cancel(self) -> None:
        self.plan.cancel()
        with QSignalBlocker(self.enable_toggle):
            self.enable_toggle.setChecked(False)
        self.timer.stop()
        self.condition.setText(tr("When all saved accounts reach their usage limits."))
        self.countdown_minutes.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status.setText(tr("Shutdown is off."))
        self.status_changed.emit(tr("Shutdown is off."), False)

    def _tick(self) -> None:
        target = self.plan.target
        if target is None:
            return
        now = time.monotonic()
        remaining = self.plan.remaining(now)
        text = (
            tr(self.plan.reason)
            if remaining is None
            else tr("Shutting down in {seconds}s. Save your work or cancel.", seconds=remaining)
        )
        self.status.setText(text)
        self.status_changed.emit(text, True)
        if self._busy or now < self._next_check:
            return
        self._busy = True
        generation = self.plan.generation

        def checked(evidence: PowerEvidence):
            self._busy = False
            if generation != self.plan.generation or self.plan.target is None:
                return
            before = self.plan.deadline
            self.plan.observe(evidence, time.monotonic())
            if before is None and self.plan.deadline is not None:
                self.countdown_started.emit()
            if self.plan.remaining(time.monotonic()) == 0:
                self._execute()
                return
            self._next_check = time.monotonic() + (15 if self.plan.deadline is not None else 60)
            self._tick()

        self.runner.submit(
            self.checks.check(target),
            checked,
            lambda _error: checked(PowerEvidence(False, "Waiting for a fresh check.")),
        )

    def _execute(self) -> None:
        from codex_account_manager.platform.power import shutdown_windows

        self.cancel()
        try:
            from codex_account_manager.core.operation_lock import OperationLock
            from codex_account_manager.core.paths import paths

            with OperationLock(paths.data_dir / "account-operation.lock"):
                shutdown_windows()
        except Exception:
            self.status.setText(tr("Windows did not accept shutdown. The plan was cancelled."))
        else:
            self.status.setText(
                tr("Shutdown requested. Windows may ask you to save open applications.")
            )


class PowerView(BaseView):
    def __init__(self, runner, accounts, palette=DARK):
        super().__init__(palette)
        self._root.addWidget(
            view_header(
                tr("Automatic shutdown"),
                tr("Choose when to shut down and how long the cancellation countdown lasts."),
            )
        )
        self.controls = PowerControls(runner, accounts)
        self._root.addWidget(self.controls)
        self._root.addStretch()
