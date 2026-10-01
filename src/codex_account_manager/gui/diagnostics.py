"""Diagnostics screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)

from codex_account_manager.diagnostics import export_bundle, run_diagnostics
from codex_account_manager.gui.async_runner import AsyncRunner
from codex_account_manager.gui.design import DARK, set_button_icon
from codex_account_manager.gui.i18n import (
    diagnostic_detail,
    diagnostic_name,
    tr,
)
from codex_account_manager.gui.view_base import BaseView, page_panel, table_widget, view_header


class DiagnosticsView(BaseView):
    def __init__(self, runner: AsyncRunner, palette=DARK):
        super().__init__(palette)
        self.runner = runner
        actions = QWidget()
        row = QHBoxLayout(actions)
        row.setContentsMargins(0, 0, 0, 0)
        run = QPushButton(tr(" Run"))
        run.setObjectName("Primary")
        set_button_icon(run, "diagnostics", palette.on_primary)
        run.clicked.connect(self.refresh)
        self.run_button = run
        bundle = QPushButton(tr("Export bundle"))
        bundle.clicked.connect(self._bundle)
        row.addWidget(run)
        row.addWidget(bundle)
        self._root.addWidget(
            view_header(
                tr("Diagnostics"),
                tr("Check your Codex installation. Select a result to see the full explanation."),
                actions,
            )
        )
        panel, panel_layout = page_panel()
        self._root.addWidget(panel, 1)
        self.table = table_widget([tr("Check"), tr("Status"), tr("Detail")])
        self.table.fit_columns((180, 140, 300), (2, 1, 5))
        self.table.setSortingEnabled(True)
        self.table.cellClicked.connect(self._show_detail)
        panel_layout.addWidget(self.table, 1)
        self.status = QLabel()
        self.status.setObjectName("Muted")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.hide()
        panel_layout.addWidget(self.status)

    def refresh(self) -> None:
        if not self.run_button.isEnabled():
            return
        self.run_button.setEnabled(False)
        self.status.hide()
        self.set_loading("diagnostics", True)
        self.runner.submit(run_diagnostics(), self._render, self._failed)

    def _failed(self, error: Exception) -> None:
        self.set_loading("diagnostics", False)
        self.run_button.setEnabled(True)
        self.status.setText(tr("Could not refresh: {error}", error=error))
        self.status.show()

    def _render(self, results) -> None:
        self.set_loading("diagnostics", False)
        self.run_button.setEnabled(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))
        for row, r in enumerate(results):
            self.table.setItem(row, 0, QTableWidgetItem(diagnostic_name(r.name)))
            status = QTableWidgetItem(tr("Ready") if r.ok else tr("Needs attention"))
            status.setForeground(Qt.GlobalColor.green if r.ok else Qt.GlobalColor.red)
            self.table.setItem(row, 1, status)
            text = diagnostic_detail(r.name, r.ok, r.detail)
            detail = QTableWidgetItem(text)
            detail.setToolTip(text)
            self.table.setItem(row, 2, detail)
        self.table.setSortingEnabled(True)

    def _show_detail(self, row: int, _column: int) -> None:
        name, detail = self.table.item(row, 0), self.table.item(row, 2)
        if name and detail:
            QMessageBox.information(self, name.text(), detail.text())

    def _bundle(self) -> None:
        from pathlib import Path

        destination, _ = QFileDialog.getSaveFileName(
            self, tr("Save diagnostics bundle"), "diagnostics.zip", tr("ZIP archive (*.zip)")
        )
        if not destination:
            return
        self.runner.submit(
            export_bundle(Path(destination)),
            lambda path: QMessageBox.information(
                self, tr("Diagnostics bundle"), tr("Written to:\n{path}", path=path)
            ),
        )
