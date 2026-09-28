"""Shared view layout and accessible table building blocks."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.gui.design import DARK, Palette


def view_header(title: str, subtitle: str, action: QWidget | None = None) -> QWidget:
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    text = QVBoxLayout()
    text.setSpacing(6)
    h1 = QLabel(title)
    h1.setObjectName("H1")
    h1.setWordWrap(True)
    sub = QLabel(subtitle)
    sub.setObjectName("Muted")
    sub.setWordWrap(True)
    text.addWidget(h1)
    text.addWidget(sub)
    row.addLayout(text, 1)
    if action is not None:
        row.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
    return host


def tooltip_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setToolTip(text)
    return item


def table_widget(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    table.horizontalHeader().setDefaultSectionSize(200)
    table.horizontalHeader().setMinimumSectionSize(80)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setShowGrid(False)
    table.setAlternatingRowColors(False)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.verticalHeader().setDefaultSectionSize(50)
    table.setWordWrap(False)
    return table


class BaseView(QWidget):
    def __init__(self, palette: Palette = DARK):
        super().__init__()
        self.palette_ = palette
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(26, 24, 26, 20)
        self._root.setSpacing(16)

    def refresh(self) -> None:  # overridden
        ...
