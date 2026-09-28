"""Main window: branded sidebar, stacked views, live theming and system tray."""

from __future__ import annotations

from PySide6.QtCore import QObject, QSignalBlocker, QSize, Qt, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager import __version__
from codex_account_manager.accounts.service import AccountService
from codex_account_manager.continuity.service import ContinuityService
from codex_account_manager.core.events import bus
from codex_account_manager.core.logging import get_logger
from codex_account_manager.gui.about import AboutView
from codex_account_manager.gui.accounts import AccountsView
from codex_account_manager.gui.async_runner import AsyncRunner
from codex_account_manager.gui.conversations import ConversationsView
from codex_account_manager.gui.design import DARK, LIGHT, app_icon, make_icon
from codex_account_manager.gui.diagnostics import DiagnosticsView
from codex_account_manager.gui.goals import GoalsView
from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.overview import DashboardView
from codex_account_manager.gui.settings import SettingsView
from codex_account_manager.gui.theme import application_palette, stylesheet
from codex_account_manager.gui.widgets import label

log = get_logger(__name__)

_NAV = [
    ("Overview", "dashboard"),
    ("Continuity", "continuity"),
    ("Accounts", "accounts"),
    ("Goals", "goals"),
    ("Diagnostics", "diagnostics"),
    ("Settings", "settings"),
    ("About", "about"),
]


