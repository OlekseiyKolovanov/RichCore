from __future__ import annotations

from dataclasses import dataclass

from .models import VipAdAlert


@dataclass(slots=True)
class VipAdRow:
    key: str
    alert: VipAdAlert


class VipAdStore:
    def __init__(self) -> None:
        self._rows: list[VipAdRow] = []
        self._dismissed_signatures: set[str] = set()
        self._known_keys: set[str] = set()
        self._occurrence_by_signature: dict[str, int] = {}

    @property
    def rows(self) -> list[VipAdRow]:
        return self._rows

    def add_alerts(self, alerts: list[VipAdAlert]) -> list[VipAdAlert]:
        added: list[VipAdAlert] = []
        for alert in alerts:
            signature = self._alert_signature(alert)
            occurrence = self._occurrence_by_signature.get(signature, 0) + 1
            self._occurrence_by_signature[signature] = occurrence
            key = signature if occurrence == 1 else f"{signature}|#{occurrence}"
            if key in self._dismissed_signatures or key in self._known_keys:
                continue

            self._rows.append(VipAdRow(key=key, alert=alert))
            self._known_keys.add(key)
            added.append(alert)

        self._sort_rows()
        return added

    def latest_alert(self) -> VipAdAlert | None:
        return self._rows[0].alert if self._rows else None

    def dismiss_alert(self, alert: VipAdAlert) -> None:
        for index, row in enumerate(self._rows):
            if row.alert is alert:
                self._dismissed_signatures.add(row.key)
                self._rows.pop(index)
                return

    def clear_all(self) -> None:
        for row in self._rows:
            self._dismissed_signatures.add(row.key)
        self._rows = []

    def dismissed_signatures(self) -> set[str]:
        return set(self._dismissed_signatures)

    def set_dismissed_signatures(self, signatures: set[str]) -> None:
        self._dismissed_signatures = set(signatures)
        self._rows = [row for row in self._rows if row.key not in self._dismissed_signatures]
        self._known_keys = {row.key for row in self._rows}

    def _sort_rows(self) -> None:
        self._rows.sort(key=lambda row: row.alert.timestamp, reverse=True)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.casefold().split())

    @staticmethod
    def _alert_signature(alert: VipAdAlert) -> str:
        timestamp = alert.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        normalized_name = VipAdStore._normalize_text(alert.player_name)
        normalized_text = VipAdStore._normalize_text(alert.text)
        normalized_keywords = ",".join(VipAdStore._normalize_text(item) for item in alert.matched_keywords)
        return f"{timestamp}|{alert.player_id}|{normalized_name}|{normalized_text}|{normalized_keywords}"
