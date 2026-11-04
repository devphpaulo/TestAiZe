"""Local toolbar icons drawn with QtGui; no icon fonts or SVG plugin required."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def tool_icon(kind: str) -> QIcon:
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    pen = QPen(QColor("#f5f5f5"), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if kind == "crop":
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(QRectF(4, 4, 16, 16))
    elif kind == "rect":
        painter.drawRect(QRectF(4, 5, 16, 14))
    elif kind == "circle":
        painter.drawEllipse(QRectF(4, 4, 16, 16))
    elif kind in {"line", "arrow"}:
        painter.drawLine(QPointF(5, 19), QPointF(19, 5))
        if kind == "arrow":
            painter.drawLine(QPointF(11, 5), QPointF(19, 5))
            painter.drawLine(QPointF(19, 5), QPointF(19, 13))
    elif kind == "text":
        painter.drawLine(5, 5, 19, 5)
        painter.drawLine(12, 5, 12, 20)
        painter.drawLine(8, 20, 16, 20)
    elif kind == "free":
        path = QPainterPath(QPointF(4, 18))
        path.cubicTo(3, 5, 13, 3, 11, 13)
        path.cubicTo(9, 23, 19, 19, 20, 6)
        painter.drawPath(path)
    elif kind == "undo":
        path = QPainterPath(QPointF(5, 8))
        path.lineTo(13, 8)
        path.cubicTo(23, 8, 22, 20, 13, 19)
        painter.drawPath(path)
        painter.drawLine(5, 8, 9, 4)
        painter.drawLine(5, 8, 9, 12)
    else:
        painter.end()
        raise ValueError(f"Unknown toolbar icon: {kind}")
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
