"""CLI detection and an explicit install action shared by setup and settings."""

import asyncio
import time

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from codex_account_manager.codex.setup import DOCS_URL, cli_version, install_cli
from codex_account_manager.gui.i18n import tr
from codex_account_manager.gui.widgets import label


class CliSetup(QWidget):
    ready = Signal(bool)
    stage_changed = Signal(str)

    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        self.busy = False
        self.installing = False
        self.setObjectName("GridHost")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        card = QFrame()
        card.setObjectName("SetupCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        glyph = label("›_", "CliIcon")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setFixedSize(68, 68)
        heading.addWidget(glyph)
        heading_text = QVBoxLayout()
        heading_text.addWidget(label(tr("Codex CLI"), "SetupCardTitle"))
        self.status = label(tr("Checking Codex CLI…"), "CliStatus")
        self.status.setWordWrap(True)
        heading_text.addWidget(self.status)
        heading.addLayout(heading_text, 1)
        layout.addLayout(heading)
        description = label(
            tr(
                "Python is included in the Windows package. Codex CLI connects this app to your accounts and conversations. Existing CLI installations are preserved."
            ),
            "Body",
        )
        description.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setObjectName("CliProgress")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)
        self.progress.setAccessibleName(tr("Codex CLI setup progress"))
        layout.addWidget(self.progress)
        self.elapsed = label("", "Caption")
        layout.addWidget(self.elapsed)
        self.phases = []
        self.phase_rows = []
        for title in ("Download installer", "Install Codex CLI", "Verify version"):
            phase_row = QFrame()
            phase_row.setObjectName("SetupPhaseRow")
            phase_layout = QHBoxLayout(phase_row)
            phase_layout.setContentsMargins(0, 18, 0, 12)
            phase_layout.setSpacing(22)
            marker = label("○", "SetupPhaseMark")
            marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
            marker.setFixedSize(38, 38)
            text_layout = QVBoxLayout()
            phase = label(tr(title), "FieldTitle")
            phase.setWordWrap(True)
            detail = label("", "Caption")
            detail.setWordWrap(True)
            text_layout.addWidget(phase)
            text_layout.addWidget(detail)
            phase_layout.addWidget(marker)
            phase_layout.addLayout(text_layout, 1)
            layout.addWidget(phase_row)
            self.phases.append(phase)
            self.phase_rows.append((phase_row, marker, detail))
        self.stage_changed.connect(self._stage)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.started_at = 0.0
        row = QHBoxLayout()
        self.install = QPushButton(tr("Install Codex CLI"))
        self.install.setObjectName("Primary")
        self.install.hide()
        self.install.clicked.connect(self._install)
        self.check = QPushButton(tr("Check again"))
        self.check.clicked.connect(self.refresh)
        guide = QPushButton(tr("Official installation guide"))
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DOCS_URL)))
        for button in (self.install, self.check, guide):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        outer.addWidget(card)
        info = QFrame()
        info.setObjectName("SetupCard")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(20, 16, 20, 16)
        info_layout.addWidget(description)
        outer.addWidget(info)
        self.guide = guide
        self.refresh()

    def _working(self, busy):
        self.busy = busy
        self.check.setEnabled(not busy)
        self.install.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.elapsed.setVisible(busy)
        for row, _marker, _detail in self.phase_rows:
            row.setVisible(self.installing)
        if busy:
            self.ready.emit(False)
            self.started_at = time.monotonic()
            self.timer.start()
            self._tick()
        else:
            self.timer.stop()
        self.check.setVisible(not self.installing)
        if self.installing:
            self.install.hide()

    def _tick(self):
        seconds = max(0, int(time.monotonic() - self.started_at))
        self.elapsed.setText(
            tr("Elapsed time: {time}", time=f"{seconds // 60:02}:{seconds % 60:02}")
        )

    def _stage(self, stage):
        if not self.installing or stage not in ("download", "install", "verify"):
            return
        index = ("download", "install", "verify").index(stage)
        self.status.setText(
            tr(
                (
                    "Downloading the official installer…",
                    "Installing Codex CLI… This may take a few minutes.",
                    "Verifying Codex CLI…",
                )[index]
            )
        )
        titles = (
            ("Installer download pending", "Downloading installer", "Installer downloaded"),
            ("CLI installation pending", "Installing CLI", "CLI installed"),
            ("Version verification pending", "Verifying version", "Version verified"),
        )
        details = (
            "Download the official Windows installer.",
            "The installer downloads and installs Codex CLI. Please wait.",
            "Check that the installed CLI starts correctly.",
        )
        for number, (phase, choices, detail) in enumerate(
            zip(self.phases, titles, details, strict=True)
        ):
            title = choices[2 if number < index else 1 if number == index else 0]
            phase.setText(tr(title))
            _row, marker, description = self.phase_rows[number]
            description.setText(tr(detail))
            marker.setText("✓" if number < index else "◌" if number == index else "○")
            marker.setProperty(
                "state", "done" if number < index else "current" if number == index else "pending"
            )
            marker.style().unpolish(marker)
            marker.style().polish(marker)

    def refresh(self):
        if self.busy:
            return
        self.status.setText(tr("Checking Codex CLI…"))
        self._working(True)
        self.runner.submit(asyncio.to_thread(cli_version), self._checked, self._failed)

    def _checked(self, version):
        self.installing = False
        self._working(False)
        self.install.setVisible(version is None)
        self.status.setText(
            tr("Codex CLI {version} is ready.", version=version)
            if version
            else tr("Codex CLI is required. Install it to connect your accounts.")
        )
        self.ready.emit(bool(version))

    def _install(self):
        if self.busy:
            return
        if (
            QMessageBox.question(
                self,
                tr("Install Codex CLI"),
                tr(
                    "Download and run OpenAI's official Windows installer? It installs Codex CLI for your Windows user and adds its folder to your user PATH. Node.js is not required. No account sign-in or model task will be started."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.installing = True
        self._working(True)
        self.ready.emit(False)
        self._stage("download")
        self.runner.submit(
            asyncio.to_thread(install_cli, self.stage_changed.emit), self._checked, self._failed
        )

    def _failed(self, error):
        was_installing = self.installing
        self.installing = False
        self._working(False)
        self.status.setText(tr(str(error)))
        if was_installing:
            self.install.setVisible(True)
        self.ready.emit(False)
