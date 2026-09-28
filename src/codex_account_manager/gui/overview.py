"""Overview screen."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.accounts.service import AccountService
from codex_account_manager.domain.models import ProfileHealth
from codex_account_manager.gui.async_runner import AsyncRunner
from codex_account_manager.gui.design import DARK
from codex_account_manager.gui.i18n import (
    tr,
)
from codex_account_manager.gui.view_base import BaseView, view_header
from codex_account_manager.gui.widgets import AccountCard, label


class DashboardView(BaseView):
    manage_requested = Signal()

    def __init__(
        self,
        runner: AsyncRunner,
        accounts: AccountService,
        on_switch: Callable[[str], None],
        palette=DARK,
    ):
        super().__init__(palette)
        self.runner = runner
        self.accounts = accounts
        self.on_switch = on_switch
        self._cards: dict[str, AccountCard] = {}
        self._health: list[ProfileHealth] = []
        self._busy = False
        self._loaded = False
        self._load_error: str | None = None
        self.refresh_btn = QPushButton(tr("Refresh usage"))
        self.refresh_btn.clicked.connect(self.refresh)
        self._root.addWidget(
            view_header(
                tr("Overview"),
                tr("Usage and availability at a glance."),
                self.refresh_btn,
            )
        )
        self.summary = label("", "Muted")
        self.summary.setWordWrap(True)
        hero = QFrame()
        self.hero = hero
        hero.setObjectName("Hero")
        hero_box = QHBoxLayout(hero)
        hero_box.setContentsMargins(20, 14, 20, 14)
        hero_text = QVBoxLayout()
        hero_text.addWidget(label(tr("CURRENT ACCOUNT"), "Eyebrow"))
        self.active_label = label(tr("Waiting for account status"), "HeroTitle")
        self.active_label.setWordWrap(True)
        hero_text.addWidget(self.active_label)
        hero_text.addWidget(self.summary)
        hero_box.addLayout(hero_text, 1)
        manage = QPushButton(tr("Manage profiles"))
        manage.clicked.connect(self.manage_requested.emit)
        hero_box.addWidget(manage)
        self._root.addWidget(hero)
        self.mode_label = label(
            tr(
                "Automatic mode · A limited account is replaced when verified capacity is available."
            ),
            "Accent",
        )
        self.mode_label.setWordWrap(True)
        hero_text.addWidget(self.mode_label)
        self.toolbar_host = QWidget()
        toolbar = QHBoxLayout(self.toolbar_host)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addWidget(label(tr("Account overview"), "H2"))
        toolbar.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Filter profiles…"))
        self.search.setAccessibleName(tr("Filter profiles"))
        self.search.setMaximumWidth(240)
        self.search.textChanged.connect(self._filter)
        toolbar.addWidget(self.search)
        self._root.addWidget(self.toolbar_host)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._grid_host = QWidget()
        self._grid_host.setObjectName("GridHost")
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(16)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._grid_host)
        self._root.addWidget(scroll, 1)
        self.status = label(tr("Ready to refresh"), "Muted")
        self._root.addWidget(self.status)
        self._filter()

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._load_error = None
        self._filter()
        self.status.setText(tr("Checking account health…"))
        self.refresh_btn.setEnabled(False)
        self.runner.submit(self.accounts.all_health(), self._render, self._on_error)

    def _render(self, health: list[ProfileHealth]) -> None:
        from datetime import datetime

        from codex_account_manager.continuity.policy import SwitchPolicy

        self._busy = False
        self.refresh_btn.setEnabled(True)
        self._loaded = True
        self._load_error = None
        self._health = health
        for widget in (self.summary, self.hero, self.toolbar_host):
            widget.setVisible(bool(health))
        available = sum(SwitchPolicy._is_available(item) for item in health)
        self.summary.setText(
            tr(
                "{total} accounts · {ready} available · {attention} need attention",
                total=len(health),
                ready=available,
                attention=len(health) - available,
            )
        )
        active = next((item.alias for item in health if item.is_active), None)
        self.active_label.setText(active or tr("No active profile identified"))
        self.status.setText(
            tr(
                "Updated {time} · {count} accounts · Stored on this device",
                time=datetime.now().strftime("%H:%M"),
                count=len(health),
            )
        )
        self._filter()

    def _filter(self, _text: str = "") -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._cards.clear()
        for widget in (self.hero, self.toolbar_host):
            widget.setVisible(self._loaded and bool(self._health))
        if not self._loaded:
            self._show_pending_state()
            return
        query = self.search.text().casefold().strip()
        health = [item for item in self._health if query in item.alias.casefold()]
        if not health:
            empty = QFrame()
            empty.setObjectName("Empty")
            box = QVBoxLayout(empty)
            box.setContentsMargins(24, 24, 24, 24)
            box.setSpacing(18)
            title = label(
                tr("No matching profiles") if self._health else tr("Bring your first account"), "H2"
            )
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(title)
            hint = label(
                tr("Try another name.")
                if self._health
                else tr(
                    "Start with a name you recognize. Sign in securely through Codex; your account is linked automatically."
                ),
                "Muted",
            )
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setWordWrap(True)
            box.addWidget(hint)
            if not self._health:
                add = QPushButton(tr("Add a profile"))
                add.setObjectName("Primary")
                add.clicked.connect(self.manage_requested.emit)
                box.addWidget(add, 0, Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(empty, 0, 0, 1, 2, Qt.AlignmentFlag.AlignTop)
            return
        for index, profile in enumerate(sorted(health, key=lambda h: not h.is_active)):
            card = AccountCard(profile, self.palette_)
            card.switch_requested.connect(self.on_switch)
            self._cards[profile.alias] = card
            self._grid.addWidget(card, index // 2, index % 2)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)

    def _on_error(self, exc: Exception) -> None:
        self._busy = False
        self.refresh_btn.setEnabled(True)
        self._load_error = str(exc)
        self.status.setText(tr("Could not refresh: {error}", error=exc))
        self._filter()

    def _show_pending_state(self) -> None:
        panel = QFrame()
        panel.setObjectName("Empty")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        panel.setMaximumHeight(210)
        box = QVBoxLayout(panel)
        box.setContentsMargins(32, 32, 32, 32)
        box.setSpacing(14)
        failed = self._load_error is not None
        title = label(
            tr("Accounts could not be loaded") if failed else tr("Loading accounts…"), "H2"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(title)
        hint = label(
            tr("Check your connection and Codex installation, then try again.")
            if failed
            else tr("Reading saved accounts and checking usage. This may take a moment."),
            "Muted",
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        box.addWidget(hint)
        if failed:
            retry = QPushButton(tr("Try again"))
            retry.setObjectName("Primary")
            retry.clicked.connect(self.refresh)
            box.addWidget(retry, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            progress = QProgressBar()
            progress.setRange(0, 0)
            progress.setTextVisible(False)
            progress.setFixedHeight(4)
            progress.setMaximumWidth(240)
            box.addWidget(progress, 0, Qt.AlignmentFlag.AlignHCenter)
        self._grid.addWidget(panel, 0, 0, 1, 2, Qt.AlignmentFlag.AlignTop)
