from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ..paths import asset_path


_WINDOW_CONTROL_ASSETS = {
    "minimize": {
        "dark": "ui/win-minimize-dark.svg",
        "light": "ui/win-minimize-light.svg",
    },
    "maximize": {
        "dark": "ui/win-maximize-dark.svg",
        "light": "ui/win-maximize-light.svg",
    },
    "restore": {
        "dark": "ui/win-restore-dark.svg",
        "light": "ui/win-restore-light.svg",
    },
    "close": {
        "dark": "ui/win-close-dark.svg",
        "light": "ui/win-close-light.svg",
    },
}


def window_control_icon(role: str, theme_mode: str) -> QIcon:
    mode = "light" if theme_mode == "light" else "dark"
    relative_path = _WINDOW_CONTROL_ASSETS.get(role, {}).get(mode)
    if not relative_path:
        return QIcon()
    icon_path = asset_path(relative_path)
    if not isinstance(icon_path, Path) or not icon_path.exists():
        return QIcon()
    return QIcon(str(icon_path))


def make_icon(name: str, color: str, size: int = 18, theme_mode: str = "dark") -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    is_blueprint = theme_mode == "blueprint"
    
    if is_blueprint:
        # Blueprint style: white outlines, no fills, thin lines
        base_color = QColor("#ffffff")
        pen = QPen(base_color, max(1.0, size / 32.0))  # Very thin white lines
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)  # No fill
    else:
        # Original style
        base_color = QColor(color)
        pen = QPen(base_color)  
        pen.setWidthF(max(2.4, size / 8.0))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        
        fill_color = QColor(base_color)
        fill_color.setAlpha(65)
        painter.setBrush(fill_color)

    if name == "reports":
        _draw_reports(painter, size)
    elif name == "vip":
        _draw_vip(painter, size)
    elif name == "binds":
        _draw_binds(painter, size)
    elif name == "optimize":
        _draw_optimize(painter, size)
    elif name == "settings":
        _draw_settings(painter, size)
    elif name == "send":
        _draw_send(painter, size)
    elif name == "teleport":
        _draw_teleport(painter, size)
    elif name == "users":
        _draw_users(painter, size)
    elif name == "spark":
        _draw_spark(painter, size)
    elif name == "trash":
        _draw_trash(painter, size)
    else:
        _draw_dot(painter, size)

    painter.end()
    return QIcon(pixmap)


def _draw_reports(painter: QPainter, size: int) -> None:
    bubble = QPainterPath()
    bubble.addRoundedRect(QRectF(size * 0.12, size * 0.16, size * 0.76, size * 0.56), 4, 4)
    tail = QPainterPath()
    tail.moveTo(size * 0.36, size * 0.70)
    tail.lineTo(size * 0.28, size * 0.88)
    tail.lineTo(size * 0.50, size * 0.72)
    painter.drawPath(bubble)
    painter.drawPath(tail)
    painter.drawLine(QPointF(size * 0.28, size * 0.34), QPointF(size * 0.72, size * 0.34))
    painter.drawLine(QPointF(size * 0.28, size * 0.54), QPointF(size * 0.58, size * 0.54))


def _draw_vip(painter: QPainter, size: int) -> None:
    shield = QPainterPath()
    shield.moveTo(size * 0.50, size * 0.10)
    shield.lineTo(size * 0.80, size * 0.22)
    shield.lineTo(size * 0.76, size * 0.58)
    shield.cubicTo(size * 0.72, size * 0.78, size * 0.58, size * 0.88, size * 0.50, size * 0.94)
    shield.cubicTo(size * 0.42, size * 0.88, size * 0.28, size * 0.78, size * 0.24, size * 0.58)
    shield.lineTo(size * 0.20, size * 0.22)
    shield.closeSubpath()
    painter.drawPath(shield)
    painter.drawLine(QPointF(size * 0.50, size * 0.32), QPointF(size * 0.50, size * 0.54))
    painter.drawPoint(QPointF(size * 0.50, size * 0.74))


def _draw_binds(painter: QPainter, size: int) -> None:
    painter.drawRoundedRect(QRectF(size * 0.12, size * 0.24, size * 0.76, size * 0.46), 3, 3)
    for row in range(2):
        for col in range(4):
            x = size * (0.21 + col * 0.14)
            y = size * (0.34 + row * 0.15)
            painter.drawRoundedRect(QRectF(x, y, size * 0.08, size * 0.06), 1.5, 1.5)
    painter.drawLine(QPointF(size * 0.28, size * 0.78), QPointF(size * 0.72, size * 0.78))


