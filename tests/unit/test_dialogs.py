"""Desktop input dialogs remain usable at common display sizes."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPlainTextEdit, QWidget

from codex_account_manager.gui.dialogs import ChoiceDialog, EntryDialog, choose_item, prompt_text


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle("Fusion")
    return instance


def test_short_entry_size_validation_and_initial_value(app):
    parent = QWidget()
    dialog = EntryDialog(parent, "Add account", "Account name", "A name you recognize.", maximum=64)
    assert dialog.minimumWidth() >= 480
    assert dialog.minimumHeight() >= 220
    assert not dialog.save_button.isEnabled()
    assert isinstance(dialog.input, QLineEdit)
    dialog.input.setText("  Personal  ")
    assert dialog.save_button.isEnabled()
    assert dialog.value() == "Personal"
    dialog.input.returnPressed.emit()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.input.setText("bad\x7fvalue")
    assert not dialog.save_button.isEnabled()
    dialog.close()


def test_multiline_note_accepts_paragraphs(app):
    parent = QWidget()
    dialog = EntryDialog(parent, "Local goal note", "Objective", "Local only.", multiline=True)
    assert dialog.minimumWidth() >= 600
    assert dialog.minimumHeight() >= 350
    assert isinstance(dialog.input, QPlainTextEdit)
    dialog.input.setPlainText("First step\nSecond step")
    assert dialog.save_button.isEnabled()
    assert dialog.value() == "First step\nSecond step"
    dialog.close()


def test_text_prompt_confirm_and_cancel(app, monkeypatch):
    original = EntryDialog.exec

    def accept(self):
        self.input.setText("Work")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(EntryDialog, "exec", accept)
    assert prompt_text(QWidget(), "Account", "Name", "Hint") == "Work"
    monkeypatch.setattr(EntryDialog, "exec", lambda _self: QDialog.DialogCode.Rejected)
    assert prompt_text(QWidget(), "Account", "Name", "Hint") is None
    monkeypatch.setattr(EntryDialog, "exec", original)


def test_choice_dialog_returns_index_for_duplicate_titles(app, monkeypatch):
    parent = QWidget()
    dialog = ChoiceDialog(parent, "Save note", "Conversation", "Pick one.", ["Same", "Same"])
    assert dialog.minimumWidth() >= 520
    dialog.choices.setCurrentIndex(1)
    assert dialog.choices.currentIndex() == 1
    dialog.close()

    def accept(self):
        self.choices.setCurrentIndex(1)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ChoiceDialog, "exec", accept)
    assert choose_item(QWidget(), "Save note", "Conversation", "Pick one.", ["Same", "Same"]) == 1
