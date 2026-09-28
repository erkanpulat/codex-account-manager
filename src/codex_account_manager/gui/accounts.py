"""Accounts screen."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)

from codex_account_manager.accounts.service import AccountService
from codex_account_manager.gui.async_runner import AsyncRunner
from codex_account_manager.gui.design import DARK, make_icon
from codex_account_manager.gui.dialogs import prompt_text
from codex_account_manager.gui.i18n import (
    tr,
)
from codex_account_manager.gui.view_base import BaseView, table_widget, view_header
from codex_account_manager.gui.widgets import label


class AccountsView(BaseView):
    def __init__(self, runner: AsyncRunner, accounts: AccountService, palette=DARK):
        super().__init__(palette)
        self.runner = runner
        self.accounts = accounts
        self._login_busy = False
        self._loaded = False

        add = QPushButton(tr(" Add profile"))
        add.setObjectName("Primary")
        add.setIcon(make_icon("accounts", palette.on_primary))
        add.clicked.connect(self._add)
        self._root.addWidget(
            view_header(
                tr("Accounts"),
                tr(
                    "Add an account, select it, and sign in. Your login details stay on this device."
                ),
                add,
            )
        )

        self.guide = label(
            tr(
                "Getting started: Add account → Select the row → Sign in. Linking is automatic after sign-in."
            ),
            "Body",
        )
        self.guide.setWordWrap(True)
        self.guide.hide()
        self._root.addWidget(self.guide)
        self.table = table_widget([tr("Account name"), tr("Sign-in status")])
        self._root.addWidget(self.table, 1)
        self.operation_status = label(tr("Loading saved accounts…"), "Accent")
        self.operation_status.setWordWrap(True)
        self._root.addWidget(self.operation_status)

        self.action_bar = QWidget()
        actions = QHBoxLayout(self.action_bar)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        self.selection_label = label(tr("Select an account"), "Muted")
        self.selection_label.setWordWrap(True)
        actions.addWidget(self.selection_label, 1)
        sign_in = QPushButton(tr("Sign in"))
        sign_in.setObjectName("Primary")
        sign_in.clicked.connect(self._login)
        self.more = QPushButton(tr("More actions"))
        self.more.setObjectName("MenuButton")
        menu = QMenu(self.more)
        self._profile_actions: list[QPushButton | QAction] = [sign_in]
        for title, handler in (
            ("Rename", self._rename),
            ("Bind account", self._bind),
            ("Remove", self._remove),
        ):
            if title == "Remove":
                menu.addSeparator()
            action = menu.addAction(tr(title))
            action.triggered.connect(handler)
            self._profile_actions.append(action)
        self.more.setMenu(menu)
        actions.addWidget(sign_in)
        actions.addWidget(self.more)
        self._root.insertWidget(2, self.action_bar)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self._selection_changed()

    def refresh(self) -> None:
        if not self._loaded:
            self.operation_status.setText(tr("Loading saved accounts…"))
        self.runner.submit(self.accounts.list_profiles(), self._render, self._load_failed)

    def _load_failed(self, error: Exception) -> None:
        self.operation_status.setText(tr("Could not load accounts: {error}", error=error))

    def _render(self, profiles) -> None:
        self._loaded = True
        if self.operation_status.text() == tr("Loading saved accounts…"):
            self.operation_status.clear()
        selected = self._selected_alias()
        self.guide.setVisible(not profiles)
        with QSignalBlocker(self.table):
            self.table.setRowCount(0)
            self.table.setRowCount(len(profiles))
            for row, profile in enumerate(profiles):
                self.table.setItem(row, 0, QTableWidgetItem(profile.alias))
                self.table.setItem(
                    row,
                    1,
                    QTableWidgetItem(
                        tr("Account linked") if profile.bound_account_id else tr("Sign-in required")
                    ),
                )
                if profile.alias == selected:
                    self.table.selectRow(row)
        self._selection_changed()

    def _selection_changed(self) -> None:
        alias = self._selected_alias()
        self.selection_label.setText(alias or tr("Select an account"))
        self.more.setEnabled(not self._login_busy and alias is not None)
        for button in self._profile_actions:
            button.setEnabled(not self._login_busy and alias is not None)

    def _selected_alias(self) -> str | None:
        if not self.table.selectedItems():
            return None
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _add(self) -> None:
        alias = prompt_text(
            self,
            tr("Add profile"),
            tr("Account name"),
            tr("Choose a name you will recognize, such as Personal or Work."),
            maximum=64,
            action="Add account",
        )
        if alias:
            self.runner.submit(self.accounts.create_profile(alias), lambda _: self.refresh())

    def _login(self) -> None:
        alias = self._selected_alias()
        if alias and not self._login_busy:
            self._login_busy = True
            self._selection_changed()
            self.operation_status.setText(
                tr("Waiting for Codex sign-in… Complete the sign-in flow in the window that opens.")
            )
            self.runner.submit(
                self.accounts.login_profile(alias), self._login_done, self._login_failed
            )

    def _login_done(self, _account_id: str) -> None:
        self._login_busy = False
        self.operation_status.setText(
            tr("Sign-in complete. Your account is linked. Refresh usage in Overview.")
        )
        self._selection_changed()
        self.refresh()

    def _login_failed(self, error: Exception) -> None:
        self._login_busy = False
        self.operation_status.setText(
            tr("Sign-in could not be completed. Select the account and try again.")
        )
        self._selection_changed()
        QMessageBox.warning(self, tr("Operation failed"), tr(str(error)))

    def _bind(self) -> None:
        alias = self._selected_alias()
        if alias:
            self.runner.submit(
                self.accounts.bind_current_account(alias),
                lambda _: self.refresh(),
                lambda e: QMessageBox.warning(self, tr("Bind failed"), str(e)),
            )

    def _rename(self) -> None:
        alias = self._selected_alias()
        if not alias:
            return
        new = prompt_text(
            self,
            tr("Rename"),
            tr("Account name"),
            tr("This changes the name shown in this application."),
            initial=alias,
            maximum=64,
            action="Save",
        )
        if new and new != alias:
            self.runner.submit(self.accounts.rename_profile(alias, new), lambda _: self.refresh())

    def _remove(self) -> None:
        alias = self._selected_alias()
        if not alias:
            return
        if (
            QMessageBox.question(
                self,
                tr("Remove profile"),
                tr(
                    "Remove '{alias}'? Shared Codex conversation history will be preserved.",
                    alias=alias,
                ),
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.runner.submit(self.accounts.remove_profile(alias), lambda _: self.refresh())