def _draw_optimize(painter: QPainter, size: int) -> None:
    arc_rect = QRectF(size * 0.18, size * 0.24, size * 0.64, size * 0.64)
    painter.drawArc(arc_rect, 30 * 16, 120 * 16)
    painter.drawArc(arc_rect, 210 * 16, 120 * 16)
    painter.drawLine(QPointF(size * 0.50, size * 0.56), QPointF(size * 0.70, size * 0.38))
    painter.drawPoint(QPointF(size * 0.50, size * 0.56))


def _draw_settings(painter: QPainter, size: int) -> None:
    center = QPointF(size * 0.50, size * 0.50)
    painter.drawEllipse(center, size * 0.16, size * 0.16)
    for dx, dy in (
        (0.0, -0.30),
        (0.22, -0.22),
        (0.30, 0.0),
        (0.22, 0.22),
        (0.0, 0.30),
        (-0.22, 0.22),
        (-0.30, 0.0),
        (-0.22, -0.22),
    ):
        start = QPointF(size * (0.50 + dx * 0.72), size * (0.50 + dy * 0.72))
        end = QPointF(size * (0.50 + dx), size * (0.50 + dy))
        painter.drawLine(start, end)


def _draw_send(painter: QPainter, size: int) -> None:
    path = QPainterPath()
    path.moveTo(size * 0.12, size * 0.48)
    path.lineTo(size * 0.88, size * 0.12)
    path.lineTo(size * 0.68, size * 0.88)
    path.lineTo(size * 0.48, size * 0.58)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(size * 0.48, size * 0.58), QPointF(size * 0.88, size * 0.12))


def _draw_teleport(painter: QPainter, size: int) -> None:
    painter.drawEllipse(QPointF(size * 0.50, size * 0.50), size * 0.22, size * 0.22)
    painter.drawLine(QPointF(size * 0.50, size * 0.10), QPointF(size * 0.50, size * 0.28))
    painter.drawLine(QPointF(size * 0.50, size * 0.72), QPointF(size * 0.50, size * 0.90))
    painter.drawLine(QPointF(size * 0.10, size * 0.50), QPointF(size * 0.28, size * 0.50))
    painter.drawLine(QPointF(size * 0.72, size * 0.50), QPointF(size * 0.90, size * 0.50))


def _draw_users(painter: QPainter, size: int) -> None:
    painter.drawEllipse(QRectF(size * 0.20, size * 0.18, size * 0.20, size * 0.20))
    painter.drawEllipse(QRectF(size * 0.54, size * 0.18, size * 0.20, size * 0.20))
    painter.drawArc(QRectF(size * 0.14, size * 0.38, size * 0.34, size * 0.28), 0, 180 * 16)
    painter.drawArc(QRectF(size * 0.48, size * 0.38, size * 0.34, size * 0.28), 0, 180 * 16)


def _draw_spark(painter: QPainter, size: int) -> None:
    path = QPainterPath()
    path.moveTo(size * 0.50, size * 0.10)
    path.lineTo(size * 0.60, size * 0.40)
    path.lineTo(size * 0.90, size * 0.50)
    path.lineTo(size * 0.60, size * 0.60)
    path.lineTo(size * 0.50, size * 0.90)
    path.lineTo(size * 0.40, size * 0.60)
    path.lineTo(size * 0.10, size * 0.50)
    path.lineTo(size * 0.40, size * 0.40)
    path.closeSubpath()
    painter.drawPath(path)


def _draw_trash(painter: QPainter, size: int) -> None:
    painter.drawLine(QPointF(size * 0.26, size * 0.26), QPointF(size * 0.74, size * 0.26))
    painter.drawRoundedRect(QRectF(size * 0.30, size * 0.32, size * 0.40, size * 0.48), 2, 2)
    painter.drawLine(QPointF(size * 0.42, size * 0.42), QPointF(size * 0.42, size * 0.70))
    painter.drawLine(QPointF(size * 0.58, size * 0.42), QPointF(size * 0.58, size * 0.70))


def _draw_dot(painter: QPainter, size: int) -> None:
    painter.drawEllipse(QPointF(size * 0.50, size * 0.50), size * 0.14, size * 0.14)
