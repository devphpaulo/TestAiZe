"""Theme for the capture controls. Drawing colors belong to the evidence."""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class CapturePalette:
    card: str
    text: str
    muted: str
    border: str
    field: str
    primary: str
    success: str

    def stylesheet(self) -> str:
        return f"""
            QWidget {{ background: {self.card}; color: {self.text}; font-family: "Inter", "Segoe UI"; }}
            QLabel#muted {{ color: {self.muted}; }}
            QFrame#currentBox, QListWidget, QPlainTextEdit, QLineEdit {{
                background: {self.field}; color: {self.text}; border: 1px solid {self.border};
                border-radius: 10px; padding: 6px;
                selection-background-color: {self.primary}; selection-color: white;
            }}
            QPlainTextEdit {{ border-radius: 12px; }}
            QPushButton {{
                background: {self.card}; color: {self.text}; border: 1px solid {self.border};
                border-radius: 9px; padding: 6px;
            }}
            QPushButton:hover, QListWidget::item:hover {{ background: {self.field}; }}
            QPushButton:checked {{ background: {self.field}; border-color: {self.primary}; }}
            QPushButton[primary="true"] {{ background: {self.primary}; color: white; }}
            QPushButton:disabled {{ background: {self.field}; color: {self.muted}; }}
            QPushButton:focus, QPlainTextEdit:focus, QLineEdit:focus, QListWidget:focus {{
                border-color: {self.primary};
            }}
            QToolTip {{ background: {self.card}; color: {self.text}; border: 1px solid {self.border}; padding: 4px; }}
        """


def capture_palette() -> CapturePalette:
    if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark:
        return CapturePalette("#111114", "#fafafa", "#a1a1aa", "#27272a", "#18181b", "#8b7dff", "#4ade80")
    return CapturePalette("#ffffff", "#0a0a0b", "#71717a", "#e4e4e7", "#f4f4f5", "#6d5dfc", "#16a34a")
