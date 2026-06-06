from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from .models import ReplyMessage, Report, VipChatMessage


TIMESTAMP_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] \[Output\] :\s*(?P<body>.*)$")
REPORT_RE = re.compile(
    r"^(?P<flag>\[БЕЗ ВІДПОВІДІ\])?\s*Репорт від гравця (?P<name>.+?)\[(?P<id>\d+)\]: (?P<text>.+)$"
)
PM_RE = re.compile(
    r"^\[PM\] \[(?P<role>[^\]]+)\] (?P<admin_name>.+?)\[(?P<admin_id>\d+)\]\s*->\s*(?P<player_name>.+?)\[(?P<player_id>\d+)\]: (?P<text>.+)$"
)
TELEPORT_RE = re.compile(
    r"^\[A\]\s+(?P<admin_name>.+?)\s+\[(?P<admin_id>\d+)\]\s*->\s*/(?P<command>pwarp|sp)\s+(?P<player_name>.+?)\s+\[(?P<player_id>\d+)\]\s*$",
    re.IGNORECASE,
)
VIP_CHAT_RE = re.compile(
    r"^\[VIP\]\s+(?P<name>.+?)\[(?P<id>\d+)\]: (?P<text>.+)$"
)


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def parse_line(line: str) -> tuple[Report | ReplyMessage | VipChatMessage | None, str | None]:
    matched = TIMESTAMP_RE.match(line.strip())
    if not matched:
        return None, None
    timestamp = parse_timestamp(matched.group("ts"))
    body = matched.group("body")

    report_match = REPORT_RE.match(body)
    if report_match:
        return (
            Report(
                timestamp=timestamp,
                player_name=report_match.group("name").strip(),
                player_id=report_match.group("id"),
                text=report_match.group("text").strip(),
                unanswered=bool(report_match.group("flag")),
            ),
            "report",
        )

    pm_match = PM_RE.match(body)
    if pm_match:
        return (
            ReplyMessage(
                timestamp=timestamp,
                kind="pm",
                admin_role=pm_match.group("role").strip(),
                admin_name=pm_match.group("admin_name").strip(),
                admin_id=pm_match.group("admin_id"),
                player_name=pm_match.group("player_name").strip(),
                player_id=pm_match.group("player_id"),
                text=pm_match.group("text").strip(),
            ),
            "reply",
        )

    teleport_match = TELEPORT_RE.match(body)
    if teleport_match:
        command = teleport_match.group("command").strip().lower()
        return (
            ReplyMessage(
                timestamp=timestamp,
                kind="teleport",
                admin_role="A",
                admin_name=teleport_match.group("admin_name").strip(),
                admin_id=teleport_match.group("admin_id"),
                player_name=teleport_match.group("player_name").strip(),
                player_id=teleport_match.group("player_id"),
                text=f"/{command}",
                command=command,
            ),
            "reply",
        )

    vip_chat_match = VIP_CHAT_RE.match(body)
    if vip_chat_match:
        return (
            VipChatMessage(
                timestamp=timestamp,
                player_name=vip_chat_match.group("name").strip(),
                player_id=vip_chat_match.group("id"),
                text=vip_chat_match.group("text").strip(),
            ),
            "vip_chat",
        )

    return None, None


def parse_lines(lines: Iterable[str]) -> tuple[list[Report], list[ReplyMessage], list[VipChatMessage]]:
    reports: list[Report] = []
    replies: list[ReplyMessage] = []
    vip_chats: list[VipChatMessage] = []
    for line in lines:
        parsed, kind = parse_line(line)
        if parsed is None:
            continue
        if kind == "report":
            reports.append(parsed)
        elif kind == "reply":
            replies.append(parsed)
        elif kind == "vip_chat":
            vip_chats.append(parsed)
    return reports, replies, vip_chats
