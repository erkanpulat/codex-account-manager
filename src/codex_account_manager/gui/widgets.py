"""Reusable presentation widgets for account health and capacity."""

from __future__ import annotations

import math
from datetime import datetime

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.domain.models import ProfileHealth
from codex_account_manager.domain.states import QuotaState
from codex_account_manager.gui.design import DARK, Palette, usage_color
from codex_account_manager.gui.i18n import tr


def label(text: str = "", role: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setObjectName(role)
    return widget


class ComboBox(QComboBox):
    """Keep the dropdown affordance visible with both application palettes."""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.palette().buttonText().color(), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        x, y = self.width() - 15, self.height() / 2
        painter.drawPolyline([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)])
        painter.end()


def _fmt_reset(value: int | None) -> str:
    if value is None:
        return tr("Unknown")
    try:
        return datetime.fromtimestamp(value).astimezone().strftime("%d.%m.%Y %H:%M")
    except (OSError, OverflowError, ValueError):
        return tr("Unknown")


class Pill(QLabel):
    def __init__(self, text: str = "", tone: str = "muted"):
        super().__init__(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("tone", tone)


class UsageBar(QWidget):
    def __init__(self, title: str, palette: Palette = DARK):
        super().__init__()
        self._palette = palette
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(label(title, "Muted"))
        self._value = label(tr("Unknown"))
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(self._value)
        layout.addLayout(row)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        layout.addWidget(self._bar)

    def set_usage(self, percent: float | None) -> None:
        if percent is not None and not math.isfinite(percent):
            percent = None
        value = max(0, min(100, round(percent))) if percent is not None else 0
        self._bar.setValue(value)
        self._value.setText(tr("Unknown") if percent is None else tr("{value}% used", value=value))
        color = usage_color(self._palette, percent)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: {self._palette.track}; border: none; border-radius: 3px; }} QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )


class AccountCard(QFrame):
    switch_requested = Signal(str)

    def __init__(self, health: ProfileHealth, palette: Palette = DARK):
        super().__init__()
        self.setObjectName("Card")
        self.setProperty("active", "true" if health.is_active else "false")
        self.alias = health.alias
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)
        header = QHBoxLayout()
        avatar = label(health.alias[:2].upper(), "Avatar")
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(avatar)
        identity = QVBoxLayout()
        name = label(health.alias, "H2")
        name.setWordWrap(True)
        name.setMinimumHeight(30)
        identity.addWidget(name)
        plan = label((health.plan_type or tr("Unknown plan")).capitalize(), "Muted")
        plan.setMinimumHeight(24)
        identity.addWidget(plan)
        header.addLayout(identity, 1)
        if health.error:
            state, tone = tr("ERROR"), "danger"
        elif not health.auth_present:
            state, tone = tr("SIGN IN"), "warning"
        elif health.account_match is not True:
            state, tone = (
                tr("UNBOUND") if health.account_match is None else tr("MISMATCH"),
                "warning",
            )
        elif health.is_active:
            state, tone = tr("ACTIVE"), "primary"
        elif health.quota_state in {QuotaState.LIMITED_NO_RESET, QuotaState.LIMITED_WITH_RESET}:
            state, tone = tr("LIMITED"), "warning"
        elif health.quota_state == QuotaState.AVAILABLE:
            state, tone = tr("READY"), "success"
        else:
            state, tone = tr("UNKNOWN"), "muted"
        header.addWidget(Pill(state, tone), 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)
        self._primary_usage = UsageBar(tr("Primary window"), palette)
        self._secondary_usage = UsageBar(tr("Secondary window"), palette)
        self._primary_usage.set_usage(health.primary_used_percent)
        self._secondary_usage.set_usage(health.secondary_used_percent)
        root.addWidget(self._primary_usage)
        root.addWidget(self._secondary_usage)
        reset = label(
            tr(
                "Scheduled renewals (local time)\nPrimary quota: {primary}\nSecondary quota: {secondary}",
                primary=_fmt_reset(health.primary_resets_at),
                secondary=_fmt_reset(health.secondary_resets_at),
            ),
            "Caption",
        )
        reset.setWordWrap(True)
        root.addWidget(reset)
        credits = health.reset_credits
        credit_button = QPushButton(
            tr("Reset credits: unavailable")
            if credits is None
            else tr("Reset credits: {count} available", count=credits.available_count)
        )
        credit_button.setObjectName("Secondary")
        credit_button.setEnabled(credits is not None)
        credit_button.clicked.connect(lambda: self._show_reset_credits(health))
        root.addWidget(credit_button)
        footer = QHBoxLayout()
        detail = label(
            tr("Current workspace account")
            if health.is_active
            else tr("Identity verified")
            if health.account_match
            else tr("Sign in and bind in Accounts"),
            "Muted",
        )
        detail.setWordWrap(True)
        footer.addWidget(detail, 1)
        self._switch_btn = QPushButton(
            tr("Active account") if health.is_active else tr("Switch account")
        )
        self._switch_btn.setObjectName("Primary" if not health.is_active else "Secondary")
        self._switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._switch_btn.setEnabled(
            not health.is_active
            and health.auth_present
            and health.account_match is True
            and not health.error
        )
        self._switch_btn.clicked.connect(lambda: self.switch_requested.emit(self.alias))
        footer.addWidget(self._switch_btn)
        root.addLayout(footer)
        if health.error:
            self.setToolTip(health.error)

    def _show_reset_credits(self, health: ProfileHealth) -> None:
        credits = health.reset_credits
        if credits is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Usage reset credits"))
        dialog.resize(640, 480)
        dialog.setMinimumSize(420, 320)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        lines = [
            health.alias,
            tr("Reset credits: {count} available", count=credits.available_count),
            tr("These are separate from scheduled quota renewals. No credit is used here."),
            tr(
                "Last checked: {time}",
                time=health.last_checked_at.astimezone().strftime("%d.%m.%Y %H:%M %Z")
                if health.last_checked_at
                else tr("Unknown"),
            ),
        ]
        if credits.credits is None:
            lines.append(tr("Credit details are unavailable."))
        elif not credits.credits:
            lines.append(tr("No credit details returned."))
        else:
            for credit in credits.credits:
                state = {
                    "available": tr("Available"),
                    "redeeming": tr("Being redeemed"),
                    "redeemed": tr("Redeemed"),
                }.get(credit.status, tr("Unknown"))
                if (
                    credit.status == "available"
                    and credit.expires_at is not None
                    and credit.expires_at <= datetime.now().timestamp()
                ):
                    state = tr("Expired; refresh usage")
                lines.extend(
                    [
                        "",
                        credit.title or tr("Usage reset credit"),
                        tr("Status: {value}", value=state),
                        tr(
                            "Scope: {value}",
                            value=tr("Codex usage limits")
                            if credit.reset_type == "codexRateLimits"
                            else tr("Unknown"),
                        ),
                        tr("Granted: {time}", time=_fmt_reset(credit.granted_at)),
                        tr(
                            "Expires: {time}",
                            time=_fmt_reset(credit.expires_at)
                            if credit.expires_at is not None
                            else tr("No expiry"),
                        ),
                    ]
                )
                if credit.description:
                    lines.append(credit.description)
            if len(credits.credits) < credits.available_count:
                lines.append(tr("The server returned details for only some credits."))
        lines.extend(
            [
                "",
                tr(
                    "To redeem a credit, open the matching account in Codex and review its usage settings. Times use your local timezone."
                ),
            ]
        )
        text.setPlainText("\n".join(lines))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
