"""An annotation is edited where the person clicked, inside the screen layer."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QPlainTextEdit


class InlineTextEdit(QPlainTextEdit):
    def __init__(self, host, parent) -> None:
        super().__init__(parent)
        self.host = host
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        self.setAccessibleName("Texto na imagem")
        self.setToolTip("Digite na imagem. Enter conclui; Shift+Enter cria uma linha.")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.host.cancel()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            parent = self.parentWidget()
            self.host.finish_text(self)
            parent.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        # Native tool windows can change activation while being raised. That is
        # not an instruction to finish typing; toolbar actions commit explicitly.
        if event.reason() in (Qt.FocusReason.MouseFocusReason, Qt.FocusReason.TabFocusReason,
                              Qt.FocusReason.BacktabFocusReason):
            self.host.finish_text(self)
