"""Visible, session-only shutdown controls. No shutdown runs in widget tests."""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.gui.design import DARK
from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.view_base import BaseView, setting_row, view_header
from codex_account_manager.gui.widgets import label
from codex_account_manager.monitoring.power import (
    CONDITION_COUNTDOWN_SECONDS,
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
        layout.addWidget(label(tr("When should the computer shut down?"), "H2"))
        hint = label(
            tr("Choose one condition. The plan stays active only while QuotaCrew is running."),
            "Caption",
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.mode = QComboBox()
        for title, mode in [
            ("When my selected work finishes", "work"),
            ("When all accounts reach their limits", "limits"),
            ("After a set time", "timer"),
        ]:
            self.mode.addItem(tr(title), mode)
        self.mode.setCurrentIndex(1)
        setting_row(layout, tr("Shutdown condition"), "", self.mode)
        self.explanation = label("", "Muted")
        self.explanation.setWordWrap(True)
        layout.addWidget(self.explanation)
        self.work_fields = QWidget()
        work_layout = QVBoxLayout(self.work_fields)
        work_layout.setContentsMargins(0, 0, 0, 0)
        self.conversation = QComboBox()
        self.conversation.setMinimumWidth(280)
        self.conversation.setAccessibleName(tr("Conversation"))
        self.refresh_button = QPushButton(tr("Refresh conversations"))
        self.refresh_button.clicked.connect(self.refresh_conversations)
        work_row = QHBoxLayout()
        work_row.addWidget(self.conversation, 1)
        work_row.addWidget(self.refresh_button)
        work_layout.addLayout(work_row)
        layout.addWidget(self.work_fields)
        self.time_fields = QWidget()
        time_layout = QVBoxLayout(self.time_fields)
        time_layout.setContentsMargins(0, 0, 0, 0)
        self.countdown_minutes = QSpinBox()
        self.countdown_minutes.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.countdown_minutes.setRange(1, MAX_COUNTDOWN_MINUTES)
        self.countdown_minutes.setValue(120)
        self.countdown_minutes.setSuffix(tr(" minutes"))
        setting_row(
            time_layout,
            tr("Shut down after (minutes)"),
            tr("Enter minutes: 120 = 2 hours, 180 = 3 hours. Range: 1–1440 minutes."),
            self.countdown_minutes,
        )
        layout.addWidget(self.time_fields)
        self.status = label(tr("Shutdown is off."), "FieldTitle")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.schedule_button = QPushButton(tr("Plan shutdown"))
        self.schedule_button.setObjectName("Primary")
        self.schedule_button.clicked.connect(self._schedule)
        self.cancel_button = QPushButton(tr("Cancel shutdown"))
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        buttons.addWidget(self.schedule_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        note = label(
            tr(
                "You can cancel from this page or the tray. Open applications are not forcibly closed."
            ),
            "Caption",
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self._loading = False
        self._warned = False
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

    def _mode_changed(self) -> None:
        mode = self.mode.currentData()
        self.work_fields.setVisible(mode == "work")
        self.time_fields.setVisible(mode == "timer")
        explanations = {
            "work": "Select a running conversation. Once it completes and no other Codex work is active, a 2-minute countdown starts. Errors and requests for input do not count as completion.",
            "limits": "Once every saved account is verified out of available usage and no Codex work is active, a 2-minute countdown starts.",
            "timer": "Time starts when you confirm. The last 2 minutes are included in your chosen duration. This mode does not wait for Codex work to finish.",
        }
        self.explanation.setText(tr(explanations[mode]))
        self.schedule_button.setEnabled(sys.platform == "win32")
        if mode == "work" and not self.conversation.count():
            self.refresh_conversations()

    def refresh_conversations(self) -> None:
        if self._loading or self.plan.target is not None or self._preparing:
            return
        self._loading = True
        selected = self.conversation.currentData()
        self.refresh_button.setEnabled(False)
        self.status.setText(tr("Loading conversations…"))

        def done(items):
            self._loading = False
            self.refresh_button.setEnabled(self.plan.target is None)
            if self.plan.target is not None or self._preparing:
                return
            self.conversation.clear()
            for thread_id, title in items:
                self.conversation.addItem(title, thread_id)
            index = self.conversation.findData(selected)
            if index >= 0:
                self.conversation.setCurrentIndex(index)
            self.status.setText(
                tr("Shutdown is off.")
                if items
                else tr("No running conversations found. Open your conversation and refresh.")
            )

        def failed(_error):
            done([])
            if self.plan.target is None:
                self.status.setText(
                    tr(
                        "Conversations could not be loaded. Keep Codex or your IDE open and refresh."
                    )
                )

        self.runner.submit(self.checks.conversations(), done, failed)

    def _schedule(self) -> None:
        if self._preparing or self.plan.target is not None:
            return
        mode = self.mode.currentData()
        if mode == "work":
            thread_id = self.conversation.currentData()
            if not thread_id:
                self.status.setText(tr("Select a verified running conversation first."))
                return
            self.arm_work(thread_id)
        else:
            self.arm(PowerTarget(mode))

    def _set_editable(self, editable: bool) -> None:
        self.mode.setEnabled(editable)
        self.conversation.setEnabled(editable)
        self.refresh_button.setEnabled(editable and not self._loading)
        self.countdown_minutes.setEnabled(editable)
        self.schedule_button.setEnabled(editable and sys.platform == "win32")
        self.cancel_button.setEnabled(not editable)

    def arm_work(self, thread_id: str) -> None:
        if self._preparing or self.plan.target is not None:
            return
        self._preparing = True
        self._set_editable(False)
        self.status.setText(tr("Verifying selected work…"))
        generation = self.plan.generation

        def ready(target):
            if generation == self.plan.generation:
                self._preparing = False
                self._set_editable(True)
                self.arm(target)

        def failed(_error):
            if generation == self.plan.generation:
                self._preparing = False
                self._set_editable(True)
                self.status.setText(tr("Select a verified running conversation first."))

        self.runner.submit(self.checks.work_target(thread_id), ready, failed)

    def arm(self, target: PowerTarget) -> None:
        if sys.platform != "win32" or self.plan.target is not None:
            return
        condition = {
            "limits": "When all saved accounts reach their usage limits.",
            "work": "When the selected work is complete.",
            "timer": "After a set time",
        }[target.mode]
        minutes = self.countdown_minutes.value() if target.mode == "timer" else 2
        confirmation = (
            tr(
                "Shut down in {minutes} minutes from now, even if Codex work is still running? Save work in other applications.",
                minutes=minutes,
            )
            if target.mode == "timer"
            else tr(
                "Enable shutdown for this session? Condition: {condition} Countdown: {minutes} minutes. Save work in other applications.",
                condition=tr(condition),
                minutes=minutes,
            )
        )
        if (
            QMessageBox.question(
                self,
                tr("Schedule shutdown"),
                confirmation,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            self.status.setText(tr("Shutdown is off."))
            return
        self.plan.set_seconds(minutes * 60)
        self.plan.arm(target, now=time.monotonic())
        self._warned = False
        self.mode.setCurrentIndex(self.mode.findData(target.mode))
        if target.thread_id:
            index = self.conversation.findData(target.thread_id)
            if index < 0:
                self.conversation.addItem(target.thread_id[:12], target.thread_id)
                index = self.conversation.count() - 1
            self.conversation.setCurrentIndex(index)
        self._set_editable(False)
        self._next_check = 0.0
        self.timer.start()
        self._tick()

    def cancel(self) -> None:
        self.plan.cancel()
        self._preparing = False
        self.timer.stop()
        self._set_editable(True)
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
        if target.mode == "timer" and remaining is not None:
            minutes, seconds = divmod(remaining, 60)
            hours, minutes = divmod(minutes, 60)
            text = tr(
                "Timed shutdown in {time}. Codex work will not delay it.",
                time=f"{hours:02}:{minutes:02}:{seconds:02}",
            )
        self.status.setText(text)
        self.status_changed.emit(text, True)
        if target.mode == "timer":
            if (
                remaining is not None
                and remaining <= CONDITION_COUNTDOWN_SECONDS
                and not self._warned
            ):
                self._warned = True
                self.countdown_started.emit()
            if remaining == 0:
                self._execute()
            return
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
                tr("Finish your work, use your remaining limits or choose a shutdown time."),
            )
        )
        self.controls = PowerControls(runner, accounts)
        self._root.addWidget(self.controls)
        self._root.addStretch()
