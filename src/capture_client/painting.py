"""Shared vector strokes for the live gesture and the exported bitmap."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from .geometry import circle_bounds


def paint_annotation(painter: QPainter, note, offset_x=0, offset_y=0, scale=1) -> None:
    if not note.points:
        return
    painter.save()
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(1 / scale, 1 / scale)
        painter.translate(-offset_x, -offset_y)
        color = QColor(note.color)
        stroke = max(1, note.stroke)
        painter.setPen(QPen(color, stroke, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        start = QPointF(*note.points[0])
        end = QPointF(*note.points[-1])
        if note.kind == "rect":
            box = QRectF(start, end).normalized()
            radius = min(3, box.width() / 4, box.height() / 4)
            painter.drawRoundedRect(box, radius, radius)
        elif note.kind == "circle":
            left, top, right, bottom = circle_bounds(note.points[0], note.points[-1])
            painter.drawEllipse(QRectF(left, top, right - left, bottom - top))
        elif note.kind in {"line", "arrow", "free"}:
            path = QPainterPath(start)
            for point in note.points[1:]:
                path.lineTo(QPointF(*point))
            painter.drawPath(path)
            if note.kind == "arrow" and start != end:
                angle = math.atan2(end.y() - start.y(), end.x() - start.x())
                length = max(16, stroke * 4)
                spread = math.radians(28)
                head = QPainterPath(end)
                for direction in (angle - spread, angle + spread):
                    head.lineTo(end.x() - length * math.cos(direction),
                                end.y() - length * math.sin(direction))
                head.closeSubpath()
                painter.setBrush(color)
                painter.setPen(QPen(color, 1, Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawPath(head)
    finally:
        painter.restore()
