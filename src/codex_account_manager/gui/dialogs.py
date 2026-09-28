"""Readable, accessible dialogs for short inputs and local notes."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.widgets import ComboBox, label


class EntryDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        field: str,
        hint: str,
        *,
        initial: str = "",
        multiline: bool = False,
        maximum: int | None = None,
        action: str = "Save",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(480 if not multiline else 600, 290 if not multiline else 430)
        self.resize(560 if not multiline else 660, 310 if not multiline else 470)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(14)
        heading = label(title, "H2")
        heading.setWordWrap(True)
        root.addWidget(heading)
        description = label(hint, "Muted")
        description.setWordWrap(True)
        root.addWidget(description)
        caption = label(field, "FieldTitle")
        root.addWidget(caption)
        self.input: QLineEdit | QPlainTextEdit
        if multiline:
            self.input = QPlainTextEdit()
            self.input.setPlainText(initial)
            self.input.textChanged.connect(self._validate)
        else:
            self.input = QLineEdit(initial)
            if maximum is not None:
                self.input.setMaxLength(maximum)
            self.input.textChanged.connect(self._validate)
        self.input.setAccessibleName(field)
        caption.setBuddy(self.input)
        root.addWidget(self.input, 1 if multiline else 0)
        self.feedback = QLabel()
        self.feedback.setObjectName("Caption")
        root.addWidget(self.feedback)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.setMinimumHeight(44)
        self.save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText(tr(action))
        self.save_button.setObjectName("Primary")
        self.save_button.setDefault(True)
        if isinstance(self.input, QLineEdit):
            self.input.returnPressed.connect(self._accept_if_valid)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons, 0, Qt.AlignmentFlag.AlignRight)
        self._validate()
        self.input.setFocus()

    def _accept_if_valid(self) -> None:
        if self.save_button.isEnabled():
            self.accept()

    def value(self) -> str:
        return (
            self.input.toPlainText().strip()
            if isinstance(self.input, QPlainTextEdit)
            else self.input.text().strip()
        )

    def _validate(self) -> None:
        value = self.value()
        valid = bool(value) and not any(
            (ord(char) < 32 and (not isinstance(self.input, QPlainTextEdit) or char not in "\n\t"))
            or ord(char) == 127
            for char in value
        )
        self.save_button.setEnabled(valid)
        self.feedback.setText(
            "" if valid or not value else tr("Use text without control characters.")
        )


def prompt_text(
    parent: QWidget,
    title: str,
    field: str,
    hint: str,
    *,
    initial: str = "",
    multiline: bool = False,
    maximum: int | None = None,
    action: str = "Save",
) -> str | None:
    dialog = EntryDialog(
        parent,
        title,
        field,
        hint,
        initial=initial,
        multiline=multiline,
        maximum=maximum,
        action=action,
    )
    return dialog.value() if dialog.exec() == QDialog.DialogCode.Accepted else None


class ChoiceDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, field: str, hint: str, items: list[str]):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(520, 270)
        self.resize(600, 290)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 24)
        root.setSpacing(14)
        heading = label(title, "H2")
        heading.setWordWrap(True)
        root.addWidget(heading)
        explanation = label(hint, "Muted")
        explanation.setWordWrap(True)
        root.addWidget(explanation)
        caption = label(field, "FieldTitle")
        root.addWidget(caption)
        self.choices = ComboBox()
        self.choices.addItems(items)
        self.choices.setAccessibleName(field)
        caption.setBuddy(self.choices)
        root.addWidget(self.choices)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setMinimumHeight(44)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Continue"))
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("Primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons, 0, Qt.AlignmentFlag.AlignRight)
        self.choices.setFocus()


def choose_item(parent: QWidget, title: str, field: str, hint: str, items: list[str]) -> int | None:
    dialog = ChoiceDialog(parent, title, field, hint, items)
    return dialog.choices.currentIndex() if dialog.exec() == QDialog.DialogCode.Accepted else None
