from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ReplyMessage:
    timestamp: datetime
    kind: str
    admin_role: str
    admin_name: str
    admin_id: str
    player_name: str
    player_id: str
    text: str
    command: str = ""


@dataclass(slots=True)
class Report:
    timestamp: datetime
    player_name: str
    player_id: str
    text: str
    unanswered: bool
    handled_by_me: bool = False
    handled_by_other: bool = False
    answered_by_me: bool = False
    answered_by_other: bool = False
    cleared: bool = False
    last_reply_text: str = ""
    last_reply_admin_name: str = ""
    last_action_summary: str = ""
    last_action_at: datetime | None = None
    source_count: int = 1
    linked_replies: list[ReplyMessage] = field(default_factory=list)


@dataclass(slots=True)
class VipChatMessage:
    timestamp: datetime
    player_name: str
    player_id: str
    text: str


@dataclass(slots=True)
class VipAdAlert:
    timestamp: datetime
    player_name: str
    player_id: str
    text: str
    matched_keywords: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class BindConfig:
    name: str
    hotkey: str
    text: str
    category: str
    open_chat: bool = True


@dataclass(slots=True)
class AppSettings:
    admin_nickname: str = ""
    game_path: str = r"C:\Program Files (x86)\UKRAINEGTA\game\bin\gta_sa.exe"
    console_log_path: str = r"C:\Program Files (x86)\UKRAINEGTA\game\mta\logs\console.log"
    open_chat_before_insert: bool = True
    overlays_enabled: bool = True
    theme_mode: str = "dark"
    vip_ad_helper_signature: str = "Р.Скоропадський"
    vip_ad_punish_mode: str = "admin"
    hotkey_other_reply: str = "F1"
    hotkey_last_report_pm: str = "F3"
    hotkey_last_reply_id: str = "F4"
    reply_binds: list[BindConfig] = field(default_factory=list)
    command_binds: list[BindConfig] = field(default_factory=list)
