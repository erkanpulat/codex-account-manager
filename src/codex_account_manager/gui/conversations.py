"""Local conversation browsing, filters and explicit conversation actions."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.continuity.tracking import ObservedWork, WorkTracker, account_hash
from codex_account_manager.core.events import bus
from codex_account_manager.domain.models import ThreadRecord
from codex_account_manager.gui.async_runner import AsyncRunner
from codex_account_manager.gui.design import DARK
from codex_account_manager.gui.i18n import source_label, state_label, tr
from codex_account_manager.gui.view_base import BaseView, table_widget, view_header
from codex_account_manager.gui.widgets import ComboBox, label
from codex_account_manager.storage.repositories import ProfileRepository


class ConversationsView(BaseView):
    notes_requested = Signal(str)

    def __init__(self, runner: AsyncRunner, palette=DARK):
        super().__init__(palette)
        self.runner = runner
        self._threads: list[ThreadRecord] = []
        self._project_names: dict[str, str] = {}
        self._busy = False
        self._tracking_busy = False
        self._tracked: list[ObservedWork] = []
        self._account_names: dict[str, str] = {}
        self.sync = QPushButton(tr(" Sync threads"))
        self.sync.clicked.connect(self._sync)
        self._root.addWidget(
            view_header(
                tr("Continuity"),
                tr(
                    "See tracked work and local Codex conversations. Filter history by project or source; drag column edges to resize."
                ),
                self.sync,
            )
        )
        tracked_panel = QFrame()
        tracked_panel.setObjectName("Panel")
        tracked_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        tracked_layout = QVBoxLayout(tracked_panel)
        tracked_layout.setContentsMargins(18, 16, 18, 16)
        tracked_layout.setSpacing(10)
        tracked_header = QHBoxLayout()
        tracked_header.addWidget(label(tr("Tracked work"), "H2"))
        tracked_header.addStretch()
        self.tracked_count = label("", "Accent")
        tracked_header.addWidget(self.tracked_count)
        self.check_tracking = QPushButton(tr("Check tracking now"))
        self.check_tracking.setObjectName("Ghost")
        self.check_tracking.clicked.connect(self._request_tracking)
        tracked_header.addWidget(self.check_tracking)
        tracked_layout.addLayout(tracked_header)
        self.tracked_hint = label(
            tr(
                "The app tracks running conversations while it is open. Only a verified limit on the same turn can trigger continuation."
            ),
            "Muted",
        )
        self.tracked_hint.setWordWrap(True)
        tracked_layout.addWidget(self.tracked_hint)
        desktop_hint = label(
            tr(
                "Desktop conversations continue inside Codex Desktop. An unavailable connection is reported without moving work to another process."
            ),
            "Muted",
        )
        desktop_hint.setWordWrap(True)
        tracked_layout.addWidget(desktop_hint)
        self.tracking_status = label(tr("Waiting for the first monitoring check…"), "Muted")
        self.tracking_status.setWordWrap(True)
        tracked_layout.addWidget(self.tracking_status)
        self.tracked_table = table_widget(
            [tr("Conversation"), tr("Account"), tr("Turn"), tr("Codex goal"), tr("Last check")]
        )
        self.tracked_table.itemSelectionChanged.connect(self._tracked_selected)
        tracked_layout.addWidget(self.tracked_table)
        self.tracked_table.hide()
        self.tracked_empty = label(tr("No work is being tracked yet."), "Muted")
        tracked_layout.addWidget(self.tracked_empty)
        self.tracked_goal = QPushButton(tr("Read selected Codex goal"))
        self.tracked_goal.setObjectName("Ghost")
        self.tracked_goal.clicked.connect(self._read_tracked_goal)
        self.tracked_goal.setEnabled(False)
        self.tracked_goal.hide()
        tracked_actions = QHBoxLayout()
        self.tracked_open = QPushButton(tr("Open in Codex Desktop"))
        self.tracked_open.setObjectName("Primary")
        self.tracked_open.setEnabled(False)
        self.tracked_open.hide()
        self.tracked_open.clicked.connect(self._open_tracked)
        tracked_actions.addWidget(self.tracked_open)
        tracked_actions.addWidget(self.tracked_goal)
        tracked_actions.addStretch()
        tracked_layout.addLayout(tracked_actions)
        self._root.addWidget(tracked_panel)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search conversations or folders…"))
        self.search.textChanged.connect(self._filter)
        self.project = ComboBox()
        self.project.setMinimumWidth(180)
        self.project.setAccessibleName(tr("Project"))
        self.project.addItem(tr("All projects"), "")
        self.project.currentIndexChanged.connect(self._filter)
        self.source = ComboBox()
        self.source.setAccessibleName(tr("Source"))
        for title, value in (
            ("Main conversations", "main"),
            ("All sources", ""),
            ("Desktop / VS Code", "vscode"),
            ("CLI", "cli"),
            ("App Server", "appServer"),
            ("Exec", "exec"),
            ("Subagents", "subAgent"),
        ):
            self.source.addItem(tr(title), value)
        self.source.currentIndexChanged.connect(self._filter)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.project)
        filters.addWidget(self.source)
        self._root.addLayout(filters)
        self.status = label(tr("Refresh to read local conversations."), "Muted")
        self.status.setWordWrap(True)
        self._root.addWidget(self.status)
        self.table = table_widget(
            [tr("Conversation"), tr("Project"), tr("Source"), tr("Last activity"), tr("Workspace")]
        )
        for index, width in enumerate((280, 180, 165, 160, 230)):
            self.table.setColumnWidth(index, width)
        self.table.itemSelectionChanged.connect(self._selected)
        self._root.addWidget(self.table, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            tr("Select a conversation to see its full title, folder and preview.")
        )
        self.details.setMaximumHeight(110)
        self.details.hide()
        self._root.addWidget(self.details)
        self.action_host = QWidget()
        actions = QHBoxLayout(self.action_host)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        self.selection_label = label(tr("Selected conversation"), "FieldTitle")
        actions.addWidget(self.selection_label, 1)
        load = QPushButton(tr("Open in Codex Desktop"))
        load.setObjectName("Primary")
        load.clicked.connect(self._resume)
        more = QPushButton(tr("More actions"))
        more.setObjectName("MenuButton")
        menu = QMenu(more)
        self._actions: list[QPushButton | QAction] = [load]
        for text, handler in (
            ("Read Codex goal", self._native_goal),
            ("Save local goal note", self._note),
        ):
            action = menu.addAction(tr(text))
            action.triggered.connect(handler)
            self._actions.append(action)
        menu.addSeparator()
        self.details_toggle = menu.addAction(tr("Show conversation details"))
        self.details_toggle.setCheckable(True)
        self.details_toggle.toggled.connect(self._selected)
        self._actions.append(self.details_toggle)
        more.setMenu(menu)
        actions.addWidget(load)
        actions.addWidget(more)
        self._root.insertWidget(self._root.indexOf(self.table), self.action_host)
        self.action_host.hide()
        self.history_toggle = QPushButton(tr("Show recent account switches"))
        self.history_toggle.setCheckable(True)
        self.history_toggle.setObjectName("Ghost")
        self._root.addWidget(self.history_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.handoffs = table_widget([tr("When"), tr("Reason"), tr("Result")])
        self.handoffs.setMaximumHeight(180)
        self.handoffs.hide()
        self.history_toggle.toggled.connect(self._show_history)
        self._root.addWidget(self.handoffs)

    @staticmethod
    def _project_key(thread) -> str:
        return thread.project_id or thread.cwd or "__none__"

    def _project_title(self, thread: ThreadRecord) -> str:
        from pathlib import PureWindowsPath

        if name := self._project_names.get(self._project_key(thread)):
            return name
        if thread.cwd:
            return PureWindowsPath(thread.cwd).name or thread.cwd
        return (
            tr("Project") + " " + thread.project_id[:8] if thread.project_id else tr("No project")
        )

    def refresh(self) -> None:
        self._sync()
        self.refresh_tracking()

    def refresh_tracking(self) -> None:
        if self._tracking_busy:
            return
        self._tracking_busy = True
        self.runner.submit(self._tracking_snapshot(), self._render_tracking, self._tracking_failed)

    def _request_tracking(self) -> None:
        self.tracking_status.setText(tr("Monitoring check requested…"))
        bus.publish("monitor.refresh_requested")

    def show_tracking_status(self, payload: dict) -> None:
        state = str(payload.get("state", "failed"))
        self.check_tracking.setEnabled(state != "checking")
        messages = {
            "checking": "Checking conversation activity…",
            "timed_out": "Tracking check timed out. Previous observations are preserved; try again.",
            "failed": "Tracking could not be checked. Previous observations are preserved; try again.",
            "signed_out": "Sign in to Codex to verify conversation tracking.",
        }
        if state in {"ready", "partial"}:
            message = tr(
                "Last check {time}: {count} conversations verified.",
                time=payload.get("checked_at", "—"),
                count=payload.get("checked", 0),
            )
            if state == "partial":
                message += " " + tr(
                    "Live state could not be verified for {count} conversations.",
                    count=payload.get("unavailable", 0),
                )
        else:
            message = tr(messages.get(state, messages["failed"]))
        self.tracking_status.setText(message)

    @staticmethod
    async def _tracking_snapshot() -> tuple[list[ObservedWork], dict[str, str]]:
        tracked = await WorkTracker().visible()
        profiles = await ProfileRepository().list()
        names = {
            account_hash(profile.bound_account_id): profile.alias
            for profile in profiles
            if profile.bound_account_id
        }
        return tracked, names

    def _tracking_failed(self, _error: Exception) -> None:
        self._tracking_busy = False
        self.tracked_hint.setText(tr("Tracked work could not be loaded. Refresh to try again."))

    def _render_tracking(self, snapshot: tuple[list[ObservedWork], dict[str, str]]) -> None:
        selected = self.tracked_table.item(self.tracked_table.currentRow(), 0)
        selected_id = (
            selected.data(Qt.ItemDataRole.UserRole)
            if selected and self.tracked_table.selectedItems()
            else None
        )
        self._tracking_busy = False
        self._tracked, self._account_names = snapshot
        self.tracked_hint.setText(
            tr(
                "The app tracks running conversations while it is open. Only a verified limit on the same turn can trigger continuation."
            )
        )
        self.tracked_count.setText(tr("{count} tracked", count=len(self._tracked)))
        self.tracked_empty.setVisible(not self._tracked)
        self.tracked_table.setVisible(bool(self._tracked))
        self.tracked_goal.setVisible(bool(self._tracked))
        self.tracked_open.setVisible(bool(self._tracked))
        self.tracked_table.clearSelection()
        self.tracked_table.setCurrentCell(-1, -1)
        self.tracked_table.setRowCount(len(self._tracked))
        titles = {
            thread.id: thread.title or thread.preview or thread.id[:12] for thread in self._threads
        }
        for row, work in enumerate(self._tracked):
            title = titles.get(work.thread_id, work.thread_id[:12])
            goal = (
                state_label(work.goal_status or "unknown")
                if work.goal_present
                else tr("No Codex goal")
            )
            values = (
                title,
                self._account_names.get(work.account_hash, tr("Unknown account")),
                tr("Waiting for Desktop continuation")
                if work.turn_status == "awaitingDesktop"
                else tr("Limit reached")
                if work.limited
                else tr("Running"),
                goal,
                datetime.fromtimestamp(work.observed_at).strftime("%d.%m %H:%M"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value.replace("\n", " "))
                item.setToolTip(work.thread_id if column == 0 else value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, work.thread_id)
                self.tracked_table.setItem(row, column, item)
            if work.thread_id == selected_id:
                self.tracked_table.selectRow(row)
        self.tracked_table.setFixedHeight(min(254, 52 * (len(self._tracked) + 1) + 2))
        self._tracked_selected()

    def _tracked_selected(self) -> None:
        selected = bool(self.tracked_table.selectedItems())
        self.tracked_goal.setEnabled(selected)
        self.tracked_open.setEnabled(selected)

    def _open_tracked(self) -> None:
        row = self.tracked_table.currentRow()
        item = self.tracked_table.item(row, 0) if row >= 0 else None
        if item:
            self.open_desktop(item.data(Qt.ItemDataRole.UserRole))

    def open_desktop(self, thread_id: str) -> None:
        from codex_account_manager.platform.windows import open_conversation

        try:
            open_conversation(thread_id)
        except (OSError, RuntimeError, ValueError):
            self.tracking_status.setText(
                tr("Codex Desktop could not be opened. Open the conversation from Codex.")
            )

    def _read_tracked_goal(self) -> None:
        row = self.tracked_table.currentRow()
        item = self.tracked_table.item(row, 0) if row >= 0 else None
        if not item:
            return
        from codex_account_manager.continuity.service import ContinuityService

        self.runner.submit(
            ContinuityService().read_native_goal(item.data(Qt.ItemDataRole.UserRole)),
            self._show_native_goal,
        )

    def _sync(self) -> None:
        if self._busy:
            return
        from codex_account_manager.continuity.service import ContinuityService

        self._busy = True
        self.sync.setEnabled(False)
        self.status.setText(tr("Reading all local conversations…"))
        self.runner.submit(
            ContinuityService().sync_threads(), self._render_threads, self._sync_failed
        )

    def _sync_failed(self, error: Exception) -> None:
        self._busy = False
        self.sync.setEnabled(True)
        self.status.setText(
            tr("Could not refresh. The previous list is unchanged: {error}", error=error)
        )

    def _render_threads(self, threads) -> None:
        self._busy = False
        self.sync.setEnabled(True)
        self._threads = sorted(threads, key=lambda thread: thread.updated_at, reverse=True)
        import ntpath
        from pathlib import PureWindowsPath

        self._project_names.clear()
        folders: dict[str, list[str]] = {}
        for thread in self._threads:
            if thread.cwd:
                folders.setdefault(self._project_key(thread), []).append(thread.cwd)
        for key, members in folders.items():
            try:
                common = ntpath.commonpath(members)
            except ValueError:
                continue
            if name := PureWindowsPath(common).name:
                self._project_names[key] = name
        previous = self.project.currentData()
        with QSignalBlocker(self.project):
            self.project.clear()
            self.project.addItem(tr("All projects"), "")
            projects: dict[str, ThreadRecord] = {}
            for thread in self._threads:
                projects.setdefault(self._project_key(thread), thread)
            for key, thread in sorted(
                projects.items(), key=lambda item: self._project_title(item[1]).casefold()
            ):
                self.project.addItem(self._project_title(thread), key)
                self.project.setItemData(
                    self.project.count() - 1, thread.cwd or key, Qt.ItemDataRole.ToolTipRole
                )
            self.project.setCurrentIndex(max(0, self.project.findData(previous)))
        self._filter()
        if self._tracked:
            self._render_tracking((self._tracked, self._account_names))

    def _filter(self, *_args) -> None:
        from codex_account_manager.core.paths import paths

        query = self.search.text().casefold().strip()
        project, source = self.project.currentData(), self.source.currentData()
        rows = [
            thread
            for thread in self._threads
            if (not project or self._project_key(thread) == project)
            and (
                not source
                or (source == "main" and not (thread.source or "").startswith("subAgent"))
                or (thread.source or "").startswith(source)
            )
            and query
            in " ".join(
                (thread.title or "", thread.preview or "", thread.cwd or "", thread.id)
            ).casefold()
        ]
        selected = self._current()
        selected_id = selected.id if selected else None
        with QSignalBlocker(self.table):
            self.table.setRowCount(0)
            self.table.setRowCount(len(rows))
            for row, thread in enumerate(rows):
                title = thread.title or thread.preview or thread.id
                values = (
                    title,
                    self._project_title(thread),
                    source_label(thread.source),
                    thread.updated_at.astimezone().strftime("%d.%m.%Y %H:%M"),
                    thread.cwd or "—",
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value.replace("\n", " "))
                    item.setToolTip(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, thread)
                    self.table.setItem(row, column, item)
                if thread.id == selected_id:
                    self.table.selectRow(row)
        self.status.setText(
            tr(
                "{shown} of {total} conversations · Local Codex: {path}",
                shown=len(rows),
                total=len(self._threads),
                path=paths.shared_codex_home,
            )
        )
        self.status.setToolTip(
            tr(
                "Includes local projects and subagents. Archived, cloud-only and other-device conversations are not included."
            )
        )
        self._selected()

    def _current(self):
        if not self.table.selectedItems():
            return None
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected(self) -> None:
        thread = self._current()
        self.details.setVisible(thread is not None and self.details_toggle.isChecked())
        self.action_host.setVisible(thread is not None)
        self.selection_label.setText(tr("Selected conversation"))
        for button in self._actions:
            button.setEnabled(thread is not None)
        self.details.setPlainText(
            ""
            if thread is None
            else "\n".join(
                (
                    thread.title or thread.id,
                    thread.cwd or tr("No project"),
                    source_label(thread.source),
                    thread.preview or "",
                )
            )
        )

    def _note(self) -> None:
        thread = self._current()
        if thread:
            self.notes_requested.emit(thread.id)

    def _native_goal(self) -> None:
        thread = self._current()
        if not thread:
            return
        from codex_account_manager.continuity.service import ContinuityService

        self.runner.submit(ContinuityService().read_native_goal(thread.id), self._show_native_goal)

    def _show_native_goal(self, goal) -> None:
        message = (
            tr("The Codex goal could not be read. This is not evidence that no goal exists.")
            if goal is None
            else tr("This conversation has no Codex goal.")
            if not goal.present
            else state_label(goal.status or "unknown") + "\n\n" + (goal.objective or "")
        )
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("Read Codex goal"))
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(message)
        dialog.exec()

    def _resume(self) -> None:
        thread = self._current()
        if thread:
            self.open_desktop(thread.id)

    def _show_history(self, visible: bool) -> None:
        self.handoffs.setVisible(visible)
        if visible:
            from codex_account_manager.continuity.service import ContinuityService

            self.runner.submit(ContinuityService().recent_handoffs(10), self._render_handoffs)

    def _render_handoffs(self, handoffs) -> None:
        self.handoffs.setRowCount(len(handoffs))
        for row, handoff in enumerate(handoffs):
            values = (
                handoff.started_at.strftime("%d.%m.%Y %H:%M"),
                state_label(handoff.reason.value),
                "…" if handoff.success is None else tr("OK") if handoff.success else tr("FAILED"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(handoff.detail or value)
                self.handoffs.setItem(row, column, item)