class _EventBridge(QObject):
    received = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self, runner: AsyncRunner):
        super().__init__()
        self.runner = runner
        self.accounts = AccountService()
        self._dark = True
        self._switching = False
        self.runner.failed.connect(self._operation_failed)
        self._bridge = _EventBridge(self)
        self._bridge.received.connect(self._domain_event)
        self._unsubscribe = bus.subscribe("*", self._bridge.received.emit)
        self.setWindowTitle(tr("Codex Account Manager"))
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1040, 700)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        self.resize(
            min(1360, available.width() - 40) if available else 1360,
            min(900, available.height() - 60) if available else 900,
        )

        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("Content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self._build_views()
        for view in self._views:
            self.stack.addWidget(view)
        self.back_to_settings = QPushButton(tr("Back to settings"))
        self.back_to_settings.setObjectName("Ghost")
        self.back_to_settings.clicked.connect(lambda: self._on_nav(5))
        self.back_to_settings.hide()
        content_layout.addWidget(self.back_to_settings, 0, Qt.AlignmentFlag.AlignLeft)
        content_layout.addWidget(self.stack)
        layout.addWidget(content, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage(tr("Local workspace · Automatic switching by default"))
        self.nav.setCurrentRow(0)
        self._build_tray()
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("Ctrl+R"), self, self._refresh_current)

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(224)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(14, 24, 14, 18)
        layout.setSpacing(12)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon(32).pixmap(32, 32))
        name = QLabel(tr("Codex Accounts"))
        name.setObjectName("Brand")
        brand.addWidget(logo)
        brand.addWidget(name)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(22)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setIconSize(QSize(22, 22))
        for title, glyph in _NAV:
            item = QListWidgetItem(make_icon(glyph, DARK.muted), "  " + tr(title))
            self.nav.addItem(item)
        for row in (3, 4):
            self.nav.item(row).setHidden(True)
        self.nav.currentRowChanged.connect(self._on_nav)
        layout.addWidget(self.nav, 1)

        layout.addWidget(label(tr("●  Local workspace"), "Accent"))
        layout.addWidget(label(tr("Accounts stay on this device"), "Muted"))
        version = QLabel(tr("v{version} · Open source", version=__version__))
        version.setObjectName("Muted")
        version.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(version)
        return side

    def _build_views(self) -> None:
        self.dashboard = DashboardView(self.runner, self.accounts, self._switch)
        self.dashboard.manage_requested.connect(lambda: self.nav.setCurrentRow(2))
        self.conversations = ConversationsView(self.runner)
        self.accounts_view = AccountsView(self.runner, self.accounts)
        self.goals = GoalsView(self.runner)
        self.diagnostics = DiagnosticsView(self.runner)
        self.settings = SettingsView(self.runner, self._apply_theme)
        self.settings.policy_changed.connect(self._policy_changed)
        self.settings.diagnostics_requested.connect(lambda: self._open_tool(4))
        self.settings.notes_requested.connect(lambda: self._open_tool(3))
        self.conversations.notes_requested.connect(self._save_note)
        self.about = AboutView()
        self._views = [
            self.dashboard,
            self.conversations,
            self.accounts_view,
            self.goals,
            self.diagnostics,
            self.settings,
            self.about,
        ]

    def _focus_search(self) -> None:
        view = self._views[self.stack.currentIndex()]
        if search := getattr(view, "search", None):
            search.setFocus()
            search.selectAll()

    def _refresh_current(self) -> None:
        self._views[self.stack.currentIndex()].refresh()

    def _open_tool(self, index: int) -> None:
        with QSignalBlocker(self.nav):
            self.nav.setCurrentRow(5)
            self.stack.setCurrentIndex(index)
            self.back_to_settings.show()
        self._views[index].refresh()

    def _save_note(self, thread_id: str) -> None:
        self._open_tool(3)
        self.goals.save_for_thread(thread_id)

    def _policy_changed(self, mode: str) -> None:
        messages = {
            "manual": tr("Manual mode · You choose when to switch accounts."),
            "confirm": tr("Confirmation mode · We ask before changing a limited account."),
            "availability_failover": tr(
                "Automatic mode · A limited account is replaced when verified capacity is available."
            ),
        }
        self.dashboard.mode_label.setText(messages.get(mode, messages["manual"]))
        self.statusBar().showMessage(messages.get(mode, messages["manual"]))

    def _on_nav(self, row: int) -> None:
        if row < 0:
            return
        self.back_to_settings.setVisible(row in {3, 4})
        self.stack.setCurrentIndex(row)
        view = self._views[row]
        if hasattr(view, "refresh"):
            view.refresh()

    def _apply_theme(self, dark: bool) -> None:
        self._dark = dark
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setPalette(application_palette(dark))
            app.setStyleSheet(stylesheet(dark=dark))
        palette = DARK if dark else LIGHT
        for view in self._views:
            view.palette_ = palette
        self.dashboard._filter()
        for i, (_label, glyph) in enumerate(_NAV):
            self.nav.item(i).setIcon(make_icon(glyph, palette.muted))

    def _switch(self, alias: str, *, follow_latest: bool = False) -> None:
        if self._switching:
            return
        self._switching = True
        if (
            QMessageBox.question(
                self,
                tr("Switch account"),
                tr(
                    "Switch to '{alias}'? Codex Desktop will restart. Save your work first; conversation history is preserved.",
                    alias=alias,
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            self._switching = False
            return
        self.dashboard.setEnabled(False)
        self.statusBar().showMessage(tr("Switching to {alias}…", alias=alias))

        async def _do():
            continuity = ContinuityService(accounts=self.accounts)
            if follow_latest:
                return await continuity.continue_on_limit(alias)
            return await continuity.handoff(alias)

        self.runner.submit(_do(), lambda _: self._switch_done(alias), self._switch_failed)

    def _switch_done(self, alias: str) -> None:
        self._switching = False
        self.dashboard.setEnabled(True)
        self.statusBar().showMessage(
            tr("Switched to {alias}. Shared history preserved.", alias=alias)
        )
        self.dashboard.refresh()

    def _switch_failed(self, exc: Exception) -> None:
        self._switching = False
        self.dashboard.setEnabled(True)
        self.statusBar().showMessage(tr("Switch failed. Check the error and Diagnostics."))
        QMessageBox.warning(self, tr("Switch failed"), tr(str(exc)))

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, tr("Operation failed"), message)

    @Slot(object)
    def _domain_event(self, event) -> None:
        if event.topic == "health.updated":
            self.dashboard._render(event.payload["health"])
        elif event.topic == "switch.suggested":
            self._switch(event.payload["target"], follow_latest=True)
        elif event.topic == "switch.failed" and "alias" not in event.payload:
            self._switch_failed(RuntimeError(event.payload["detail"]))
        elif event.topic == "switch.completed":
            self.dashboard.refresh()
        elif event.topic == "work.observed" and self.stack.currentIndex() == 1:
            self.conversations.refresh_tracking()
        elif event.topic == "work.observation_status":
            self.conversations.show_tracking_status(event.payload)
        elif event.topic == "continuation.status":
            if event.payload.get("state") == "desktop_required" and event.payload.get("thread_id"):
                self.conversations.open_desktop(event.payload["thread_id"])
            messages = {
                "desktop_submitted": "Continuation sent to Codex Desktop. The conversation stays in Desktop with its tools.",
                "desktop_required": "Account switched. Continue the conversation in Codex Desktop to keep its browser and app tools.",
                "running": "Continuing interrupted work automatically. Disable continuation in Settings to stop.",
                "completed": "Automatic continuation finished. Review the result in Codex.",
                "stopped": "Automatic continuation stopped. Your pauses and goal limits are preserved.",
                "needs_user": "Automatic continuation needs attention. Open the conversation in Codex; approval, input or an error may require your action.",
                "skipped": "Account switched. No previously observed running conversation could be verified for continuation.",
            }
            message = tr(messages.get(event.payload["state"], messages["needs_user"]))
            stages = {
                "desktop": "Codex Desktop continuation",
                "connection": "Codex connection",
                "account": "Active account verification",
                "conversation": "Conversation loading",
                "verification": "Conversation state verification",
                "goal": "Goal state verification",
                "journal": "Continuation record",
                "execution": "Continuation request",
            }
            stage = stages.get(event.payload.get("stage"))
            if stage:
                message += " " + tr("Stopped at: {stage}", stage=tr(stage))
            self.statusBar().showMessage(message)

    def dispose(self) -> None:
        self._unsubscribe()
        self.tray.hide()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(tr("Codex Account Manager"))
        menu = QMenu(self)
        for title, callback in (
            (tr("Open Codex Account Manager"), self._show),
            (tr("Refresh usage"), self.dashboard.refresh),
            (tr("Quit"), self._quit),
        ):
            action = QAction(title, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self._show()

    def _show(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        from PySide6.QtWidgets import QApplication

        self.tray.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()
