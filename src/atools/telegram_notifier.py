from __future__ import annotations

import html
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from urllib import error, request

from .models import Report, VipAdAlert, VipChatMessage


BOT_TOKEN = "8748252432:AAF5Oqy2PuNnbwGPVc6jy8EHYY2PliyhIHI"
GROUP_ID = -1003786764608
REPORT_THRESHOLD = 5
REPORT_THRESHOLD_THREAD_ID = 3
VIP_FALSE_POSITIVE_THREAD_ID = 7
VIP_PUNISHMENT_THREAD_ID = 26
VIP_CLEAN_THREAD_ID = 28


@dataclass(slots=True, frozen=True)
class _OutboundMessage:
    thread_id: int
    text: str


class TelegramForumNotifier:
    def __init__(
        self,
        bot_token: str = BOT_TOKEN,
        group_id: int = GROUP_ID,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._bot_token = bot_token.strip()
        self._group_id = int(group_id)
        self._enabled = bool(self._bot_token) and bool(self._group_id)
        self._queue: queue.Queue[_OutboundMessage | None] = queue.Queue()
        self._worker = threading.Thread(
            target=self._run,
            name="telegram-forum-notifier",
            daemon=True,
        )
        if self._enabled:
            self._worker.start()

    def send_html(self, thread_id: int, text: str) -> None:
        if not self._enabled:
            return
        self._queue.put(_OutboundMessage(thread_id=thread_id, text=text))

    def close(self, timeout: float = 2.5) -> None:
        if not self._enabled or not self._worker.is_alive():
            return
        self._queue.put(None)
        self._worker.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                self._send_with_retry(item)
            except Exception:
                self._logger.exception("Telegram notification worker failed")
            finally:
                self._queue.task_done()

    def _send_with_retry(self, item: _OutboundMessage) -> None:
        last_error: Exception | None = None
        for delay in (0.0, 1.5, 4.0):
            if delay:
                time.sleep(delay)
            try:
                self._send(item)
                return
            except (OSError, RuntimeError, ValueError, error.URLError) as exc:
                last_error = exc

        if last_error is not None:
            self._logger.error(
                "Telegram notification was not delivered to thread %s: %s",
                item.thread_id,
                last_error,
            )

    def _send(self, item: _OutboundMessage) -> None:
        payload = {
            "chat_id": self._group_id,
            "message_thread_id": item.thread_id,
            "text": item.text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        data = json.dumps(payload).encode("utf-8")
        api_url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        api_request = request.Request(
            api_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with request.urlopen(api_request, timeout=8) as response:
            raw_body = response.read().decode("utf-8", errors="replace")

        response_payload = json.loads(raw_body)
        if not response_payload.get("ok"):
            raise RuntimeError(response_payload.get("description", "Unknown Telegram API error"))


def format_report_threshold_message(open_count: int, reports: Sequence[Report]) -> str:
    lines = [
        "<b>RichCore | 5+ незакритих репортів</b>",
        "",
        f"<b>Відкрито зараз:</b> <code>{open_count}</code>",
        f"<b>Час:</b> <code>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</code>",
    ]

    preview_lines = []
    for report in list(reports)[:5]:
        preview_lines.append(
            f"• <b>{_escape(report.player_name)}</b> "
            f"<code>[{_escape(report.player_id)}]</code> - {_escape(_truncate(report.text, 110))}"
        )

    if preview_lines:
        lines.extend(["", "<b>Останні незакриті:</b>", *preview_lines])

    return "\n".join(lines)


def format_vip_false_positive_message(alert: VipAdAlert) -> str:
    ai_reason = ", ".join(alert.matched_keywords) if alert.matched_keywords else "не вказано"
    lines = [
        "<b>RichCore | Відхилене спрацювання AD VIP</b>",
        "",
        f"<b>Гравець:</b> <b>{_escape(alert.player_name)}</b> <code>[{_escape(alert.player_id)}]</code>",
        f"<b>Час:</b> <code>{alert.timestamp.strftime('%d.%m.%Y %H:%M:%S')}</code>",
        f"<b>Причина AI:</b> {_escape(ai_reason)}",
        "",
        f"<b>Текст спрацювання:</b>\n{_escape(_truncate(alert.text, 900))}",
    ]
    return "\n".join(lines)


def format_vip_punishment_message(alert: VipAdAlert, command: str) -> str:
    ai_reason = ", ".join(alert.matched_keywords) if alert.matched_keywords else "не вказано"
    lines = [
        "<b>RichCore | Видано покарання за рекламу у VIP</b>",
        "",
        f"<b>Гравець:</b> <b>{_escape(alert.player_name)}</b> <code>[{_escape(alert.player_id)}]</code>",
        f"<b>Час спрацювання:</b> <code>{alert.timestamp.strftime('%d.%m.%Y %H:%M:%S')}</code>",
        f"<b>Причина AI:</b> {_escape(ai_reason)}",
        "",
        f"<b>Повідомлення:</b>\n{_escape(_truncate(alert.text, 900))}",
        "",
        f"<b>Команда:</b> <code>{_escape(command)}</code>",
    ]
    return "\n".join(lines)


def format_vip_clean_message(message: VipChatMessage) -> str:
    lines = [
        "<b>RichCore | Чисте повідомлення у VIP</b>",
        "",
        f"<b>Гравець:</b> <b>{_escape(message.player_name)}</b> <code>[{_escape(message.player_id)}]</code>",
        f"<b>Час:</b> <code>{message.timestamp.strftime('%d.%m.%Y %H:%M:%S')}</code>",
        "",
        f"<b>Текст:</b>\n{_escape(_truncate(message.text, 900))}",
    ]
    return "\n".join(lines)


def _truncate(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _escape(value: str) -> str:
    return html.escape(value, quote=False)
