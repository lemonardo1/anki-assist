from __future__ import annotations

from aqt.qt import QKeyEvent, QPlainTextEdit, Qt, pyqtSignal


class SubmitTextEdit(QPlainTextEdit):
    """Plain-text editor that submits on the platform's primary shortcut key."""

    submit_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        # Qt maps portable Control to Command on macOS.
        is_primary = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if is_enter and is_primary:
            event.accept()
            self.submit_requested.emit()
            return
        super().keyPressEvent(event)
