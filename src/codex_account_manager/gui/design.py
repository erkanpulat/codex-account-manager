"""Design tokens and a small icon factory.

A single source of truth for colors, spacing and typography keeps the UI
consistent. Icons are drawn with QPainter so the app needs no image assets and
stays crisp at any DPI.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    primary: str
    primary_hover: str
    on_primary: str
    success: str
    warning: str
    danger: str
    track: str


DARK = Palette(
    bg="#0e1525",
    surface="#151f32",
    surface_alt="#1e2c43",
    border="#2b3b55",
    text="#edf3ff",
    muted="#b1bfd4",
    primary="#8ab8ff",
    primary_hover="#adcfff",
    on_primary="#0e2345",
    success="#3ecf8e",
    warning="#e6a23c",
    danger="#f06a75",
    track="#2b3b55",
)

LIGHT = Palette(
    bg="#f3f6fb",
    surface="#ffffff",
    surface_alt="#e9eff9",
    border="#d3dded",
    text="#151f32",
    muted="#52627a",
    primary="#245dc5",
    primary_hover="#174aab",
    on_primary="#ffffff",
    success="#23734b",
    warning="#8b570c",
    danger="#b63143",
    track="#dde6f3",
)

# 8px spacing scale.
SPACE = (0, 4, 8, 12, 16, 24, 32, 48)
RADIUS = 12


def usage_color(palette: Palette, percent: float | None) -> str:
    if percent is None:
        return palette.muted
    if percent >= 90:
        return palette.danger
    if percent >= 70:
        return palette.warning
    return palette.primary


def make_icon(name: str, color: str, size: int = 20) -> QIcon:
    """Render a named glyph into a QIcon using QPainter (no asset files)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(size * 0.11)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = size
    m = s * 0.2  # margin

    if name == "dashboard":
        p.drawRoundedRect(QRectF(m, m, s * 0.25, s * 0.25), 2, 2)
        p.drawRoundedRect(QRectF(s * 0.55, m, s * 0.25, s * 0.25), 2, 2)
        p.drawRoundedRect(QRectF(m, s * 0.55, s * 0.25, s * 0.25), 2, 2)
        p.drawRoundedRect(QRectF(s * 0.55, s * 0.55, s * 0.25, s * 0.25), 2, 2)
    elif name == "continuity":
        path = QPainterPath()
        path.moveTo(m, s * 0.5)
        path.cubicTo(s * 0.35, m, s * 0.65, s - m, s - m, s * 0.5)
        p.drawPath(path)
    elif name == "accounts":
        p.drawEllipse(QRectF(s * 0.32, m, s * 0.36, s * 0.36))
        path = QPainterPath()
        path.moveTo(m, s - m)
        path.cubicTo(s * 0.2, s * 0.55, s * 0.8, s * 0.55, s - m, s - m)
        p.drawPath(path)
    elif name == "goals":
        p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))
        p.drawEllipse(QRectF(s * 0.38, s * 0.38, s * 0.24, s * 0.24))
    elif name == "diagnostics":
        p.drawEllipse(QRectF(m, m, s * 0.5, s * 0.5))
        p.drawLine(int(s * 0.58), int(s * 0.58), int(s - m), int(s - m))
    elif name == "settings":
        p.drawEllipse(QRectF(s * 0.36, s * 0.36, s * 0.28, s * 0.28))
        for angle in range(0, 360, 45):
            import math

            rad = math.radians(angle)
            cx, cy = s / 2, s / 2
            x1 = cx + math.cos(rad) * s * 0.28
            y1 = cy + math.sin(rad) * s * 0.28
            x2 = cx + math.cos(rad) * s * 0.4
            y2 = cy + math.sin(rad) * s * 0.4
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
    elif name == "refresh":
        rect = QRectF(m, m, s - 2 * m, s - 2 * m)
        p.drawArc(rect, 60 * 16, 260 * 16)
    elif name == "about":
        p.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))
        p.drawPoint(int(s * 0.5), int(s * 0.35))
        p.drawLine(int(s * 0.5), int(s * 0.48), int(s * 0.5), int(s * 0.7))
    elif name == "logo":
        p.drawRoundedRect(QRectF(m, m, s - 2 * m, s - 2 * m), 3, 3)
        p.drawLine(int(s * 0.36), int(s * 0.5), int(s * 0.46), int(s * 0.6))
        p.drawLine(int(s * 0.46), int(s * 0.6), int(s * 0.66), int(s * 0.4))
    p.end()
    return QIcon(pix)


def app_icon(size: int = 64) -> QIcon:
    """Two account tiles joined by a path, drawn identically at every resolution."""
    from PySide6.QtGui import QLinearGradient

    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size / 64, size / 64)
    gradient = QLinearGradient(4, 4, 60, 60)
    gradient.setColorAt(0, QColor("#619cff"))
    gradient.setColorAt(1, QColor("#315bcc"))
    p.setBrush(gradient)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 16, 16)
    p.setBrush(QColor("#dceaff"))
    p.drawRoundedRect(QRectF(12, 13, 24, 27), 7, 7)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(28, 26, 24, 27), 7, 7)
    p.setBrush(QColor("#315bcc"))
    p.drawEllipse(QRectF(19, 19, 9, 9))
    p.drawRoundedRect(QRectF(17, 30, 13, 5), 2, 2)
    p.drawEllipse(QRectF(35, 32, 9, 9))
    p.drawRoundedRect(QRectF(33, 43, 13, 5), 2, 2)
    p.end()
    return QIcon(pix)
