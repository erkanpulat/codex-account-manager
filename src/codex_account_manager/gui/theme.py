"""Qt stylesheet generated from the design palette (dark/light)."""

from __future__ import annotations

from codex_account_manager.gui.design import DARK, LIGHT, RADIUS, Palette


def _sheet(p: Palette) -> str:
    return f"""
* {{
    font-family: 'Segoe UI';
    font-size: 16px;
    color: {p.text};
}}
QMainWindow, QDialog, QMessageBox {{ background: {p.bg}; }}
QWidget#Root {{ background: {p.bg}; }}
QWidget#Sidebar {{ background: {p.surface}; border-right: 1px solid {p.border}; }}
QWidget#Content, QWidget#GridHost {{ background: {p.bg}; }}

QLabel#H1 {{ font-size: 28px; font-weight: 700; }}
QLabel#H2 {{ font-size: 18px; font-weight: 600; }}
QLabel#Muted {{ color: {p.muted}; }}
QLabel#Caption {{ color: {p.muted}; font-size: 13px; }}
QLabel#FieldTitle {{ font-size: 16px; font-weight: 600; }}
QLabel#Section {{ color: {p.muted}; font-size: 13px; font-weight: 600; }}
QFrame#SettingRow {{ border-bottom: 1px solid {p.border}; }}
QPushButton::menu-indicator {{ subcontrol-position: right center; right: 8px; }}
QPushButton#MenuButton {{ padding-right: 28px; }}
QPushButton:open {{ border-color: {p.primary}; }}

QLabel#Body {{ font-size: 16px; color: {p.muted}; }}
QLabel#Step {{ font-size: 23px; font-weight: 700; color: {p.primary}; }}
QFrame#Guide {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 16px; }}
QLabel#Eyebrow {{ color: {p.muted}; font-size: 12px; font-weight: 600; letter-spacing: 0.6px; }}
QLabel#HeroTitle {{ font-size: 24px; font-weight: 600; }}
QLabel#Accent {{ color: {p.primary}; font-size: 14px; }}
QFrame#Hero {{ background: {p.surface}; border: 1px solid {p.border}; border-left: 3px solid {p.primary}; border-radius: 12px; }}
QFrame#Empty {{ background: {p.surface}; border: 1px dashed {p.border}; border-radius: 12px; }}
QLabel#Avatar {{ background: {p.surface_alt}; color: {p.primary}; border: 1px solid {p.border}; border-radius: 12px; font-size: 18px; font-weight: 600; }}
QLabel#Pill {{ border: 1px solid {p.border}; border-radius: 10px; padding: 3px 9px; font-size: 12px; font-weight: 600; }}
QLabel#Pill[tone="success"] {{ color: {p.success}; }}
QLabel#Pill[tone="warning"] {{ color: {p.warning}; }}
QLabel#Pill[tone="danger"] {{ color: {p.danger}; }}
QLabel#Pill[tone="primary"] {{ color: {p.primary}; }}
QLabel#Pill[tone="muted"] {{ color: {p.muted}; }}
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; padding: 6px; }}
QMenu::item {{ padding: 8px 24px; }}
QMenu::item:selected {{ background: {p.surface_alt}; }}
QLabel#Brand {{ font-size: 17px; font-weight: 700; letter-spacing: 0.3px; }}

QPushButton {{
    background: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 8px 14px;
    min-height: 22px;
    color: {p.text};
}}
QPushButton:focus {{ border-color: {p.primary}; }}
QPushButton:hover {{ border-color: {p.primary}; }}
QPushButton:disabled {{ color: {p.muted}; border-color: {p.border}; }}
QPushButton#Primary {{ background: {p.primary}; border: none; color: {p.on_primary}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {p.primary_hover}; }}
QPushButton#Primary:disabled {{ background: {p.surface_alt}; color: {p.muted}; }}
QPushButton#Danger {{ color: {p.danger}; border-color: {p.border}; }}
QPushButton#Danger:hover {{ border-color: {p.danger}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {p.muted}; padding: 6px; }}
QPushButton#Ghost:hover {{ color: {p.text}; }}

QListWidget#Nav {{ background: transparent; border: none; outline: 0; padding: 6px; }}
QListWidget#Nav::item {{
    padding: 13px 12px; border-radius: 9px; color: {p.muted}; margin: 2px 6px;
}}
QListWidget#Nav::item:selected {{ background: {p.surface_alt}; color: {p.primary}; border-left: 3px solid {p.primary}; }}
QListWidget#Nav::item:hover {{ color: {p.text}; }}

QFrame#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS}px; }}
QFrame#Card[active="true"] {{ border: 1px solid {p.primary}; }}
QFrame#Panel {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS}px; }}

QProgressBar {{
    background: {p.track}; border: none; border-radius: 5px; height: 8px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ border-radius: 5px; }}

QTableWidget {{
    background: {p.surface}; gridline-color: {p.border};
    border: 1px solid {p.border}; border-radius: {RADIUS}px;
    selection-background-color: {p.surface_alt}; selection-color: {p.text};
}}
QHeaderView {{ background: {p.surface}; }}
QHeaderView::section {{
    background: {p.surface}; color: {p.muted}; border: none;
    border-bottom: 1px solid {p.border}; padding: 8px 10px; font-weight: 600;
}}
QTableWidget::item {{ padding: 6px 10px; }}
QTableCornerButton::section {{ background: {p.surface}; border: none; }}

QComboBox {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 8px; padding: 6px 24px 6px 10px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; }}
QComboBox:hover {{ border-color: {p.primary}; }}
QComboBox QAbstractItemView {{
    background: {p.surface}; border: 1px solid {p.border};
    selection-background-color: {p.surface_alt}; outline: 0;
}}
QCheckBox {{ spacing: 10px; padding: 6px 0; }}
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QPlainTextEdit {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 8px; }}
QSpinBox {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 8px; padding: 8px; }}
QLineEdit {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 8px; padding: 7px 10px; }}
QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus, QLineEdit:focus {{ border-color: {p.primary}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 5px; min-width: 30px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QStatusBar {{ background: {p.surface}; border-top: 1px solid {p.border}; color: {p.muted}; }}
QToolTip {{ background: {p.surface_alt}; color: {p.text}; border: 1px solid {p.border}; padding: 6px; }}
"""


def stylesheet(dark: bool = True) -> str:
    return _sheet(DARK if dark else LIGHT)


def application_palette(dark: bool = True):
    from PySide6.QtGui import QColor, QPalette

    colors = DARK if dark else LIGHT
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, colors.bg),
        (QPalette.ColorRole.WindowText, colors.text),
        (QPalette.ColorRole.Base, colors.surface),
        (QPalette.ColorRole.AlternateBase, colors.surface_alt),
        (QPalette.ColorRole.Text, colors.text),
        (QPalette.ColorRole.Button, colors.surface_alt),
        (QPalette.ColorRole.ButtonText, colors.text),
        (QPalette.ColorRole.Highlight, colors.primary),
        (QPalette.ColorRole.HighlightedText, colors.on_primary),
        (QPalette.ColorRole.ToolTipBase, colors.surface_alt),
        (QPalette.ColorRole.ToolTipText, colors.text),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(colors.muted))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(colors.muted)
    )
    return palette
