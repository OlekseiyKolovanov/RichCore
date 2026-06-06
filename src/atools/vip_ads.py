from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime, time as clock_time

from PySide6.QtCore import QObject, Signal

from .ai_responder import SharedAIService
from .models import VipAdAlert, VipChatMessage
from .vip_triggers import find_offensive_triggers


_VIP_START_TIME = clock_time(11, 0)
_VIP_END_TIME = clock_time(21, 0)


class VipAdDetector(QObject):
    alerts_ready = Signal(list)
    clean_ready = Signal(list)

    def __init__(self, ai_service: SharedAIService | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._logger = logging.getLogger(__name__)
        self._ai_service = ai_service or SharedAIService()
        self._ai_service.prepare_async()
        self._queue: queue.Queue[tuple[list[VipChatMessage], bool] | None] = queue.Queue()
        self._worker = threading.Thread(
            target=self._run,
            name="vip-ai-detector",
            daemon=True,
        )
        self._worker.start()

    def submit_messages(self, messages: list[VipChatMessage], emit_clean: bool = False) -> None:
        if messages:
            self._queue.put((list(messages), bool(emit_clean)))

    def match_messages(self, messages: list[VipChatMessage]) -> list[VipAdAlert]:
        alerts, _clean = self.classify_messages(messages)
        return alerts

    def classify_messages(self, messages: list[VipChatMessage]) -> tuple[list[VipAdAlert], list[VipChatMessage]]:
        return self._classify_batch(messages)

    def close(self, timeout: float = 2.5) -> None:
        if not self._worker.is_alive():
            return
        self._queue.put(None)
        self._worker.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return

                messages, emit_clean = item
                try:
                    alerts, clean_messages = self._classify_batch(messages)
                except Exception:
                    self._logger.exception("VIP AI detector failed")
                    alerts, clean_messages = [], list(messages)

                if alerts:
                    self.alerts_ready.emit(alerts)
                if emit_clean and clean_messages:
                    self.clean_ready.emit(clean_messages)
            finally:
                self._queue.task_done()

    def _classify_batch(self, messages: list[VipChatMessage]) -> tuple[list[VipAdAlert], list[VipChatMessage]]:
        candidates: list[VipChatMessage] = []
        clean_messages: list[VipChatMessage] = []
        alerts: list[VipAdAlert] = []

        for message in messages:
            offensive_triggers = find_offensive_triggers(message.text)
            if offensive_triggers:
                alerts.append(
                    VipAdAlert(
                        timestamp=message.timestamp,
                        player_name=message.player_name,
                        player_id=message.player_id,
                        text=message.text,
                        matched_keywords=("образлива лексика", *offensive_triggers),
                    )
                )
            elif self._is_allowed_timestamp(message.timestamp):
                candidates.append(message)
            else:
                clean_messages.append(message)

        if not candidates:
            return alerts, clean_messages

        decisions = self._ai_service.classify_vip_messages(candidates)

        for message, decision in zip(candidates, decisions):
            if decision.is_ad:
                tags = decision.tags[:3] if decision.tags else ()
                matched = tags or (decision.reason,)
                alerts.append(
                    VipAdAlert(
                        timestamp=message.timestamp,
                        player_name=message.player_name,
                        player_id=message.player_id,
                        text=message.text,
                        matched_keywords=tuple(matched),
                    )
                )
                continue

            clean_messages.append(message)

        return alerts, clean_messages

    @staticmethod
    def _is_allowed_timestamp(timestamp: datetime) -> bool:
        current_time = timestamp.time()
        return _VIP_START_TIME <= current_time <= _VIP_END_TIME
