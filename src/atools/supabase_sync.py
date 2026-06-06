from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from urllib import error, parse, request

from .models import ReplyMessage, Report


DEFAULT_SUPABASE_URL = "https://krehodldvzbscnfabecb.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtyZWhvZGxkdnpic2NuZmFiZWNiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM3MjY4MjUsImV4cCI6MjA4OTMwMjgyNX0."
    "vqC18em1suwGVipJa0fPsKSOK0LMSDayP-QAIaPG21I"
)


@dataclass(slots=True, frozen=True)
class _OutboundPayload:
    report_row: dict[str, object]
    reply_row: dict[str, object] | None = None


class SupabaseSync:
    def __init__(
        self,
        project_url: str = DEFAULT_SUPABASE_URL,
        anon_key: str = DEFAULT_SUPABASE_ANON_KEY,
        enabled: bool = True,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._project_url = project_url.rstrip("/")
        self._anon_key = anon_key.strip()
        self._enabled = bool(enabled) and bool(self._project_url) and bool(self._anon_key)
        self._queue: queue.Queue[_OutboundPayload | None] = queue.Queue()
        self._worker = threading.Thread(
            target=self._run,
            name="supabase-sync",
            daemon=True,
        )
        self._worker.start()

    def configure(self, enabled: bool) -> None:
        self._enabled = bool(enabled) and bool(self._project_url) and bool(self._anon_key)

    def send_report(self, report: Report) -> None:
        if not self._enabled:
            return
        self._queue.put(_OutboundPayload(report_row=_report_record(report)))

    def send_reply(self, report: Report, reply: ReplyMessage) -> None:
        if not self._enabled:
            return
        self._queue.put(
            _OutboundPayload(
                report_row=_report_record(report),
                reply_row=_reply_record(report, reply),
            )
        )

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
                self._send_with_retry(item)
            except Exception:
                self._logger.exception("Supabase sync worker failed")
            finally:
                self._queue.task_done()

    def _send_with_retry(self, item: _OutboundPayload) -> None:
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
            self._logger.error("Supabase event was not delivered: %s", last_error)

    def _send(self, item: _OutboundPayload) -> None:
        self._upsert("reports", "report_uid", [item.report_row])
        if item.reply_row is not None:
            self._upsert("report_replies", "reply_uid", [item.reply_row])

    def _upsert(self, table_name: str, conflict_column: str, rows: list[dict[str, object]]) -> None:
        query = parse.urlencode({"on_conflict": conflict_column})
        payload = json.dumps(rows, ensure_ascii=False).encode("utf-8")
        api_request = request.Request(
            f"{self._project_url}/rest/v1/{table_name}?{query}",
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "apikey": self._anon_key,
                "Authorization": f"Bearer {self._anon_key}",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        try:
            with request.urlopen(api_request, timeout=8) as response:
                response.read()
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").strip()
            if body:
                raise RuntimeError(f"Supabase {table_name} request failed [{exc.code}]: {body}") from exc
            raise RuntimeError(f"Supabase {table_name} request failed [{exc.code}]") from exc


def _report_record(report: Report) -> dict[str, object]:
    return {
        "report_uid": _report_uid(report),
        "report_created_at": _format_timestamp(report.timestamp),
        "player_id": report.player_id,
        "player_name": report.player_name,
        "report_text": report.text,
        "unanswered": report.unanswered,
    }


def _reply_record(report: Report, reply: ReplyMessage) -> dict[str, object]:
    return {
        "reply_uid": _reply_uid(report, reply),
        "report_uid": _report_uid(report),
        "report_created_at": _format_timestamp(report.timestamp),
        "report_text": report.text,
        "player_id": report.player_id,
        "player_name": report.player_name,
        "reply_created_at": _format_timestamp(reply.timestamp),
        "reply_kind": reply.kind,
        "reply_text": reply.text,
        "reply_admin_role": reply.admin_role,
        "reply_admin_id": reply.admin_id,
        "reply_admin_name": reply.admin_name,
        "command": reply.command,
    }


def _format_timestamp(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _report_uid(report: Report) -> str:
    normalized_name = " ".join(report.player_name.casefold().split())
    normalized_text = " ".join(report.text.casefold().split())
    return "|".join(
        [
            _format_timestamp(report.timestamp),
            report.player_id,
            normalized_name,
            normalized_text,
        ]
    )


def _reply_uid(report: Report, reply: ReplyMessage) -> str:
    normalized_text = " ".join(reply.text.casefold().split())
    return "|".join(
        [
            _report_uid(report),
            _format_timestamp(reply.timestamp),
            reply.admin_id,
            normalized_text,
        ]
    )
