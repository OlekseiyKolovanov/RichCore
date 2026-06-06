from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import ReplyMessage, Report


@dataclass(slots=True)
class ReportRow:
    key: str
    report: Report


class ReportStore:
    _MERGE_WINDOW_SECONDS = 15.0

    def __init__(self) -> None:
        self._rows: list[ReportRow] = []
        self._reply_index: dict[str, list[ReplyMessage]] = {}
        self._dismissed_signatures: set[str] = set()
        self._report_occurrence_by_signature: dict[str, int] = {}
        self.last_answered_by_me_player_id: str = ""
        self.last_answered_by_me_text: str = ""

    @property
    def rows(self) -> list[ReportRow]:
        return self._rows

    def clear_all(self) -> None:
        for row in self._rows:
            self._dismissed_signatures.add(row.key)
        self._rows = []

    def add_reports(self, reports: list[Report]) -> None:
        for report in reports:
            if self._merge_report(report):
                continue

            # Keep every report as an individual row, even if content and player repeat.
            signature = self._report_signature(report)
            occurrence = self._report_occurrence_by_signature.get(signature, 0) + 1
            self._report_occurrence_by_signature[signature] = occurrence
            key = signature if occurrence == 1 else f"{signature}|#{occurrence}"

            if key in self._dismissed_signatures:
                continue

            self._rows.append(ReportRow(key=key, report=report))
        self._sort_rows()

    def add_replies(self, replies: list[ReplyMessage], admin_nickname: str) -> list[tuple[Report, ReplyMessage]]:
        linked_replies: list[tuple[Report, ReplyMessage]] = []
        for reply in replies:
            self._reply_index.setdefault(reply.player_id, []).append(reply)
            target_report = self._latest_report_by_player(reply.player_id)
            if target_report is None:
                continue

            target_report.last_action_at = reply.timestamp
            is_my_reply = self._is_my_reply(reply, admin_nickname)
            if reply.kind == "pm":
                reply_signature = (
                    reply.timestamp,
                    reply.admin_id,
                    self._normalize_text(reply.text),
                )
                known_reply_signatures = {
                    (item.timestamp, item.admin_id, self._normalize_text(item.text))
                    for item in target_report.linked_replies
                }
                if reply_signature not in known_reply_signatures:
                    target_report.linked_replies.append(reply)
                target_report.last_reply_text = reply.text
                target_report.last_reply_admin_name = reply.admin_name
                target_report.last_action_summary = f"PM: {reply.text}"
                target_report.unanswered = False
                if is_my_reply:
                    target_report.handled_by_me = True
                    target_report.answered_by_me = True
                    self.last_answered_by_me_player_id = reply.player_id
                    self.last_answered_by_me_text = reply.text
                else:
                    target_report.handled_by_other = True
                    target_report.answered_by_other = True
                linked_replies.append((target_report, reply))
            else:
                target_report.last_action_summary = f"\u0422\u0435\u043b\u0435\u043f\u043e\u0440\u0442\u0430\u0446\u0456\u044f /{reply.command}"
                if is_my_reply:
                    target_report.handled_by_me = True
                else:
                    target_report.handled_by_other = True
        self._sort_rows()
        return linked_replies

    def mark_answered_by_me(self, player_id: str, text: str) -> None:
        report = self._latest_report_by_player(player_id)
        if report is None:
            return
        self.mark_report_answered_by_me(report, text)

    def mark_report_answered_by_me(self, report: Report, text: str) -> None:
        report.handled_by_me = True
        report.answered_by_me = True
        report.unanswered = False
        report.last_reply_text = text
        report.last_reply_admin_name = "\u042f"
        report.last_action_summary = f"PM: {text}"
        report.last_action_at = datetime.now()
        self.last_answered_by_me_player_id = report.player_id
        self.last_answered_by_me_text = text
        self._sort_rows()

    def latest_report(self) -> Report | None:
        if not self._rows:
            return None
        for row in self._rows:
            if not self._report_is_finished(row.report):
                return row.report
        return self._rows[0].report

    def latest_received_report(self) -> Report | None:
        if not self._rows:
            return None
        return max((row.report for row in self._rows), key=lambda report: report.timestamp)

    def latest_report_by_player(self, player_id: str) -> Report | None:
        return self._latest_report_by_player(player_id)

    def latest_other_reply_for_player(self, player_id: str, admin_nickname: str) -> ReplyMessage | None:
        replies = self._reply_index.get(player_id, [])
        for reply in reversed(replies):
            if reply.kind == "pm" and not self._is_my_reply(reply, admin_nickname):
                return reply
        return None

    def latest_other_reply_for_report(self, report: Report, admin_nickname: str) -> ReplyMessage | None:
        for reply in reversed(report.linked_replies):
            if reply.kind == "pm" and not self._is_my_reply(reply, admin_nickname):
                return reply
        return self.latest_other_reply_for_player(report.player_id, admin_nickname)

    def dismiss_report(self, report: Report) -> None:
        for index, row in enumerate(self._rows):
            if row.report is report:
                self._dismissed_signatures.add(row.key)
                self._rows.pop(index)
                return

    def dismissed_signatures(self) -> set[str]:
        return set(self._dismissed_signatures)

    def set_dismissed_signatures(self, signatures: set[str]) -> None:
        self._dismissed_signatures = set(signatures)
        self._rows = [row for row in self._rows if row.key not in self._dismissed_signatures]

    def _latest_report_by_player(self, player_id: str) -> Report | None:
        for row in self._rows:
            if row.report.player_id == player_id and not self._report_is_finished(row.report):
                return row.report
        for row in self._rows:
            if row.report.player_id == player_id:
                return row.report
        return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.casefold().split())

    def _merge_report(self, incoming: Report) -> bool:
        candidate = self._merge_candidate(incoming)
        if candidate is None:
            return False

        current = candidate.report
        current.unanswered = current.unanswered or incoming.unanswered
        current.source_count += max(incoming.source_count, 1)
        if not current.player_name and incoming.player_name:
            current.player_name = incoming.player_name
        if not current.text and incoming.text:
            current.text = incoming.text
        if incoming.timestamp > current.timestamp and current.last_action_at is None:
            current.timestamp = incoming.timestamp
        return True

    def _merge_candidate(self, incoming: Report) -> ReportRow | None:
        normalized_text = self._normalize_text(incoming.text)
        best_row: ReportRow | None = None
        best_delta: float | None = None
        for row in self._rows:
            report = row.report
            if report.player_id != incoming.player_id:
                continue
            if self._normalize_text(report.text) != normalized_text:
                continue
            delta = abs((incoming.timestamp - report.timestamp).total_seconds())
            if delta > self._MERGE_WINDOW_SECONDS:
                continue
            if best_delta is None or delta < best_delta:
                best_row = row
                best_delta = delta
        return best_row

    def _sort_rows(self) -> None:
        self._rows.sort(
            key=lambda row: (
                1 if self._report_is_finished(row.report) else 0,
                -(
                    (row.report.last_action_at if self._report_is_finished(row.report) else row.report.timestamp)
                    or row.report.timestamp
                ).timestamp(),
            ),
        )

    @staticmethod
    def _report_signature(report: Report) -> str:
        timestamp = report.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        normalized_name = ReportStore._normalize_text(report.player_name)
        normalized_text = ReportStore._normalize_text(report.text)
        unanswered_flag = "1" if report.unanswered else "0"
        return f"{timestamp}|{report.player_id}|{normalized_name}|{normalized_text}|{unanswered_flag}"

    @staticmethod
    def _report_is_finished(report: Report) -> bool:
        return report.answered_by_me or report.answered_by_other

    @staticmethod
    def _is_my_reply(reply: ReplyMessage, admin_nickname: str) -> bool:
        return bool(admin_nickname.strip()) and reply.admin_name.casefold() == admin_nickname.strip().casefold()
