from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .parser import parse_lines


class ConsoleLogWatcher(QObject):
    raw_lines_parsed = Signal(list)
    reports_parsed = Signal(list)
    replies_parsed = Signal(list)
    vip_messages_parsed = Signal(list, bool)
    status_changed = Signal(str)

    def __init__(self, path: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._logger = logging.getLogger(__name__)
        self._path = Path(path)
        self._offset = 0
        self._did_initial_poll = False
        self._last_status = ""
        self._timer = QTimer(self)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self.poll)

    def set_path(self, path: str) -> None:
        new_path = Path(path)
        if new_path != self._path:
            self._path = new_path
            self._offset = 0
            self._did_initial_poll = False
            self._last_status = ""

    def start(self) -> None:
        self._timer.start()
        self.poll()

    def poll(self) -> None:
        if not self._path.exists():
            self._emit_status(f"Лог не знайдено: {self._path}")
            return

        try:
            with self._path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                if size < self._offset:
                    self._offset = 0
                if self._offset == 0 and size > 1_200_000:
                    self._offset = size - 1_200_000
                handle.seek(self._offset)
                lines = handle.readlines()
                self._offset = handle.tell()
        except OSError as exc:
            self._logger.exception("Failed to read console log")
            self._emit_status(f"Помилка читання логу: {exc}")
            return

        if lines:
            self.raw_lines_parsed.emit(lines)

        reports, replies, vip_chats = parse_lines(lines)

        if reports:
            self.reports_parsed.emit(reports)
        if replies:
            self.replies_parsed.emit(replies)
        if vip_chats:
            self.vip_messages_parsed.emit(vip_chats, self._did_initial_poll)

        self._did_initial_poll = True
        self._emit_status(f"Лог підключено: {self._path}")

    def _emit_status(self, text: str) -> None:
        if text == self._last_status:
            return
        self._last_status = text
        self.status_changed.emit(text)
