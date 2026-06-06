from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..models import BindConfig
from ..paths import asset_path


class OverlayWindow(QWidget):
    def __init__(self, title: str, x: int, y: int, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(title)
        icon_path = asset_path("iconka.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.move(x, y)
        self.resize(320, 260)

        layout = QVBoxLayout(self)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("title")
        layout.addWidget(self.title_label)
        self.content = QLabel("")
        self.content.setTextFormat(Qt.TextFormat.RichText)
        self.content.setWordWrap(True)
        layout.addWidget(self.content)

    def update_binds(self, binds: list[BindConfig]) -> None:
        rows = [f"<b>{bind.hotkey}</b>  {bind.name}" for bind in binds]
        self.content.setText("<br>".join(rows) or "Немає біндів")
